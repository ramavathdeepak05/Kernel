"""Members + RBAC roles (W6-1) — engine-level."""

from __future__ import annotations

import pytest

from core.account import AccountEngine, AccountStore, MemberStatus, Role, role_scopes
from core.account.scopes import LEDGER_READ, MEMBERS_ADMIN
from core.entitlements import EntitlementStore
from core.errors import AccountNotFoundError
from core.types import TenantId

_T = TenantId("acme")


def _engine() -> tuple[AccountEngine, AccountStore]:
    accounts = AccountStore()
    return AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s"), accounts


def test_invite_and_list_member():
    eng, _ = _engine()
    m = eng.provision_member(_T, email="a@acme.io", role="ADMIN", display_name="A")
    assert m.role == "ADMIN" and m.status is MemberStatus.ACTIVE
    assert [x.member_id for x in eng.list_members(_T)] == [m.member_id]


def test_provision_is_idempotent_by_email():
    eng, _ = _engine()
    m1 = eng.provision_member(_T, email="a@acme.io", role="VIEWER")
    m2 = eng.provision_member(_T, email="A@ACME.IO", role="ADMIN")  # same email, case-insensitive
    assert m1.member_id == m2.member_id and m2.role == "ADMIN"
    assert len(eng.list_members(_T)) == 1


def test_unknown_role_is_rejected():
    eng, _ = _engine()
    with pytest.raises(ValueError, match="Unknown role"):
        eng.provision_member(_T, email="a@acme.io", role="SUPERUSER")


def test_set_role():
    eng, _ = _engine()
    m = eng.provision_member(_T, email="a@acme.io", role="VIEWER")
    updated = eng.set_member_role(_T, m.member_id, "COMPLIANCE")
    assert updated.role == "COMPLIANCE"


def test_deactivate_revokes_member_keys():
    eng, accounts = _engine()
    m = eng.provision_member(_T, email="a@acme.io", role="ADMIN")
    rec, _ = eng.issue_api_key(_T, scopes=[LEDGER_READ], member_id=m.member_id)
    other, _ = eng.issue_api_key(_T, scopes=[LEDGER_READ])  # not bound to the member
    eng.deactivate_member(_T, m.member_id)
    assert eng.get_member(_T, m.member_id).status is MemberStatus.DEACTIVATED
    assert accounts.get_api_key(rec.key_id).revoked is True
    assert accounts.get_api_key(other.key_id).revoked is False  # unrelated key untouched


def test_tenant_isolation_on_member_lookup():
    eng, _ = _engine()
    m = eng.provision_member(_T, email="a@acme.io", role="VIEWER")
    with pytest.raises(AccountNotFoundError):
        eng.get_member(TenantId("other"), m.member_id)


def test_role_scopes_mapping():
    assert MEMBERS_ADMIN in role_scopes(Role.OWNER)
    assert MEMBERS_ADMIN in role_scopes("ADMIN")
    assert role_scopes("VIEWER") < role_scopes("ADMIN")  # viewer is a strict subset
    assert LEDGER_READ in role_scopes("COMPLIANCE")
    assert MEMBERS_ADMIN not in role_scopes("COMPLIANCE")
