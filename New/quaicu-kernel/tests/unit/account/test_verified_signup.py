"""Verified-signup (OTP) + company-email enforcement — core/account."""

from __future__ import annotations

import pytest

from core.account.email_domains import assert_company_email, is_company_email
from core.account.engine import AccountEngine
from core.account.model import SignupDetails
from core.account.store import AccountStore
from core.entitlements import EntitlementStore
from core.errors import (
    AccountExistsError,
    AccountNotFoundError,
    EmailDomainNotAllowedError,
    SignupVerificationError,
)


def _engine() -> AccountEngine:
    return AccountEngine(
        AccountStore(), EntitlementStore(), pepper="test-pepper", session_secret="test-session-secret"
    )


def _details(email: str = "ada@acme-bank.com") -> SignupDetails:
    return SignupDetails(
        full_name="Ada Lovelace",
        email=email,
        company_name="Acme Bank",
        password="hunter2pass",
        job_title="CTO",
        phone="+1",
        use_case="AI governance",
        industry="Banking",
        company_size="51-200",
        regulations=("RBI", "DPDP"),
    )


# ── company-email rule ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("email", ["ada@acme-bank.com", "x@quaicu.org", "p@sub.company.io"])
def test_company_emails_allowed(email: str):
    assert is_company_email(email)


@pytest.mark.parametrize("email", ["a@gmail.com", "b@yahoo.com", "c@outlook.com", "d@icloud.com", "nope"])
def test_free_or_invalid_emails_rejected(email: str):
    assert not is_company_email(email)
    with pytest.raises(EmailDomainNotAllowedError):
        assert_company_email(email)


# ── OTP roundtrip ─────────────────────────────────────────────────────────────────


def test_start_then_verify_provisions_account():
    eng = _engine()
    token, otp = eng.start_signup(_details())
    assert len(otp) == 6 and otp.isdigit()
    account, key = eng.verify_signup(verification_token=token, otp=otp)
    assert account.email == "ada@acme-bank.com"
    assert account.full_name == "Ada Lovelace" and account.job_title == "CTO"
    assert account.profile["use_case"] == "AI governance"
    assert account.profile["regulations"] == ["RBI", "DPDP"]
    assert account.password_hash.startswith("scrypt$")  # password hashed, not stored plaintext
    assert key.startswith("qk_")
    # The provisioned key authenticates.
    assert eng.verify_api_key(key).account_id == account.account_id


def test_login_with_email_password_and_session_token():
    eng = _engine()
    token, otp = eng.start_signup(_details())
    account, api_key = eng.verify_signup(verification_token=token, otp=otp)

    # Correct password → account; session JWT resolves to the right principal.
    authed = eng.authenticate(email="ada@acme-bank.com", password="hunter2pass")
    assert authed.account_id == account.account_id
    session, expires_in = eng.mint_session(authed)
    assert expires_in > 0
    principal = eng.resolve_principal(session)
    assert str(principal.tenant_id) == str(account.tenant_id)
    assert principal.account_id == account.account_id

    # Wrong password rejected; the API key still resolves too (both bearer types work).
    with pytest.raises(AccountNotFoundError):
        eng.authenticate(email="ada@acme-bank.com", password="wrong-password")
    assert eng.resolve_principal(api_key).account_id == account.account_id


def test_start_does_not_provision_until_verified():
    eng = _engine()
    eng.start_signup(_details())
    # No account exists yet — only the (stateless) token was minted.
    assert eng._accounts.get_account_by_email("ada@acme-bank.com") is None


def test_wrong_otp_rejected():
    eng = _engine()
    token, otp = eng.start_signup(_details())
    bad = "000000" if otp != "000000" else "111111"
    with pytest.raises(SignupVerificationError):
        eng.verify_signup(verification_token=token, otp=bad)


def test_forged_token_rejected():
    eng = _engine()
    token, otp = eng.start_signup(_details())
    tampered = token[:-2] + ("aa" if not token.endswith("aa") else "bb")
    with pytest.raises(SignupVerificationError):
        eng.verify_signup(verification_token=tampered, otp=otp)


def test_free_email_blocked_at_start():
    eng = _engine()
    with pytest.raises(EmailDomainNotAllowedError):
        eng.start_signup(_details(email="someone@gmail.com"))


def test_existing_account_blocks_start():
    eng = _engine()
    eng.signup(email="ada@acme-bank.com", name="Acme")
    with pytest.raises(AccountExistsError):
        eng.start_signup(_details())


def test_start_blocks_duplicate_present_only_in_durable_store():
    """Cross-instance: the account exists in the DB but not in THIS instance's cache — start_signup
    must still reject it (no needless OTP), via the durable email_exists fallback."""
    import datetime as _dt

    from core.account.model import Account, AccountStatus
    from core.types import TenantId

    class _Repo:
        def load_all(self):
            return ([], [])

        def get_account_by_email(self, email):
            if email.lower() == "ada@acme-bank.com":
                return Account(
                    "acct_x", TenantId("acme"), email, "Acme", AccountStatus.ACTIVE,
                    _dt.datetime.now(_dt.timezone.utc),
                )
            return None

        def save_account(self, a): ...
        def save_api_key(self, k): ...
        def replace_api_key(self, k): ...
        def close(self): ...

    eng = AccountEngine(AccountStore(repository=_Repo()), EntitlementStore(), pepper="t")
    # Cache is empty (never hydrated), but the durable store has the account.
    with pytest.raises(AccountExistsError):
        eng.start_signup(_details())
