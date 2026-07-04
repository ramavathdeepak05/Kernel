# Deploy the SaaS plane to Cloud Run

> **Preferred path going forward: Terraform.** This `gcloud` walkthrough is the original manual deploy;
> the same plane is now codified as IaC in [`deploy/terraform/gcp-saas`](../../deploy/terraform/gcp-saas/README.md)
> (region-parameterized for EU/India/Gulf residency, opt-in zero-egress). Use the module to stand up a
> new residency zone or to make this service reproducible; the steps below remain useful for
> understanding the env/secret surface the module sets.

Get the free (STARTER) + paid (BUSINESS) tiers live on Google Cloud Run. The image already honors
Cloud Run's injected `$PORT` and selects its ASGI app via `KERNEL_APP`, so deploying is config + env.
See also [HOSTING](../HOSTING.md), [GO_LIVE_SETUP](GO_LIVE_SETUP.md), and the customer-hosted
ENTERPRISE Terraform at [deploy/terraform/gcp-enterprise](../../deploy/terraform/gcp-enterprise/README.md).

## 0. Prerequisites
- `gcloud` authenticated; a project with billing; Artifact Registry + Cloud Run + Cloud SQL APIs on.
- The image built and pushed (CI publishes `ghcr.io/<owner>/kernel:<tag>` on a release tag; or build
  locally and push to Artifact Registry — see step 1).
- A Cloud SQL Postgres instance for the BUSINESS tier (the STARTER tier is in-memory, needs none).

## 1. Build + push the image (skip if using the GHCR release image)
```bash
PROJECT=your-project ; REGION=us-central1 ; REPO=quaicu ; TAG=v0.1.0
gcloud artifacts repositories create $REPO --repository-format=docker --location=$REGION 2>/dev/null || true
IMAGE="$REGION-docker.pkg.dev/$PROJECT/$REPO/kernel:$TAG"
# from New/quaicu-kernel/ :
gcloud builds submit --tag "$IMAGE" -f delivery/docker/Dockerfile .
```

## 2. The SaaS plane needs its config files in the image (or mounted)
The shared plane reads `KERNEL_CONFIG_SAAS` (a plane descriptor) which points at one durable kernel
config (ADR-0013). Simplest path: bake `delivery/docker/kernel.saas.toml` + `kernel.shared.toml`
into the image at `/etc/quaicu/` (add a `COPY delivery/docker/kernel.*.toml /etc/quaicu/` line to a
deploy Dockerfile, or mount them via a Secret/volume). The descriptor already references
`/etc/quaicu/kernel.{starter,business}.toml`.

## 3. Secrets (Secret Manager → env)
```bash
printf 'a-strong-random-pepper' | gcloud secrets create QUAICU_API_KEY_PEPPER --data-file=- 2>/dev/null || true
printf 'your-jwt-or-oidc-secret' | gcloud secrets create KERNEL_JWT_SECRET --data-file=- 2>/dev/null || true
# BUSINESS tier DSN (Cloud SQL). Use the connector socket form for Cloud Run:
#   postgresql://USER:PASS@/quaicu?host=/cloudsql/PROJECT:REGION:INSTANCE
printf '<business-dsn>' | gcloud secrets create ENTITLEMENTS_DSN --data-file=- 2>/dev/null || true
printf '<business-dsn>' | gcloud secrets create ACCOUNT_DSN --data-file=- 2>/dev/null || true
```

## 4. Deploy the shared SaaS plane (STARTER free + BUSINESS paid)
```bash
gcloud run deploy quaicu-kernel-saas \
  --image "$IMAGE" \
  --region "$REGION" \
  --allow-unauthenticated \
  --port 8080 \
  --add-cloudsql-instances "$PROJECT:$REGION:quaicu-pg" \
  --set-env-vars KERNEL_APP=delivery.entrypoint_saas:app,KERNEL_CONFIG_SAAS=/etc/quaicu/kernel.saas.toml,KERNEL_WORKERS=4 \
  --set-secrets QUAICU_API_KEY_PEPPER=QUAICU_API_KEY_PEPPER:latest,KERNEL_JWT_SECRET=KERNEL_JWT_SECRET:latest,ENTITLEMENTS_DSN=ENTITLEMENTS_DSN:latest,ACCOUNT_DSN=ACCOUNT_DSN:latest \
  --min-instances 0 --max-instances 10
```
- `KERNEL_APP=delivery.entrypoint_saas:app` selects the shared-plane app; the image listens on `$PORT`
  (8080) automatically.
- `--min-instances 0` = scale-to-zero (cheapest for the free tier). Bump to 1 to avoid cold starts.
- The STARTER tier is in-memory — fine on a single instance; for multi-instance free traffic the
  ephemeral ledger is per-instance (audit still flows to Cloud Logging via the log sink). The BUSINESS
  tier is all-durable (Cloud SQL), so it's safe across instances.

## 5. Migrate the BUSINESS database (once)
Run migrations 001–006 against the Cloud SQL instance (via the Auth Proxy or a one-off job):
```bash
DATABASE_URL='postgresql+asyncpg://USER:PASS@127.0.0.1:5433/quaicu?ssl=disable' \
  alembic -c adapters/storage/migrations/alembic.ini upgrade head
```

