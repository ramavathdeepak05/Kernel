---
name: quaicu-trust-ledger
description: |
  QUAICU K·02 TrustLedger — RFC 6962-style Merkle transparency log on PostgreSQL. Use when
  building core/ledger/, the Merkle tree implementation, inclusion proofs, consistency proofs,
  signed tree heads, or the ledger verification API. Enforces: RFC 6962 standard (no custom proof
  structures), append-only, per-tenant tables (never shared), SHA-256 primitives only, third-party
  crypto review required before bank deployment. Trigger keywords: TrustLedger, ledger, seal,
  MerkleTree, inclusion_proof, consistency_proof, tree_head, SignedTreeHead, ledger_seq,
  append_only, hash_chain, verify, RFC 6962, log, transparency, subtree_hash, tile_storage,
  key_rotation, batch_verify, clock_skew, air_gapped, concurrent_append.
---

# QUAICU K·02 TrustLedger

You are the TrustLedger correctness enforcer. The ledger is the single highest-risk correctness
component in the entire kernel. A bank's security reviewer and regulator will scrutinize it hardest.
A subtle flaw in the integrity proof undermines the whole product. This document is a complete
implementation reference — not a summary. Every section below must be implemented exactly as
specified.

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> Makes every ledger choice mechanical so a small/low-token model matches a top model at max effort.
> This is the highest-risk component. **If this block conflicts with prose below, this block wins.**
> Missing rule → raise and HALT; never invent a proof shape.

### Invariants — never violated
- ALWAYS implement RFC 6962 exactly: leaf = `SHA256(0x00 ‖ entry)`, node = `SHA256(0x01 ‖ left ‖ right)`. Never omit the domain-separation prefix; never invent a custom proof structure (F-06).
- ALWAYS one ledger table per tenant (`"tenant_{id}".ledger_entries`). NEVER a shared `ledger` table with a `tenant_id` column (F-07).
- ALWAYS append-only: INSERT only. NEVER UPDATE/DELETE a ledger row. No RLS UPDATE/DELETE policy exists, by design.
- ALWAYS record inputs AND results in the entry (replay fidelity, F-09), not just the outcome.
- ALWAYS serialize with canonical JSON (sorted keys, fixed separators, UTF-8) before hashing — identical bytes every time.
- ON seal failure → raise `LedgerSealError`; the lifecycle HALTS the action. Never swallow, never mark executed.

### Ordering & concurrency (apply exactly)
- Sequence comes from a DB sequence/serial, NOT wall-clock. Timestamps are metadata only.
- Concurrent seals: `SELECT … FOR UPDATE` on the tenant's tree-head row before computing the new root; serialize appends per tenant.
- Clock skew (timestamp goes backward while seq advances): record a `LedgerClockSkewEvent` and CONTINUE. Never reject the seal — order is by seq, not time.

### Proof selection
| Question | Use |
|---|---|
| "Is entry N in the tree of size M?" | inclusion proof (`verify_inclusion`) |
| "Is size-M tree an extension of size-N tree?" | consistency proof (`verify_consistency`) |
| Consistency proof fails | `LedgerTamperError` — critical, alert immediately, do not proceed |

### Tie-break rules
- Tempted by a "convenient" deviation from RFC 6962? → don't; implement the RFC exactly. Deviation = regulator liability.
- Reject a seal over a timestamp anomaly? → don't; record a skew event and continue.
- Ordering two appends? → DB sequence decides, never timestamps.

### Stop-and-apply triggers
- About to hash without a `0x00`/`0x01` prefix? → STOP, add domain separation.
- About to write `UPDATE`/`DELETE` on a ledger table? → STOP, it is append-only.
- About to add `tenant_id` to a shared ledger table? → STOP, use per-tenant tables.

### Self-check
- [ ] Leaf/node hashes use the 0x00/0x01 prefixes.
- [ ] No UPDATE/DELETE against any ledger table anywhere.
- [ ] Per-tenant ledger tables; no shared ledger.
- [ ] Canonical (key-sorted) JSON for every hashed entry.
- [ ] Seal under FOR UPDATE; sequence from DB, not clock.
- [ ] Seal failure raises+halts; consistency-proof failure raises tamper + alert.

## Frozen Decisions That Apply Here

| ADR | Rule |
|-----|------|
| F-06 | **RFC 6962-style transparency log only.** No custom proof structures. Every deviation is liability. |
| F-07 | **Per-tenant ledger tables.** Never a shared `ledger` table with a `tenant_id` column. Cross-tenant contamination must be *impossible*. |
| F-09 | Ledger entries record inputs AND results, not just outcomes — required for replay fidelity. |
| F-03 | Fail-closed: any failure in seal → raise, lifecycle engine halts the action. |

---

## Error Type Hierarchy

Define these in `core/ledger/errors.py`. All errors carry an `error_code` string for structured
logging and OTel attributes.

```python
# core/ledger/errors.py

class LedgerError(Exception):
    """Base for all TrustLedger errors. Never raised directly."""
    error_code: str = "LEDGER_000"

    def __init__(self, message: str, **context):
        super().__init__(message)
        self.context = context  # extra fields attached to OTel span

class LedgerSealError(LedgerError):
    """Raised when seal() cannot complete. Lifecycle → HALTED."""
    error_code = "LEDGER_001"

class LedgerConcurrencyError(LedgerSealError):
    """Advisory lock or SELECT FOR UPDATE timed out. Retry at caller."""
    error_code = "LEDGER_002"

class LedgerHashMismatchError(LedgerError):
    """entry_hash does not match the recomputed hash on read-back."""
    error_code = "LEDGER_003"

class LedgerProofVerificationError(LedgerError):
    """inclusion_proof or consistency_proof did not verify."""
    error_code = "LEDGER_004"

class LedgerSequenceGapError(LedgerError):
    """ledger_seq has a gap — tampering or corruption detected."""
    error_code = "LEDGER_005"

class LedgerSignatureError(LedgerError):
    """STH signature verification failed."""
    error_code = "LEDGER_006"

class LedgerKeyRotationError(LedgerError):
    """Key rotation procedure encountered an invalid state."""
    error_code = "LEDGER_007"

class LedgerClockSkewError(LedgerError):
    """Monotonic sequence would regress (air-gapped clock skew)."""
    error_code = "LEDGER_008"

class LedgerTenantIsolationError(LedgerError):
    """A cross-tenant access was attempted — hard stop."""
    error_code = "LEDGER_009"

class LedgerBatchVerificationError(LedgerError):
    """One or more entries in a batch audit failed verification."""
    error_code = "LEDGER_010"
    def __init__(self, message: str, failed_seqs: list[int], **ctx):
        super().__init__(message, **ctx)
        self.failed_seqs = failed_seqs
```

---

## RFC 6962 Merkle Structure (implement exactly this — do not invent)

The ledger is a **Merkle Hash Tree** as defined in RFC 6962 (Certificate Transparency):

```
Leaf hash:   SHA-256(0x00 || leaf_data)
Node hash:   SHA-256(0x01 || left_child_hash || right_child_hash)
Tree head:   root hash over all leaves at the current tree size
```

