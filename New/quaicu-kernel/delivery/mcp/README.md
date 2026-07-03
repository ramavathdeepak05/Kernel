# QUAICU MCP governance (D2-1)

Govern an AI agent's **MCP tool calls** with the kernel: every call is mapped to a governed action
(policy → HITL → K·02 seal). Fail-closed — a denied or unapproved call **never runs the tool**.

Install: `pip install .[mcp]`

## Outcomes (all sealed)
| Policy decision | Result to the agent |
|---|---|
| **allow** | the tool runs; its result is returned |
| **deny** | `isError` result — the tool is **blocked** |
| **require_approval** | `isError` result carrying the approval **handle** — the action is durably PENDING; a human approves via `/v1/approvals` (or the email/Teams link), then the agent retries (idempotent) |
| infra/tool failure | `isError` (fail-closed HALT) |

## Writing policies for MCP tools

Each tool call is a governed action of type **`mcp.<tool_name>`** (e.g. `mcp.wire_transfer`), and the
tool's **arguments become the action payload** — so a CEL policy can condition on individual
arguments as `payload_<field>`:

```yaml
# governs a specific tool, conditioned on its argument:
- governs: "mcp.wire_transfer"
  condition: "payload_amount > 10000"     # the tool's `amount` argument
  decision: "require_approval"
  approvers: ["role:compliance"]
```

CEL variables available: `action_type`, `action_tenant`, `actor_id`, `actor_roles`, and
`payload_<field>` for each tool argument.

**Governing a group of tools with one policy.** `governs` matches an action type exactly (or `*`),
so to write a single policy for several tools, point them at a shared action type via the `policy`
knob (`register_tool(name, policy="mcp.tool")` / `default_policy="mcp.tool"` / `policy_for`), then
write one `governs: "mcp.tool"` policy. Without a knob value each tool defaults to its own
`mcp.<tool_name>` action type.

## Two ways to use it

### 1. Proxy an existing MCP server (drop-in — no client or tool code change)
Point your agent at `quaicu-kernel-mcp` instead of the real tool server; it mirrors the downstream's
tools and governs each call before forwarding.

```toml
# in your kernel config (KERNEL_CONFIG)
[mcp]
mode               = "proxy"
agent_id           = "agent:mcp"                 # sealed as the actor on every tool call
agent_roles        = ["agent"]
default_policy     = "mcp.tool"                  # the CEL policy that governs the calls
downstream_command = ["python", "-m", "my_tools_server"]
```
```bash
KERNEL_CONFIG=/etc/quaicu/kernel.gcp.toml quaicu-kernel-mcp
```

### 2. Govern your own tools (registered handlers)
```python
from delivery.sdk.kernel import Kernel
from core.types import Actor, ActorId
from delivery.mcp.server import GovernedMCPServer

kernel = Kernel.from_config("kernel.gcp.toml")
await kernel.startup()
agent = Actor(id=ActorId("agent:research"), tenant=kernel.tenant, roles=("agent",))

server = GovernedMCPServer(kernel, actor=agent, default_policy="mcp.tool")
server.register_tool(
    "wire_transfer",
    handler=lambda args: do_transfer(**args),
    policy="payments.transfer",              # e.g. a require_approval CEL policy
    description="Move funds between accounts",
    input_schema={"type": "object", "properties": {"amount": {"type": "number"}}},
)
await server.run_stdio()
```

### 3. Hosted, multi-tenant HTTP endpoint (no code shipped to the client)

Serve one **authenticated Streamable-HTTP** endpoint that governs every tenant's tool calls — the MCP
analogue of the BYO AI gateway. A tenant's agent connects to `https://…/mcp` with its **API key**;
the endpoint resolves the tenant + actor from the key, governs the call against *that tenant's*
policies, and seals it to *that tenant's* ledger. One deployment serves every tenant — onboarding is
just issuing an API key, no per-tenant process, and **no kernel source on the client** (unlike the
stdio modes above, which run the package locally).

