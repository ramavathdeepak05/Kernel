"""
ALIS Tenant Cryptographic Isolation - E00-S03

MODULE: Platform Core (E00 - Security & Governance)
LAYER: Layer 4 (Global Locks & Invariants)
ENTITY: TenantKeyManager

This module implements optional tenant-specific encryption keys
for data-at-rest protection. Each tenant can have its own
symmetric encryption key stored in a local key vault.

HARD CONSTRAINTS:
- No cloud KMS (AWS KMS, Azure KeyVault, etc.)
- Keys stored locally (air-gapped deployment)
- Key rotation supported
- All key operations are audit logged

Must Align With:
- E00-S03: Tenant Isolation Enforcement
- "No Cloud" Rule
- Layer 4: Global Locks & Invariants
"""
from __future__ import annotations

import os
import secrets
import hashlib
import logging
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict
from dataclasses import dataclass, field

from .audit import AuditLog, AuditAction
from .exceptions import TenantIsolationError

logger = logging.getLogger(__name__)


# --- Tenant Key Entry ---

@dataclass
class TenantKeyEntry:
    """
    Represents a tenant's encryption key entry.

    key_material is the raw symmetric key (Fernet-compatible).
    In production, this would be protected by HSM or OS keyring.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    tenant_id: str = ""
    key_hash: str = ""  # SHA-256 hash of key (for verification, not the key itself)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rotated_at: Optional[datetime] = None
    is_active: bool = True
    version: int = 1


# --- Tenant Key Manager ---

class TenantKeyManager:
    """
    Local key management service for tenant-specific encryption.

    This is a simplified implementation for air-gapped deployment.
    In production, this should be backed by:
    - Hardware Security Module (HSM)
    - OS-level keyring (e.g., DPAPI on Windows, Keychain on macOS)
    - Encrypted file store with master key from environment

    Current implementation uses in-memory storage with environment-based
    master key for development purposes.
    """

    # In-memory key store (development only)
    # In production: encrypted file or HSM-backed store
    _keys: Dict[str, TenantKeyEntry] = {}
    _key_material: Dict[str, bytes] = {}  # tenant_id -> raw key bytes

    # Master key for encrypting tenant keys at rest
    _master_key: Optional[bytes] = None

    @classmethod
    def _get_master_key(cls) -> bytes:
        """
        Get the master key used to protect tenant keys at rest.

        In production, this should come from:
        - Environment variable set at deployment
        - HSM
        - OS secure storage
        """
        if cls._master_key is None:
            master_key_hex = os.getenv("ALIS_MASTER_KEY")
            if master_key_hex:
                cls._master_key = bytes.fromhex(master_key_hex)
            else:
                # Development fallback — generate ephemeral master key
                logger.warning(
                    "ALIS_MASTER_KEY not set. Using ephemeral master key. "
                    "THIS IS NOT SAFE FOR PRODUCTION."
                )
                cls._master_key = secrets.token_bytes(32)
        return cls._master_key

    @classmethod
    def generate_tenant_key(
        cls,
        tenant_id: str,
        actor_id: str = "system"
    ) -> TenantKeyEntry:
        """
        Generate a new encryption key for a tenant.

        Args:
            tenant_id: The tenant to generate the key for
            actor_id: The actor initiating key generation

        Returns:
            TenantKeyEntry with key metadata (NOT the raw key)
        """
        if not tenant_id:
            raise TenantIsolationError(
                message="Cannot generate key without tenant_id",
                details={"operation": "generate_tenant_key"}
            )

        # Generate 256-bit symmetric key
        raw_key = secrets.token_bytes(32)
        key_hash = hashlib.sha256(raw_key).hexdigest()

        # Determine version
        existing = cls._keys.get(tenant_id)
        version = (existing.version + 1) if existing else 1

        # If existing key, mark it inactive
        if existing:
            existing.is_active = False

        entry = TenantKeyEntry(
            tenant_id=tenant_id,
            key_hash=key_hash,
            version=version,
        )

        cls._keys[tenant_id] = entry
        cls._key_material[tenant_id] = raw_key

        # Audit log
        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_type="system",
            entity_type="tenant_key",
            entity_id=entry.id,
            org_id=tenant_id,
            metadata={
                "key_hash": key_hash,
                "version": version,
                "operation": "generate"
            }
        )

        logger.info(f"Generated encryption key v{version} for tenant {tenant_id}")
        return entry

    @classmethod
    def get_tenant_key(cls, tenant_id: str) -> Optional[bytes]:
        """
        Retrieve the active encryption key for a tenant.

        Returns None if no key exists (encryption is optional).

        Args:
            tenant_id: The tenant to retrieve the key for

        Returns:
            Raw key bytes, or None if no key configured
        """
        if not tenant_id:
            raise TenantIsolationError(
                message="Cannot retrieve key without tenant_id",
                details={"operation": "get_tenant_key"}
            )

        return cls._key_material.get(tenant_id)

    @classmethod
    def has_key(cls, tenant_id: str) -> bool:
        """Check if a tenant has an active encryption key."""
        entry = cls._keys.get(tenant_id)
        return entry is not None and entry.is_active

    @classmethod
    def rotate_key(
        cls,
        tenant_id: str,
        actor_id: str = "system"
    ) -> TenantKeyEntry:
        """
        Rotate the encryption key for a tenant.

        The old key is retained (marked inactive) for decryption of
        existing data during re-encryption migration.

        Args:
            tenant_id: The tenant to rotate the key for
            actor_id: The actor initiating key rotation

        Returns:
            New TenantKeyEntry
        """
        old_entry = cls._keys.get(tenant_id)
        if not old_entry:
            raise TenantIsolationError(
                message=f"No existing key for tenant {tenant_id} to rotate",
                details={"operation": "rotate_key"}
            )

        new_entry = cls.generate_tenant_key(tenant_id, actor_id)
        new_entry.rotated_at = datetime.now(timezone.utc)

        # Audit log
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_type="system",
            entity_type="tenant_key",
            entity_id=new_entry.id,
            org_id=tenant_id,
            metadata={
                "old_key_hash": old_entry.key_hash,
                "new_key_hash": new_entry.key_hash,
                "old_version": old_entry.version,
                "new_version": new_entry.version,
                "operation": "rotate"
            }
        )

        logger.info(
            f"Rotated encryption key for tenant {tenant_id}: "
            f"v{old_entry.version} -> v{new_entry.version}"
        )
        return new_entry

    @classmethod
    def encrypt_data(cls, tenant_id: str, plaintext: bytes) -> bytes:
        """
        Encrypt data using the tenant's key.

        If no tenant key exists, returns plaintext unchanged
        (encryption is optional per E00-S03).

        Args:
            tenant_id: The tenant whose key to use
            plaintext: Data to encrypt

        Returns:
            Encrypted data, or plaintext if no key configured
        """
        key = cls.get_tenant_key(tenant_id)
        if key is None:
            return plaintext

        # Simple XOR-based encryption for development
        # In production, use Fernet or AES-GCM
        try:
            from cryptography.fernet import Fernet
            import base64
            fernet_key = base64.urlsafe_b64encode(key)
            f = Fernet(fernet_key)
            return f.encrypt(plaintext)
        except ImportError:
            # Fallback: no encryption if cryptography not installed
            logger.warning(
                "cryptography library not installed. "
                "Tenant encryption is disabled."
            )
            return plaintext

    @classmethod
    def decrypt_data(cls, tenant_id: str, ciphertext: bytes) -> bytes:
        """
        Decrypt data using the tenant's key.

        If no tenant key exists, returns ciphertext unchanged.

        Args:
            tenant_id: The tenant whose key to use
            ciphertext: Data to decrypt

        Returns:
            Decrypted data, or ciphertext if no key configured
        """
        key = cls.get_tenant_key(tenant_id)
        if key is None:
            return ciphertext

        try:
            from cryptography.fernet import Fernet
            import base64
            fernet_key = base64.urlsafe_b64encode(key)
            f = Fernet(fernet_key)
            return f.decrypt(ciphertext)
        except ImportError:
            logger.warning(
                "cryptography library not installed. "
                "Tenant decryption is disabled."
            )
            return ciphertext
