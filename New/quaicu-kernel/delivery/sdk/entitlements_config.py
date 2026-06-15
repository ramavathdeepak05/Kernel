"""Config-driven entitlement-store wiring (ADR-0009 / WS-C).

Builds the `EntitlementStore` that `create_app` consumes, wiring a durable
`PostgresEntitlementRepository` when the config supplies a DSN — so customer plans (and
billing-driven tier flips) survive a restart. Without a DSN it returns a plain in-memory store,
preserving the behavior of an ephemeral / non-billing deploy.

The DSN is read from a dedicated ``[entitlements]`` section, falling back to the shared
``[storage]`` DSN (the plans live in the same Postgres as the other durable tables). It may use a
``${ENV_VAR}`` reference, resolved from the environment at load so credentials stay out of the file.

Config shape::

    [entitlements]
    dsn = "${ENTITLEMENTS_DSN}"     # optional; falls back to [storage].dsn

The caller is responsible for calling ``await store.hydrate()`` at startup (create_app's lifespan
does this) to repopulate the cache from the durable repository.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from core.entitlements import EntitlementStore


def _resolve_dsn(config: Mapping[str, Any]) -> str | None:
    """Return the entitlements DSN: ``[entitlements].dsn`` → ``[storage].dsn`` → None."""
    entitlements = config.get("entitlements")
    if isinstance(entitlements, Mapping) and entitlements.get("dsn"):
        dsn = str(entitlements["dsn"])
    else:
        storage = config.get("storage")
        dsn = str(storage["dsn"]) if isinstance(storage, Mapping) and storage.get("dsn") else ""
    dsn = os.path.expandvars(dsn).strip()
    return dsn or None


def build_entitlement_store(config: Mapping[str, Any]) -> EntitlementStore:
    """Construct an `EntitlementStore`, durable when a DSN is configured, else in-memory.

    Only wires the Postgres repository when an ``[entitlements]`` section is explicitly present (so
    a deploy that merely configures ``[storage]`` for the kernel's other tables does not implicitly
    take on entitlement persistence). The fallback to ``[storage].dsn`` applies *within* an
    ``[entitlements]`` section that omits its own ``dsn``.
    """
    if "entitlements" not in config:
        return EntitlementStore()
    dsn = _resolve_dsn(config)
    if not dsn:
        return EntitlementStore()
    # Imported lazily so the in-memory path never imports asyncpg.
    from adapters.entitlements import PostgresEntitlementRepository

    return EntitlementStore(repository=PostgresEntitlementRepository(dsn))
