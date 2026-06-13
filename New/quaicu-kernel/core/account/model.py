"""Account & API-key — data model (ADR-0010).

An `Account` is the customer org that owns a tenant. `ApiKey` is a credential for the kernel's own
management API (the self-serve path that doesn't bring an external IdP token). Secrets are never
stored: only a SHA-256 hash of the secret is kept, alongside a public ``key_id`` prefix used to look
the key up. Immutable, like every other kernel domain model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from core.types import TenantId


class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class Account:
    """A customer organisation, 1:1 with a tenant on signup."""

    account_id: str
    tenant_id: TenantId
    email: str
    name: str
    status: AccountStatus
    created_at: datetime


@dataclass(frozen=True)
class ApiKey:
    """A hashed API-key record. The plaintext secret is shown once at issuance and never stored.

    A presented key is ``qk_<key_id>_<secret>``; ``key_id`` locates this record, then ``secret`` is
    hashed and compared to ``hashed_secret`` in constant time.
    """

    key_id: str
    tenant_id: TenantId
    hashed_secret: str          # hex SHA-256 of the secret half
    created_at: datetime
    revoked: bool = False
