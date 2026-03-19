"""
ALIS MFA Service — TOTP-based Two-Factor Authentication

MODULE: Platform Core (E01 — Platform Foundation)
LAYER: Layer 5 (Roles, Authority & Quorum)

Provides TOTP enrollment, verification, backup codes, and device trust
for the ALIS authentication system.

Hard constraints:
  - TOTP secrets are encrypted at rest using Fernet (AES-128-CBC) derived
    from settings.app_secret_key.
  - Backup codes are stored as SHA-256 hashes; plaintext is shown exactly once.
  - Device fingerprints are one-way SHA-256 hashes (UA + IP).
  - All DB access uses execute_query / execute_transaction with tenant_id.
  - No async/await — sync only.
"""

import secrets
import hashlib
import uuid as _uuid
import base64
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Roles that MUST complete MFA before a full session is issued
# ---------------------------------------------------------------------------
MFA_REQUIRED_ROLES = {"SUPER_ADMIN", "ADMIN", "REGISTRAR", "FINANCE_OFFICER", "HOD", "COE"}


# ---------------------------------------------------------------------------
# MFAService
# ---------------------------------------------------------------------------

class MFAService:
    """
    Stateless service class for TOTP-based MFA operations.

    All methods are static — no instance state. Thread-safe for multi-worker
    deployments because the only mutable state lives in PostgreSQL and Redis.
    """

    # ------------------------------------------------------------------
    # Fernet key derivation
    # ------------------------------------------------------------------

    @staticmethod
    def _get_fernet():
        """
        Derive a stable Fernet key from settings.app_secret_key.

        The key is deterministic (same secret → same Fernet key) so encrypted
        secrets remain decryptable across restarts without a separate key-store.
        """
        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise ImportError(
                "The 'cryptography' package is required for MFA. "
                "Install it with: pip install cryptography"
            ) from exc

        from server.core.settings import settings
        # Take first 32 bytes of the secret key, right-pad with '0' if shorter.
        key_bytes = settings.app_secret_key.encode()[:32].ljust(32, b"0")
        return Fernet(base64.urlsafe_b64encode(key_bytes))

    # ------------------------------------------------------------------
    # TOTP helpers
    # ------------------------------------------------------------------

    @staticmethod
    def generate_totp_secret() -> str:
        """Generate a new random base32 TOTP secret."""
        try:
            import pyotp
        except ImportError as exc:
            raise ImportError(
                "The 'pyotp' package is required for MFA. "
                "Install it with: pip install pyotp"
            ) from exc
        return pyotp.random_base32()

    @staticmethod
    def encrypt_secret(secret: str) -> str:
        """Encrypt a plaintext TOTP secret for storage."""
        return MFAService._get_fernet().encrypt(secret.encode()).decode()

    @staticmethod
    def decrypt_secret(encrypted: str) -> str:
        """Decrypt a stored TOTP secret."""
        return MFAService._get_fernet().decrypt(encrypted.encode()).decode()

    @staticmethod
    def get_totp_uri(secret: str, user_email: str, org_name: str = "ALIS") -> str:
        """Return an otpauth:// URI suitable for QR code generation."""
        try:
            import pyotp
        except ImportError as exc:
            raise ImportError(
                "The 'pyotp' package is required for MFA. "
                "Install it with: pip install pyotp"
            ) from exc
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=user_email, issuer_name=org_name)

    @staticmethod
    def verify_totp(encrypted_secret: str, code: str) -> bool:
        """
        Verify a TOTP code against an encrypted secret.

        valid_window=1 allows ±30-second clock skew (one step each side).
        """
        try:
            import pyotp
        except ImportError as exc:
            raise ImportError(
                "The 'pyotp' package is required for MFA. "
                "Install it with: pip install pyotp"
            ) from exc
        try:
            secret = MFAService.decrypt_secret(encrypted_secret)
            totp = pyotp.TOTP(secret)
            return totp.verify(code, valid_window=1)
        except Exception:
            logger.exception("MFAService.verify_totp: decryption/verification error")
            return False

    # ------------------------------------------------------------------
    # Backup codes
    # ------------------------------------------------------------------

    @staticmethod
    def generate_backup_codes(count: int = 8) -> "tuple[list[str], list[str]]":
        """
        Generate backup codes.

        Returns (plain_codes, hashed_codes).
        Store hashed_codes in the DB; show plain_codes to the user exactly once.
        Each plain code is an 8-character uppercase hex string (e.g. "A3F7B2C1").
        """
        plain = [secrets.token_hex(4).upper() for _ in range(count)]
        hashed = [hashlib.sha256(c.encode()).hexdigest() for c in plain]
        return plain, hashed

    @staticmethod
    def verify_backup_code(org_id: str, user_id: str, code: str) -> bool:
        """
        Check whether 'code' matches any stored backup code for the user.

        If matched, the code is invalidated (removed from the array) atomically.
        Returns True on match, False otherwise.
        """
        from server.db_service import execute_query, execute_transaction

        code_hash = hashlib.sha256(code.upper().encode()).hexdigest()
        devices = execute_query(
            "SELECT id, backup_codes FROM mfa_devices "
            "WHERE org_id = %s AND user_id = %s AND is_active = TRUE",
            (org_id, user_id),
            tenant_id=org_id,
        )
        for device in devices:
            codes = device.get("backup_codes") or []
            if code_hash in codes:
                new_codes = [c for c in codes if c != code_hash]
                execute_transaction(
                    [(
                        "UPDATE mfa_devices SET backup_codes = %s WHERE id = %s",
                        (new_codes, device["id"]),
                    )],
                    tenant_id=org_id,
                )
                return True
        return False

    # ------------------------------------------------------------------
    # Enrollment
    # ------------------------------------------------------------------

    @staticmethod
    def enroll_device(
        org_id: str,
        user_id: str,
        device_name: str = "Authenticator App",
    ) -> dict:
        """
        Begin TOTP enrollment for a user.

        Creates (or resets) an mfa_devices row with is_active=FALSE.
        The device is only activated after confirm_enrollment() succeeds.

        Returns:
            {
                "device_id":    str,
                "totp_uri":     str,   # otpauth:// URI for QR code
                "backup_codes": list[str],  # plaintext — show once, then discard
            }
        """
        from server.db_service import execute_query, execute_transaction

        secret = MFAService.generate_totp_secret()
        encrypted = MFAService.encrypt_secret(secret)
        plain_codes, hashed_codes = MFAService.generate_backup_codes()
        device_id = str(_uuid.uuid4())

        execute_transaction(
            [(
                "INSERT INTO mfa_devices "
                "  (id, org_id, user_id, device_name, totp_secret, backup_codes, is_active) "
                "VALUES (%s, %s, %s, %s, %s, %s, FALSE) "
                "ON CONFLICT (org_id, user_id, device_name) DO UPDATE "
                "SET totp_secret = EXCLUDED.totp_secret, "
                "    backup_codes = EXCLUDED.backup_codes, "
                "    is_active = FALSE, "
                "    enrolled_at = NOW()",
                (device_id, org_id, user_id, device_name, encrypted, hashed_codes),
            )],
            tenant_id=org_id,
        )

        # Fetch user email for the provisioning URI
        user_rows = execute_query(
            "SELECT email, username FROM users WHERE id = %s",
            (user_id,),
            tenant_id=org_id,
        )
        email = user_rows[0]["email"] if user_rows else str(user_id)

        uri = MFAService.get_totp_uri(secret, email)
        return {
            "device_id": device_id,
            "totp_uri": uri,
            "backup_codes": plain_codes,
        }

    @staticmethod
    def confirm_enrollment(org_id: str, user_id: str, code: str) -> bool:
        """
        Verify the first TOTP code to activate the device.

        Scans all inactive (is_active=FALSE) devices for the user, tries each
        TOTP secret, and activates the first one that matches.

        Returns True on success, False if no device matched.
        """
        from server.db_service import execute_query, execute_transaction

        devices = execute_query(
            "SELECT id, totp_secret FROM mfa_devices "
            "WHERE org_id = %s AND user_id = %s AND is_active = FALSE",
            (org_id, user_id),
            tenant_id=org_id,
        )
        for device in devices:
            if MFAService.verify_totp(device["totp_secret"], code):
                execute_transaction(
                    [(
                        "UPDATE mfa_devices SET is_active = TRUE WHERE id = %s",
                        (device["id"],),
                    )],
                    tenant_id=org_id,
                )
                return True
        return False

    # ------------------------------------------------------------------
    # Login challenge verification
    # ------------------------------------------------------------------

    @staticmethod
    def verify_challenge(org_id: str, user_id: str, code: str) -> bool:
        """
        Verify a TOTP code (or backup code) during the login MFA challenge.

        On success, stamps last_used_at on the matching device.
        Falls back to backup code verification if no active TOTP device matches.

        Returns True if the challenge is satisfied, False otherwise.
        """
        from server.db_service import execute_query, execute_transaction

        devices = execute_query(
            "SELECT id, totp_secret FROM mfa_devices "
            "WHERE org_id = %s AND user_id = %s AND is_active = TRUE",
            (org_id, user_id),
            tenant_id=org_id,
        )
        for device in devices:
            if MFAService.verify_totp(device["totp_secret"], code):
                execute_transaction(
                    [(
                        "UPDATE mfa_devices SET last_used_at = NOW() WHERE id = %s",
                        (device["id"],),
                    )],
                    tenant_id=org_id,
                )
                return True

        # Fall back to backup code
        return MFAService.verify_backup_code(org_id, user_id, code)

    # ------------------------------------------------------------------
    # MFA status
    # ------------------------------------------------------------------

    @staticmethod
    def has_active_mfa(org_id: str, user_id: str) -> bool:
        """Return True if the user has at least one active MFA device enrolled."""
        from server.db_service import execute_query

        rows = execute_query(
            "SELECT 1 FROM mfa_devices "
            "WHERE org_id = %s AND user_id = %s AND is_active = TRUE LIMIT 1",
            (org_id, user_id),
            tenant_id=org_id,
        )
        return bool(rows)

    @staticmethod
    def disable_mfa(org_id: str, user_id: str) -> None:
        """Deactivate all MFA devices for a user (soft-disable, keeps history)."""
        from server.db_service import execute_transaction

        execute_transaction(
            [(
                "UPDATE mfa_devices SET is_active = FALSE "
                "WHERE org_id = %s AND user_id = %s",
                (org_id, user_id),
            )],
            tenant_id=org_id,
        )

    # ------------------------------------------------------------------
    # Device trust
    # ------------------------------------------------------------------

    @staticmethod
    def trust_device(org_id: str, user_id: str, device_fingerprint: str) -> None:
        """
        Mark a device as trusted for 30 days.

        Subsequent logins from this device fingerprint skip the MFA challenge
        until trusted_until expires.

        The fingerprint must be a stable per-device string (e.g. UA + IP).
        It is stored as a one-way SHA-256 hash.
        """
        from server.db_service import execute_transaction

        device_hash = hashlib.sha256(device_fingerprint.encode()).hexdigest()
        execute_transaction(
            [(
                "INSERT INTO trusted_devices "
                "  (id, org_id, user_id, device_hash, trusted_until) "
                "VALUES (%s, %s, %s, %s, NOW() + INTERVAL '30 days') "
                "ON CONFLICT (org_id, user_id, device_hash) DO UPDATE "
                "SET trusted_until = NOW() + INTERVAL '30 days'",
                (str(_uuid.uuid4()), org_id, user_id, device_hash),
            )],
            tenant_id=org_id,
        )

    @staticmethod
    def is_device_trusted(org_id: str, user_id: str, device_fingerprint: str) -> bool:
        """
        Return True if the device fingerprint maps to a non-expired trusted_devices row.
        """
        from server.db_service import execute_query

        device_hash = hashlib.sha256(device_fingerprint.encode()).hexdigest()
        rows = execute_query(
            "SELECT 1 FROM trusted_devices "
            "WHERE org_id = %s AND user_id = %s "
            "  AND device_hash = %s AND trusted_until > NOW()",
            (org_id, user_id, device_hash),
            tenant_id=org_id,
        )
        return bool(rows)
