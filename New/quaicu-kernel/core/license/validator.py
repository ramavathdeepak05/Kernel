"""Enterprise license — sign & verify (ADR-0009).

A license token is a compact ``<payload>.<signature>`` string (both base64url):
  - ``payload``   = canonical JSON of the `License` claim set.
  - ``signature`` = Ed25519 signature over the canonical payload bytes.

Verification is **offline** and **fail-closed**: a missing, malformed, expired, or badly-signed
token raises `LicenseInvalidError`, and the ENTERPRISE kernel path refuses to boot. Uses the same
``cryptography`` Ed25519 primitives as the ledger signer (`core/ledger/signer.py`).
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from core.errors import LicenseInvalidError
from core.license.model import License


def _canonical_payload(lic: License) -> bytes:
    """Deterministic JSON of the claim set — identical bytes signer and verifier agree on."""
    payload = {
        "license_id": lic.license_id,
        "licensee": lic.licensee,
        "tenants": list(lic.tenants),
        "tier": lic.tier,
        "issued_at": lic.issued_at.astimezone(timezone.utc).isoformat(),
        "expires_at": lic.expires_at.astimezone(timezone.utc).isoformat(),
        "features": list(lic.features),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def sign_license(lic: License, private_key: Ed25519PrivateKey) -> str:
    """Produce a ``<payload>.<signature>`` license token. Used by the license-issuing tool."""
    payload = _canonical_payload(lic)
    signature = private_key.sign(payload)
    return f"{_b64url_encode(payload)}.{_b64url_encode(signature)}"


def _parse_license_payload(payload: bytes) -> License:
    data = json.loads(payload)
    return License(
        license_id=str(data["license_id"]),
        licensee=str(data["licensee"]),
        tenants=tuple(data["tenants"]),
        tier=str(data["tier"]),
        issued_at=datetime.fromisoformat(data["issued_at"]),
        expires_at=datetime.fromisoformat(data["expires_at"]),
        features=tuple(data.get("features", ())),
    )


def verify_license(
    token: str,
    public_key: Ed25519PublicKey,
    *,
    now: datetime | None = None,
) -> License:
    """Verify a license token offline and return its `License`. Fail-closed.

    Raises `LicenseInvalidError` if the token is missing/malformed, the signature does not verify,
    or the license has expired.
    """
    if not token or "." not in token:
        raise LicenseInvalidError(
            "License token missing or malformed (expected '<payload>.<signature>').",
            detail={"present": bool(token)},
        )

    payload_b64, _, sig_b64 = token.partition(".")
    try:
        payload = _b64url_decode(payload_b64)
        signature = _b64url_decode(sig_b64)
    except Exception as exc:  # noqa: BLE001 — any decode failure is an invalid token
        raise LicenseInvalidError(
            f"License token is not valid base64url: {exc}",
        ) from exc

    try:
        public_key.verify(signature, payload)
    except InvalidSignature as exc:
        raise LicenseInvalidError(
            "License signature does not verify against the configured public key.",
        ) from exc

    try:
        lic = _parse_license_payload(payload)
    except (KeyError, ValueError) as exc:
        raise LicenseInvalidError(
            f"License payload is missing required claims: {exc}",
        ) from exc

    now = now or datetime.now(timezone.utc)
    if lic.is_expired(now=now):
        raise LicenseInvalidError(
            f"License {lic.license_id!r} expired at {lic.expires_at.isoformat()}.",
            detail={"license_id": lic.license_id, "expires_at": lic.expires_at.isoformat()},
        )

    return lic


def load_public_key(pem_or_hex: str) -> Ed25519PublicKey:
    """Load an Ed25519 public key from a PEM string or a 32-byte hex string (operator-supplied)."""
    text = pem_or_hex.strip()
    if "BEGIN" in text:
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        key = load_pem_public_key(text.encode("utf-8"))
        if not isinstance(key, Ed25519PublicKey):
            raise LicenseInvalidError("Configured public key is not an Ed25519 key.")
        return key
    try:
        return Ed25519PublicKey.from_public_bytes(bytes.fromhex(text))
    except Exception as exc:  # noqa: BLE001
        raise LicenseInvalidError(f"Could not load Ed25519 public key: {exc}") from exc
