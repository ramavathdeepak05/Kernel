# Verify a Ledger Proof

Every sealed action produces an RFC-6962 Merkle inclusion proof that can be verified without trusting QUAICU. This is the offline-verifiable moat.

!!! info "Coming soon"
    The full step-by-step guide (SHA-256 leaf encoding, domain separation 0x00/0x01, consistency proof verification) is being written.

## What the seal contains

```json
{
  "ledger_seq": 14209,
  "leaf_hash": "sha256:abc123...",
  "inclusion_proof": ["sha256:...", "sha256:...", "sha256:..."],
  "tree_size": 15000,
  "signed_tree_head": {
    "hash": "sha256:xyz...",
    "signature": "ed25519:...",
    "timestamp": "2026-06-28T10:00:00Z"
  }
}
```

## Verification steps (summary)

1. **Compute the leaf hash**: SHA-256 of `0x00 || canonical_json(action)` (RFC-6962 leaf encoding)
2. **Reconstruct the root**: apply the inclusion proof path, using `0x01 || left || right` for internal nodes
3. **Verify the signed tree head**: check the Ed25519 signature against QUAICU's published public key
4. **Confirm consistency**: if you hold a previous signed tree head, verify the consistency proof

A verifier that does steps 1–4 using only standard cryptographic primitives (SHA-256, Ed25519) does not need to trust QUAICU at all.

## Contact

For the QUAICU public signing key and a reference verifier implementation: [hello@quaicu.org](mailto:hello@quaicu.org)
