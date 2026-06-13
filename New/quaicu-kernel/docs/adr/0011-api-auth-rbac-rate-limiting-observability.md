# ADR-0011: API-key auth, RBAC scopes, per-tier rate limiting, request logging

- **Status:** Accepted
- **Date:** 2026-06-13
- **Decided by:** orchestrator
- **Affects:** `core/account/` (scopes, `AuthenticatedPrincipal`, `resolve_principal`), `core/entitlements/engine.py` (`rate_limit_for`), `delivery/api/auth.py` (new), `delivery/api/ratelimit.py` (new), `delivery/api/observability.py` (new), `delivery/api/app.py` (middleware wiring + `require_api_key`/`rate_limit` flags), and all per-tenant routes (scope guards)

## Context

ADR-0009/0010 made the kernel multi-tenant and tier-aware and gave it self-serve signup with hashed
API keys. But the shared SaaS plane still had an unguarded edge (WS-D):

1. **API keys were issued but never honored.** `AccountEngine.verify_api_key` existed; nothing on the
   request path called it. Management routes only required *a* bearer token (for the IdentityPort) —
   they never proved the caller owned the tenant they were addressing on the self-serve path.
2. **No authorization granularity.** A credential was all-or-nothing; there was no way to mint a
   read-only or CI-scoped key, and policy administration leaned solely on `policy_admin_roles` from an
   IdP token.
3. **Tier quotas weren't enforced.** `TIER_MATRIX.rate_limit_per_min` was declared but nothing read
   it, so a Starter tenant could issue unbounded traffic against the shared plane.
4. **No audit/correlation edge.** Requests had no correlation id and no structured access log — the
   substrate metering/billing (WS-C) and compliance need.

## Decision

- **RBAC scopes (`core/account/scopes.py`).** A scope is a stable `"resource:verb"` string
  (`actions:write`, `ledger:read`, `policy:admin`, …). `ApiKey` carries a `frozenset[str]` of scopes;
  `issue_api_key(tenant, scopes=…)` mints narrow keys (fail-closed: unknown scopes raise). The signup
  key gets `OWNER_SCOPES` (all) — it's the tenant's root credential. `AccountEngine.resolve_principal`
  returns an `AuthenticatedPrincipal(tenant_id, account_id, key_id, scopes)`; `verify_api_key` keeps
  its `Account` return for compatibility.
- **`ApiKeyAuthMiddleware` (opt-in via `create_app(require_api_key=True)`).** For protected `/v1/*`
  paths (everything except `/v1/signup` and the admin-token-guarded `/v1/admin/*`) it requires a valid
  `qk_` key, verifies it, asserts the key's tenant equals the request's **routing tenant**
  (`kernel.tenant` in single-kernel mode; the claim/header tenant in shared-plane mode), and stashes
  the principal on `request.state.principal`. Off by default, so IdP-token and single-kernel
  deployments — and the existing suite — are unchanged.
- **`enforce_scope(request, scope)`** is called inside each route after the existing bearer/identity
  checks. It is a **no-op when no principal is present** (auth disabled), and raises 403
  `INSUFFICIENT_SCOPE` otherwise. This keeps backward compatibility while making every protected route
  scope-aware: `actions:write/read`, `ledger:read`, `dashboard:read`, `approval:read/decide`,
  `inference:write`, `policy:admin`.
- **`RateLimitMiddleware`** enforces `EntitlementEngine.rate_limit_for(tenant)` (tier default honoring
  per-tenant `quota_overrides`) with a fixed 1-minute in-process window, returning **429** +
  `Retry-After` before routing. It **fails open**: no entitlement source, unresolved tenant,
  unprovisioned plan, or an unbounded (`-1`) tier → pass through. It is a quota control, not auth.
- **`RequestLoggingMiddleware`** (always on) assigns/propagates an `X-Request-ID` and emits one
  structured access-log record (method, path, status, duration, tenant, request id) per request.
- **Middleware order** (outer→inner): CORS → RequestLogging → RateLimit → ApiKeyAuth → reference PEP →
  routes. CORS preflight is answered first; everything is logged; quota is checked before auth.

## Consequences

- The shared plane has a real authn/authz edge: a key proves tenant ownership, scopes bound what it
  can do, and a Starter tenant can't exceed its tier's request rate.
- Narrow, least-privilege credentials are now possible (read-only dashboards, CI propose-only tokens).
- The access log + correlation id are the substrate WS-C billing/metering and compliance build on.
- Backward compatible: `require_api_key` defaults off; `enforce_scope` no-ops without a principal;
  rate limiting no-ops without an entitlement source. All prior API tests stay green.
- Forbidden: trusting the routing tenant as the *authenticated* identity (the key proves it, and the
  kernel's IdentityPort still verifies the governance actor); treating the rate limiter as an auth
  control; storing scopes a key shouldn't have (normalization is fail-closed).

## Alternatives considered

- **Per-route FastAPI `Depends` for scopes** instead of an in-handler `enforce_scope`. Rejected:
  routes already do manual bearer/tenant resolution; a uniform call beside that logic is clearer and
  keeps the no-op-when-disabled semantics trivial.
- **Distributed (Redis) rate-limit store now.** Deferred: the limit *lookup* (matrix-driven) is the
  contract; the in-process window is swappable behind the same middleware when horizontal scale needs
  a shared counter.
- **Mandatory API-key auth.** Rejected for this wave — dedicated/Enterprise and IdP-token deployments
  authenticate via the IdentityPort; forcing keys would break them. Auth is opt-in per deployment.
- **Named IdP connectors (Okta/Auth0/Keycloak via OIDC/JWKS) + console OIDC login.** Still part of
  WS-D but deferred to Wave 2 (they layer on `JWTIdentityAdapter`); this ADR lands the self-serve
  key edge that go-live needs first.
