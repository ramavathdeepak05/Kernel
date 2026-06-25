"""API-key → governance-actor bridge (SaaS plane).

A verified `qk_` API key is not a JWT, so the kernel's IdentityPort can't resolve a governance actor
from it — governed actions used to fail-closed ("identity unresolved"). These tests cover the bridge:
`resolve_principal` now carries governance roles, and `resolve_governed_actor` turns a verified
API-key principal into a host-provided actor while leaving the JWT/IdP path untouched.
"""

from __future__ import annotations

from types import SimpleNamespace

from core.account.engine import AccountEngine
from core.account.model import AuthenticatedPrincipal
from core.account.roles import Role, actor_roles_for
from core.account.store import AccountStore
from core.entitlements import EntitlementStore
from core.types import TenantId
from delivery.api.deps import resolve_governed_actor

_T = TenantId("tenant-1")


def _request(authorization: str, principal: object) -> SimpleNamespace:
    return SimpleNamespace(headers={"authorization": authorization}, state=SimpleNamespace(principal=principal))


def _principal(roles: tuple[str, ...]) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        tenant_id=_T, account_id="acct_abc", key_id="k1", scopes=frozenset(), roles=roles
    )


# ── resolve_governed_actor ───────────────────────────────────────────────────

def test_bridge_builds_actor_from_apikey_principal() -> None:
    req = _request("Bearer qk_abc_secret", _principal(("owner", "policy_admin")))
    actor = resolve_governed_actor(req, _T)
    assert actor is not None
    assert str(actor.id) == "acct_abc"
    assert actor.tenant == _T
    assert actor.roles == ("owner", "policy_admin")


def test_bridge_returns_none_for_jwt_bearer() -> None:
    # A session JWT / IdP token must keep flowing through the IdentityPort (path unchanged).
    req = _request("Bearer eyJhbGciOi.JpdCI.sig", _principal(("owner",)))
    assert resolve_governed_actor(req, _T) is None


def test_bridge_returns_none_without_principal() -> None:
    req = _request("Bearer qk_abc_secret", None)
    assert resolve_governed_actor(req, _T) is None


def test_bridge_returns_none_without_bearer() -> None:
    req = _request("", _principal(("owner",)))
    assert resolve_governed_actor(req, _T) is None


# ── resolve_principal carries governance roles ───────────────────────────────

def test_account_key_resolves_owner_roles() -> None:
    eng = AccountEngine(AccountStore(), EntitlementStore(), pepper="p", session_secret="s")
    account, presented = eng.signup(email="a@b.io", name="Acme")  # the tenant-root (owner) key
    principal = eng.resolve_principal(presented)
    assert principal.roles == actor_roles_for(Role.OWNER)
    assert principal.account_id == account.account_id


def test_member_bound_key_resolves_member_roles() -> None:
    eng = AccountEngine(AccountStore(), EntitlementStore(), pepper="p", session_secret="s")
    account, _ = eng.signup(email="a@b.io", name="Acme")
    member = eng.provision_member(
        account.tenant_id, email="c@x.io", display_name="C", role=Role.COMPLIANCE.value
    )
    _record, presented = eng.issue_api_key(account.tenant_id, member_id=member.member_id)
    principal = eng.resolve_principal(presented)
    assert principal.roles == actor_roles_for(Role.COMPLIANCE)


# ── member-bound key → a distinct governance actor (separation of duties) ─────

def test_member_bound_key_subject_is_distinct_from_owner() -> None:
    eng = AccountEngine(AccountStore(), EntitlementStore(), pepper="p", session_secret="s")
    account, _ = eng.signup(email="a@b.io", name="Acme")
    member = eng.provision_member(
        account.tenant_id, email="c@x.io", display_name="C", role=Role.COMPLIANCE.value
    )
    _record, presented = eng.issue_api_key(account.tenant_id, member_id=member.member_id)
    principal = eng.resolve_principal(presented)
    assert principal.subject == f"member:{member.member_id}"
    assert principal.actor_id == f"member:{member.member_id}"
    assert principal.actor_id != account.account_id  # distinct from the proposer → SoD can be satisfied


def test_owner_key_subject_is_the_account() -> None:
    eng = AccountEngine(AccountStore(), EntitlementStore(), pepper="p", session_secret="s")
    account, presented = eng.signup(email="a@b.io", name="Acme")
    assert eng.resolve_principal(presented).actor_id == account.account_id


def test_bridge_actor_id_uses_subject() -> None:
    principal = AuthenticatedPrincipal(
        tenant_id=_T, account_id="acct_owner", key_id="k", scopes=frozenset(),
        roles=("compliance",), subject="member:mem_1",
    )
    actor = resolve_governed_actor(_request("Bearer qk_a_b", principal), _T)
    assert actor is not None and str(actor.id) == "member:mem_1"
