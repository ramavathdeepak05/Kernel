"""K·14 / WS-F — regulator ledger-proof export.

Turns a tenant's K·02 transparency log (over a time window) into a **self-contained, independently
verifiable** proof bundle a regulator can check offline, without trusting — or even contacting — the
kernel:

  - the signed tree head (RFC 6962 STH: size, root, Ed25519 signature, signing public key);
  - one inclusion proof per governed action in the window (leaf hash + audit path);
  - the K·14 evidence narrative + manifest (which regulations/policy versions the window covers).

A verifier (`verify_ledger_proof_bundle`, shipped here so the regulator can run the same code)
recomputes the Merkle root from each inclusion proof and checks it equals the *signed* root, then
verifies the STH signature against the embedded public key. If both hold, the bundle proves every
listed action was sealed into an append-only log signed by the kernel's key — tamper-evident end to
end (F-09). The build side performs zero model re-calls and only reads already-sealed entries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from core.ledger.merkle import _recompute_root_from_path
from core.ledger.signer import SignedTreeHead, _signing_message
from core.regmap.catalog import generate_evidence_pack
from core.regmap.model import EvidencePack
from core.types import LedgerEntry

FORMAT_VERSION = "quaicu.ledger-proof/1.0"


@dataclass(frozen=True)
class InclusionProofExport:
    """One action's inclusion proof, hex-encoded for JSON transport."""

    ledger_seq: int
    leaf_hash_hex: str
    audit_path_hex: tuple[str, ...]
    action_id: str
    action_type: str
    decision: str
    sealed_at: str


@dataclass(frozen=True)
class SignedTreeHeadExport:
    """The signed tree head, hex-encoded, with the signing public key so it verifies offline."""

    tree_size: int
    root_hash_hex: str
    signature_hex: str
    key_id: str
    timestamp: str
    public_key_pem: str | None  # Ed25519 SPKI PEM; None if the signer does not expose it


@dataclass(frozen=True)
class LedgerProofBundle:
    """A complete, self-verifying regulator export."""

    tenant_id: str
    window_start: str
    window_end: str
    sth: SignedTreeHeadExport
    inclusion_proofs: tuple[InclusionProofExport, ...]
    evidence: EvidencePack
    generated_at: str
    format_version: str = FORMAT_VERSION
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """A fully JSON-serializable view (what the export route returns)."""
        return {
            "format_version": self.format_version,
            "tenant_id": self.tenant_id,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "generated_at": self.generated_at,
            "signed_tree_head": {
                "tree_size": self.sth.tree_size,
                "root_hash_hex": self.sth.root_hash_hex,
                "signature_hex": self.sth.signature_hex,
                "key_id": self.sth.key_id,
                "timestamp": self.sth.timestamp,
                "public_key_pem": self.sth.public_key_pem,
            },
            "inclusion_proofs": [
                {
                    "ledger_seq": p.ledger_seq,
                    "leaf_hash_hex": p.leaf_hash_hex,
                    "audit_path_hex": list(p.audit_path_hex),
                    "action_id": p.action_id,
                    "action_type": p.action_type,
                    "decision": p.decision,
                    "sealed_at": p.sealed_at,
                }
                for p in self.inclusion_proofs
            ],
            "evidence": {
                "verifiable": self.evidence.verifiable,
                "narrative": self.evidence.narrative,
                "manifest": {
                    "regulation_refs": list(self.evidence.manifest.regulation_refs),
                    "policy_versions": list(self.evidence.manifest.policy_versions),
                    "action_count": self.evidence.manifest.action_count,
                    "ledger_proof_refs": list(self.evidence.manifest.ledger_proof_refs),
                },
            },
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=2)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def build_ledger_proof_bundle(
    *,
    tenant_id: str,
    window_start: datetime,
    window_end: datetime,
    entries_with_paths: list[tuple[LedgerEntry, list[bytes]]],
    sth: SignedTreeHead,
    public_key_pem: str | None,
    regulation_refs: list[str] | None = None,
    policy_versions: list[str] | None = None,
) -> LedgerProofBundle:
    """Assemble a `LedgerProofBundle` from sealed entries + their inclusion proofs.

    ``entries_with_paths`` pairs each in-window `LedgerEntry` with its K·02 audit path (from
    ``TrustLedger.get_inclusion_proof``). ``sth`` is the tenant's current signed tree head; the proofs
    are verified against its root by the receiving regulator.
    """
    proofs = tuple(
        InclusionProofExport(
            ledger_seq=entry.ledger_seq,
            leaf_hash_hex=entry.leaf_hash.hex(),
            audit_path_hex=tuple(node.hex() for node in path),
            action_id=str(entry.action_id),
            action_type=entry.action_type,
            decision=entry.decision.value,
            sealed_at=_iso(entry.sealed_at),
        )
        for entry, path in entries_with_paths
    )

    # Real K·02 proof refs (leaf hashes) make the evidence pack independently verifiable (not a stub).
    pack = generate_evidence_pack(
        tenant_id=tenant_id,
        regulation_refs=list(regulation_refs or []),
        policy_versions=list(policy_versions or []),
        ledger_entries=[e for e, _ in entries_with_paths],
        window_start=window_start,
        window_end=window_end,
        ledger_proof_refs=[p.leaf_hash_hex for p in proofs],
    )

    sth_export = SignedTreeHeadExport(
        tree_size=sth.tree_size,
        root_hash_hex=sth.root_hash.hex(),
        signature_hex=sth.signature.hex(),
        key_id=sth.key_id,
        timestamp=_iso(sth.timestamp),
        public_key_pem=public_key_pem,
    )

    return LedgerProofBundle(
        tenant_id=tenant_id,
        window_start=_iso(window_start),
        window_end=_iso(window_end),
        sth=sth_export,
        inclusion_proofs=proofs,
        evidence=pack,
        generated_at=_iso(datetime.now(tz=timezone.utc)),
    )