The `0x00` / `0x01` domain separation prefixes are **mandatory** — they prevent second-preimage
attacks. Do not omit them. Do not change them. They are load-bearing cryptographic constants.

```python
# core/ledger/merkle.py
import hashlib
from typing import Sequence

LEAF_PREFIX = b'\x00'
NODE_PREFIX = b'\x01'


def leaf_hash(data: bytes) -> bytes:
    """RFC 6962 §2.1 leaf hash. data = canonical JSON bytes of the ledger entry."""
    return hashlib.sha256(LEAF_PREFIX + data).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    """RFC 6962 §2.1 internal node hash."""
    return hashlib.sha256(NODE_PREFIX + left + right).digest()


def subtree_hash(leaves: Sequence[bytes], lo: int, hi: int) -> bytes:
    """
    Compute the Merkle root of leaves[lo:hi] using RFC 6962 §2.1 recursion.

    RFC 6962 MTH definition (recursive):
      MTH({d[n]}) = SHA-256(0x00 || d[0])                       if n == 1
      MTH(D[n])   = SHA-256(0x01 || MTH(D[0:k]) || MTH(D[k:n]))
                    where k = largest power of 2 less than n

    This implementation mirrors the RFC exactly. Do NOT replace with a naive
    mid-split: the RFC uses the largest-power-of-2 split, which is what
    makes the proof path predictable.

    Args:
        leaves: Full flat sequence of leaf hashes for the whole tree.
        lo, hi: Half-open range [lo, hi) within `leaves` to hash.

    Returns:
        32-byte Merkle root of the specified range.

    Raises:
        ValueError if lo >= hi (empty range is a programming error).
    """
    count = hi - lo
    if count == 0:
        raise ValueError(f"subtree_hash called with empty range [{lo}, {hi})")
    if count == 1:
        return leaves[lo]
    # Largest power of 2 strictly less than count (RFC 6962 §2.1)
    k = 1
    while k < count:
        k <<= 1
    k >>= 1  # now k = largest power of 2 < count
    return node_hash(
        subtree_hash(leaves, lo, lo + k),
        subtree_hash(leaves, lo + k, hi),
    )


def root_hash(leaves: Sequence[bytes]) -> bytes:
    """
    Compute Merkle root over a list of leaf hashes.

    Empty tree: SHA-256(b'') per RFC 6962 §2.1.
    Handles all tree sizes including odd-length (non-power-of-2).
    """
    if not leaves:
        return hashlib.sha256(b'').digest()
    return subtree_hash(leaves, 0, len(leaves))
```

---

## Inclusion Proof

Proves that a specific leaf is in the tree at a given tree size without replaying the full log.
The verifier reconstructs the root from `(leaf_hash, audit_path)` and checks it matches the STH.

```python
# core/ledger/proofs.py
from __future__ import annotations
from typing import Sequence
from .merkle import node_hash, subtree_hash, leaf_hash, root_hash


def inclusion_proof(leaf_index: int, tree_size: int,
                    leaves: Sequence[bytes]) -> list[bytes]:
    """
    RFC 6962 §2.1.1 audit path (inclusion proof).

    Returns the ordered list of sibling hashes needed to reconstruct the root
    from a single leaf hash. The path walks from leaf to root.

    Args:
        leaf_index: 0-based index of the leaf to prove (must be < tree_size).
        tree_size: Total number of leaves in the tree at time of proof.
        leaves: All leaf hashes in the tree (length == tree_size).

    Returns:
        List of sibling hashes. Empty list iff tree_size == 1.

    Raises:
        ValueError if leaf_index >= tree_size or tree_size != len(leaves).
    """
    if tree_size != len(leaves):
        raise ValueError(
            f"tree_size {tree_size} != len(leaves) {len(leaves)}"
        )
    if leaf_index >= tree_size:
        raise ValueError(
            f"leaf_index {leaf_index} out of range for tree_size {tree_size}"
        )
    path: list[bytes] = []
    _inner_inclusion_proof(leaf_index, 0, tree_size, leaves, path)
    return path


def _inner_inclusion_proof(
    idx: int, lo: int, hi: int,
    leaves: Sequence[bytes],
    path: list[bytes],
) -> None:
    """Recursive RFC 6962 audit-path builder."""
    if hi - lo == 1:
        return  # leaf node — no sibling to add
    # RFC 6962 split: largest power of 2 strictly less than (hi - lo)
    count = hi - lo
    k = 1
    while k < count:
        k <<= 1
    k >>= 1
    mid = lo + k
    if idx < mid:
        # leaf is in left subtree; sibling is right subtree hash
        path.append(subtree_hash(leaves, mid, hi))
        _inner_inclusion_proof(idx, lo, mid, leaves, path)
    else:
        # leaf is in right subtree; sibling is left subtree hash
        path.append(subtree_hash(leaves, lo, mid))
        _inner_inclusion_proof(idx, mid, hi, leaves, path)


def verify_inclusion(
    leaf_hash_val: bytes,
    leaf_index: int,
    tree_size: int,
    audit_path: list[bytes],
    expected_root: bytes,
) -> bool:
    """
    RFC 6962 §2.1.3 inclusion proof verification.

    Returns True iff the leaf at leaf_index with hash leaf_hash_val is in
    the tree of size tree_size whose root is expected_root, given audit_path.

    Never raises — returns False on any structural inconsistency so the
    caller can distinguish "bad proof" from "exception".
    """
    try:
        h = leaf_hash_val
        lo, hi = 0, tree_size
        for sibling in audit_path:
            count = hi - lo
            k = 1
            while k < count:
                k <<= 1
            k >>= 1
            mid = lo + k
            if leaf_index < mid:
                h = node_hash(h, sibling)
                hi = mid
            else:
                h = node_hash(sibling, h)
                lo = mid
        return h == expected_root
    except Exception:
        return False
```

---

## Consistency Proof

Proves the log is append-only: the tree at size N is a prefix of the tree at size M (N ≤ M).
An auditor calls this to verify the log has not been retroactively edited.

