# ADR-0010: Self-serve account provisioning + per-request API tier routing

- **Status:** Accepted
- **Date:** 2026-06-13
- **Decided by:** orchestrator
- **Affects:** `core/account/` (new), `core/errors.py`, `delivery/sdk/kernel.py` (per-request `tenant` on `resolve_actor`/`check`/`generate`), `delivery/api/app.py`, `delivery/api/deps.py` (new), `delivery/api/routes/{signup,admin}.py` (new), and all per-tenant routes (`actions`, `authorize`, `inference`, `ledger`, `dashboard`, `approvals`, `policies`)

## Context

ADR-0009 gave the kernel a tiering model (`EntitlementEngine`) and a `TieredKernelProvider`, but two
gaps remained before the shared SaaS plane can actually serve customers:

1. **No way to onboard a tenant.** A Starter customer is meant to be *self-serve*, yet there was no
   signup, no tenant creation, and no credential issuance — the kernel assumed an external IdP token
   already existed.
2. **The API was single-kernel.** `create_app(kernel)` bound one global `Kernel` to `app.state`, and
   routes derived the tenant from `kernel.tenant`. The shared plane needs the tenant to come from the
   *request* and select the tier kernel that serves it.

## Decision

- **`core/account/`** — `Account` (customer org, 1:1 with a tenant) and `ApiKey` (hashed; only a
  SHA-256 of the secret is stored). `AccountEngine.signup()` creates the account, mints a tenant id,
  **provisions a default STARTER plan** in the entitlement store, and issues one API key whose
  plaintext is returned exactly once. `verify_api_key()` is the fail-closed auth path for the kernel's
  own management surface (the self-serve alternative to bringing an external IdP token).
- **`delivery/api/deps.py`** — `get_kernel(request)` / `get_request_tenant(request)` resolve the
  serving kernel and tenant in **both** deployment shapes: single-kernel (`app.state.kernel`) and
  shared-plane (`app.state.provider`). In shared-plane mode the tenant is read from the JWT
  `tenant`/`tid` claim (or `X-Tenant-Id`) **without verifying the signature** — that only selects
  which kernel handles the request; the resolved kernel's IdentityPort still cryptographically
  verifies the token and enforces tenant isolation (F-07).
- **`create_app`** now takes exactly one of `kernel=` or `provider=`, plus optional control-plane
  singletons (`account_engine`, `entitlement_store`, `admin_token`). The legacy single-kernel call is
  unchanged, so every existing test and dedicated/Enterprise deployment keeps working.
- **Routes** — `POST /v1/signup` (the one intentionally unauthenticated write, for onboarding) and
  control-plane `/v1/admin/tenants*` (guarded by a deployment `admin_token`; fuller operator RBAC is
  WS-D). **All** per-tenant routes are migrated to `get_kernel`/`get_request_tenant`, and the SDK's
  `resolve_actor`/`check`/`generate` accept a per-request `tenant` (defaulting to the kernel's own),
  so a shared tier-kernel verifies identity and scopes data/isolation against the *request's* tenant
  rather than its fixed one. Tenant-isolation checks compare the path tenant to the request tenant.

New error types are added to the frozen `core/errors.py` under existing-style parents (ADR-0001
incremental-freeze): `AccountError` (+ `AccountExistsError`, `AccountNotFoundError`,
`ApiKeyInvalidError`).

## Consequences

- A customer can self-onboard to a Starter tenant with a working credential in one request.
- The API serves both the shared plane and dedicated deployments from one `create_app`; routes use one
  accessor, so the remaining routes (`authorize`, `inference`, `ledger`, `policies`, `dashboard`,
  `approvals`) can be migrated to `get_kernel`/`get_request_tenant` incrementally without app changes.
- Routing-by-unverified-claim is safe because selection ≠ authorization: the per-tenant kernel still
  verifies the token. Cross-tenant access cannot be gained by spoofing the routing claim.
- Forbidden: trusting the routing tenant as the authenticated identity; storing API-key plaintext;
  leaving `admin_token` unset and assuming the admin routes are closed by anything other than the
  built-in 503.

## Alternatives considered

- **Verify the JWT at the edge before routing.** Rejected for now — it would require the edge to hold
  every tenant's verification key/JWKS ahead of the per-tenant kernel that already does this; selection
  needs only the (untrusted) tenant claim, and authorization stays in the kernel.
- **A dedicated auth server issuing all tokens.** Deferred to WS-D (named IdP connectors + API-key
  rotation); signup + hashed API keys are the minimal self-serve credential for go-live.
