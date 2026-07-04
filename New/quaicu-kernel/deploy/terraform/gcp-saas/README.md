# QUAICU SaaS plane — Terraform (GCP, Model A)

Infrastructure-as-code for the **shared SaaS plane** (the multi-tenant `quaicu-kernel` Cloud Run
service: STARTER free + BUSINESS paid). It codifies the previously hand-run deploy in
[`docs/operations/DEPLOY_CLOUD_RUN.md`](../../../docs/operations/DEPLOY_CLOUD_RUN.md) and is
**region-parameterized** so the same module stands up an EU / India / Gulf residency zone (W5-1/W5-2).

> Tracks ACTION_TRACKER **W5-1 / W5-2 / W5-3**. This is a reviewable module — harden (VPC-SC, CMEK on
> all stores, private IP, WAF) with your platform team before treating it as the sole production
> source of truth. For the customer-hosted single-tenant (Model B) deployment, use
> [`../gcp-enterprise`](../gcp-enterprise/README.md).

## What it provisions
- Least-privilege runtime **service account** (cloudsql.client, secretmanager.accessor, logging).
- **Cloud SQL** Postgres 16 (REGIONAL HA, PITR, deletion-protected) for the durable BUSINESS-tier
  entitlements + accounts (STARTER is in-memory).
- **Secret Manager** secrets: `QUAICU_API_KEY_PEPPER`, `KERNEL_JWT_SECRET`, `ENTITLEMENTS_DSN`,
  `ACCOUNT_DSN`, `QUAICU_EDGE_SECRET`, and (optionally) `RAZORPAY_KEY_ID/SECRET`.
- **Cloud Run v2** shared-plane service (`KERNEL_APP=delivery.entrypoint_saas:app`), wired to the
  secrets + the Cloud SQL connector socket, public-invoker by default (behind the Cloudflare Worker).
  Production-shaped since D4-1: CPU/memory limits + `startup_cpu_boost`, per-instance request
  `concurrency` (autoscaling signal, pairs with `kernel_workers`), a **startup probe on `/readyz`**
  (a new revision receives traffic only after lifespan hydration completes → zero-downtime rolling
  deploys) and a **liveness probe on `/health`**.
- **Optional Memorystore Redis** (`enable_redis_metering = true`, requires the private-egress
  connector): injects `REDIS_URL` so daily usage quotas count exactly across workers/instances.
  Default off = per-process meter (approximate at scale-out).

## Usage
```bash
cd deploy/terraform/gcp-saas
terraform init
# Pick a residency zone preset, and supply secrets via your own (gitignored) secrets.auto.tfvars:
terraform plan  -var-file=regions/eu.tfvars
terraform apply -var-file=regions/eu.tfvars
```
`secrets.auto.tfvars` (DO NOT COMMIT) holds the sensitive inputs:
```hcl
project_id       = "my-eu-project"
image            = "europe-west1-docker.pkg.dev/my-eu-project/quaicu/kernel:vX.Y.Z"
db_password      = "..."
api_key_pepper   = "..."   # high-entropy; rotating invalidates all API keys
jwt_secret       = "..."
entitlements_dsn = "postgresql://quaicu:PASS@/quaicu?host=/cloudsql/PROJECT:REGION:quaicu-saas-pg"
account_dsn      = "postgresql://quaicu:PASS@/quaicu?host=/cloudsql/PROJECT:REGION:quaicu-saas-pg"
edge_secret      = "..."   # must equal the Cloudflare Worker's EDGE_SECRET (W1-1)
```

## Region presets (W5-2 — one stack per residency zone)
| Preset | Region | Regime |
|--------|--------|--------|
| `regions/eu.tfvars` | `europe-west1` | GDPR — no US egress |
| `regions/india.tfvars` | `asia-south1` | DPDP localization (+ RBI/SEBI pack) |
| `regions/gulf.tfvars` | `me-central1` | KSA/UAE sovereignty |
Multi-region = apply the module per zone (separate state) with the matching tfvars. See
[`DATA_RESIDENCY.md`](../../../docs/operations/DATA_RESIDENCY.md).

## Zero-egress (W5-3) — opt-in, default off
Set `enable_private_egress = true` + `vpc_connector = "projects/.../connectors/..."` to route Cloud
Run egress through a Serverless VPC Access connector and switch Cloud SQL to a private path. The
**VPC Service Controls perimeter is org-level** and is documented (not forced) in
[`ZERO_EGRESS_VALIDATION.md`](../../../docs/operations/ZERO_EGRESS_VALIDATION.md). Default off → a
plain apply matches today's public-path service.

## Adopting the EXISTING (hand-deployed) service
The live `quaicu-kernel` service was created with `gcloud run deploy`. To make this module its source
of truth without recreating it, **import** rather than apply greenfield:
```bash
# Example (adjust ids); run one import per resource the module declares:
terraform import google_cloud_run_v2_service.kernel \
  projects/PROJECT/locations/us-central1/services/quaicu-kernel
terraform import google_sql_database_instance.pg PROJECT:us-central1:quaicu-pg
# ... secrets, SA, IAM. Then `terraform plan` and reconcile drift to zero before relying on it.
```
Alternatively apply to a fresh parallel project/region and cut over the Worker origin.

## Validate (no apply)
```bash
terraform init -backend=false && terraform validate && terraform fmt -check
```
