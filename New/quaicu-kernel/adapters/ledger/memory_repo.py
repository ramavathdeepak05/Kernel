"""InMemoryLedgerRepository — dict-backed durable-ledger backend for dev/tests.

Implements the `LedgerRepository` Protocol structurally. It is "durable" only for the lifetime of
the process, but it exercises the full write-through + hydrate path (the `TrustLedger` persists
through it on seal and rebuilds from it on hydrate), so the durability contract can be unit-tested
without a database. Production uses `PostgresLedgerRepository`.
"""

from __future__ import annotations

import threading

from core.ledger.signer import SignedTreeHead
from core.types import LedgerEntry, TenantId


class InMemoryLedgerRepository:
    """Thread-safe in-memory `LedgerRepository`. Entries keyed by (tenant, ledger_seq)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, int], LedgerEntry] = {}
        self._sths: dict[str, SignedTreeHead] = {}

    async def append_entry(self, entry: LedgerEntry) -> None:
        key = (str(entry.tenant), entry.ledger_seq)
        with self._lock:
            # Idempotent on (tenant, ledger_seq): re-appending the same sealed entry is a no-op.
            self._entries.setdefault(key, entry)

    async def load_entries(self) -> list[LedgerEntry]:
        with self._lock:
            entries = list(self._entries.values())
        return sorted(entries, key=lambda e: (str(e.tenant), e.ledger_seq))

    async def save_sth(self, tenant: TenantId, sth: SignedTreeHead) -> None:
        with self._lock:
            self._sths[str(tenant)] = sth

    async def load_sths(self) -> dict[str, SignedTreeHead]:
        with self._lock:
            return dict(self._sths)

    async def close(self) -> None:
        return None
