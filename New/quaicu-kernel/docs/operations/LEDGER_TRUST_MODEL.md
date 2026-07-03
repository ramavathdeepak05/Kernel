# Ledger proof-bundle trust model (K·02 / D3-1)

How an auditor or regulator independently trusts a QUAICU ledger export. A proof bundle
(`GET /v1/ledger/{tenant}/export`) asserts that a set of governed actions were sealed into an
append-only RFC 6962 transparency log. Verifying it has **two separable properties**.

## 1. Integrity — self-contained

`verify_ledger_proof_bundle` recomputes the Merkle root from each entry's inclusion proof and checks
it equals the **signed root** in the STH. This detects any tampering *within* the bundle (a changed
leaf, a doctored proof, an altered root) using **nothing but the bundle** — no key, no network.

## 2. Authenticity — requires a pinned key (the D3-1 change)

Integrity alone is not enough: an attacker can fabricate a fully self-consistent bundle signed with
**their own** keypair and embed that key. To stop this, the STH signature is verified against an
**out-of-band, pinned** key — never the key embedded in the bundle:

```python
from core.regmap.export import verify_ledger_proof_bundle

ok, errors = verify_ledger_proof_bundle(
    bundle,
    trusted_keys={key_id: public_key_pem},   # the key you pinned at onboarding
)
```

Rules (all fail-closed):

- **No `trusted_keys`** → authenticity cannot be attested → `ok = False`.
- Bundle's `key_id` **not in** `trusted_keys` (a forged/unknown key) → `ok = False`.
- Signature does not verify against `trusted_keys[key_id]` → `ok = False`.
- If the bundle also embeds a public key and it differs from the pinned key → `ok = False`
  (tamper signal). The embedded key is advisory only.

## Obtaining and pinning the key

Once, at onboarding, over an authenticated channel:

```
GET /v1/ledger/signing-key   →   { "key_id": "...", "public_key_pem": "-----BEGIN PUBLIC KEY-----\n...",
                                    "algorithm": "ed25519" | "ecdsa-p256" }
```

Record `key_id → public_key_pem` in **your own** records (a key registry / trust-center entry) and
pin it. Thereafter you verify every export against your pinned copy, so a later kernel-side key swap
cannot pass — the swapped `key_id`/key won't match what you pinned.

The signing scheme is transparent to the verifier: an Ed25519 (software / OpenBao) key and an
ECDSA-P256 (GCP/AWS Cloud KMS) key pin and verify through the same code path.

## The hosted verify endpoint

`POST /v1/ledger/export/verify` runs the verifier server-side and pins against **that tenant kernel's
own** signing key — so it answers *"did we sign this?"*. For a fully independent check, run
`verify_ledger_proof_bundle` yourself, offline, against the key you pinned.

## Key rotation

Rotating the STH signing key mints a new `key_id`; new exports sign under it. **Retired keys are
never deleted** while any entry references them, and old bundles stay verifiable — so your pinned
registry keeps both the old and new `key_id → key` entries. (Cross-signed rotation entries and the
external witness/anchoring that detects a silent split-view are D3-2.)