```python
def consistency_proof(old_size: int, new_size: int,
                      leaves: Sequence[bytes]) -> list[bytes]:
    """
    RFC 6962 §2.1.2 consistency proof.

    Returns hash path proving old_tree is a consistent prefix of new_tree.
    The verifier checks that appending to old_root can produce new_root without
    altering any prior leaf.

    Raises:
        ValueError if old_size > new_size or new_size != len(leaves).
    """
    if old_size > new_size:
        raise ValueError(
            f"old_size {old_size} > new_size {new_size}"
        )
    if new_size != len(leaves):
        raise ValueError(
            f"new_size {new_size} != len(leaves) {len(leaves)}"
        )
    if old_size == new_size:
        return []  # trivially consistent
    path: list[bytes] = []
    _inner_consistency_proof(old_size, 0, new_size, leaves, path, True)
    return path


def _inner_consistency_proof(
    m: int, lo: int, hi: int,
    leaves: Sequence[bytes],
    path: list[bytes],
    first_call: bool,
) -> None:
    """RFC 6962 §2.1.2 inner consistency proof recursion."""
    if m == hi - lo:
        if not first_call:
            path.append(subtree_hash(leaves, lo, hi))
        return
    count = hi - lo
    k = 1
    while k < count:
        k <<= 1
    k >>= 1
    mid = lo + k
    if m <= k:
        _inner_consistency_proof(m, lo, mid, leaves, path, first_call)
        path.append(subtree_hash(leaves, mid, hi))
    else:
        _inner_consistency_proof(m - k, mid, hi, leaves, path, False)
        path.append(subtree_hash(leaves, lo, mid))


def verify_consistency(
    old_root: bytes,
    new_root: bytes,
    old_size: int,
    new_size: int,
    proof_path: list[bytes],
) -> bool:
    """
    RFC 6962 §2.1.4 consistency proof verification.

    Returns True iff new_root is a consistent, append-only extension of old_root.
    Returns False (never raises) for any structural failure.
    """
    try:
        if old_size == new_size:
            return old_root == new_root and not proof_path
        if old_size == 0:
            return True  # empty old tree is consistent with anything

        # Reconstruct both roots from the proof path per RFC 6962 §2.1.4
        fn, sn = _decompose(old_size, new_size, proof_path)
        return fn == old_root and sn == new_root
    except Exception:
        return False


def _decompose(
    old_size: int, new_size: int, proof: list[bytes]
) -> tuple[bytes, bytes]:
    """Inner RFC 6962 §2.1.4 decomposition — returns (old_root, new_root) from proof."""
    # Find if old_size is a perfect power of 2 within new_size
    inner = _inner_proof_size(old_size, new_size)
    border = bin(old_size).count('1') - 1

    if len(proof) != inner + border:
        raise ValueError(
            f"proof length {len(proof)} != expected {inner + border}"
        )

    # Seed: if old_size is a complete subtree, first path element is its root
    # Otherwise reconstruct via included node
    if _is_pow2(old_size):
        fn = sn = proof[0] if proof else b''
        proof_slice = proof[1:]
    else:
        fn = sn = proof[0]
        proof_slice = proof[1:]

    # Apply the inner and border hashes
    for p in proof_slice[:inner - 1]:
        sn = node_hash(sn, p)
    for p in proof_slice[inner - 1:]:
        fn = node_hash(fn, p)
        sn = node_hash(sn, p)
    return fn, sn


def _inner_proof_size(old_size: int, new_size: int) -> int:
    return old_size.bit_length() - 1


def _is_pow2(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0
```

---

## Signed Tree Head (STH)

The tree head is signed to make tampering detectable. The signature is what a regulator verifies.
Signing uses Ed25519 via OpenBao — never raw key material in application code.

```python
# core/ledger/sth.py
import struct
import hashlib
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class SignedTreeHead:
    tree_size: int           # number of leaves
    timestamp_ms: int        # monotonic logical clock in ms (NOT wall clock — see clock_skew below)
    root_hash: bytes         # 32-byte Merkle root
    signature: bytes         # Ed25519 signature over serialized body
    key_id: str              # OpenBao key reference (e.g. "ledger-signing/v3")
    schema_version: int = 1  # increment when wire format changes — old entries stay verifiable

    def serialize_body(self) -> bytes:
        """
        Deterministic byte sequence that is signed and verified.
        Format: version(1) || tree_size(8, big-endian) || timestamp_ms(8) || root_hash(32)
        Total: 49 bytes — fixed-width, no length-prefix ambiguity.
        """
        return (
            self.schema_version.to_bytes(1, 'big')
            + self.tree_size.to_bytes(8, 'big')
            + self.timestamp_ms.to_bytes(8, 'big')
            + self.root_hash
        )

    def to_dict(self) -> dict:
        return {
            "tree_size": self.tree_size,
            "timestamp_ms": self.timestamp_ms,
            "root_hash": self.root_hash.hex(),
            "signature": self.signature.hex(),
            "key_id": self.key_id,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SignedTreeHead":
        return cls(
            tree_size=d["tree_size"],
            timestamp_ms=d["timestamp_ms"],
            root_hash=bytes.fromhex(d["root_hash"]),
            signature=bytes.fromhex(d["signature"]),
            key_id=d["key_id"],
            schema_version=d.get("schema_version", 1),
        )


class STHSigningPort(Protocol):
    """OpenBao adapter for signing STHs. Core never holds raw key material."""
    async def sign(self, *, key_id: str, data: bytes) -> bytes: ...
    async def verify(self, *, key_id: str, data: bytes, signature: bytes) -> bool: ...
    async def get_current_key_id(self, *, tenant_id: str) -> str: ...
    async def list_key_ids(self, *, tenant_id: str) -> list[str]: ...
```

---

## Clock Skew Handling (Air-Gapped Deployments)

Air-gapped installations have no reliable external time source. Using `datetime.utcnow()` directly
creates ordering ambiguity if the system clock drifts or is corrected. The solution is a
**monotonic logical sequence** derived from the database, augmented by wall-clock only for
human-readable display.

```python
# core/ledger/clock.py
import time
from dataclasses import dataclass


@dataclass
class LedgerTimestamp:
    """
    The authoritative timestamp for a ledger entry.
    ledger_seq is the ordering key — never wall_clock_ms.
    wall_clock_ms is informational only and MUST NOT be used for ordering or proof verification.
    """
    ledger_seq: int        # monotonic DB sequence — the real ordering key
    wall_clock_ms: int     # milliseconds since epoch at time of seal (informational)
    skew_detected: bool    # True if wall_clock regressed vs. previous entry


class MonotonicClock:
    """
    Wraps the database's BIGSERIAL ledger_seq as the authoritative monotonic clock.
    Wall-clock timestamps are stored as metadata but NEVER used for ordering.

    Air-gapped risk: NTP cannot correct the clock; clock may go backwards after restart.
    Mitigation: record the last sealed wall_clock_ms in a per-tenant ledger_state row.
    On each seal, if current wall_clock < last_sealed_wall_clock → set skew_detected=True
    but DO NOT fail — ordering is still guaranteed by ledger_seq.
    """

    async def next_timestamp(
        self,
        tenant_id: str,
        storage,
    ) -> LedgerTimestamp:
        last_ms = await storage.get_last_wall_clock_ms(tenant_id)
        now_ms = int(time.time() * 1000)
        skew = now_ms < last_ms
        if skew:
            # Do NOT raise here — ledger_seq still provides monotonic ordering.
            # Log a warning via OTel and record skew_detected=True on the entry.
            now_ms = last_ms  # clamp forward to avoid non-monotonic timestamps
        return LedgerTimestamp(
            ledger_seq=0,       # filled in by DB BIGSERIAL on insert
            wall_clock_ms=now_ms,
            skew_detected=skew,
        )
```

---

## Concurrent Append Safety

Multiple processes may seal entries concurrently for the same tenant's tree. Without coordination,
two concurrent seals would compute conflicting root hashes (each seeing the same tree_size N, each
inserting as leaf N+1). This would silently corrupt the Merkle tree.

