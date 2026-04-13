"""Finance — GST e-Invoice / IRN Generation

NIC e-Invoice API integration (B2B invoices above threshold from policy).
IRN stored in student_invoices.irn.
Feature flag: finance.einvoice_enabled (R11)
Threshold from policy: finance.einvoice_threshold_inr (R1)

When settings.nic_einvoice_configured is False (dev/CI environments), the
service falls back to a SHA-256 stub IRN and logs a WARNING.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

import httpx
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.core.policy_engine import policy_engine
from server.core.settings import settings
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# Redis key prefix for cached NIC auth tokens
_NIC_AUTH_KEY_PREFIX = "alis:nic:auth:"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_feature_flag(org_id: str, flag_key: str) -> bool:
    """Return True if the feature flag is enabled for this tenant."""
    rows = execute_query(
        """
        SELECT flag_value
        FROM tenant_feature_flags
        WHERE org_id = %s AND flag_key = %s
        LIMIT 1
        """,
        (org_id, flag_key),
    )
    if not rows:
        return False
    return str(rows[0]["flag_value"]).lower() == "true"


def _get_redis():
    """Return a Redis client. Returns None if Redis is unavailable."""
    try:
        import redis as _redis_lib

        return _redis_lib.from_url(settings.redis_url, decode_responses=True)
    except Exception:
        return None


def _encrypt_password_aes256(password: str, client_secret: str) -> str:
    """
    Encrypt *password* with AES-256-CBC.

    NIC requirement:
    - Key  = first 32 bytes of client_secret (UTF-8, zero-padded if shorter)
    - IV   = first 16 bytes of client_secret (UTF-8, zero-padded if shorter)
    - Output: base64-encoded ciphertext
    """
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives import padding as sym_padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    key_bytes = client_secret.encode("utf-8")
    key = (key_bytes + b"\x00" * 32)[:32]
    iv = (key_bytes + b"\x00" * 16)[:16]

    padder = sym_padding.PKCS7(128).padder()
    padded = padder.update(password.encode("utf-8")) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    return base64.b64encode(ciphertext).decode("utf-8")


# ---------------------------------------------------------------------------
# NIC API client (internal)
# ---------------------------------------------------------------------------


class _NICClient:
    """Thin wrapper around the NIC e-Invoice REST API."""

    def __init__(self) -> None:
        self._base_url = settings.nic_einvoice_base_url.rstrip("/")
        self._client_id = settings.nic_einvoice_client_id
        self._client_secret = settings.nic_einvoice_client_secret
        self._gstin = settings.nic_einvoice_gstin
        self._username = settings.nic_einvoice_username
        self._password = settings.nic_einvoice_password
        self._timeout = settings.nic_einvoice_timeout_seconds

    # ------------------------------------------------------------------
    # Auth token (with Redis cache)
    # ------------------------------------------------------------------

    def _cache_key(self) -> str:
        return f"{_NIC_AUTH_KEY_PREFIX}{self._gstin}"

    def _get_cached_token(self) -> str | None:
        r = _get_redis()
        if r is None:
            return None
        try:
            return r.get(self._cache_key())
        except Exception:
            return None

    def _cache_token(self, token: str, expiry_str: str) -> None:
        """Cache the auth token with TTL = expiry - 5 minutes."""
        r = _get_redis()
        if r is None:
            return
        try:
            # NIC returns expiry as "DD/MM/YYYY HH:MM:SS" or ISO; attempt both
            try:
                expiry_dt = datetime.strptime(expiry_str, "%d/%m/%Y %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                expiry_dt = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))

            now = datetime.now(timezone.utc)
            ttl_seconds = int((expiry_dt - now).total_seconds()) - 300  # -5 min buffer
            if ttl_seconds > 0:
                r.setex(self._cache_key(), ttl_seconds, token)
        except Exception as exc:
            logger.warning("nic_auth_cache_write_failed | %s", exc)

    def _fetch_auth_token(self) -> str:
        """POST to NIC auth endpoint and return the AuthToken."""
        encrypted_pw = _encrypt_password_aes256(self._password, self._client_secret)
        body = {
            "UserName": self._username,
            "Password": encrypted_pw,
            "AppKey": self._client_id,
            "ForceRefreshAccessToken": False,
        }
        url = f"{self._base_url}/eivital/dec/v1.04/user/authtoken"
        try:
            resp = httpx.post(
                url,
                json=body,
                headers={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BusinessRuleViolation(
                f"NIC auth request failed: HTTP {exc.response.status_code}",
                code="NIC_API_ERROR",
            ) from exc
        except httpx.RequestError as exc:
            raise BusinessRuleViolation(
                f"NIC auth request error: {exc}",
                code="NIC_API_ERROR",
            ) from exc

        data = resp.json()
        if data.get("Status") != 1:
            raise BusinessRuleViolation(
                f"NIC auth returned non-success status: {data.get('Info') or data}",
                code="NIC_API_ERROR",
            )

        token_data = data.get("Data", {})
        token = token_data.get("AuthToken")
        expiry = token_data.get("TokenExpiry", "")
        if not token:
            raise BusinessRuleViolation(
                "NIC auth response missing AuthToken",
                code="NIC_API_ERROR",
            )

        self._cache_token(token, expiry)
        logger.info("nic_auth_token_refreshed | gstin=%s", self._gstin)
        return token

    def get_auth_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid NIC auth token (from cache or freshly fetched)."""
        if not force_refresh:
            cached = self._get_cached_token()
            if cached:
                return cached
        return self._fetch_auth_token()

    # ------------------------------------------------------------------
    # IRN generation
    # ------------------------------------------------------------------

    def generate_irn(self, payload: dict, auth_token: str) -> dict:
        """
        POST the e-invoice payload to NIC and return the IRN response dict.
        Retries once on 401 (stale token).
        """
        url = f"{self._base_url}/eicore/exp/EInvoiceV1_0_3/Invoice"
        headers = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "user_name": self._username,
            "AuthToken": auth_token,
            "Content-Type": "application/json",
        }

        def _do_post(token: str) -> httpx.Response:
            headers["AuthToken"] = token
            return httpx.post(url, json=payload, headers=headers, timeout=self._timeout)

        try:
            resp = _do_post(auth_token)

            # Retry once on 401
            if resp.status_code == 401:
                logger.warning("nic_irn_401_retry | refreshing auth token")
                fresh_token = self.get_auth_token(force_refresh=True)
                resp = _do_post(fresh_token)

            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise BusinessRuleViolation(
                f"NIC IRN request failed: HTTP {exc.response.status_code}",
                code="NIC_API_ERROR",
            ) from exc
        except httpx.RequestError as exc:
            raise BusinessRuleViolation(
                f"NIC IRN request error: {exc}",
                code="NIC_API_ERROR",
            ) from exc

        data = resp.json()
        if data.get("Status") != 1:
            raise BusinessRuleViolation(
                f"NIC IRN generation failed: {data.get('Info') or data}",
                code="NIC_API_ERROR",
            )

        irn_data = data.get("Data", {})
        if not irn_data.get("Irn"):
            raise BusinessRuleViolation(
                "NIC IRN response missing Irn field",
                code="NIC_API_ERROR",
            )
        return irn_data


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------


