# QUAICU Kernel — Go-Live Setup (SaaS / Model A)

Everything you need to stand up the hosted SaaS plane: the **API**, the **operator console
(frontend)**, **Stripe/Razorpay** payments, the **database**, and the supporting config (secrets, CORS,
DNS/TLS, OIDC). For the two delivery models see [DEPLOYMENT_MODELS](DEPLOYMENT_MODELS.md); for the
hosting basics see [HOSTING](../HOSTING.md).

> Conventions: API on port **7000**; console (Vite/React) builds to static files. All secrets are
> `${ENV_VAR}` references in TOML, resolved at load — **never commit live keys**.

---

## 0. Prerequisites
- A domain (e.g. `api.yourco.com` for the API, `app.yourco.com` for the console).
- Managed Postgres (Cloud SQL / Aurora) reachable from the API.
- Signing backend: **Cloud KMS** (`gcp_kms_ledger`, recommended) or OpenBao.
- A container host: Cloud Run / GKE / ECS, or the Helm chart at `delivery/docker/helm/`.
- Stripe and/or Razorpay account(s).
- (Optional) an OIDC IdP (Okta/Auth0/Azure AD/Identity Platform) for console + API auth.

---

## 1. Database + migrations
Run the Alembic migrations once against your Postgres (creates actions, policy, ledger, RLS, and
entitlement tables — migrations 001–005):
```bash
DATABASE_URL=postgresql://USER:PASS@HOST/DB \
  alembic -c adapters/storage/migrations/alembic.ini upgrade head
```

## 2. Secrets / environment
Set these in your container env (Secret Manager / SSM / k8s Secret — not in the TOML):

| Env var | Purpose |
|---|---|
| `KERNEL_CONFIG_SAAS` | path to `kernel.saas.toml` (mounted) |
| `ENTITLEMENTS_DSN`, `KERNEL_DSN` | Postgres DSNs |
| `QUAICU_API_KEY_PEPPER` | **required** — server-side pepper for API-key hashing |
| `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` | Stripe (see §4) |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | Razorpay (see §4) |
| `GCP_PROJECT`, `GCP_LOCATION` | if using Cloud KMS / Vertex |
| `KERNEL_WORKERS` | >1 only with a durable profile |

## 3. Run the API (shared plane)
```bash
KERNEL_CONFIG_SAAS=/etc/quaicu/kernel.saas.toml quaicu-kernel-saas
# or: uvicorn delivery.entrypoint_saas:app --host 0.0.0.0 --port 7000 --workers 4
```
`kernel.saas.toml` points at one durable `kernel.shared.toml` serving all tiers (ADR-0013), the durable
`[entitlements]` store, and (when configured) wires billing. Metering + per-tier limits are now active
out of the box (the `UsageMeter` is wired into the SaaS app). Verify: `curl https://api.yourco.com/health`.

## 4. Payments — Stripe / Razorpay

Billing is **config-driven** (`delivery/sdk/billing_config.py`): add a `[billing]` section to
`kernel.saas.toml` and the `/v1/billing/*` routes + the console Billing page light up. Omit it and
billing stays disabled (routes 503).

### 4a. Stripe
1. In the Stripe dashboard create a **Product + recurring Price** per paid tier; note each `price_…` id.
2. Add a **webhook endpoint** → `https://api.yourco.com/v1/billing/webhook` and copy its **signing
   secret** (`whsec_…`).
3. Config (secrets via env):
   ```toml
   [billing.stripe]
   webhook_secret = "${STRIPE_WEBHOOK_SECRET}"
   api_key        = "${STRIPE_API_KEY}"          # omit for webhook-only (no checkout)
   [billing.stripe.price_to_tier]
   "price_business"   = "BUSINESS"
   "price_enterprise" = "ENTERPRISE"
   ```
4. Flow: console/app calls `POST /v1/billing/checkout` (API-key, `billing:write` scope) → returns a
   Stripe Checkout `url` → user pays → Stripe fires the webhook → `BillingEngine` flips the tenant's
   tier in the `EntitlementStore` (idempotent; survives restart via Postgres). The new tier's limits
   apply on the next request.

### 4b. Razorpay (India / UPI)
1. Create **Plans** per tier; note each `plan_…` id. Add a **webhook** →
   `…/v1/billing/webhook` with a secret.