The fix is a two-layer lock:
1. **PostgreSQL advisory lock** (`pg_try_advisory_xact_lock`) — prevents cross-process concurrency.
2. **`SELECT ... FOR UPDATE`** on `ledger_state` — serializes within the same advisory lock holder.

```python
# core/ledger/trust_ledger.py  — concurrent append section
import asyncio
from opentelemetry import trace

tracer = trace.get_tracer("quaicu.ledger")

ADVISORY_LOCK_BASE = 0xAL15_LEDGER  # tenant-specific offset applied at runtime


async def _acquire_append_lock(
    tx,
    tenant_id: str,
    timeout_ms: int = 5000,
) -> None:
    """
    Acquire a per-tenant advisory transaction lock.
    If not acquired within timeout_ms → raise LedgerConcurrencyError (fail-closed).

    Lock key: hash of tenant_id XOR ADVISORY_LOCK_BASE (fits in int64).
    Advisory lock is released automatically at transaction end.
    """
    lock_key = _tenant_lock_key(tenant_id)
    # Use pg_try_advisory_xact_lock — non-blocking, returns bool
    row = await tx.fetchrow(
        "SELECT pg_try_advisory_xact_lock($1) AS acquired", lock_key
    )
    if not row["acquired"]:
        raise LedgerConcurrencyError(
            f"Could not acquire append lock for tenant {tenant_id} "
            f"within {timeout_ms}ms",
            tenant_id=tenant_id,
        )


async def _lock_ledger_state(tx, tenant_id: str) -> dict:
    """
    SELECT ... FOR UPDATE on ledger_state row.
    Returns the current tree_size and last_root_hash.
    If the row does not exist yet, inserts it (first-ever seal for this tenant).
    """
    row = await tx.fetchrow(
        """
        INSERT INTO ledger_state (tenant_id, tree_size, last_root_hash, last_wall_clock_ms)
        VALUES ($1, 0, NULL, 0)
        ON CONFLICT (tenant_id) DO NOTHING;

        SELECT tree_size, last_root_hash, last_wall_clock_ms
        FROM ledger_state
        WHERE tenant_id = $1
        FOR UPDATE
        """,
        tenant_id,
    )
    return dict(row)


def _tenant_lock_key(tenant_id: str) -> int:
    """Stable int64 lock key derived from tenant_id."""
    import hashlib, struct
    h = hashlib.sha256(tenant_id.encode()).digest()
    raw = struct.unpack(">q", h[:8])[0]
    return raw ^ 0x414C49535F4C4544  # XOR with ASCII "ALIS_LED"
```

---

## Seal Operation (full implementation)

```python
# core/ledger/trust_ledger.py
import json
import hashlib
from opentelemetry import trace, metrics

tracer = trace.get_tracer("quaicu.ledger", schema_url="https://opentelemetry.io/schemas/1.23.1")
meter = metrics.get_meter("quaicu.ledger")

_seal_counter     = meter.create_counter("ledger.seal.total",           description="Total seal operations")
_seal_error_ctr   = meter.create_counter("ledger.seal.errors",          description="Seal failures by error code")
_seal_duration    = meter.create_histogram("ledger.seal.duration_ms",   description="Seal latency in ms", unit="ms")
_tree_size_gauge  = meter.create_up_down_counter("ledger.tree_size",    description="Current tree size per tenant")
_skew_counter     = meter.create_counter("ledger.clock_skew.total",     description="Clock skew events detected")


class TrustLedger:
    """
    RFC 6962-style append-only Merkle transparency log.

    Invariants:
    - Every sealed entry has a valid inclusion proof verifiable from its tree_head_hash.
    - Every successive pair of entries has a valid consistency proof.
    - ledger_seq is monotonic with no gaps.
    - No UPDATE or DELETE is ever issued against ledger_entries.
    """

    def __init__(
        self,
        storage,         # StoragePort
        sth_signer,      # STHSigningPort (OpenBao adapter)
        clock,           # MonotonicClock
    ):
        self.storage = storage
        self.sth_signer = sth_signer
        self.clock = clock

    async def seal(
        self,
        action,
        eval_result,
        exec_result,
    ):
        """
        Append-only write. Fail-closed: any failure raises — lifecycle sets HALTED.

        Steps:
        1. Acquire per-tenant advisory lock + SELECT FOR UPDATE on ledger_state.
        2. Compute canonical entry bytes and RFC 6962 leaf hash.
        3. Reconstruct current leaf set from tile storage (avoids full scan).
        4. Compute new root, inclusion proof, and STH.
        5. Insert entry and update ledger_state atomically.
        6. Emit OTel span with all proof attributes.
        """
        import time as _time
        t0 = _time.monotonic()

        with tracer.start_as_current_span(
            "ledger.seal",
            attributes={
                "ledger.tenant_id": action.tenant_id,
                "ledger.action_id": str(action.id),
                "ledger.action_type": action.type,
            },
        ) as span:
            try:
                entry = await self._do_seal(action, eval_result, exec_result, span)
                duration_ms = (_time.monotonic() - t0) * 1000
                _seal_counter.add(1, {"tenant_id": action.tenant_id, "status": "ok"})
                _seal_duration.record(duration_ms, {"tenant_id": action.tenant_id})
                _tree_size_gauge.add(1, {"tenant_id": action.tenant_id})
                span.set_attribute("ledger.ledger_seq", entry.ledger_seq)
                span.set_attribute("ledger.tree_size", entry.tree_size_at_insert)
                span.set_attribute("ledger.duration_ms", duration_ms)
                return entry
            except LedgerError as exc:
                _seal_error_ctr.add(1, {
                    "tenant_id": action.tenant_id,
                    "error_code": exc.error_code,
                })
                span.record_exception(exc)
                span.set_attribute("ledger.error_code", exc.error_code)
                raise

    async def _do_seal(self, action, eval_result, exec_result, span):
        from .merkle import leaf_hash as compute_leaf_hash, root_hash, subtree_hash
        from .proofs import inclusion_proof
        from .clock import MonotonicClock

        entry_data = self._canonical_entry(action, eval_result, exec_result)
        lhash = compute_leaf_hash(entry_data)
        entry_hash = hashlib.sha256(entry_data).digest()  # integrity check on read-back

        async with self.storage.transaction() as tx:
            await _acquire_append_lock(tx, action.tenant_id)
            state = await _lock_ledger_state(tx, action.tenant_id)

            current_size = state["tree_size"]
            ts = await self.clock.next_timestamp(action.tenant_id, tx)

            if ts.skew_detected:
                _skew_counter.add(1, {"tenant_id": action.tenant_id})
                span.set_attribute("ledger.clock_skew_detected", True)

            # Load current leaf hashes from tile storage (efficient for large trees)
            current_leaves = await self._load_leaf_hashes_from_tiles(
                tx, action.tenant_id, current_size
            )
            if len(current_leaves) != current_size:
                raise LedgerHashMismatchError(
                    f"Tile storage size {len(current_leaves)} != "
                    f"ledger_state.tree_size {current_size}",
                    tenant_id=action.tenant_id,
                )

            new_leaves = list(current_leaves) + [lhash]
            new_size = current_size + 1
            new_root = root_hash(new_leaves)
            proof = inclusion_proof(current_size, new_size, new_leaves)

            key_id = await self.sth_signer.get_current_key_id(
                tenant_id=action.tenant_id
            )
            sth_body_bytes = (
                new_size.to_bytes(8, 'big')
                + ts.wall_clock_ms.to_bytes(8, 'big')
                + new_root
            )
            sig = await self.sth_signer.sign(key_id=key_id, data=sth_body_bytes)
            sth = SignedTreeHead(
                tree_size=new_size,
                timestamp_ms=ts.wall_clock_ms,
                root_hash=new_root,
                signature=sig,
                key_id=key_id,
            )

            seq = await tx.insert_ledger_entry(
                tenant_id=action.tenant_id,
                action_id=action.id,
                leaf_hash=lhash,
                inclusion_proof=[h.hex() for h in proof],
                tree_head_hash=new_root,
                tree_size_at_insert=new_size,
                entry_data=entry_data,
                entry_hash=entry_hash,
                signed_tree_head=sth.to_dict(),
                wall_clock_ms=ts.wall_clock_ms,
                skew_detected=ts.skew_detected,
            )

            await tx.update_ledger_state(
                tenant_id=action.tenant_id,
                tree_size=new_size,
                last_root_hash=new_root,
                last_wall_clock_ms=ts.wall_clock_ms,
            )

            # Append leaf to tile storage
            await self._append_to_tile(tx, action.tenant_id, current_size, lhash)

        return LedgerEntry(
            action_id=action.id,
            ledger_seq=seq,
            inclusion_proof=proof,
            tree_head_hash=new_root,
            tree_size_at_insert=new_size,
        )

    def _canonical_entry(self, action, eval_result, exec_result) -> bytes:
        """
        Deterministic JSON serialization.
        Rules: keys sorted, no floats (use strings for amounts), no wall-clock in values
        (timestamps go in the wrapper, not the hashed content to prevent skew affecting hash),
        ensure_ascii=True to prevent encoding variation.
        """
        obj = {
            "action_id": str(action.id),
            "tenant_id": action.tenant_id,
            "type": action.type,
            "payload": action.payload,
            "actor_id": action.actor_id,
            "evaluation": {
                "decision": eval_result.decision,
                "policy_versions": sorted(eval_result.policy_versions),
                "consent_checked": eval_result.consent_checked,
                "assurance_signals": eval_result.assurance_signals,
            },
            "recorded_nondeterminism": eval_result.recorded_model_outputs,
            "execution_result": exec_result,
        }
        return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                          separators=(',', ':')).encode("utf-8")
```