def _build_nic_payload(invoice: dict, date_str: str) -> dict:
    """
    Construct the NIC e-Invoice JSON payload from a student_invoices row.

    Amounts are INR floats rounded to 2 decimal places.
    BuyerDtls uses "URP" (Unregistered Person) for students without GSTIN.
    """
    amount = round(float(invoice["total_amount"]), 2)
    seller_gstin = settings.nic_einvoice_gstin

    # Derive state code from seller GSTIN (first 2 digits)
    state_code = seller_gstin[:2] if len(seller_gstin) >= 2 else "36"

    seller_name = getattr(settings, "institution_name", None) or "ALIS Institution"

    buyer_name = invoice.get("student_name") or invoice.get("payer_name") or "Student"

    return {
        "Version": "1.1",
        "TranDtls": {
            "TaxSch": "GST",
            "SupTyp": "B2B",
            "RegRev": "N",
            "IgstOnIntra": "N",
        },
        "DocDtls": {
            "Typ": "INV",
            "No": invoice["invoice_number"],
            "Dt": date_str,
        },
        "SellerDtls": {
            "Gstin": seller_gstin,
            "LglNm": seller_name,
            "Addr1": ".",
            "Loc": "Hyderabad",
            "Pin": 500001,
            "Stcd": state_code,
        },
        "BuyerDtls": {
            "Gstin": "URP",
            "LglNm": buyer_name,
            "Pos": state_code,
            "Addr1": ".",
            "Loc": "Hyderabad",
            "Pin": 500001,
            "Stcd": state_code,
        },
        "ItemList": [
            {
                "SlNo": "1",
                "PrdDesc": "Tuition Fee",
                "IsServc": "Y",
                "HsnCd": "999293",
                "Qty": 1.0,
                "Unit": "OTH",
                "UnitPrice": amount,
                "TotAmt": amount,
                "AssAmt": amount,
                "GstRt": 0.0,
                "IgstAmt": 0.0,
                "CgstAmt": 0.0,
                "SgstAmt": 0.0,
                "TotItemVal": amount,
            }
        ],
        "ValDtls": {
            "AssVal": amount,
            "GstVal": 0.0,
            "TotInvVal": amount,
        },
    }


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class EInvoiceService:
    @classmethod
    def should_generate_irn(cls, invoice_amount: float, org_id: str) -> bool:
        """
        Determine whether an IRN must be generated for this invoice amount.

        Rules (R1, R11):
        - Feature flag finance.einvoice_enabled must be true.
        - Invoice amount must be >= policy threshold finance.einvoice_threshold_inr.
        """
        feature_enabled = _check_feature_flag(org_id, "finance.einvoice_enabled")
        if not feature_enabled:
            return False
        threshold = policy_engine.get_value(
            "finance.einvoice_threshold_inr", org_id, default=500000
        )
        return float(invoice_amount) >= float(threshold)

    @classmethod
    def generate_irn(
        cls,
        invoice_id: str,
        org_id: str,
        actor_id: str,
    ) -> dict:
        """
        Generate an IRN for a qualifying invoice.

        Production path (settings.nic_einvoice_configured = True):
          1. Fetch or refresh NIC auth token (Redis-cached).
          2. Build NIC e-Invoice JSON payload from student_invoices row.
          3. POST to NIC IRN generation endpoint; retry once on 401.
          4. Persist Irn, AckNo, AckDt and full payload.
          5. Fire domain event finance.irn_generated.

        Dev/CI fallback (settings.nic_einvoice_configured = False):
          Uses SHA-256 stub IRN — logs a WARNING.
        """
        # ------------------------------------------------------------------
        # 1. Fetch invoice
        # ------------------------------------------------------------------
        rows = execute_query(
            """
            SELECT si.id,
                   si.invoice_number,
                   si.total_amount,
                   si.irn,
                   u.full_name AS student_name
            FROM   student_invoices si
            LEFT JOIN users u ON u.id = si.student_id
            WHERE  si.id = %s AND si.org_id = %s
            """,
            (invoice_id, org_id),
        )
        if not rows:
            raise NotFoundError(
                f"Invoice {invoice_id} not found",
                code="INVOICE_NOT_FOUND",
            )
        invoice = rows[0]

        if invoice["irn"]:
            raise BusinessRuleViolation(
                "IRN already generated for this invoice",
                code="IRN_ALREADY_EXISTS",
            )

        if not cls.should_generate_irn(float(invoice["total_amount"]), org_id):
            raise BusinessRuleViolation(
                "Invoice does not meet e-invoice criteria (feature disabled or below threshold)",
                code="EINVOICE_NOT_REQUIRED",
            )

        # ------------------------------------------------------------------
        # 2. Build payload
        # ------------------------------------------------------------------
        now_utc = datetime.now(timezone.utc)
        date_str = now_utc.strftime("%d/%m/%Y")
        payload = _build_nic_payload(invoice, date_str)

        # ------------------------------------------------------------------
        # 3. Generate IRN — real API or stub
        # ------------------------------------------------------------------
        if settings.nic_einvoice_configured:
            irn, irn_ack_no = cls._call_nic_api(payload)
        else:
            logger.warning(
                "nic_einvoice_not_configured | org=%s invoice=%s — using SHA-256 stub IRN; "
                "set NIC_EINVOICE_CLIENT_ID and NIC_EINVOICE_GSTIN for production",
                org_id,
                invoice_id,
            )
            hash_input = f"{org_id}:{invoice_id}:{now_utc.isoformat()}"
            irn = hashlib.sha256(hash_input.encode()).hexdigest()[:64]
            irn_ack_no = str(uuid4()).replace("-", "")[:16].upper()

        # ------------------------------------------------------------------
        # 4. Persist
        # ------------------------------------------------------------------
        execute_transaction(
            [
                (
                    """
                UPDATE student_invoices
                SET irn              = %s,
                    irn_generated_at = NOW(),
                    irn_ack_no       = %s,
                    einvoice_payload = %s,
                    updated_at       = NOW()
                WHERE id = %s AND org_id = %s
                """,
                    (irn, irn_ack_no, json.dumps(payload), invoice_id, org_id),
                )
            ]
        )
        from server.core.audit import AuditAction, AuditLog

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="student_invoice",
            entity_id=invoice_id,
            tenant_id=org_id,
            metadata={"source": "generate_irn", "irn": irn[:16]},
        )

        # ------------------------------------------------------------------
        # 5. Domain event
        # ------------------------------------------------------------------
        DomainEventBus.publish(
            DomainEvent(
                event_type="finance.irn_generated",
                org_id=org_id,
                payload={
                    "invoice_id": invoice_id,
                    "irn": irn,
                    "invoice_number": invoice["invoice_number"],
                },
                entity_type="invoice",
                entity_id=invoice_id,
                actor_id=actor_id,
            )
        )

        logger.info(
            "irn_generated | org=%s invoice=%s irn=%s actor=%s",
            org_id,
            invoice_id,
            irn[:16] + "...",
            actor_id,
        )

        return {
            "invoice_id": invoice_id,
            "irn": irn,
            "irn_generated_at": now_utc.isoformat(),
            "irn_ack_no": irn_ack_no,
        }

    @classmethod
    def _call_nic_api(cls, payload: dict) -> tuple[str, str]:
        """
        Authenticate with NIC and submit the e-invoice payload.
        Returns (irn, ack_no).
        Raises BusinessRuleViolation with code NIC_API_ERROR on failure.
        """
        client = _NICClient()
        auth_token = client.get_auth_token()
        irn_data = client.generate_irn(payload, auth_token)

        irn = irn_data["Irn"]
        ack_no = str(irn_data.get("AckNo", ""))

        logger.info(
            "nic_irn_received | irn=%s ack_no=%s ack_dt=%s",
            irn[:16] + "...",
            ack_no,
            irn_data.get("AckDt"),
        )
        return irn, ack_no

    @classmethod
    def get_irn_status(cls, invoice_id: str, org_id: str) -> dict:
        """Return the current IRN status for an invoice."""
        rows = execute_query(
            """
            SELECT id, invoice_number, irn, irn_generated_at, irn_ack_no
            FROM student_invoices
            WHERE id = %s AND org_id = %s
            """,
            (invoice_id, org_id),
        )
        if not rows:
            raise NotFoundError(
                f"Invoice {invoice_id} not found",
                code="INVOICE_NOT_FOUND",
            )
        r = rows[0]
        return {
            "invoice_id": invoice_id,
            "invoice_number": r["invoice_number"],
            "irn": r["irn"],
            "irn_generated_at": r["irn_generated_at"].isoformat()
            if r["irn_generated_at"]
            else None,
            "irn_ack_no": r["irn_ack_no"],
            "has_irn": bool(r["irn"]),
        }
