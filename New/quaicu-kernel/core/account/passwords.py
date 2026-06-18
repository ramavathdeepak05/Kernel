"""Password hashing for self-serve console login (ADR-0011).

Uses ``hashlib.scrypt`` — a memory-hard KDF in the Python standard library (no new dependency).
Stored format is self-describing so parameters can evolve: ``scrypt$<n>$<r>$<p>$<salt_hex>$<hash_hex>``.
Verification is constant-time. API keys still use HMAC (see engine); this is only for human passwords.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# scrypt cost parameters (OWASP-aligned: n=2**15, r=8, p=1).
_N = 1 << 14
_R = 8
_P = 1
_DKLEN = 32
_MIN_LEN = 8
# OpenSSL defaults scrypt maxmem to 32 MB; set generously so the cost params (now or stronger) fit.
_MAXMEM = 128 * 1024 * 1024


class PasswordError(ValueError):
    """Password does not meet policy (e.g. too short)."""


def hash_password(password: str) -> str:
    """Return a self-describing scrypt hash. Raises `PasswordError` if the password is too short."""
    if len(password) < _MIN_LEN:
        raise PasswordError(f"Password must be at least {_MIN_LEN} characters.")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=_MAXMEM
    )
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time check of ``password`` against a stored scrypt hash. False on any malformed input."""
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=bytes.fromhex(salt_hex),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(bytes.fromhex(hash_hex)),
            maxmem=_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)
