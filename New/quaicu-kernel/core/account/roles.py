"""Enterprise RBAC roles — named bundles of scopes for tenant members (W6-1).

`scopes.py` defines the fine-grained `resource:verb` permissions a credential carries. Roles are the
coarse, human-facing layer an admin assigns to a **member** (and that an IdP sends over SCIM). Each
role maps to a frozenset of scopes; a member's effective permissions are exactly `role_scopes(role)`.

Adding a role is additive. Changing an existing role's scope set widens/narrows every member on it, so
treat it like a permission change. Roles are deliberately few and opinionated — enterprises map their
IdP groups onto these, not the other way round.
"""

from __future__ import annotations

from enum import Enum

from core.account.scopes import (
    ACTIONS_READ,
    ACTIONS_WRITE,
    APPROVAL_DECIDE,
    APPROVAL_READ,
    BILLING_WRITE,
    DASHBOARD_READ,
    ERASURE_WRITE,
    INFERENCE_WRITE,
    LEDGER_READ,
    MEMBERS_ADMIN,
    OWNER_SCOPES,
    POLICY_ADMIN,
    POLICY_READ,
    SCIM_ADMIN,
)


class Role(str, Enum):
    """A member's role. The value is the stable wire string (stored, sent over SCIM)."""

    OWNER = "OWNER"          # the tenant root — everything (the signup account's role)
    ADMIN = "ADMIN"          # manage members + policies + billing + operate, but not the root
    COMPLIANCE = "COMPLIANCE"  # approve HITL, read the ledger/dashboards/policies (oversight)
    VIEWER = "VIEWER"        # read-only across the governance read-models


# Role → scopes. OWNER gets all scopes (incl. members/scim admin); ADMIN gets everything an operator
# needs including member management; COMPLIANCE is oversight (decide + read); VIEWER is read-only.
_ROLE_SCOPES: dict[Role, frozenset[str]] = {
    Role.OWNER: OWNER_SCOPES,
    Role.ADMIN: frozenset(
        {
            ACTIONS_WRITE, ACTIONS_READ, LEDGER_READ, DASHBOARD_READ,
            APPROVAL_READ, APPROVAL_DECIDE, POLICY_READ, POLICY_ADMIN,
            INFERENCE_WRITE, ERASURE_WRITE, BILLING_WRITE, MEMBERS_ADMIN, SCIM_ADMIN,
        }
    ),
    Role.COMPLIANCE: frozenset(
        {ACTIONS_READ, LEDGER_READ, DASHBOARD_READ, APPROVAL_READ, APPROVAL_DECIDE, POLICY_READ}
    ),
    Role.VIEWER: frozenset({ACTIONS_READ, LEDGER_READ, DASHBOARD_READ, APPROVAL_READ, POLICY_READ}),
}


def parse_role(value: object) -> Role:
    """Coerce a wire string to a Role (fail-closed on an unknown role)."""
    if isinstance(value, Role):
        return value
    try:
        return Role(str(value).upper())
    except ValueError as exc:
        raise ValueError(
            f"Unknown role {value!r} (expected one of {[r.value for r in Role]})."
        ) from exc


def role_scopes(role: object) -> frozenset[str]:
    """The effective scope set for a role."""
    return _ROLE_SCOPES[parse_role(role)]


# Governance actor roles per account/member role — the tuple that lands in `Actor.roles` and drives
# CEL policy evaluation. Mirrors the console session JWT's `roles` claim (e.g. an owner logs in with
# ["owner", "policy_admin"]) so an API-key-authenticated owner resolves the same governance identity.
_ACTOR_ROLES: dict[Role, tuple[str, ...]] = {
    Role.OWNER: ("owner", "policy_admin"),
    Role.ADMIN: ("admin", "policy_admin"),
    Role.COMPLIANCE: ("compliance",),
    Role.VIEWER: ("viewer",),
}


def actor_roles_for(role: object) -> tuple[str, ...]:
    """The governance `Actor.roles` for an account/member role (fail-closed via `parse_role`)."""
    return _ACTOR_ROLES[parse_role(role)]
