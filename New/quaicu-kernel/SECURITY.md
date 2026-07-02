# Security

QUAICU is a fail-closed, multi-tenant AI governance kernel. This document is the public security
posture + vulnerability-disclosure policy, and the **shared-responsibility boundary** that the
penetration-test SoW, the GDPR DPA, and the SLA reference.

_Owner: [security] · Tracks ACTION_TRACKER **W4-6 / D0-4** · Last updated: 2026-07-01_

## Reporting a vulnerability
- **Email:** security@quaicu.org (or support@quaicu.org). PGP key: `[publish key / link]`.
- Please include reproduction steps and impact; do not publicly disclose until we've remediated.
- **Our targets:** acknowledge within **`[2]` business days**; triage severity within **`[5]`
  business days**; remediation per the SLAs in `docs/operations/VULN_MANAGEMENT.md`.
- We will keep you updated and credit you (if you wish) once a fix ships. We do not currently run a
  paid bug-bounty; good-faith research under this policy will not be pursued legally.

## Supported versions
The hosted SaaS plane runs the latest release; security fixes are applied to the current production
revision. Self-hosted (Model B / dedicated) customers receive advisories and patched images.

## Security posture (summary)
- **Tenant isolation:** schema-per-tenant + Postgres Row-Level Security (`SET LOCAL app.current_tenant`
  per transaction). Cross-tenant access on a path-tenant mismatch is a 403, never a silent empty read.
- **Authentication:** API keys are stored as **HMAC-SHA256 with a server-side pepper**
  (`QUAICU_API_KEY_PEPPER`, never blank in prod); OIDC token verification for IdP-token deployments;
  console sessions are bearer-token.
- **Fail-closed governance:** every governed action runs evaluate → gate → execute → seal → emit; a
  policy condition that errors denies. No action reaches execution without passing the kernel.
- **Tamper-evident audit:** the K·02 transparency ledger is an append-only RFC-6962 Merkle log; entries
  seal the actor + approver identity. (Independent crypto review is commissioned — see
  `docs/operations/CRYPTO_REVIEW_RFQ.md`.)
- **Edge:** the Cloudflare Worker forwards a verified real client IP authenticated by a shared edge
  secret (`X-Edge-Auth`), so rate-limiting cannot be defeated by spoofing `X-Forwarded-For`.
- **Transport/at-rest:** TLS in transit; Google Cloud encryption at rest (Cloud SQL, Secret Manager).
- **Supply chain:** CI runs lint + unit tests, **blocking** dependency (`pip-audit`, both locks) and
  image (Trivy HIGH/CRITICAL) scans, a CycloneDX **SBOM every build**, and **cosign image signing +
  SBOM attestation** using a Cloud KMS HSM key (`--tlog-upload=false`, zero-egress-safe) — see
  `cloudbuild.yaml` + `VULN_MANAGEMENT.md`.

## Shared-responsibility boundary
QUAICU builds on third-party managed services and is **not** responsible for vulnerabilities *within*
those platforms themselves (their providers are) — but **is** responsible for its own configuration
and use of them:

| Provider | Used for | Their responsibility | Ours |
|----------|----------|----------------------|------|
| **Google Cloud** | Cloud Run, Cloud SQL, Secret Manager, KMS | platform/infra security | correct IAM, network, RLS, secret hygiene |
| **Cloudflare** | edge / CDN / Worker front door | edge platform | Worker code, edge-auth secret, CSP/headers |
| **Razorpay / Stripe** | payments (hosted checkout) | PCI cardholder-data handling | correct integration, signature verification |
| **Resend** | transactional email | mail platform | template/content, key hygiene |
| **OpenBao** | ledger signing (where wired) | KMS platform | key custody, rotation |

A finding *in QUAICU's use* of any of the above is in scope; a finding *in the provider's own
platform* is theirs. See the penetration-test SoW (`docs/compliance/PENTEST_SOW.md`) for how this
scopes an engagement.

## Related documents
- Vulnerability management + patch SLAs: `docs/operations/VULN_MANAGEMENT.md`
- Incident response + breach notification: `docs/operations/INCIDENT_RESPONSE.md`
- DR/BCP: `docs/operations/DR_BCP_RUNBOOK.md`
- Data retention / WORM / key rotation: `docs/operations/RETENTION_WORM_KEYROTATION.md`
- Pre-answered security questionnaire: `docs/compliance/CAIQ_SIG_ANSWERS.md`
