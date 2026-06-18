"""Account & API-key — the engine (ADR-0010).

`AccountEngine` owns self-serve provisioning: a signup creates an `Account`, mints a tenant id,
provisions a **default STARTER plan** in the entitlement store (so the new tenant can immediately make
governed calls on the shared plane), and issues one API key. The plaintext key is returned exactly
once; only its SHA-256 hash is persisted.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
from datetime import datetime, timezone

from collections.abc import Iterable

from core.account.email_domains import assert_company_email
from core.account.model import (
    Account,
    AccountStatus,
    ApiKey,
    AuthenticatedPrincipal,
    SignupDetails,
)
from core.account.scopes import normalize_scopes
from core.account.store import AccountStore
from core.entitlements import CustomerPlan, EntitlementStore, FeatureTier, PlanStatus
from core.errors import AccountExistsError, ApiKeyInvalidError, SignupVerificationError
from core.types import TenantId

# How long a signup OTP / verification token is valid.
_SIGNUP_TTL_SECONDS = 600

log = logging.getLogger("quaicu.account")

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# Env var supplying the server-side pepper mixed into API-key hashes. Set this in production so the
# stored hashes are keyed HMACs rather than bare digests (FIPS/PCI scanner-friendly, and a stolen
# store alone is useless without the pepper).
_PEPPER_ENV = "QUAICU_API_KEY_PEPPER"


def _slugify(text: str) -> str:
    slug = _SLUG_RE.sub("-", text.lower()).strip("-")
    return slug[:32] or "tenant"


class AccountEngine:
    """Self-serve account provisioning and API-key authentication."""

    def __init__(
        self,
        accounts: AccountStore,
        entitlements: EntitlementStore,
        *,
        pepper: bytes | str | None = None,
    ) -> None:
        self._accounts = accounts
        self._entitlements = entitlements
        # API keys are stored as HMAC-SHA256(pepper, secret), not a bare SHA-256 digest. The pepper
        # is a server-side secret (never persisted with the hash). Falls back to env, then empty —
        # an empty pepper is allowed for dev/tests but warned about so production wires a real one.
        resolved = pepper if pepper is not None else os.getenv(_PEPPER_ENV, "")
        self._pepper: bytes = resolved.encode("utf-8") if isinstance(resolved, str) else resolved
        if not self._pepper:
            log.warning(
                "%s is not set — API-key hashes use an empty pepper. Set a strong secret in "
                "production.",
                _PEPPER_ENV,
            )

    def hydrate(self) -> None:
        """Repopulate the account cache from its durable store at startup. No-op if in-memory."""
        self._accounts.hydrate()

    def _hash_secret(self, secret: str) -> str:
        """HMAC-SHA256 of the key secret under the server-side pepper (hex digest)."""
        return hmac.new(self._pepper, secret.encode("utf-8"), hashlib.sha256).hexdigest()

    # ── Signup ───────────────────────────────────────────────────────────────────

    def signup(
        self,
        *,
        email: str,
        name: str,
        full_name: str = "",
        job_title: str = "",
        phone: str = "",
    ) -> tuple[Account, str]:
        """Provision a new account on the STARTER tier. Returns (account, plaintext_api_key).

        The provisioning primitive: the verified flow (`verify_signup`) calls this only after an OTP
        proves email ownership; admin/tests may call it directly. Raises `AccountExistsError` if the
        email already owns an account. The plaintext key is the only time the full credential is
        available — the store keeps only its hash.
        """
        if self._accounts.email_exists(email):
            raise AccountExistsError(
                f"An account already exists for {email!r}.",
                detail={"email": email},
            )

        now = datetime.now(timezone.utc)
        tenant = TenantId(f"{_slugify(name)}-{secrets.token_hex(3)}")
        account = Account(
            account_id=f"acct_{secrets.token_hex(8)}",
            tenant_id=tenant,
            email=email,
            name=name,
            status=AccountStatus.ACTIVE,
            created_at=now,
            full_name=full_name,
            job_title=job_title,
            phone=phone,
        )
        self._accounts.add_account(account)

        # Default plan: STARTER, ACTIVE — the new tenant is immediately routable on the shared plane.
        self._entitlements.upsert(
            CustomerPlan(
                tenant_id=tenant,
                tier=FeatureTier.STARTER,
                status=PlanStatus.ACTIVE,
                created_at=now,
                updated_at=now,
            )
        )

        _, plaintext = self.issue_api_key(tenant)
        log.info("signup complete: tenant=%s tier=STARTER", tenant)
        return account, plaintext

    # ── Verified signup (OTP) ──────────────────────────────────────────────────────

    def start_signup(self, details: SignupDetails) -> tuple[str, str]:
        """Begin a verified signup. Returns ``(verification_token, otp)`` — does NOT provision yet.

        Validates the company email and that no account exists, then mints a 6-digit OTP and a signed,
        self-contained verification token carrying the (HMAC-hashed) OTP, the customer details, and an
        expiry. The caller emails the OTP and hands the opaque token back to the browser; provisioning
        happens only in `verify_signup` once the user proves they received the code. Stateless: no
        server-side pending store, so it works across stateless/replicated instances.

        Raises `EmailDomainNotAllowedError` (free/personal email) or `AccountExistsError`.
        """
        assert_company_email(details.email)
        if self._accounts.email_exists(details.email):
            raise AccountExistsError(
                f"An account already exists for {details.email!r}.",
                detail={"email": details.email},
            )

        otp = f"{secrets.randbelow(1_000_000):06d}"
        exp = datetime.now(timezone.utc).timestamp() + _SIGNUP_TTL_SECONDS
        token = self._seal_token(
            {
                "v": 1,
                "otp_hash": self._hash_secret(otp),
                "exp": exp,
                "details": {
                    "full_name": details.full_name,
                    "email": details.email,
                    "company_name": details.company_name,
                    "job_title": details.job_title,
                    "phone": details.phone,
                },
            }
        )
        log.info("signup started (OTP issued): email=%s", details.email)
        return token, otp

    def verify_signup(self, *, verification_token: str, otp: str) -> tuple[Account, str]:
        """Complete a verified signup: check the OTP against the token, then provision.

        Raises `SignupVerificationError` if the token is forged/expired or the OTP is wrong, and
        `AccountExistsError` if the email was claimed in the meantime. On success, provisions the
        STARTER account (with the collected details) and returns ``(account, plaintext_api_key)``.
        """
        payload = self._open_token(verification_token)
        expected = str(payload.get("otp_hash", ""))
        if not expected or not hmac.compare_digest(expected, self._hash_secret(otp.strip())):
            raise SignupVerificationError("Incorrect verification code.")
        d = payload.get("details", {})
        return self.signup(
            email=str(d["email"]),
            name=str(d["company_name"]),
            full_name=str(d.get("full_name", "")),
            job_title=str(d.get("job_title", "")),
            phone=str(d.get("phone", "")),
        )

    # ── Encrypted, self-contained verification token (AES-256-GCM over the pepper) ──

    def _token_key(self) -> bytes:
        """Derive a stable 32-byte AES key from the server pepper (domain-separated)."""
        return hashlib.sha256(self._pepper + b"|quaicu-signup-token-v1").digest()

    def _seal_token(self, payload: dict) -> str:
        """Encrypt+authenticate the signup payload. Confidential (details hidden) and tamper-proof."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._token_key()).encrypt(nonce, raw, None)
        return base64.urlsafe_b64encode(nonce + ciphertext).rstrip(b"=").decode()

    def _open_token(self, token: str) -> dict:
        """Decrypt + verify a verification token. Raises `SignupVerificationError` on any failure."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        try:
            blob = base64.urlsafe_b64decode((token or "") + "=" * (-len(token or "") % 4))
            nonce, ciphertext = blob[:12], blob[12:]
            raw = AESGCM(self._token_key()).decrypt(nonce, ciphertext, None)
            payload = json.loads(raw)
        except Exception as exc:  # noqa: BLE001 — bad base64 / wrong key / forged tag / bad JSON
            raise SignupVerificationError("Verification token is invalid.") from exc
        if float(payload.get("exp", 0)) < datetime.now(timezone.utc).timestamp():
            raise SignupVerificationError("Verification code expired — request a new one.")
        return payload

    # ── API keys ─────────────────────────────────────────────────────────────────

    def issue_api_key(
        self, tenant: TenantId, *, scopes: Iterable[str] | None = None
    ) -> tuple[ApiKey, str]:
        """Mint a new API key for ``tenant``. Returns (record, plaintext). Plaintext shown once.

        ``scopes`` restricts the key to a subset of `core/account/scopes.ALL_SCOPES` (fail-closed:
        unknown scopes raise). ``None`` grants the full owner scope set — used for the signup key.
        """
        key_id = secrets.token_hex(8)
        secret = secrets.token_urlsafe(32)
        record = ApiKey(
            key_id=key_id,
            tenant_id=tenant,
            hashed_secret=self._hash_secret(secret),
            created_at=datetime.now(timezone.utc),
            scopes=normalize_scopes(scopes),
        )
        self._accounts.add_api_key(record)
        return record, f"qk_{key_id}_{secret}"

    def revoke_api_key(self, key_id: str) -> None:
        """Revoke a key so it can no longer authenticate. Idempotent."""
        import dataclasses

        existing = self._accounts.get_api_key(key_id)
        if existing is None:
            raise ApiKeyInvalidError(
                f"No API key {key_id!r} to revoke.", detail={"key_id": key_id}
            )
        self._accounts.replace_api_key(dataclasses.replace(existing, revoked=True))

    def _verify(self, presented: str) -> tuple[Account, ApiKey]:
        """Resolve (account, key) for a presented ``qk_<key_id>_<secret>`` key. Fail-closed.

        Raises `ApiKeyInvalidError` if the key is malformed, unknown, revoked, or the secret does not
        match. The comparison is constant-time.
        """
        parts = (presented or "").split("_", 2)
        if len(parts) != 3 or parts[0] != "qk":
            raise ApiKeyInvalidError("Malformed API key (expected 'qk_<id>_<secret>').")

        _, key_id, secret = parts
        record = self._accounts.get_api_key(key_id)
        if record is None or record.revoked:
            raise ApiKeyInvalidError(
                "API key is unknown or revoked.", detail={"key_id": key_id}
            )
        if not hmac.compare_digest(record.hashed_secret, self._hash_secret(secret)):
            raise ApiKeyInvalidError("API key secret does not match.", detail={"key_id": key_id})

        account = self._accounts.get_account_by_tenant(record.tenant_id)
        if account is None:
            raise ApiKeyInvalidError(
                "API key has no owning account.", detail={"key_id": key_id}
            )
        return account, record

    def verify_api_key(self, presented: str) -> Account:
        """Resolve the owning `Account` for a presented API key. Fail-closed (see `_verify`)."""
        account, _ = self._verify(presented)
        return account

    def resolve_principal(self, presented: str) -> AuthenticatedPrincipal:
        """Resolve the full `AuthenticatedPrincipal` (tenant, account, key id, scopes) for a key.

        This is what the API auth layer uses: it needs the key's scopes for RBAC, not just the
        account. Fail-closed (see `_verify`).
        """
        account, record = self._verify(presented)
        return AuthenticatedPrincipal(
            tenant_id=record.tenant_id,
            account_id=account.account_id,
            key_id=record.key_id,
            scopes=record.scopes,
        )
