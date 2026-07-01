# QUAICU Governance Kernel

**A standalone, fail-closed, zero-trust governance kernel that makes every AI-driven action and model
inference policy-compliant, auditable, and cryptographically provable — *before* execution.**

Every governed action runs a strict, transaction-bound lifecycle —
**Propose → Evaluate → Gate → Execute → Seal → Emit** — and if *any* step fails, times out, or errors,
the action is **denied or halted**. The kernel never fails open. The result is a tamper-evident,
RFC 6962 Merkle-sealed receipt for every autonomous decision: *what* your AI did, *why*, *who approved
it*, and proof it wasn't altered after the fact.

> One core. Zero forks. Fails closed, always.

---

## What it is

A hexagonal (ports/adapters) Python kernel: the core governance logic in `core/` imports zero concrete
infrastructure; every external dependency sits behind a port with swappable adapters in `adapters/`.
Moving from a local container to managed cloud is a **config change, not a rewrite**.

It ships in two shapes:
- **Shared SaaS plane** — a multi-tenant service (`delivery/entrypoint_saas:app`) serving STARTER +
  BUSINESS tiers, routed per tenant. Self-serve signup mints a tenant + API key.
- **Dedicated single-tenant** — a license-gated single kernel (`delivery/entrypoint:app`) deployed in
  the customer's own cloud project (their KMS, their data).

### The 14 governance layers
K·01 Policy Engine (sandboxed CEL) · K·02 TrustLedger (RFC 6962 Merkle log) · K·03 HITL Gate ·
K·04 DPDP Consent · K·05 AI Gateway (PII masking, prompt logging, budgets) · K·06 Process Engine ·
K·07 Event Bus · K·08 Model Registry · K·09 Fairness · K·10 Drift · K·11 Explainability ·
K·12 Incident Engine · K·13 Sandbox (counterfactual replay) · K·14 Regulatory Mapping (signed evidence
packs). See `ARCHITECTURE.md` and `docs/` for the full spec.

---

## Install

```bash
# From source (the package root is this directory):
pip install .                      # runtime only
pip install ".[gcp]"               # + Cloud KMS signer / Vertex inference adapters
pip install ".[test,dev]"          # + test + lint/type tooling

# Or run the prebuilt container image (multi-stage, non-root, reproducible from the hash-pinned lock):
docker build -f delivery/docker/Dockerfile -t quaicu-kernel:local .
```

## Quickstart (SDK — govern existing code without changing its signature)

```python
from delivery.sdk.kernel import Kernel
from core.types import Actor, ActorId

kernel = Kernel.from_config("delivery/docker/kernel.dev.toml")

@kernel.guard(policy="credit.approve")
async def approve_credit_line(loan_id: str, amount: float) -> dict:
    return {"status": "approved", "loan_id": loan_id, "amount": amount}

async def handler(user_id: str):
    actor = Actor(id=ActorId(user_id), tenant=kernel.tenant, roles=("role:underwriter",))
    async with kernel.actor_context(actor):
        # Unchanged call-site; an unauthorized actor raises LifecycleDeniedError.
        return await approve_credit_line(loan_id="L-9821", amount=75000.0)
```

`@kernel.governed_tool(...)` governs agent tools (LangGraph/CrewAI/etc.) and returns the tool's own
result; `kernel.check(...)` returns a policy verdict without executing (pure PDP/monitor).

## How to deploy

The kernel is configured by a TOML adapter profile selected at boot (`KERNEL_CONFIG` /
`KERNEL_CONFIG_SAAS`). Ready-made profiles live in `delivery/docker/`:

| Profile | Use |
|---|---|
| `kernel.dev.toml` | local, in-memory, zero external deps |
| `kernel.shared.toml` + `kernel.saas.toml` | shared SaaS plane — one durable kernel (Postgres + Cloud KMS) serving STARTER + BUSINESS; tier = feature gate (ADR-0013) |
| `kernel.prod.toml` | durable single kernel (Postgres + OpenBao signer) — safe with `KERNEL_WORKERS > 1` |
| `kernel.gcp.toml` | GCP-native single kernel (Cloud SQL + Cloud KMS HSM + Vertex AI over PSC) |

Run migrations (`alembic -c adapters/storage/migrations/alembic.ini upgrade head`) before first boot
on any durable profile. Full guides:
- **Cloud Run:** `docs/operations/DEPLOY_CLOUD_RUN.md`
- **Terraform (SaaS + dedicated enterprise):** `deploy/terraform/gcp-saas/`, `deploy/terraform/gcp-enterprise/`
- **Deployment models + residency:** `docs/operations/DEPLOYMENT_MODELS.md`, `docs/operations/DATA_RESIDENCY.md`

---

## Security & licensing

- **Security posture + vulnerability disclosure:** [`SECURITY.md`](SECURITY.md)
  (report to `security@quaicu.org`). Supply-chain: blocking lint/test/pip-audit/Trivy gates, a
  CycloneDX SBOM per build, and cosign image signing — see `docs/operations/VULN_MANAGEMENT.md`.
- **License:** proprietary — see [`LICENSE`](LICENSE). Use requires an executed commercial/subscription
  agreement (STARTER / BUSINESS / ENTERPRISE tiers); absent one, source is viewable for evaluation only.

> QUAICU is a governance control plane, not a substitute for your own legal/regulatory compliance
> obligations.
