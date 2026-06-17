# Changelog

All notable changes to the QUAICU Kernel are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); the project aims for [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **GCP cloud-native adapters (ADR-0012):** Cloud KMS ledger signer (`gcp_kms_ledger`, ECDSA P-256,
  FIPS 140-2 L3) with an algorithm-aware STH verifier, and Vertex AI inference (`vertex_inference`).
  Behind the optional `[gcp]` extra; `kernel.gcp.toml` profile. Verified live against Cloud SQL + KMS.
- **Self-serve onboarding:** `POST /v1/signup` wired via `[account].enabled`; a durable, Postgres-backed
  account store (migration 006) so signups survive restart / scale-out.
- **Free-tier governance:** STARTER now runs the in-memory CEL engine with seeded ACTIVATED policies
  (`[[policy.seed]]`), so the free tier enforces real allow/deny instead of pass-through.
- **Metering & audit:** `UsageMeter` wired into the entrypoints (daily-quota enforcement); a Redis
  shared meter (`[metering].redis_url`) for exact cross-replica counts; event sinks
  (`LoggingEventSink` / `PubSubEventSink`) for a durable audit stream with no database.
- **Marketplace metering** reporter scaffold (`adapters/billing/marketplace.py`) with GCP/AWS send seams.
- **Deploy:** Cloud Run-ready image (honors `$PORT`, `KERNEL_APP`); Cloud Run runbook
  (`docs/operations/DEPLOY_CLOUD_RUN.md`) and an ENTERPRISE customer-hosted Terraform module
  (`deploy/terraform/gcp-enterprise/`).
- **Docs:** `CEL_POLICY_GUIDE.md` (shareable CEL authoring context for client AIs), hosting /
  deployment-model / go-live runbooks, `ENTERPRISE_CLOUD_STRATEGY.md`, a starter DPDP policy pack,
  `LICENSE`, `SECURITY.md`, `docs/PRICING.md`, and the K·02 crypto-review RFQ.

### Security
- Rate-limit DoS fix: the per-minute counter keys on the verified principal (or client IP), never a
  spoofable `X-Tenant-Id`; auth runs before the limiter.
- OpenBao `verify()` raises on infrastructure errors instead of silently returning False.
- API keys hashed with HMAC-SHA256 + a server-side pepper (`QUAICU_API_KEY_PEPPER`).
- Postgres adapters set the RLS tenant context (`app.current_tenant`) per transaction (migration 004).

### Pending (pre-1.0 launch blockers)
- K·02 external cryptographic review of the RFC 6962 ledger (incl. the ECDSA-P256 STH path).
- Regulatory policy content packs beyond the starter DPDP pack.
- Final legal sign-off on LICENSE / SECURITY / PRICING; marketplace listing registration.

## [0.1.0] — unreleased
Initial pre-release: all 14 governance layers, the REST API + Python SDK + operator console, and the
three-tier commercial model (STARTER / BUSINESS / ENTERPRISE).
