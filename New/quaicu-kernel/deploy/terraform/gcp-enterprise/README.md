# QUAICU Kernel — ENTERPRISE customer-hosted (GCP) Terraform

Stands up a dedicated, single-tenant kernel **inside the customer's own GCP project**. The customer's
data never leaves their account; QUAICU only issues the offline `license_token` that gates boot. This
is the high-ACV, "bypasses ~90% of vendor security questionnaires" model (see
[../../../docs/DEPLOYMENT_MODELS.md](../../../docs/DEPLOYMENT_MODELS.md)).

What it provisions (all in the customer project):
- **Cloud Run** — the kernel on the all-durable `kernel.gcp.toml` profile, license-gated.
- **Cloud KMS** — an HSM-backed **ECDSA P-256** key for RFC 6962 STH signing (GCP KMS has no Ed25519;
  matches the `gcp_kms_ledger` adapter / ADR-0012). `prevent_destroy` is set — destroying it makes
  past STHs unverifiable.
- **Cloud SQL (Postgres 16)** — regional/HA, PITR, deletion-protected: durable ledger, policy,
  storage, entitlements, accounts.
- **Service account** (keyless / Workload Identity) with least-privilege IAM, and Secret Manager for
  the DSN, API-key pepper, and license token.

> ⚠️ **Reviewable STARTER module.** Before production, harden with your platform team: VPC Service
> Controls perimeter + private IP (no public egress), Private Service Connect to Vertex, CMEK on all
> stores, IAM least-privilege review, and backup/DR policy. `aiplatform` (Vertex) API is enabled but
> the networking is left to your VPC design.

## Use
```bash
cd deploy/terraform/gcp-enterprise
terraform init
terraform apply \
  -var project_id=CUSTOMER_PROJECT \
  -var image=ghcr.io/<owner>/kernel:v0.1.0 \
  -var kernel_tenant_id=acme-bank \
  -var license_token="$(cat license.jwt)" \
  -var db_password="$(openssl rand -base64 24)" \
  -var api_key_pepper="$(openssl rand -base64 32)"
```

## After apply
1. **Migrate** the database (once): run Alembic migrations 001–006 against the Cloud SQL instance
   (via the Auth Proxy using `terraform output sql_connection_name`).
2. **Bake or mount `kernel.gcp.toml`** at `/etc/quaicu/` in the image (the module sets
   `KERNEL_CONFIG=/etc/quaicu/kernel.gcp.toml`). Its `[ledger]` `key_ring`/`key` must match
   `terraform output kms_key` (defaults `quaicu-ledger` / `sth-signer`).
3. **Smoke test:** `curl "$(terraform output -raw service_url)/health"`.

## Notes
- AWS parity (CloudFormation/Terraform with KMS Ed25519 + Bedrock + Aurora) is the analogous
  follow-up — see [../../../docs/strategy/ENTERPRISE_CLOUD_STRATEGY.md](../../../docs/strategy/ENTERPRISE_CLOUD_STRATEGY.md).
- A GCP Marketplace "click-to-deploy" listing can wrap this module (Deployment Manager / Terraform).
