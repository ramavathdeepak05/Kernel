"""HSM-backed crypto-shred keyrings + durable wrapped-DEK stores (W6-4)."""

from __future__ import annotations

from adapters.erasure.gcp_kms import (
    ErasureDependencyError,
    GcpKmsShredKeyring,
    InMemoryWrappedDekStore,
    WrappedDekStore,
)
from adapters.erasure.postgres import PostgresWrappedDekStore

__all__ = [
    "ErasureDependencyError",
    "GcpKmsShredKeyring",
    "InMemoryWrappedDekStore",
    "PostgresWrappedDekStore",
    "WrappedDekStore",
]
