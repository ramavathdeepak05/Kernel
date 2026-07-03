"""Consistency monitor / anchor orchestration (K·02 / D3-2).

Bridges the tenant's ledger and an independent `AnchorPort` (witness): it reads the current Signed
Tree Head, computes a consistency proof from the witness's last-seen size, and asks the witness to
cosign. If the current STH is not a consistent append-only extension of what the witness last saw —
a fork or silent rewind — the witness refuses and `LedgerTamperError` propagates (fail-closed).

Call at export time (so the bundle carries a fresh cosignature) and/or periodically from a scheduler.
"""

from __future__ import annotations

from typing import Protocol

from core.ledger.signer import SignedTreeHead
from core.ports.anchor import AnchorPort, WitnessCosignature
from core.types import TenantId


class _LedgerView(Protocol):
    def get_signed_tree_head(self, tenant: TenantId) -> SignedTreeHead: ...
    def get_consistency_proof(
        self, tenant: TenantId, old_size: int
    ) -> tuple[bytes, bytes, list[bytes]]: ...


def anchor_current_sth(
    ledger: _LedgerView, witness: AnchorPort, tenant: TenantId
) -> WitnessCosignature:
    """Anchor the tenant's current STH with an independent witness; return its cosignature.

    Raises ``LedgerTamperError`` (via the witness) if the current STH is not a consistent extension
    of the last one the witness cosigned — split-view / rewind detection.
    """
    sth = ledger.get_signed_tree_head(tenant)
    last = witness.last_seen(tenant)
    if last is None or last[0] >= sth.tree_size:
        # First STH, or same/smaller size — hand the witness an empty proof; it judges consistency
        # (a same-size fork or a smaller-size rewind both fail the witness's own check).
        proof: list[bytes] = []
    else:
        _, _, proof = ledger.get_consistency_proof(tenant, last[0])
    return witness.cosign(tenant, sth, proof)
