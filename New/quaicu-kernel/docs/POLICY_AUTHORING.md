# Writing QUAICU policies (CEL) — with the AI assistant

You don't hand-write policies blind, and QUAICU doesn't ship your business rules. It gives you a stable
schema to write against, an **AI assistant** to draft the CEL, and a safe lifecycle (backtest + shadow)
to get it right before it enforces. This is the firewall model: the vendor provides the engine + safe
rollout; you express the rules for your context.

## The CEL activation schema (what a policy can reference)

Every policy is a CEL **boolean expression** evaluated against this flat activation
(`core/policy/evaluator.py`). Use these exact names:

| Variable | Type | Example |
|---|---|---|
| `action_type` | string | `action_type == "loan.approve"` |
| `action_tenant` | string | `action_tenant == "acme"` |
| `actor_id` | string | `actor_id == "svc:batch"` |
| `actor_roles` | list&lt;string&gt; | `"role:analyst" in actor_roles` |
| `payload_<field>` | string/int/double/bool | `payload_amount > 1000000` |

Payload fields are **flattened and prefixed** (`payload.amount` → `payload_amount`). A policy pairs the
condition with a **decision**: `allow`, `deny`, or `require_approval`.

## The authoring workflow (observe → draft → backtest → activate)

1. **Observe.** Run the tier's `monitor` / `audit_only` profile — actions are governed-but-allowed and
   recorded, so you can see your real `action_type`s and payload fields (you don't guess the schema).
2. **Draft with the AI assistant** (below) or by hand.
3. **Register as DRAFT** → `POST /v1/policies`. **Submit** → DRAFT→REVIEW.
4. **Backtest** the draft against recorded history (the simulate → ImpactReport bridge): see what it
   *would* have allowed/denied before it enforces.
5. **Shadow** (optional): run non-enforcing and compare.
6. **Activate** → REVIEW→ACTIVATED (fail-closed; deny-overrides conflict resolution).

## The AI assistant — `POST /v1/policies/assist`

Describe a rule in plain English; get a candidate CEL policy that the kernel has **already compiled** to
guarantee it's valid (a non-compiling suggestion comes back `valid: false`, never a broken policy).

```bash
curl -X POST https://api.yourco.com/v1/policies/assist \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"description":"loan approvals over 1,000,000 need a human",
       "action_types":["loan.approve"], "payload_fields":["amount"]}'
```
```json
{
  "condition": "action_type == \"loan.approve\" && payload_amount > 1000000",
  "decision": "require_approval",
  "explanation": "High-value loan approvals are routed to human approval.",
  "valid": true,
  "warnings": []
}
```

It's **advisory**: review the suggestion, then run it through the lifecycle above. Passing the
`action_types` / `payload_fields` / `actor_roles` you saw while observing makes the drafts far better
(the model writes against your real names, and you get a warning if it references an unseen field).

### Enabling the assistant
It's a vendor-configured model (so it works even for free-tier tenants with no inference entitlement),
off until you add a `[policy_assistant]` section:

```toml
[policy_assistant]
adapter = "openai_compat"        # or "vertex_inference" — any InferencePort in the registry
model   = "gpt-4o-mini"
[policy_assistant.inference]
base_url = "https://api.openai.com/v1"
api_key  = "${OPENAI_API_KEY}"
```
For a **free / zero-cost** assistant, point `adapter = "openai_compat"` at a local **Ollama**
(`base_url = "http://localhost:11434/v1"`, `model = "llama3"`). Calls require the `policy:admin` scope
and count against the tenant's rate limit.
