# Security Model

The QUAICU Kernel's security guarantees are testable, automated, and enforced at the code level, not documented aspirations.

---

## Invariants

| Invariant | What it means | How verified |
|-----------|---------------|--------------|
| **Fail-Closed** | Any failure → DENY or HALT. No silent passthrough. | Faults injected at every layer in CI |
| **No Bypass** | No code path executes a governed action without policy evaluation | Property-based tests prove no shortcut exists |
| **Determinism** | Same inputs → same policy decision every time | No wall-clock, no randomness in evaluation paths |
| **Total Conflict** | Policy evaluation always returns a decision, never "undefined" | Exhaustive conflict resolution tests |
| **Tenant Isolation** | Nothing crosses a tenant boundary at any layer | Adversarial cross-tenant tests at every layer |
| **Ledger Immutability** | A sealed entry is never modified | Append-only DB constraints + proof verification |
| **Idempotency** | Re-submitting an action never double-executes it | Replay tests with duplicate idempotency keys |
| **Replay Fidelity** | Any historical action is re-derivable from the ledger | Side-effect-freedom tests on replay paths |

---

## Tenant isolation

Schema-per-tenant is not a filter, it is structural separation:

- Each tenant gets its own PostgreSQL schema with entirely separate tables
- The TrustLedger always lives in the tenant's schema (never shared)
- Row-Level Security (RLS) is enabled as defence-in-depth even under schema isolation
- Per-tenant connection pools with `SET LOCAL app.current_tenant` on every transaction
- Adversarial cross-tenant attack scenarios are tested at every layer in CI

---

## API key security

API keys are stored as HMAC-SHA256 hashes with a `QUAICU_API_KEY_PEPPER` secret. The pepper is required in production, the kernel refuses to start without it.

The rate limiter keys on `verified_principal.tenant_id` for authenticated requests, and `client_ip` for unauthenticated requests. The `X-Tenant-Id` header is never trusted directly for rate limiting.

---

## Cryptographic signing

Every sealed action is signed by the deployment's HSM:

- **Sovereign tier:** OpenBao (Ed25519)
- **Dedicated / SaaS tier:** Cloud KMS (ECDSA P-256, FIPS 140-2 Level 3)

The signing key never leaves the HSM. The kernel holds only a reference (`key_path`), not the key material.

---

## Known open item

The rate limiter's unauthenticated IP fallback uses `request.client.host`. Behind a load balancer, this collapses to the proxy IP. A trusted forwarded-for handler at the ASGI edge is needed for production behind a load balancer. See `Kernel/CLAUDE.md` for the open thread. Authenticated traffic is unaffected.

---

## Responsible disclosure

Contact [hello@quaicu.org](mailto:hello@quaicu.org) for security disclosures. See `SECURITY.md` in the source repository for the full incident response process.
