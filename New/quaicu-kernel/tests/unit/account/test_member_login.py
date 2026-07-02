"""Member console login: set-password → authenticate → member session (D1-5)."""

from __future__ import annotations

import jwt as _jwt
import pytest

from core.account import AccountEngine, AccountStore
from core.account.roles import Role
from core.account.scopes import APPROVAL_DECIDE
from core.entitlements import EntitlementStore
from core.errors import AccountNotFoundError, SignupVerificationError
from core.types import TenantId

SECRET = "test-session-secret"
EMAIL = "checker@acme.io"
PASSWORD = "s3cret-passphrase"


def _engine() -> AccountEngine:
    return AccountEngine(AccountStore(), EntitlementStore(), session_secret=SECRET)


def _member(engine: AccountEngine, role: str = Role.COMPLIANCE.value):
    return engine.provision_member(
        TenantId("acme"), email=EMAIL, role=role, display_name="Checker"
    )


def test_set_password_then_authenticate() -> None:
    e = _engine()
    m = _member(e)
    assert not m.password_hash  # invited member has no password yet
    token = e.mint_member_set_password_token(m)
    updated = e.set_member_password(token=token, new_password=PASSWORD)
    assert updated.password_hash
    got = e.authenticate_member(email=EMAIL, password=PASSWORD)
    assert got.member_id == m.member_id


def test_wrong_password_and_unset_password_rejected() -> None:
    e = _engine()
    m = _member(e)
    # No password set yet → cannot authenticate.
    with pytest.raises(AccountNotFoundError):
        e.authenticate_member(email=EMAIL, password=PASSWORD)
    e.set_member_password(token=e.mint_member_set_password_token(m), new_password=PASSWORD)
    with pytest.raises(AccountNotFoundError):
        e.authenticate_member(email=EMAIL, password="wrong-password")


def test_tampered_set_password_token_rejected() -> None:
    e = _engine()
    m = _member(e)
    token = e.mint_member_set_password_token(m)
    with pytest.raises(SignupVerificationError):
        e.set_member_password(token=token[:-4] + "AAAA", new_password=PASSWORD)


def test_member_session_seals_member_identity_and_role() -> None:
    e = _engine()
    m = _member(e)
    token, expires_in = e.mint_member_session(m)
    assert expires_in > 0
    claims = _jwt.decode(token, options={"verify_signature": False})
    # sub = member_id → the sealed governance actor is the member (SoD holds vs the proposer).
    assert claims["sub"] == m.member_id
    assert claims["tenant"] == "acme"
    assert claims["kind"] == "member"
    assert "compliance" in claims["roles"]           # governance role → satisfies role:compliance gates
    assert APPROVAL_DECIDE in claims["scopes"]        # can decide approvals at the API edge
