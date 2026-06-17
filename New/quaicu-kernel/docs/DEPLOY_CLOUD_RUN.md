# Deploy the SaaS plane to Cloud Run

Get the free (STARTER) + paid (BUSINESS) tiers live on Google Cloud Run. The image already honors
Cloud Run's injected `$PORT` and selects its ASGI app via `KERNEL_APP`, so deploying is config + env.
See also [HOSTING](HOSTING.md), [GO_LIVE_SETUP](GO_LIVE_SETUP.md), and
[DEPLOY_ENTERPRISE_GCP](DEPLOY_ENTERPRISE_GCP.md) for the customer-hosted model.

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
The shared plane reads `KERNEL_CONFIG_SAAS` (a plane descriptor) which points at per-tier config files.
Simplest path: bake `delivery/docker/kernel.saas.toml`, `kernel.starter.toml`, `kernel.business.toml`
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

## Notes
- **Payments (BUSINESS):** add a `[billing.stripe]` / `[billing.razorpay]` section to
  `kernel.saas.toml` + the webhook endpoint; see [GO_LIVE_SETUP](GO_LIVE_SETUP.md) §4.
- **Exact quotas across instances:** set `[metering].redis_url` (Memorystore) so daily-quota counts
  are exact when `--max-instances > 1`.
- **Single-tenant / dedicated** instead of the plane: omit `KERNEL_APP` (defaults to
  `delivery.entrypoint:app`) and set `KERNEL_CONFIG=/etc/quaicu/kernel.prod.toml` (or `kernel.gcp.toml`).
