"""
Control Plane Crypto — S2

Symmetric encryption for tenant DB passwords stored in cp_tenants.
Uses AES-256-GCM via the cryptography library.

Key derivation: HKDF(ALIS_MASTER_KEY, info=b"cp-tenant-db-passwords")
"""
from __future__ import annotations

import base64
import os
from functools import lru_cache


@lru_cache(maxsize=1)
def _get_key() -> bytes:
    """Derive 32-byte AES key from ALIS_MASTER_KEY. Cached after first call."""
    from control_plane.settings import settings
    master = settings.alis_master_key.encode() if settings.alis_master_key else b"dev-key-not-for-production-use!!"
    try:
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        from cryptography.hazmat.primitives import hashes
        kdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"cp-tenant-db-passwords",
        )
        return kdf.derive(master)
    except ImportError:
        # Fallback: SHA-256 of master key (acceptable for dev, not production)
        import hashlib
        return hashlib.sha256(master).digest()


def encrypt(plaintext: str) -> str:
    """Encrypt a string and return base64-encoded ciphertext (nonce + tag + ct)."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = _get_key()
        nonce = os.urandom(12)  # 96-bit nonce for AES-GCM
        ct = AESGCM(key).encrypt(nonce, plaintext.encode(), None)
        return base64.b64encode(nonce + ct).decode()
    except ImportError:
        # Dev fallback — not secure, but avoids hard crash when cryptography not installed
        return base64.b64encode(plaintext.encode()).decode() + "::dev"


def decrypt(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext produced by encrypt()."""
    if ciphertext.endswith("::dev"):
        return base64.b64decode(ciphertext[:-5]).decode()
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        key = _get_key()
        raw = base64.b64decode(ciphertext)
        nonce, ct = raw[:12], raw[12:]
        return AESGCM(key).decrypt(nonce, ct, None).decode()
    except ImportError:
        raise RuntimeError("cryptography library required to decrypt tenant DB passwords in production")
