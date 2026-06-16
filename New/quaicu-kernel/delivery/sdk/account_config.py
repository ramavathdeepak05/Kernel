"""Config-driven account/signup wiring (ADR-0010).

Builds the `AccountEngine` that powers self-serve signup + API-key auth, enabled by an ``[account]``
section. Off by default, so existing IdP-token / single-kernel deployments are unaffected; when on,
`POST /v1/signup` provisions a STARTER tenant + key and protected ``/v1/*`` routes require that key.

Signup provisions a STARTER plan into the **shared** `EntitlementStore` (the same one the rate-limit /
entitlements edge reads), so an entitlement source must be present when accounts are enabled.

Config shape::

    [account]
    enabled = true                # turn on self-serve signup + API-key auth
    # require_api_key defaults to `enabled`; set false to allow signup while leaving routes open.
    # The API-key pepper comes from the QUAICU_API_KEY_PEPPER env var (see core/account/engine.py).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def account_enabled(config: Mapping[str, Any]) -> bool:
    return bool(config.get("account", {}).get("enabled"))


def require_api_key(config: Mapping[str, Any]) -> bool:
    """Whether protected routes require an API key. Defaults to the account-enabled flag."""
    acct = config.get("account", {})
    return bool(acct.get("require_api_key", acct.get("enabled", False)))


def build_account_engine(config: Mapping[str, Any], entitlement_store: Any | None) -> Any | None:
    """Construct the `AccountEngine` when ``[account].enabled``; None otherwise.

    Requires an entitlement store (signup writes the new tenant's STARTER plan into it). The durable
    account repository (Postgres) layers in here later; today the store is in-process.
    """
    if not account_enabled(config):
        return None
    if entitlement_store is None:
        raise ValueError(
            "[account].enabled requires an entitlement source — add [entitlements] (or [billing]) so "
            "signup can provision the new tenant's STARTER plan."
        )
    from core.account import AccountEngine, AccountStore

    return AccountEngine(AccountStore(), entitlement_store)
