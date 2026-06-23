# RFQ — K·02 TrustLedger Cryptographic Review (DRAFT)

*[Internal. Send to a reputable firm — Trail of Bits / NCC Group / Kudelski / Cure53. Fill the
bracketed fields. This gates the regulated-enterprise (bank/health/gov) launch — commission early;
~6–8 week lead is typical.]*

## 1. Who we are
QUAICU — a fail-closed AI governance kernel. The **K·02 TrustLedger** is our RFC 6962-style Merkle
transparency log: every governed action is sealed into an append-only, per-tenant log with a signed
tree head (STH), so a regulator can independently verify the audit trail offline. Regulated buyers
require third-party attestation of this component.

## 2. Scope of review
Source: `core/ledger/` (Merkle tree, inclusion/consistency proofs, STH signing), the offline verifier
`core/regmap/export.py`, and the two signer adapters `adapters/ledger/openbao.py` (Ed25519) and
`adapters/ledger/gcp_kms.py` (**ECDSA P-256** — Cloud KMS has no Ed25519; this path is new and must be
in scope). Commit/tag: **[TAG]**.

Specifically assess:
1. **RFC 6962 conformance** — leaf/node hashing with 0x00/0x01 domain separation; inclusion and
   consistency proof construction and verification; canonical serialization.
2. **STH signing** — both schemes: Ed25519 (software/OpenBao) and ECDSA-P256-SHA256 (Cloud KMS). The
   verifier dispatches on public-key type rather than a wire tag — confirm this can't be downgraded
   or confused. Key never leaves the HSM (KMS/OpenBao).
3. **Append-only / tamper-evidence** — can any sequence of operations produce two valid STHs that
   are inconsistent? Replay/rollback resistance; per-tenant isolation of logs.
4. **Proof export** — the signed evidence pack (`verify_ledger_proof_bundle`) verifies offline with no
   kernel state; confirm there is no trust-the-server gap.
5. **Implementation hygiene** — timing side channels, error handling (fail-closed), dependency risk.

## 3. Deliverables
- A written report (findings by severity, with reproduction), a remediation review of our fixes, and
- a **letter of attestation** suitable to share with regulated customers and marketplace reviewers.

## 4. Logistics
- Access: read-only repo access at the pinned tag; a walkthrough call; our engineering on call for Qs.
- Timeline: report in **[N] weeks**; remediation re-review within **[N]** of fixes.
- Budget / NDA / contacts: **[TBD]**.

## 5. Out of scope (this engagement)
The broader application (API auth, billing, console), and non-K·02 governance layers — unless a
finding crosses into them.

## 6. Commissioning checklist (W2-1 — send-ready once the brackets are filled)

This RFQ gates the regulated-enterprise launch and has the longest lead time in Wave 2 (~6–8 wk), so
commission it **first**. To turn this draft into an outbound RFQ:

**Fill these before sending:**
- [ ] `[TAG]` (§2) — pin to a specific release commit/tag so the firm reviews a frozen tree.
- [ ] `[N]` weeks (§4) — proposed report timeline (typical 3–4 wk) and remediation re-review window.
- [ ] Budget band (§4) — set an internal ceiling; a focused K·02 review is usually a few-week fixed-fee engagement.
- [ ] NDA — attach your mutual NDA; most firms will counter-sign or supply their own.
- [ ] Contacts (§4) — name the engineering point-of-contact for the walkthrough call and Qs.

**Vendor shortlist** (request a quote from 2–3 in parallel; all have public Merkle/transparency-log or
applied-crypto track records):
| Firm | Why | How to approach |
|---|---|---|
| **Trail of Bits** | Deep applied-crypto + protocol review; published on transparency logs | Contact via their website engagement form; reference "K·02 RFC 6962 Merkle ledger + Ed25519/ECDSA-P256 STH signing" |
| **NCC Group** | Large crypto practice; familiar to enterprise/bank procurement | Standard RFP intake; the bank-facing brand helps the attestation land |
| **Kudelski Security** | Strong applied-crypto / HSM & key-management focus | Good fit given the OpenBao/Cloud-KMS signer split |
| **Cure53** | Sharp, fast, focused crypto/appsec reviews | Best for a tight, time-boxed scope |

**What to require in the deliverable** (so it's usable in sales): findings-by-severity report **with
reproductions**, a **remediation re-review** of our fixes, and a **letter of attestation** suitable to
share with regulated customers and marketplace reviewers (this letter is the asset the whole credibility
story hangs on — make it an explicit contract deliverable, not a maybe).

**After it lands:** record the report date + attestation in the trust center (W4-6) and the Wave-2 clock
tracker (`docs/compliance/WAVE2_COMPLIANCE_CLOCKS.md`); feed any findings back through the normal fix
flow and request the re-review letter.