```python
from delivery.mcp.server import GovernedMCPServer
from delivery.sdk.saas_app import build_saas_app

# Tools are registered in code (they can't come from TOML); identity is per-request, not bound here.
mcp = GovernedMCPServer(name="hosted")
mcp.register_tool("wire_transfer", handler=lambda a: do_transfer(**a), policy="payments.transfer")

app = build_saas_app(config, mcp_server=mcp)   # mounts the governed endpoint at /mcp
```

The client points any MCP Streamable-HTTP client at `…/mcp` with `Authorization: Bearer <qk_…>`.
Requests without a valid key get `401`; the transport is stateless + JSON-response (scales with
`--workers>1`, no sticky sessions). Per-request identity is read from the transport's request context
and verified (`delivery/mcp/auth.py`) — concurrent tenants never share identity (a tenant B key can
only ever seal to tenant B).

**Two hosted modes** (pass at most one to `create_app`/`build_saas_app`):

- **`mcp_server`** — operator-registered tools: the platform provides the tool handlers in code; the
  same catalogue is governed for every tenant.
- **`mcp_proxy`** — **BYO downstream** (the full AI-gateway parallel): each tenant registers *their
  own* downstream MCP server, and the endpoint mirrors + governs + forwards *their* tools.

```python
from delivery.mcp.proxy import GovernedMCPProxy
from delivery.sdk.saas_app import build_saas_app

app = build_saas_app(config, mcp_proxy=GovernedMCPProxy(default_policy="mcp.tool"))
```

**Turn it on (deployed SaaS plane).** No code needed — set the `[mcp]` section in the plane config
(`kernel.saas.toml`) and redeploy an image built with the `[mcp]` extra:

```toml
[mcp]
enabled        = true
default_policy = "mcp.tool"   # optional — govern all tools under one action type
```

`build_saas_app` reads this and mounts `/mcp` (BYO-downstream proxy). The production Dockerfile already
installs the `[mcp]` extra via `requirements-gcp.lock`. Then each tenant registers their downstream
(`PUT /v1/mcp/connection` / console → MCP gateway) and activates `mcp.<tool>` policies.

Each tenant registers their downstream once:

```
PUT /v1/mcp/connection    { "url": "https://tools.acme.io/mcp", "auth_value": "Bearer …" }
```

Then their agent connects to `…/mcp` with its QUAICU key; `tools/list` mirrors *their* downstream's
tools and every `tools/call` is governed by their policies, forwarded to their downstream on ALLOW,
and sealed to their ledger. The secret is stored encrypted (`AccountEngine.set_mcp_connection`) and
shown back only masked; a tenant with no downstream configured gets a clear fail-closed error. The
downstream can be **Streamable HTTP** or **SSE** (`transport` on the connection), configurable via
`PUT /v1/mcp/connection` or the console **MCP gateway** page.

**Connection reuse.** `HttpDownstream` (`delivery/mcp/downstream.py`) opens a fresh mcp *session* per
call — MCP sessions are stateful and their anyio streams are task-bound, so they can't be safely
pooled in a stateless multi-worker server. The underlying **HTTP connection is** pooled: a single
shared `httpx.AsyncClient` per worker (passed via the mcp client's `httpx_client_factory`) keeps
TCP/TLS warm across calls; it's closed on app shutdown.

## Reusable core
`delivery/mcp/governance.py::govern_tool_call(kernel, *, actor, tool_name, arguments, policy, execute)`
is a thin wrapper over `kernel.wrap(...)` (the same governed lifecycle the SDK decorators use). It has
no `mcp` dependency, so it's reusable and unit-testable — the server/proxy import `mcp` lazily.

The hosted endpoint (`delivery/mcp/http.py`) binds a per-request `session_resolver` onto the
`GovernedMCPServer` (via `bind_session_resolver`) that authenticates the transport's request and
yields the tenant's `(kernel, actor)`; `create_app(..., mcp_server=…)` mounts it and runs the MCP
session manager in the app lifespan.
