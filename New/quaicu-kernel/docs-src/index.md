# QUAICU Governance Kernel

**AI governance kernel and policy packs for regulated enterprises.**

The QUAICU Governance Kernel is a standalone, fail-closed AI governance engine that makes every AI decision policy-compliant, auditable, and cryptographically provable before execution. Available as Python SDK, REST API, or Docker.

<div style="display:flex;gap:12px;margin:24px 0 32px;">
  <a href="/app/" class="md-button md-button--primary">Sign In →</a>
  <a href="/app/signup" class="md-button">Sign Up</a>
</div>

---

## Where to start

Choose the path that matches your role:

=== "I'm a builder / integrator"
    You want to embed governance into your application or ship it to a client.

    1. [Quickstart →](quickstart.md) — Docker running in 60 seconds
    2. [Python SDK End-to-End →](tutorials/python-sdk-end-to-end.md)
    3. [REST API Integration →](tutorials/rest-api-integration.md)
    4. [Write a Policy →](how-to/write-a-policy.md)

=== "I'm a CTO / technical evaluator"
    You want to understand the architecture before committing.

    1. [Architecture →](concepts/architecture.md) — Hexagonal design, 14 layers
    2. [Governance Lifecycle →](concepts/lifecycle.md) — PROPOSE → EVALUATE → GATE → EXECUTE → SEAL → EMIT
    3. [Security Model →](concepts/security.md) — Fail-closed invariants, tenant isolation
    4. [Deployment Tiers →](concepts/deployment-tiers.md) — Sovereign, Dedicated, SaaS

=== "I'm a compliance officer / auditor"
    You want to understand what the kernel proves and how to verify it.

    1. [Governance Layers →](concepts/governance-layers.md) — K·01–K·14 explained
    2. [Verify a Ledger Proof →](how-to/verify-ledger-proof.md) — Offline-verifiable RFC-6962 proofs
    3. [Policy Lifecycle →](reference/policy/lifecycle.md) — DRAFT → ACTIVATED → DEPRECATED
    4. [Security Model →](concepts/security.md) — Audit invariants

---

## Production status

!!! success "K·01–K·08 · Production-Ready"
    The core governance layers (Policy Engine, TrustLedger, HITL Gate, DPDP Consent, AI Gateway, Process Engine, Event Bus, Model Registry) are live in production at Woxsen University under the ALIS deployment.

!!! info "K·09–K·14 · Built and Green"
    The extended assurance layers (Fairness, Drift, Explainability, Incident/Rollback, Sandbox, Regulatory Mapping) are built and passing their test suites. First live deployment via design-partner pilot.

---

## Integration in three lines

=== "Python SDK"
    ```python
    from delivery.sdk import Kernel

    kernel = Kernel.from_config("kernel.toml")

    @kernel.governed(policy="credit.approve")
    async def approve_loan(loan_id: str, amount: float) -> dict:
        return {"status": "approved", "loan_id": loan_id, "amount": amount}
    ```

=== "REST API"
    ```bash
    curl -X POST https://your-kernel/v1/actions/propose \
      -H "X-API-Key: $QUAICU_KEY" \
      -d '{"action_type": "credit.approve", "payload": {"amount": 75000}}'
    ```

=== "Docker"
    ```bash
    cd delivery/docker
    docker compose up --build
    # Kernel running at http://localhost:7000
    # API docs at http://localhost:7000/docs
    ```

---

## Key guarantees

| Guarantee | What it means |
|-----------|---------------|
| **Fail-Closed** | Any error, timeout, or policy failure → DENY or HALT. No silent passthrough. |
| **No Bypass** | No code path executes a governed action without evaluation. |
| **Tenant Isolation** | Schema-per-tenant. Nothing crosses a tenant boundary. |
| **Ledger Immutability** | Sealed entries are append-only and cannot be modified. |
| **Offline-Verifiable** | A regulator verifies RFC-6962 proofs without trusting QUAICU. |

---

## Contact and licensing

The kernel is available standalone — license, embed, or deploy under your client's IT policy.

**NDA-first. Discussed under NDA.**  
[hello@quaicu.org](mailto:hello@quaicu.org) · [quaicu.org](https://quaicu.org) · [Talk to us about licensing](https://quaicu.org/contact.html)
