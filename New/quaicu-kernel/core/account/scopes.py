"""RBAC scopes — the fine-grained permissions an API key may carry (ADR-0011, WS-D).

The kernel's management surface is gated two ways: tenant isolation (which tenant's data you may
touch) and **scopes** (which operations you may perform on it). A scope is a stable
``"resource:verb"`` string. An `ApiKey` carries a `frozenset` of scopes; a route asserts the scope it
requires via `delivery/api/auth.enforce_scope`.

The bootstrap key minted at signup gets `OWNER_SCOPES` (everything) — it is the tenant's root
credential. Narrower keys (CI tokens, read-only dashboards) can be issued with a subset via
`AccountEngine.issue_api_key(tenant, scopes=...)`.

Adding a scope here is additive: define the constant, add it to `ALL_SCOPES`, and assert it where the
operation is performed. Removing or renaming a scope is a breaking change for issued keys — don't.
"""

from __future__ import annotations

# ── Scope constants (resource:verb) ─────────────────────────────────────────────

ACTIONS_WRITE = "actions:write"        # propose / drive a governed action
ACTIONS_READ = "actions:read"          # look up an action's state
LEDGER_READ = "ledger:read"            # read the tenant's audit trail / proofs
DASHBOARD_READ = "dashboard:read"      # read governance read-models
APPROVAL_READ = "approval:read"        # list the HITL queue
APPROVAL_DECIDE = "approval:decide"    # approve / reject a pending HITL request
POLICY_READ = "policy:read"            # list / inspect policies
POLICY_ADMIN = "policy:admin"          # author / activate / deprecate policies
INFERENCE_WRITE = "inference:write"    # make a governed model call


# Every scope the kernel currently understands. The bootstrap (signup) key gets all of them.
ALL_SCOPES: frozenset[str] = frozenset(
    {
        ACTIONS_WRITE,
        ACTIONS_READ,
        LEDGER_READ,
        DASHBOARD_READ,
        APPROVAL_READ,
        APPROVAL_DECIDE,
        POLICY_READ,
        POLICY_ADMIN,
        INFERENCE_WRITE,
    }
)

# The bootstrap credential issued at signup — the tenant's root key.
OWNER_SCOPES: frozenset[str] = ALL_SCOPES


def normalize_scopes(scopes: object) -> frozenset[str]:
    """Coerce an iterable of scope strings to a validated frozenset.

    Unknown scopes are rejected (fail-closed): an issued key must only carry scopes the kernel can
    actually enforce, so a typo can never silently widen access.
    """
    if scopes is None:
        return OWNER_SCOPES
    requested = frozenset(str(s) for s in scopes)  # type: ignore[union-attr]
    unknown = requested - ALL_SCOPES
    if unknown:
        raise ValueError(f"Unknown scope(s): {sorted(unknown)}")
    return requested
