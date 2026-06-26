# The Auditor View — independent, offline-verifiable AI-governance evidence

> **For:** SI risk/assurance practices, audit firms, and the regulators they answer to. **The pitch:**
> an auditor can establish **what a client's AI did, under which policy, and who approved it — and verify
> it cryptographically, offline, without trusting QUAICU.** This is the SI-channel wedge
> ([`SI_CHANNEL_PROGRAM.md`](SI_CHANNEL_PROGRAM.md)). Everything here is **built today** — it packages
> existing surfaces, not a roadmap.

## What an auditor can independently establish

For any governed action in a client's tenant, the sealed record answers the audit questions:

- **What** the AI did — the action type + recorded inputs/outputs (PII masked).
- **Under which policy** — the policy id + version that decided it (K·01).
- **Who approved it** — the human approver's identity on high-risk actions (K·03; sealed per ADR-0007).
- **Provably, after the fact** — sealed to a per-tenant, append-only **RFC-6962 Merkle transparency log**
  (K·02), HSM/KMS-signed.

## The verification flow (no vendor trust, no network)

1. **Export** — the client (or the auditor, with read access) pulls a proof bundle for a time window:
   `GET /v1/ledger/{tenant}/export` → a self-verifying **`LedgerProofBundle`** (sealed entries + RFC-6962
   inclusion proofs + the signed tree head + the signing public key).
2. **Verify offline** — the auditor runs `core.regmap.export.verify_ledger_proof_bundle(bundle)` (or the
   convenience mirror `POST /v1/ledger/export/verify`). It recomputes every inclusion proof against the
   signed root and checks the STH signature against the embedded key — **purely from the bundle, no kernel
   access, no network.** This is the *same check a regulator runs*, and the same code the bundled demos
   use.
3. **Map to obligations** — [`../compliance/COMPLIANCE_MATRIX.md`](../compliance/COMPLIANCE_MATRIX.md)
   ties each control/evidence to **RBI FREE-AI / DPDP / EU AI Act** requirements; the K·14 evidence pack
   links sealed actions back to the specific regulation, **point-in-time** (the rules as they stood when
   the action occurred).

> The signing algorithm is inferred from the embedded key, so a GCP/AWS **Cloud-KMS-signed** bundle (FIPS)
> verifies with the **same offline code** as a software/OpenBao Ed25519 one — the auditor's verifier
> doesn't change across customer deployments.

## See it (hand these to an SI to run themselves)

- **Local, zero-setup:** [`../../examples/underwriting-demo/`](../../examples/underwriting-demo/README.md)
  — propose → HITL approve → seal → **`verify_ledger_proof_bundle()` → ✅ verified offline**; and
  [`../../examples/policy-pack-demo/`](../../examples/policy-pack-demo/README.md) — the shipped
  RBI/DPDP/EU-AI-Act packs governing a realistic action stream, then export + verify.
- **Live:** the console **Audit** page → **Download proof bundle (JSON)** (W6-6), which the auditor
  verifies with the offline verifier.

## Why this matters to the auditor (and the flywheel)

The auditor gets **defensible, reproducible evidence** instead of screenshots and the vendor's word — and
because they can verify it independently, **they can stand behind it to the regulator.** Once a firm's
assurance methodology treats QUAICU's proof bundle as the evidence standard, every client engagement
pulls QUAICU in (the [`SI_CHANNEL_PROGRAM.md`](SI_CHANNEL_PROGRAM.md) flywheel).

## Honest scope

- **Built:** the proof-bundle export, the offline verifier (+ its API mirror), the K·14 evidence pack, the
  console download, the regime→control matrix. An auditor can do the full verify flow above **today**.
- **Not built (follow-up, only if an SI pulls it):** a dedicated **read-only auditor console role** —
  scoped, time-boxed access for an external auditor to browse/export a tenant's audit trail in the UI
  without operator privileges. Today the auditor works from exported bundles (+ a tenant-shared console
  session). Note it; don't build it ahead of demand.
- QUAICU is the **evidence + enforcement** layer — it does not render the client or the audit compliant;
  it produces verifiable proof the auditor evaluates. (Consistent with the other kits' disclaimers.)
- Several **managed adapters** (Cloud DLP masking, HSM erasure keyring, some gateway shims) are validated
  against fake clients, not live cloud — state that in due diligence.

## References
- Architecture + crypto: [`../ARCHITECTURE_ONEPAGER.md`](../ARCHITECTURE_ONEPAGER.md),
  [`../compliance/SECURITY_WHITEPAPER.md`](../compliance/SECURITY_WHITEPAPER.md).
- Regime mapping: [`../compliance/COMPLIANCE_MATRIX.md`](../compliance/COMPLIANCE_MATRIX.md).
- Verifier: `core/regmap/export.py` (`build_ledger_proof_bundle` / `verify_ledger_proof_bundle`); export
  route `delivery/api/routes/ledger.py` (`/v1/ledger/{tenant}/export`, `/v1/ledger/export/verify`).
