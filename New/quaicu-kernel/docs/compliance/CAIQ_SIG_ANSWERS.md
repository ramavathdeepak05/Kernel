# Security questionnaire — pre-answered (CAIQ / SIG)

> **DRAFT — answer-once, reuse.** Pre-answered responses to the recurring questions in enterprise
> security questionnaires (CSA CAIQ, Shared Assessments SIG). Grounded in the current posture; confirm
> against the live system and the certifications as they land. Bracketed `[…]` items are pending.

_Owner: [security/compliance] · Tracks ACTION_TRACKER **W4-7** · Last updated: 2026-06-23_

## A. Governance & compliance
- **Certifications:** SOC 2 `[in progress — W2-2]`; ISO 27001/27701 `[planned — W2-4]`; independent
  pen-test `[booked — W2-3]`; K·02 crypto review `[commissioned — W2-1]`. See `WAVE2_COMPLIANCE_CLOCKS.md`.
- **Regulatory mappings:** DPDP + EU AI Act + RBI/SEBI policy packs ship in-product (`docs/policy-packs/`).
- **Security policy / responsible disclosure:** `SECURITY.md`. Vuln management + patch SLAs:
  `docs/operations/VULN_MANAGEMENT.md`.

## B. Data security & isolation
- **Multi-tenancy:** schema-per-tenant + Postgres Row-Level Security (`SET LOCAL app.current_tenant`);
  cross-tenant access is a 403, never a silent empty read.
- **Encryption:** TLS in transit; Google Cloud encryption at rest (Cloud SQL, Secret Manager, KMS).
- **Key management:** secrets in Secret Manager; API keys HMAC-peppered; rotation per
  `RETENTION_WORM_KEYROTATION.md`.
- **Data deletion / portability:** crypto-shred erasure (`core/erasure/`); audit/ledger export.
- **Data residency:** us-central1 today; EU/India/Gulf residency is roadmap (W5); Model B
  (customer-hosted single-tenant) keeps data in the customer's own infra.

## C. Identity & access
- **AuthN:** API keys (HMAC + pepper) and/or OIDC token verification; console bearer sessions.
- **AuthZ:** scoped roles; tenant-matched access (F-07).
- **SSO/SCIM:** OIDC verify supported; SCIM provisioning + enterprise RBAC UI are roadmap (W6-1).
- **Edge:** real-client-IP rate limiting authenticated by a shared edge secret (no `X-Forwarded-For`
  spoofing).

## D. Logging, monitoring & audit
- **Audit trail:** the K·02 append-only RFC-6962 Merkle ledger seals every governed action with actor +
  approver identity — tamper-evident.
- **Access logging:** structured per-request logs + correlation IDs (`observability.py`) to Cloud Logging.
- **Monitoring/alerting:** `[wiring per OBSERVABILITY_ONCALL_STATUS.md]`.

## E. Resilience & operations
- **BCP/DR:** Cloud SQL automated backups + PITR; runbook in `DR_BCP_RUNBOOK.md`; RTO/RPO `[pending the
  restore test]`.
- **Health checks:** `/health` (liveness) + `/readyz` (readiness).
- **Incident response:** `INCIDENT_RESPONSE.md`, incl. GDPR-72h / DPDP breach-notification playbook.
- **Change management / supply chain:** CI lint+test gate (blocking) + Trivy/pip-audit/SBOM (report
  mode) — `cloudbuild.yaml`.

## F. Sub-processors & shared responsibility
- **Sub-processors:** Razorpay/Stripe (payments), Resend (email), Google Cloud (infra), Cloudflare
  (edge). Shared-responsibility boundary table in `SECURITY.md`.
- **Payments / PCI:** hosted checkout only; QUAICU never stores card data — SAQ-A scope
  (`docs/compliance/PCI_SAQ_A_SCOPE.md`).

> **Maintenance:** when a control changes or a certification lands, update here first — this is the
> reuse surface for every customer questionnaire.
