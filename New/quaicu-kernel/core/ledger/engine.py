"""K·02 TrustLedger — per-tenant RFC 6962 transparency log.

ADR invariants enforced here:
  F-06: RFC 6962 Merkle tree, no custom proof structures.
  F-07: Strict per-tenant isolation — each tenant owns a completely separate MerkleTree,
        sequence counter, and entry list. Cross-tenant contamination is structurally impossible.
  F-03: Fail-closed — any exception in `seal` raises LedgerSealError so the engine HALTS.
  F-09: Replay-safe — recorded_result is stored in the entry verbatim at original execution.
  F-04: No bypass — TrustLedger depends only on core.types, core.errors, and its own submodules.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from core.errors import LedgerSealError
from core.ledger.merkle import MerkleTree
from core.ledger.signer import InMemoryEd25519Signer, SignedTreeHead, TreeSigner
from core.types import (
    Action,
    ApproverRef,
    EvaluationResult,
    LedgerEntry,
    TenantId,
)

_log = logging.getLogger("quaicu.ledger")


# ── Canonical serialization ───────────────────────────────────────────────────


def _canonical_bytes(
    action: Action,
    evaluation: EvaluationResult,
    recorded_result: Any,
    approver: ApproverRef | None,
    consent_state: dict[str, Any] | None = None,
) -> bytes:
    """Deterministic serialization of a seal request for hashing.

    sort_keys=True and ensure_ascii=True guarantee byte-identical output across Python versions
    and locales. `default=str` handles any non-JSON-native value without raising.
    consent_state is included so the K·04 state at evaluation time is covered by the Merkle leaf.
    """
    d = {
        "action_id": str(action.id),
        "action_type": action.type,
        "tenant": str(action.tenant),
        "actor_id": str(action.actor.id),
        "decision": evaluation.decision.value,
        "policy_versions": list(evaluation.policy_versions),
        "approver": str(approver) if approver else None,
        "consent_state": consent_state or {},
        "recorded_result": recorded_result if isinstance(recorded_result, dict) else {},
    }
    return json.dumps(d, sort_keys=True, ensure_ascii=True, default=str).encode("utf-8")


# ── TrustLedger ───────────────────────────────────────────────────────────────


class TrustLedger:
    """K·02. Per-tenant RFC 6962 transparency log.

    Tenant isolation: each tenant gets a completely separate MerkleTree and sequence counter.
    No tenant's entries ever appear in another tenant's tree.
    """

    def __init__(self, signer: TreeSigner | None = None) -> None:
        self._signer: TreeSigner = signer or InMemoryEd25519Signer()
        self._trees: dict[TenantId, MerkleTree] = {}
        self._sequences: dict[TenantId, int] = {}
        self._entries: dict[TenantId, list[LedgerEntry]] = {}
        self._sths: dict[TenantId, SignedTreeHead] = {}
        # Single asyncio lock — seals are serialized to keep sequence numbers monotonic.
        self._lock: asyncio.Lock = asyncio.Lock()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensure_tenant(self, tenant: TenantId) -> None:
        if tenant not in self._trees:
            self._trees[tenant] = MerkleTree()
            self._sequences[tenant] = 0
            self._entries[tenant] = []

    # ── Ledger protocol ───────────────────────────────────────────────────────

    async def seal(
        self,
        *,
        action: Action,
        evaluation: EvaluationResult,
        recorded_result: Any,
        approver: ApproverRef | None = None,
    ) -> LedgerEntry:
        """Seal an action into the per-tenant transparency log.

        Raises LedgerSealError on ANY failure so the lifecycle engine HALTS the action (F-03).
        An action is never marked COMPLETED without a successful seal.
        """
        try:
            async with self._lock:
                tenant = action.tenant
                self._ensure_tenant(tenant)

                # Extract K·04 consent state from evaluation metadata so it is
                # covered by the Merkle leaf hash and resolvable point-in-time.
                consent_state = dict(evaluation.metadata.get("consent_state", {}))

                seq = self._sequences[tenant]
                entry_bytes = _canonical_bytes(
                    action, evaluation, recorded_result, approver, consent_state
                )
                idx, lh = self._trees[tenant].append(entry_bytes)
                now = datetime.now(tz=timezone.utc)

                entry = LedgerEntry(
                    ledger_seq=seq,
                    tenant=tenant,
                    action_id=action.id,
                    action_type=action.type,
                    actor_id=action.actor.id,
                    decision=evaluation.decision,
                    policy_versions=evaluation.policy_versions,
                    leaf_hash=lh,
                    sealed_at=now,
                    approver=approver,
                    consent_state=consent_state,
                    recorded_result=recorded_result if isinstance(recorded_result, dict) else {},
                )

                self._entries[tenant].append(entry)
                self._sequences[tenant] = seq + 1

                root = self._trees[tenant].root()
                sth = self._signer.sign(self._trees[tenant].size, root, now)
                self._sths[tenant] = sth

                _log.debug(
                    "sealed action",
                    extra={
                        "tenant": tenant,
                        "seq": seq,
                        "action_id": str(action.id),
                        "tree_size": self._trees[tenant].size,
                    },
                )
                return entry

        except LedgerSealError:
            raise
        except Exception as exc:
            raise LedgerSealError(
                f"Failed to seal action {action.id} for tenant {action.tenant}: {exc}",
                detail={"action_id": str(action.id), "tenant": str(action.tenant)},
            ) from exc

    # ── Read-side operations ──────────────────────────────────────────────────

    def get_entry(self, tenant: TenantId, seq: int) -> LedgerEntry:
        """Return the entry at sequence number `seq` for `tenant`."""
        entries = self._entries.get(tenant, [])
        if seq < 0 or seq >= len(entries):
            raise KeyError(f"No entry at seq={seq} for tenant={tenant}")
        return entries[seq]

    def get_signed_tree_head(self, tenant: TenantId) -> SignedTreeHead:
        """Return the current Signed Tree Head for `tenant`."""
        if tenant not in self._sths:
            raise KeyError(f"No STH for tenant={tenant}")
        return self._sths[tenant]

    def get_inclusion_proof(
        self, tenant: TenantId, seq: int
    ) -> tuple[bytes, list[bytes]]:
        """Return (leaf_hash, proof_path) for the entry at `seq`."""
        entry = self.get_entry(tenant, seq)
        tree = self._trees[tenant]
        proof = tree.inclusion_proof(seq)
        return entry.leaf_hash, proof

    def verify_inclusion(
        self, tenant: TenantId, seq: int, sth: SignedTreeHead
    ) -> bool:
        """Verify that entry `seq` is included in the tree described by `sth`."""
        tree = self._trees.get(tenant)
        if tree is None:
            return False
        entry = self.get_entry(tenant, seq)
        proof = tree.inclusion_proof(seq)
        return tree.verify_inclusion(seq, entry.leaf_hash, proof, sth.root_hash)

    def get_consistency_proof(
        self, tenant: TenantId, old_size: int
    ) -> tuple[bytes, bytes, list[bytes]]:
        """Return (old_root, new_root, proof_path) from old_size to current size."""
        tree = self._trees.get(tenant)
        if tree is None:
            raise KeyError(f"No tree for tenant={tenant}")
        # Compute the old root from just the first old_size leaves.
        from core.ledger.merkle import compute_root

        old_leaves = list(tree._leaves[:old_size])
        old_root = compute_root(old_leaves)
        new_root = tree.root()
        proof = tree.consistency_proof(old_size)
        return old_root, new_root, proof

    def verify_consistency(
        self,
        tenant: TenantId,
        old_sth: SignedTreeHead,
        new_sth: SignedTreeHead,
    ) -> bool:
        """Verify that old_sth and new_sth describe the same append-only prefix."""
        tree = self._trees.get(tenant)
        if tree is None:
            return False
        proof = tree.consistency_proof(old_sth.tree_size)
        return tree.verify_consistency(
            old_sth.tree_size,
            old_sth.root_hash,
            new_sth.tree_size,
            new_sth.root_hash,
            proof,
        )