2. Config:
   ```toml
   [billing.razorpay]
   webhook_secret = "${RAZORPAY_WEBHOOK_SECRET}"
   key_id         = "${RAZORPAY_KEY_ID}"
   key_secret     = "${RAZORPAY_KEY_SECRET}"
   [billing.razorpay.plan_to_tier]
   "plan_business" = "BUSINESS"
   ```
Both providers can run side by side. Webhook signatures are verified **fail-closed** (bad signature →
rejected); the webhook route is exempt from API-key auth + rate-limit (it's provider-signed). Tip: test
locally with the Stripe CLI (`stripe listen --forward-to localhost:7000/v1/billing/webhook`).

> **Marketplace billing (AWS/GCP):** to charge via cloud-commit credits instead of cards, use the
> `MarketplaceMeteringReporter` (`adapters/billing/marketplace.py`) — it reports per-tenant usage
> deltas read from the `UsageMeter`. Finish the cloud `send` seam (`gcp_sender`/`aws_sender`) and call
> `report_all(meter, tenants)` from a scheduler (Cloud Scheduler / EventBridge). See
> [ENTERPRISE_CLOUD_STRATEGY](../strategy/ENTERPRISE_CLOUD_STRATEGY.md) §5.

## 5. Frontend — operator console
React/Vite app in `console/`. It calls the kernel REST API and sends the user's bearer token.

**Build:**
```bash
cd console
npm ci
npm run build            # → console/dist (static files)
```
**Configure (`console/.env.local`, baked at build time):**
```
VITE_OIDC_ISSUER=https://YOUR-IDP/oauth2/default
VITE_OIDC_CLIENT_ID=<spa-client-id>     # MUST equal the kernel's OIDC `audience`
# leave OIDC unset to use manual token-paste (local dev only)
```
**Host the static `dist/`** on any static host (Cloud Storage + CDN, S3+CloudFront, Netlify, nginx).
Two ways to reach the API:
- **Same-origin (simplest):** serve the console and reverse-proxy `/v1` + `/health` to the API — no
  CORS needed (mirrors the dev proxy in `console/vite.config.ts`).
- **Cross-origin:** host the console on `app.yourco.com`, API on `api.yourco.com`, and set the API's
  CORS allow-list (`create_app(cors_origins=["https://app.yourco.com"])`).

The console exercises `/v1/me/entitlements` (tier view), `/v1/billing/checkout` (upgrade), policy
authoring, dashboards, ledger trail, and HITL approvals.

## 6. Identity (OIDC) — optional but recommended
- Register a SPA app in your IdP; set the redirect URI to `https://app.yourco.com/callback`.
- The console obtains an `id_token` (Auth Code + PKCE) and sends it as the bearer; the kernel's
  `oidc` IdentityPort verifies it (issuer + audience + rotating JWKS, fail-closed).
- **The kernel's `audience` must equal the console's `VITE_OIDC_CLIENT_ID`.** The tenant is read from
  the token's `tenant`/`tid` claim.
- Alternatively, use self-serve **API keys** (`/v1/signup`) and set `require_api_key=True` — no IdP
  needed.

## 7. DNS / TLS / network
- TLS terminates at your load balancer / ingress (Cloud Run and managed LBs do this for you).
- If behind an LB, configure a **trusted forwarded-for handler** so the rate-limiter's IP fallback
  sees real client IPs (don't trust raw `X-Forwarded-For`).
- Lock egress: for the regulated story, reach inference/KMS over **Private Service Connect /
  PrivateLink** and block public egress.

## 8. Go-live checklist
- [ ] Migrations applied (`alembic upgrade head`).
- [ ] `QUAICU_API_KEY_PEPPER` set; `require_api_key=True` (or OIDC) on.
- [ ] Durable profile so `KERNEL_WORKERS>1` / replicas are safe.
- [ ] Cloud KMS signing wired (`gcp_kms_ledger`) for the auditable ledger.
- [ ] `[billing]` configured; webhook endpoint registered; `price_to_tier` / `plan_to_tier` mapped.
- [ ] Checkout → webhook → tier-flip tested end-to-end (Stripe CLI / Razorpay test mode).
- [ ] Console built with prod `VITE_OIDC_*`; API reachable (same-origin proxy or CORS allow-list).
- [ ] TLS + trusted proxy headers; egress locked down.
- [ ] `/health` green; `/v1/me/entitlements` returns the right tier; a 429 fires past the tier limit.
- [ ] (Multi-replica) set `[metering].redis_url` / `REDIS_URL` so the **shared Redis meter** gives
      exact cross-replica daily-quota counts (install the `[redis]` extra).