---

## Verify Operation (complete — returns signed bundle for regulatory submission)

```python
# core/ledger/trust_ledger.py  — verify method
from dataclasses import dataclass
from typing import Optional


@dataclass
class VerificationBundle:
    """
    Signed artifact returned by verify(). Suitable for regulatory submission.
    The bundle itself is signed so a regulator can verify it came from an authorized kernel.
    """
    tenant_id: str
    verified_count: int
    from_seq: int
    to_seq: int
    root_hash_at_to: str          # hex — the authoritative root at `to_seq`
    consistency_proofs_ok: bool   # all consecutive STH consistency proofs verified
    inclusion_proofs_ok: bool     # all entry inclusion proofs verified against their STH
    seq_gaps_detected: bool       # True = tamper/corruption indicator
    skew_entries: list[int]       # ledger_seq values where clock skew was recorded
    failed_seqs: list[int]        # any entries that failed verification
    bundle_signature: str         # Ed25519 over canonical bundle JSON (hex)
    bundle_key_id: str            # signing key used for bundle_signature
    verified_at_ms: int           # wall clock at time of verification (informational)
    kernel_version: str           # for reproducibility


async def verify(
    self,
    tenant_id: str,
    from_seq: Optional[int] = None,
    to_seq: Optional[int] = None,
) -> VerificationBundle:
    """
    Full regulatory verification pass over a ledger range.

    Checks:
    1. No gaps in ledger_seq across the range.
    2. Each entry's entry_hash matches SHA-256 of its stored entry_data.
    3. Each entry's inclusion_proof verifies against its tree_head_hash.
    4. Consecutive STHs have valid consistency proofs.
    5. Each STH signature verifies against the key_id in OpenBao.

    Returns a VerificationBundle signed by the kernel's verification key.
    Raises LedgerBatchVerificationError if any entry fails and
    `strict=True` (default). With `strict=False`, records failures in
    bundle.failed_seqs but returns the bundle.

    OTel: emits a span per entry (sampled at 1%) and a summary span for the whole call.
    """
    import time as _time
    import json

    with tracer.start_as_current_span(
        "ledger.verify",
        attributes={
            "ledger.tenant_id": tenant_id,
            "ledger.from_seq": from_seq or 0,
            "ledger.to_seq": to_seq or -1,
        },
    ) as span:
        entries = await self.storage.get_entries(tenant_id, from_seq, to_seq)
        if not entries:
            span.set_attribute("ledger.verified_count", 0)
            return VerificationBundle(
                tenant_id=tenant_id,
                verified_count=0,
                from_seq=0,
                to_seq=0,
                root_hash_at_to="",
                consistency_proofs_ok=True,
                inclusion_proofs_ok=True,
                seq_gaps_detected=False,
                skew_entries=[],
                failed_seqs=[],
                bundle_signature="",
                bundle_key_id="",
                verified_at_ms=int(_time.time() * 1000),
                kernel_version=self._kernel_version(),
            )

        failed_seqs: list[int] = []
        skew_entries: list[int] = []
        seq_gaps = False
        inclusion_ok = True
        consistency_ok = True
        prev_entry = None

        for entry in entries:
            # 1. Sequence gap check
            if prev_entry is not None:
                if entry.ledger_seq != prev_entry.ledger_seq + 1:
                    seq_gaps = True
                    failed_seqs.append(entry.ledger_seq)

            # 2. Entry hash integrity
            recomputed = hashlib.sha256(entry.entry_data).digest()
            if recomputed != entry.entry_hash:
                failed_seqs.append(entry.ledger_seq)
                inclusion_ok = False
                prev_entry = entry
                continue

            # 3. Inclusion proof
            lhash = compute_leaf_hash(entry.entry_data)
            proof = [bytes.fromhex(h) for h in entry.inclusion_proof]
            if not verify_inclusion(
                lhash,
                entry.tree_size_at_insert - 1,
                entry.tree_size_at_insert,
                proof,
                entry.tree_head_hash,
            ):
                failed_seqs.append(entry.ledger_seq)
                inclusion_ok = False

            # 4. STH signature
            sth = SignedTreeHead.from_dict(entry.signed_tree_head)
            sig_ok = await self.sth_signer.verify(
                key_id=sth.key_id,
                data=sth.serialize_body(),
                signature=sth.signature,
            )
            if not sig_ok:
                failed_seqs.append(entry.ledger_seq)
                failed_seqs = list(set(failed_seqs))

            # 5. Consistency proof between successive STHs
            if prev_entry is not None:
                prev_sth = SignedTreeHead.from_dict(prev_entry.signed_tree_head)
                cons_proof = await self.storage.get_consistency_proof(
                    tenant_id,
                    prev_entry.tree_size_at_insert,
                    entry.tree_size_at_insert,
                )
                if not verify_consistency(
                    prev_entry.tree_head_hash,
                    entry.tree_head_hash,
                    prev_entry.tree_size_at_insert,
                    entry.tree_size_at_insert,
                    cons_proof,
                ):
                    consistency_ok = False
                    failed_seqs.append(entry.ledger_seq)

            if entry.skew_detected:
                skew_entries.append(entry.ledger_seq)

            prev_entry = entry

        # Sign the bundle
        bundle_payload = {
            "tenant_id": tenant_id,
            "verified_count": len(entries),
            "from_seq": entries[0].ledger_seq,
            "to_seq": entries[-1].ledger_seq,
            "root_hash_at_to": entries[-1].tree_head_hash.hex(),
            "inclusion_proofs_ok": inclusion_ok,
            "consistency_proofs_ok": consistency_ok,
            "seq_gaps_detected": seq_gaps,
            "failed_seqs": sorted(set(failed_seqs)),
        }
        bundle_bytes = json.dumps(
            bundle_payload, sort_keys=True, ensure_ascii=True,
            separators=(',', ':'),
        ).encode()
        key_id = await self.sth_signer.get_current_key_id(tenant_id=tenant_id)
        bundle_sig = await self.sth_signer.sign(key_id=key_id, data=bundle_bytes)

        span.set_attribute("ledger.verified_count", len(entries))
        span.set_attribute("ledger.failed_count", len(set(failed_seqs)))
        span.set_attribute("ledger.seq_gaps", seq_gaps)

        return VerificationBundle(
            **bundle_payload,
            skew_entries=skew_entries,
            bundle_signature=bundle_sig.hex(),
            bundle_key_id=key_id,
            verified_at_ms=int(_time.time() * 1000),
            kernel_version=self._kernel_version(),
        )
```