## 6. Smoke test
```bash
URL=$(gcloud run services describe quaicu-kernel-saas --region $REGION --format 'value(status.url)')
curl -s "$URL/health"                     # {"ok": true, "mode": "shared-plane", ...}
open  "$URL/docs"                          # interactive API
# Self-serve free-tier onboarding:
curl -s -X POST "$URL/v1/signup" -H 'Content-Type: application/json' \
  -d '{"email":"founder@acme.io","name":"Acme"}'   # → 201 { api_key, tenant_id, tier: STARTER }
```

## 7. Console (frontend) → Cloudflare Pages
```bash
cd console
npm ci && npm run build         # → console/dist (wrangler.toml already present)
VITE_API_BASE="$URL" npx wrangler pages deploy dist
```
Set `VITE_OIDC_ISSUER` / `VITE_OIDC_CLIENT_ID` for OIDC login (the kernel's `audience` must equal the
client id), and add the console origin to the API's CORS allow-list (`create_app(cors_origins=[…])`).

## 8. Rolling deploys — zero-downtime runbook (D4-1)

A Cloud Run deploy creates a **new revision** and shifts traffic when it is "ready". Two things make
that genuinely zero-downtime here:

1. **Readiness-gated rollout.** The Terraform module sets a `startup_probe` on **`/readyz`**, which
   only returns 200 after the app's lifespan hydration (policies + ledger trees + accounts) is done.
   A new revision therefore takes no traffic while hydrating; a revision that can't become ready is
   marked failed and the old revision keeps serving. (A plain `gcloud run deploy` without the probe
   gates only on "container listens on $PORT" — traffic can arrive mid-hydration; prefer the module,
   or add `--startup-probe` flags.)
2. **Graceful drain on the way out.** On SIGTERM the app flips `/readyz` to 503 (so the balancer
   stops routing to it), cancels the anchor/entitlement background tasks, closes MCP clients and DB
   pools, and lets in-flight requests finish (uvicorn default behavior). `/health` (liveness) keeps
   passing during the drain, so the instance isn't killed early.

Rolling deploy + verification:

```bash
# 1. Deploy the new image (new revision; traffic auto-shifts once the startup probe passes):
gcloud run deploy quaicu-kernel --image "$IMAGE" --region "$REGION"

# 2. In a second terminal DURING the rollout, prove no dropped requests:
while true; do curl -s -o /dev/null -w '%{http_code}\n' "$URL/v1/me/entitlements" \
  -H "Authorization: Bearer $QK_KEY"; sleep 0.5; done   # expect an unbroken run of 200s

# 3. Confirm the new revision serves and the old one drained:
gcloud run revisions list --service quaicu-kernel --region "$REGION"

# 4. Roll back instantly if needed (traffic pinning, no rebuild):
gcloud run services update-traffic quaicu-kernel --region "$REGION" \
  --to-revisions <previous-revision>=100
```

**Database-migration ordering** (matters when a release carries a migration): deploy the new image
FIRST, then run `alembic upgrade head`. D4-1's migration 017 (RLS on 6 more tables) specifically
requires the GUC-setting adapter build to be live before the migration flips FORCE RLS on, or reads
return empty. Additive migrations are generally deploy-then-migrate safe here because adapters set
their tenant GUC unconditionally (harmless pre-RLS).

## Multi-worker semantics (D4-1) — what's exact vs approximate

With `KERNEL_WORKERS > 1` and/or multiple instances, the shared plane is **correct** on everything
durable: actions (idempotency), the ledger (optimistic seal linearization — concurrent seals never
lose entries or fork the log), approvals, accounts/API keys (durable fallback + ≤60s revocation
TTL, `QUAICU_APIKEY_TTL`), entitlements (durable fallback + periodic re-read,
`QUAICU_ENTITLEMENTS_REFRESH`, default 60s — a tier flip propagates within that window).

Approximate by design (per-process counters, documented trade-off):
- **Per-minute rate limit** (`rate_limit_per_min`): enforced per worker → effective ceiling ≈
  configured × workers × instances. It is a coarse DoS guard, not billing; size the configured
  value accordingly.
- **AI-gateway token budget** (`QUAICU_AI_DEFAULT_MAX_TOKENS`): tracked per process.
- **Daily action quota** (`max_actions_per_day`): per-process **unless** `REDIS_URL` /
  `[metering].redis_url` is set (Memorystore) — then counts are exact across all workers/instances.
  The Terraform module provisions this opt-in via `enable_redis_metering = true`.

The periodic ledger **anchor loop** (D3-2, `[anchor] interval_seconds`) elects a single runner per
pass via a Postgres advisory lock, so N workers do not multiply witness cosign requests.

## Notes
- **Payments (BUSINESS):** add a `[billing.stripe]` / `[billing.razorpay]` section to
  `kernel.saas.toml` + the webhook endpoint; see [GO_LIVE_SETUP](GO_LIVE_SETUP.md) §4 (same dir).
- **Exact quotas across instances:** set `[metering].redis_url` (Memorystore) so daily-quota counts
  are exact when `--max-instances > 1`.
- **Single-tenant / dedicated** instead of the plane: omit `KERNEL_APP` (defaults to
  `delivery.entrypoint:app`) and set `KERNEL_CONFIG=/etc/quaicu/kernel.prod.toml` (or `kernel.gcp.toml`).