def verify_ledger_proof_bundle(bundle_dict: dict) -> tuple[bool, list[str]]:
    """Independently verify an exported bundle (the code a regulator runs offline).

    Returns ``(ok, errors)``. ``ok`` is True only when (1) every inclusion proof recomputes the
    *signed* Merkle root and (2) the STH signature verifies against the embedded public key. Operates
    purely on the exported dict — no kernel state, no network.
    """
    errors: list[str] = []
    try:
        sth = bundle_dict["signed_tree_head"]
        tree_size = int(sth["tree_size"])
        root = bytes.fromhex(sth["root_hash_hex"])
        proofs = bundle_dict.get("inclusion_proofs", [])
    except (KeyError, ValueError, TypeError) as exc:
        return False, [f"malformed bundle: {exc}"]

    # (1) every inclusion proof must reconstruct the signed root.
    for p in proofs:
        try:
            seq = int(p["ledger_seq"])
            leaf = bytes.fromhex(p["leaf_hash_hex"])
            path = [bytes.fromhex(h) for h in p["audit_path_hex"]]
        except (KeyError, ValueError, TypeError) as exc:
            errors.append(f"malformed inclusion proof: {exc}")
            continue
        recomputed = _recompute_root_from_path(seq, tree_size, leaf, path)
        if recomputed != root:
            errors.append(f"inclusion proof for seq {seq} does not match the signed root")

    # (2) the STH signature must verify against the embedded public key.
    pem = sth.get("public_key_pem")
    if not pem:
        errors.append("no signing public key in bundle — STH signature cannot be verified")
    else:
        try:
            from cryptography.hazmat.primitives.serialization import load_pem_public_key

            public_key = load_pem_public_key(pem.encode())
            public_key.verify(bytes.fromhex(sth["signature_hex"]), _signing_message(tree_size, root))
        except Exception as exc:  # noqa: BLE001 — any failure is a verification failure
            errors.append(f"STH signature does not verify: {exc}")

    return (not errors), errors