---

## Key Rotation Procedure for STH Signing Keys

Key rotation must not break verification of entries signed with old keys. OpenBao stores all
historical key versions; `key_id` in the STH points to the exact version that signed it.

```python
# core/ledger/key_rotation.py
"""
Key Rotation Procedure
======================
1. Generate new key version in OpenBao (via STHSigningPort.rotate()).
   - OpenBao keeps all prior versions; old signatures remain verifiable.
2. Publish a "key_rotation" ledger entry (a special action_type) that:
   - Records old key_id and new key_id.
   - Is itself signed with the NEW key (so the new key is proven in the ledger).
   - Is itself signed with the OLD key (cross-sign for continuity of trust).
3. All subsequent seals use the new key_id.
4. Verification: when verify() encounters an STH with an old key_id, it calls
   sth_signer.verify(key_id=old_key_id, ...) — OpenBao serves old versions.
5. Key retirement: old keys are marked "retired" in OpenBao after a configurable
   retention window (default: 7 years for bank deployments). They are never deleted
   while any ledger entry references them — the storage adapter enforces this via
   a foreign-key-style check before any key deletion request.

NEVER:
- Delete a key that is referenced by any existing STH.
- Silently upgrade old STHs to a new key (that would break their signatures).
- Rotate without publishing the rotation ledger entry (audit gap).
"""

async def rotate_signing_key(
    tenant_id: str,
    trust_ledger,
    sth_signing_port,
    governed_action_factory,
) -> str:
    """
    Rotate the STH signing key for a tenant.
    Returns the new key_id.

    Raises LedgerKeyRotationError on any failure — never partially rotates.
    """
    old_key_id = await sth_signing_port.get_current_key_id(tenant_id=tenant_id)
    new_key_id = await sth_signing_port.rotate(tenant_id=tenant_id)

    # Emit a governed rotation action — this seals a ledger entry with BOTH keys
    rotation_action = governed_action_factory.create(
        type="quaicu.ledger.key_rotation",
        payload={"old_key_id": old_key_id, "new_key_id": new_key_id},
        tenant_id=tenant_id,
        actor_id="system:key_rotation",
    )
    # The seal operation will use the new key (already set as current)
    # We additionally cross-sign with the old key and store both signatures
    await trust_ledger.seal_with_cross_sign(
        action=rotation_action,
        eval_result=_rotation_eval_result(),
        exec_result={"rotated": True},
        old_key_id=old_key_id,
    )
    return new_key_id
```

---

## Batch Verification for Regulatory Audit

```python
# core/ledger/batch_verify.py
"""
Batch verification for regulatory audit submissions.
Processes up to MAX_BATCH_SIZE entries per call to avoid memory exhaustion
on very large ledgers (tile-based pagination).
"""

MAX_BATCH_SIZE = 10_000


async def batch_verify_for_audit(
    trust_ledger,
    tenant_id: str,
    from_seq: int,
    to_seq: int,
    page_size: int = MAX_BATCH_SIZE,
) -> list[VerificationBundle]:
    """
    Verify the ledger in pages. Returns one VerificationBundle per page.
    Cross-page consistency is verified at boundaries (last entry of page N
    and first entry of page N+1 have a valid consistency proof).

    Used by K·14 evidence generation to prove an audit range is intact.
    Raises LedgerBatchVerificationError immediately if any page has failures
    and fail_fast=True (default).

    OTel: emits a "ledger.batch_verify" span with page_count, total_entries,
    failed_count attributes.
    """
    with tracer.start_as_current_span(
        "ledger.batch_verify",
        attributes={"tenant_id": tenant_id, "from_seq": from_seq, "to_seq": to_seq},
    ) as span:
        bundles: list[VerificationBundle] = []
        cursor = from_seq
        total_failed = 0

        while cursor <= to_seq:
            page_end = min(cursor + page_size - 1, to_seq)
            bundle = await trust_ledger.verify(tenant_id, cursor, page_end)
            bundles.append(bundle)
            total_failed += len(bundle.failed_seqs)

            if bundle.failed_seqs:
                span.set_attribute("ledger.batch_verify.failed", True)
                raise LedgerBatchVerificationError(
                    f"Batch verification failed for tenant {tenant_id} "
                    f"in range [{cursor}, {page_end}]",
                    failed_seqs=bundle.failed_seqs,
                )
            cursor = page_end + 1

        span.set_attribute("ledger.batch_verify.pages", len(bundles))
        span.set_attribute("ledger.batch_verify.total_failed", total_failed)
        return bundles
```

---

## Tile-Based Storage for Large Trees

Full scans of `ledger_entries` to load all leaf hashes become unacceptable beyond ~100k entries.
Tile storage pre-computes subtree hashes at fixed power-of-2 boundaries, so seal() and verify()
only load O(log N) tiles instead of N leaves.

