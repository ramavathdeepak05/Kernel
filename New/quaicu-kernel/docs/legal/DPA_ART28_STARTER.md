# GDPR Article 28 Data Processing Addendum — starter outline

> **DRAFT — NOT LEGAL ADVICE.** This is an engineering-side checklist of the clauses a GDPR Art.28 DPA
> must contain and where QUAICU already supports each, to **brief counsel and speed drafting** — it is
> not a contract and must be drafted/reviewed by a qualified data-protection lawyer before use.

_Owner: [counsel] · Tracks ACTION_TRACKER **W2-5** · Last updated: 2026-06-23_

## Context
When a QUAICU customer (the **controller**) has us process personal data on their behalf, QUAICU is a
**processor** and GDPR Art.28(3) requires a written contract with the mandatory terms below. This is
legally required to process **any** EU personal data, so it gates the EU beachhead.

## Mandatory Art.28(3) clauses (and QUAICU's posture)
| # | Required term (Art.28(3)) | Drafting note / where QUAICU supports it |
|---|---|---|
| (a) | Process **only on documented instructions** of the controller (incl. for transfers) | The kernel acts on tenant-scoped, logged actions; the controller's configured policies define lawful processing. Bind "instructions" to the configured policy set + signed order form. |
| (b) | Persons authorised to process are under a **duty of confidentiality** | Reference internal confidentiality obligations; name access controls (least-privilege, audited access — see RBI pack `access.grant` logging analogue). |
| (c) | Take all **Art.32 security measures** | Point to: schema-per-tenant + RLS isolation, HMAC-peppered API keys, encryption in transit/at rest, the K·02 tamper-evident ledger, fail-closed governance, Trivy/cosign/SBOM in CI. (Attach the SECURITY.md / trust-center summary.) |
| (d) | Engage **no sub-processor** without authorisation; flow down Art.28 terms | List current sub-processors (below); commit to a notice mechanism for changes + the right to object. |
| (e) | **Assist the controller** with data-subject rights (Arts.12–22) | The erasure engine (`core/erasure/`) + consent layer (K·04) + audit/ledger export support access/erasure/portability responses. |
| (f) | **Assist with Art.32–36** (security, breach notice, DPIAs) | Tamper-evident audit trail + (planned) incident-response runbook; breach-notification process feeds the controller's Art.33 **72-hour** duty. |
| (g) | **Delete or return** all personal data at end of provision; delete copies | Crypto-shred erasure path (today `InMemoryShredKeyring`; HSM-backed `GcpKmsShredKeyring` is W6-4) → "provable deletion". State the default (delete) + retention window. |
| (h) | Make available info to **demonstrate compliance** and allow **audits/inspections** | K·14 regulatory-mapping evidence packs + the audit ledger; offer audit rights (mirrors the RBI outsourcing audit-rights control). |

## Sub-processors (of record — confirm before publishing)
From the product's own privacy disclosure (`console/src/legal/content.ts`):
- **Razorpay** — payments (and Stripe where enabled).
- **Resend** — transactional email.
- **Google Cloud** — hosting / infrastructure.
- **Cloudflare** — edge / CDN / Worker (front door).

For each: record the processing purpose, data categories, location, and their own DPA/SCC posture.

## International transfers (Chapter V)
- If personal data leaves the EEA, attach the EU **Standard Contractual Clauses (2021/914)** with a
  completed transfer-impact assessment, **or** rely on an adequacy decision.
- QUAICU's **Model B (customer-hosted single-tenant)** and the planned EU-region SaaS deployment
  (residency work, W5) materially reduce transfer exposure — note which deployment model the customer
  is on, as it changes the transfer analysis.

## Next actions
1. Counsel drafts the binding DPA from this checklist + the company's standard MSA.
2. Finalise and publish the **sub-processor list** + change-notification mechanism (feeds the trust
   center, W4-6).
3. Attach the **SCC** module set for processor→processor / controller→processor as applicable.
4. Cross-link the security-measures annex to the SOC 2 / ISO 27001 evidence once available.
