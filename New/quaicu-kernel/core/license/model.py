"""Enterprise license — data model (ADR-0009).

A `License` authorises a dedicated ENTERPRISE deployment to boot. It is an immutable, signed claim
set: who the licensee is, which tenant(s) it covers, and when it expires. The token is verified
**offline** (no network) against a public key the operator supplies, so air-gapped installs work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class License:
    """An offline-verifiable Enterprise license claim set.

    ``tenants`` lists the tenant ids this license covers; ``("*",)`` authorises any tenant on the
    deployment. ``tier`` is sealed in for completeness and must read ``"ENTERPRISE"``.
    """

    license_id: str
    licensee: str
    tenants: tuple[str, ...]
    tier: str
    issued_at: datetime
    expires_at: datetime
    features: tuple[str, ...] = field(default_factory=tuple)

    def covers_tenant(self, tenant: str) -> bool:
        return "*" in self.tenants or tenant in self.tenants

    def is_expired(self, *, now: datetime) -> bool:
        return now >= self.expires_at