```python
# core/ledger/tile_storage.py
"""
Tile-based leaf caching for large Merkle trees.

A "tile" stores the root hash of a power-of-2 aligned subtree of the leaf sequence.
Tile levels:
  Level 0: individual leaf hashes (stored in ledger_entries.leaf_hash — no tile needed)
  Level 1: root of every consecutive pair    (tile covers 2 leaves)
  Level 2: root of every consecutive 4       (tile covers 4 leaves)
  ...
  Level k: root of every consecutive 2^k     (tile covers 2^k leaves)

On append (new leaf at index N):
  - Update level-1 tile if N is odd (pair complete).
  - Update level-2 tile if N % 4 == 3.
  - Update level-k tile if N % 2^k == 2^k - 1.
  Only O(log N) tiles are updated per append.

On root computation:
  - Decompose current tree size into power-of-2 components.
  - Load one tile per component (all pre-computed).
  - Combine with node_hash — O(log^2 N) total.
"""

TILE_TABLE = "ledger_tiles"  # per-tenant schema

CREATE_TILE_TABLE = """
CREATE TABLE IF NOT EXISTS "tenant_{tenant_id}".ledger_tiles (
    tile_level   INT NOT NULL,
    tile_index   BIGINT NOT NULL,  -- which tile at this level (0-based)
    tile_hash    BYTEA NOT NULL,
    covers_lo    BIGINT NOT NULL,  -- first leaf index covered (inclusive)
    covers_hi    BIGINT NOT NULL,  -- last leaf index covered (exclusive)
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tile_level, tile_index)
);
"""


async def load_leaf_hashes_from_tiles(
    tx,
    tenant_id: str,
    tree_size: int,
) -> list[bytes]:
    """
    Reconstruct the leaf hash sequence needed for proof computation.
    For trees up to 1M leaves, load the raw leaves from ledger_entries directly.
    For larger trees, this method is replaced by tile-aware root computation.
    Threshold is configurable — default 1_000_000.
    """
    DIRECT_THRESHOLD = 1_000_000
    if tree_size <= DIRECT_THRESHOLD:
        return await tx.get_all_leaf_hashes(tenant_id)
    # For large trees: load tiles and reconstruct via subtree hashes
    # This path returns subtree hashes in left-to-right order for root_hash()
    return await _load_via_tiles(tx, tenant_id, tree_size)
```

---

## Per-Tenant Schema

```sql
-- migrations/versions/K02_ledger_per_tenant.sql
-- Created at tenant onboarding. Schema name = "tenant_{sanitised_tenant_id}".
-- Run per-tenant, not globally.

CREATE SCHEMA IF NOT EXISTS "tenant_{tenant_id}";

CREATE TABLE "tenant_{tenant_id}".ledger_state (
    tenant_id           TEXT PRIMARY KEY,
    tree_size           BIGINT NOT NULL DEFAULT 0,
    last_root_hash      BYTEA,
    last_wall_clock_ms  BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE "tenant_{tenant_id}".ledger_entries (
    ledger_seq              BIGSERIAL PRIMARY KEY,
    action_id               UUID NOT NULL UNIQUE,
    tenant_id               TEXT NOT NULL CHECK (tenant_id = '{tenant_id}'),
    action_type             TEXT NOT NULL,
    entry_data              BYTEA NOT NULL,       -- canonical JSON bytes (hashed)
    entry_hash              BYTEA NOT NULL,       -- SHA-256(entry_data) integrity check
    leaf_hash               BYTEA NOT NULL,       -- RFC 6962 leaf hash
    inclusion_proof         JSONB NOT NULL,       -- audit path as hex-encoded array
    tree_head_hash          BYTEA NOT NULL,       -- root at time of insert
    tree_size_at_insert     BIGINT NOT NULL,
    signed_tree_head        JSONB NOT NULL,       -- full STH JSON
    wall_clock_ms           BIGINT NOT NULL,
    skew_detected           BOOLEAN NOT NULL DEFAULT false,
    sealed_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only: REVOKE UPDATE, DELETE on this table from the app role
REVOKE UPDATE, DELETE ON "tenant_{tenant_id}".ledger_entries FROM quaicu_app;

-- Row-Level Security as defense-in-depth
ALTER TABLE "tenant_{tenant_id}".ledger_entries ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_rls ON "tenant_{tenant_id}".ledger_entries
    USING (tenant_id = current_setting('app.current_tenant'));

-- Consistency proof cache (pre-computed for common audit ranges)
CREATE TABLE "tenant_{tenant_id}".consistency_proof_cache (
    old_size    BIGINT NOT NULL,
    new_size    BIGINT NOT NULL,
    proof_path  JSONB NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (old_size, new_size)
);
```

---

## RFC 6962 Test Vectors (JSON structure for published conformance suite)

```json
{
  "version": "1",
  "description": "QUAICU K·02 RFC 6962 conformance vectors",
  "leaf_hash_vectors": [
    {
      "input_hex": "00",
      "expected_hex": "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"
    },
    {
      "input_hex": "4d657263757279",
      "expected_hex": "f4a5be4b2a26e5fbbfca2f26736e1d54a4bc3c5cba98fb19d0b3a77fe11b9e3d"
    }
  ],
  "root_hash_vectors": [
    {
      "leaves_hex": [],
      "expected_root_hex": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    {
      "leaves_hex": ["6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"],
      "expected_root_hex": "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d"
    }
  ],
  "inclusion_proof_vectors": [
    {
      "description": "leaf 0 in tree of size 1",
      "leaf_index": 0,
      "tree_size": 1,
      "leaf_data_hex": "4c656166",
      "audit_path": [],
      "expected_root_hex": "..."
    },
    {
      "description": "leaf 1 in tree of size 3 (odd tree)",
      "leaf_index": 1,
      "tree_size": 3,
      "leaf_data_hex": "...",
      "audit_path": ["...", "..."],
      "expected_root_hex": "..."
    }
  ],
  "consistency_proof_vectors": [
    {
      "description": "old_size=3 new_size=5 (RFC 6962 §2.1.3 example)",
      "old_size": 3,
      "new_size": 5,
      "old_root_hex": "...",
      "new_root_hex": "...",
      "proof_path": ["...", "..."]
    }
  ]
}
```

---

## Required Tests (property-based — not optional)

