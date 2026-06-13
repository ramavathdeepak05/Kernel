"""Enterprise license sign/verify — offline, fail-closed (ADR-0009)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.errors import LicenseInvalidError
from core.license import License, sign_license, verify_license


def _key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def _license(tenants=("acme",), days_valid=365) -> License:
    now = datetime.now(timezone.utc)
    return License(
        license_id="lic-1",
        licensee="Acme Bank",
        tenants=tenants,
        tier="ENTERPRISE",
        issued_at=now,
        expires_at=now + timedelta(days=days_valid),
    )


def test_roundtrip_verifies_and_covers_tenant():
    sk = _key()
    lic = _license()
    back = verify_license(sign_license(lic, sk), sk.public_key())
    assert back.licensee == "Acme Bank"
    assert back.covers_tenant("acme")
    assert not back.covers_tenant("other")


def test_wildcard_covers_any_tenant():
    sk = _key()
    back = verify_license(sign_license(_license(tenants=("*",)), sk), sk.public_key())
    assert back.covers_tenant("anything")


def test_tampered_token_rejected():
    sk = _key()
    tok = sign_license(_license(), sk)
    with pytest.raises(LicenseInvalidError):
        verify_license(tok[:-3] + "AAA", sk.public_key())


def test_wrong_key_rejected():
    tok = sign_license(_license(), _key())
    with pytest.raises(LicenseInvalidError):
        verify_license(tok, _key().public_key())


def test_expired_license_rejected():
    sk = _key()
    now = datetime.now(timezone.utc)
    expired = License("l", "X", ("*",), "ENTERPRISE", now - timedelta(days=2), now - timedelta(days=1))
    with pytest.raises(LicenseInvalidError):
        verify_license(sign_license(expired, sk), sk.public_key())


def test_malformed_token_rejected():
    with pytest.raises(LicenseInvalidError):
        verify_license("not-a-token", _key().public_key())