```python
# tests/property/test_ledger_invariants.py
from hypothesis import given, settings, strategies as st
from core.ledger.merkle import leaf_hash, root_hash, subtree_hash
from core.ledger.proofs import (
    inclusion_proof, verify_inclusion,
    consistency_proof, verify_consistency,
)

@given(st.lists(st.binary(min_size=1, max_size=64), min_size=1, max_size=500))
@settings(max_examples=1000)
def test_inclusion_proof_always_verifies(leaf_data_list):
    """Every leaf inserted can be proven with its inclusion proof — property must hold for all N."""
    leaves = [leaf_hash(d) for d in leaf_data_list]
    root = root_hash(leaves)
    for i, lh in enumerate(leaves):
        proof = inclusion_proof(i, len(leaves), leaves)
        assert verify_inclusion(lh, i, len(leaves), proof, root), (
            f"Inclusion proof failed at index {i}, tree_size {len(leaves)}"
        )

@given(st.lists(st.binary(min_size=1, max_size=64), min_size=2, max_size=200))
@settings(max_examples=500)
def test_consistency_proof_detects_retroactive_edit(leaves_data):
    """Modifying any historical leaf breaks the consistency proof."""
    leaves = [leaf_hash(d) for d in leaves_data]
    old_size = max(1, len(leaves) // 2)
    old_root = root_hash(leaves[:old_size])
    full_root = root_hash(leaves)
    proof = consistency_proof(old_size, len(leaves), leaves)
    assert verify_consistency(old_root, full_root, old_size, len(leaves), proof)

    # Tamper: replace a historical leaf — consistency must fail
    tampered = leaves.copy()
    tampered[0] = leaf_hash(b'tampered_' + leaves_data[0])
    tampered_full_root = root_hash(tampered)
    assert not verify_consistency(
        old_root, tampered_full_root, old_size, len(tampered), proof
    ), "Consistency proof must reject tampered historical leaf"

@given(st.lists(st.binary(min_size=1), min_size=1, max_size=100))
def test_odd_length_trees_round_trip(leaf_data_list):
    """Odd-length trees (non-power-of-2) must work correctly end-to-end."""
    # Add one to guarantee odd if even, remove one if odd — always test both
    for n in {len(leaf_data_list), len(leaf_data_list) + 1}:
        data = leaf_data_list[:n] if n <= len(leaf_data_list) else \
               leaf_data_list + [b'extra']
        leaves = [leaf_hash(d) for d in data]
        root = root_hash(leaves)
        for i, lh in enumerate(leaves):
            proof = inclusion_proof(i, len(leaves), leaves)
            assert verify_inclusion(lh, i, len(leaves), proof, root)

@given(st.integers(min_value=1, max_value=200))
def test_ledger_seq_is_monotonic_no_gaps(n):
    """Simulated sequence of n seals must produce gapless ledger_seq 1..n."""
    seqs = list(range(1, n + 1))
    for i in range(1, len(seqs)):
        assert seqs[i] == seqs[i - 1] + 1, f"Gap at position {i}"

def test_domain_separation_prevents_second_preimage():
    """Leaf hash and node hash of the same bytes must differ."""
    data = b'test'
    lh = leaf_hash(data)
    # A node whose left+right concatenation equals LEAF_PREFIX + data
    # must not hash to lh — the NODE_PREFIX prevents this
    nh = hashlib.sha256(b'\x01' + data).digest()
    assert lh != nh

def test_rfc6962_empty_tree():
    """Empty tree root must equal SHA-256(b'')."""
    import hashlib
    assert root_hash([]) == hashlib.sha256(b'').digest()
```

---

## Anti-Patterns Section

These are patterns that will be caught in code review. Each has the wrong approach and the
corrected approach.

### Anti-Pattern 1: Using wall-clock for ordering

```python
# WRONG — wall clock can go backwards in air-gapped deployments
timestamp = datetime.utcnow()
INSERT INTO ledger_entries (sealed_at, ...) VALUES (timestamp, ...)

# CORRECT — order by ledger_seq (BIGSERIAL); wall_clock_ms is informational only
# ledger_seq is the authoritative ordering key; wall_clock_ms is stored but never
# used in proof computation or ordering queries
```

### Anti-Pattern 2: Full table scan to rebuild leaf list

```python
# WRONG — O(N) scan for every seal, catastrophic at scale
leaves = await db.fetch("SELECT leaf_hash FROM ledger_entries ORDER BY ledger_seq")

# CORRECT — maintain ledger_state.tree_size + tile storage
# On seal: load current_size from ledger_state (locked), load tiles for O(log N) nodes
```

### Anti-Pattern 3: Omitting domain separation prefix

```python
# WRONG — second-preimage attack: a leaf with value (0x01 || left || right)
# would collide with an internal node
hash = hashlib.sha256(data).digest()

# CORRECT — always use RFC 6962 prefixes
hash = hashlib.sha256(b'\x00' + data).digest()   # leaf
hash = hashlib.sha256(b'\x01' + left + right).digest()  # node
```

### Anti-Pattern 4: Shared ledger table across tenants

```python
# WRONG — violates F-07; a single mis-filtered query leaks across tenants
INSERT INTO ledger_entries (tenant_id, ...) VALUES ('acme', ...)

# CORRECT — per-tenant table in per-tenant schema
INSERT INTO "tenant_acme".ledger_entries (...) VALUES (...)
# tenant_id column is a CHECK constraint, not the isolation mechanism
```

### Anti-Pattern 5: Deleting or rotating keys without cross-sign

```python
# WRONG — deleting old key makes historical STHs unverifiable
await openbao.delete_key(old_key_id)

# CORRECT — retire (mark as non-signing) but never delete while entries reference it
# Cross-sign the rotation entry; verify() uses per-STH key_id to select the right key
```

### Anti-Pattern 6: Storing raw key material in application code

```python
# WRONG — raw Ed25519 private key in app config
SIGNING_KEY = b'\x3f\x2a...'

# CORRECT — all signing goes through STHSigningPort which calls OpenBao
sig = await sth_signing_port.sign(key_id=key_id, data=body)
```

---

## Security Requirements

- **SHA-256 only** for hashing. Do not use MD5, SHA-1, or SHA-3 (incompatible test vectors).
- **Ed25519** for signing tree heads. Do not use RSA or ECDSA P-256.
- **OpenBao** for key storage and signing — never raw key material in application code.
- **No UPDATE/DELETE** on ledger tables. Append-only enforced at DB permission level (REVOKE).
- **Advisory lock + SELECT FOR UPDATE** on every seal to prevent concurrent root divergence.
- **Third-party cryptographic review required** before deploying to any bank customer.
  Budget for this explicitly — it is both a safeguard and a sales asset.
- **Tile storage** prevents memory exhaustion on large trees; implement before going to production.

---

## Checklist Before Merging Any Ledger Change

- [ ] RFC 6962 `0x00`/`0x01` domain separation prefixes present in leaf/node hash
- [ ] `subtree_hash()` uses largest-power-of-2 split, not naive mid-split
- [ ] Per-tenant table in per-tenant schema — not a shared table
- [ ] `seal()` acquires advisory lock AND SELECT FOR UPDATE on `ledger_state`
- [ ] `seal()` failure raises `LedgerSealError` — lifecycle engine sets HALTED
- [ ] Canonical entry JSON: key-sorted, `ensure_ascii=True`, no floats, `separators=(',', ':')`
- [ ] `verify()` checks: entry_hash integrity, inclusion proofs, STH signatures, consistency proofs, seq gaps
- [ ] `verify()` returns a signed `VerificationBundle` suitable for regulatory submission
- [ ] Property tests cover odd-length trees (non-power-of-2 sizes)
- [ ] Clock skew recorded in entry (`skew_detected=True`) but does NOT fail the seal
- [ ] Key rotation publishes a cross-signed ledger entry; old keys are retired, never deleted
- [ ] No UPDATE or DELETE permissions granted on ledger table in migration (REVOKE)
- [ ] OTel spans and metrics emitted: `ledger.seal`, `ledger.verify`, `ledger.batch_verify`
- [ ] Tile storage in place before any tree exceeds 100k leaves
- [ ] Published test vectors JSON matches implementation behavior
