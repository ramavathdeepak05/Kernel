"""
P14 — DigiLocker Integration

Pulls government-verified documents from DigiLocker (India's national digital
document wallet) for applicants who chose DIGILOCKER verification mode.

OAuth2 flow:
  1. Redirect applicant to DigiLocker auth URL
  2. Exchange code for access token
  3. Pull document list + fetch specific document files

All HTTP calls are isolated in this module. The rest of ALIS never touches
DigiLocker directly — it calls this client and receives plain dicts.

When not configured (settings.digilocker_enabled == False), all methods
return None / empty results so the workflow degrades gracefully.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Document types DigiLocker can provide
DIGILOCKER_DOC_TYPES = {
    "AADHAAR": "in.gov.uidai.aadhaar-reg-cert",
    "DRIVING_LICENSE": "in.gov.morth.driving-licence",
    "MARKSHEET_10": "in.gov.cbse.10-marksheet",
    "MARKSHEET_12": "in.gov.cbse.12-marksheet",
    "DEGREE": "in.gov.ugc.degree-cert",
    "BIRTH_CERTIFICATE": "in.gov.registrar.birth-cert",
    "CASTE_CERTIFICATE": "in.gov.gov.caste-cert",
    "INCOME_CERTIFICATE": "in.gov.gov.income-cert",
}


@dataclass
class DigiLockerDocument:
    doc_type: str           # ALIS doc type key
    issuer: str             # DigiLocker issuer URI
    name: str               # Document name
    size: Optional[int]     # File size in bytes
    mime_type: str          # application/pdf | image/jpeg
    uri: str                # DigiLocker document URI
    is_valid: bool          # DigiLocker verification status
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DigiLockerPullResult:
    success: bool
    documents: List[DigiLockerDocument]
    error: Optional[str] = None
    token_used: Optional[str] = None


class DigiLockerClient:
    """
    Client for the DigiLocker Public API.

    Usage:
        client = DigiLockerClient()
        if not client.is_enabled():
            # Fall back to manual document upload
            return

        auth_url = client.get_auth_url(state="app-001")
        # ... redirect applicant ...
        token = client.exchange_code(code="abc123")
        result = client.pull_documents(access_token=token["access_token"])
    """

    BASE_URL: str

    def __init__(self) -> None:
        from server.core.settings import settings
        self._settings = settings
        self.BASE_URL = settings.digilocker_base_url

    def is_enabled(self) -> bool:
        return self._settings.digilocker_enabled

    def get_auth_url(self, state: str) -> str:
        """
        Build the OAuth2 authorization URL to redirect the applicant to DigiLocker.

        The applicant authorises ALIS to pull their documents. DigiLocker then
        redirects to our redirect_uri with a ?code=... parameter.
        """
        if not self.is_enabled():
            raise RuntimeError("DigiLocker integration is not configured.")

        params = {
            "response_type": "code",
            "client_id": self._settings.digilocker_client_id,
            "redirect_uri": self._settings.digilocker_redirect_uri,
            "state": state,
            "scope": "files.pull",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.BASE_URL}/authorize?{query}"

    def exchange_code(self, code: str) -> Dict[str, Any]:
        """
        Exchange the authorization code for an access token.

        Returns dict with: access_token, token_type, expires_in, refresh_token
        """
        if not self.is_enabled():
            raise RuntimeError("DigiLocker integration is not configured.")

        import httpx
        timeout = self._settings.digilocker_timeout_seconds

        try:
            resp = httpx.post(
                f"{self.BASE_URL}/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self._settings.digilocker_redirect_uri,
                    "client_id": self._settings.digilocker_client_id,
                    "client_secret": self._settings.digilocker_client_secret,
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            token_data = resp.json()
            logger.info("DigiLocker: token exchanged successfully")
            return token_data
        except Exception as exc:
            logger.error("DigiLocker: token exchange failed — %s", exc)
            raise

    def pull_documents(self, access_token: str) -> DigiLockerPullResult:
        """
        Fetch the list of issued documents from DigiLocker for the authenticated user.

        Returns a DigiLockerPullResult with all available documents.
        """
        if not self.is_enabled():
            return DigiLockerPullResult(success=False, documents=[], error="DigiLocker not configured")

        import httpx
        timeout = self._settings.digilocker_timeout_seconds
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            resp = httpx.get(
                f"{self.BASE_URL}/files/issued",
                headers=headers,
                timeout=timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            documents = self._parse_documents(data.get("items", []))
            logger.info("DigiLocker: pulled %d documents", len(documents))
            return DigiLockerPullResult(
                success=True,
                documents=documents,
                token_used=access_token[:8] + "…",
            )
        except Exception as exc:
            logger.error("DigiLocker: document pull failed — %s", exc)
            return DigiLockerPullResult(success=False, documents=[], error=str(exc))

    def fetch_document_file(
        self, access_token: str, doc_uri: str
    ) -> Optional[bytes]:
        """
        Download the actual file bytes for a specific DigiLocker document URI.
        Returns None on failure.
        """
        if not self.is_enabled():
            return None

        import httpx
        timeout = self._settings.digilocker_timeout_seconds
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            resp = httpx.get(doc_uri, headers=headers, timeout=timeout)
            resp.raise_for_status()
            logger.info("DigiLocker: downloaded file [%d bytes]", len(resp.content))
            return resp.content
        except Exception as exc:
            logger.error("DigiLocker: file download failed — %s", exc)
            return None

    def _parse_documents(self, items: List[Dict[str, Any]]) -> List[DigiLockerDocument]:
        docs = []
        for item in items:
            issuer = item.get("issuer", "")
            doc_type = self._issuer_to_doc_type(issuer)
            docs.append(DigiLockerDocument(
                doc_type=doc_type,
                issuer=issuer,
                name=item.get("name", ""),
                size=item.get("size"),
                mime_type=item.get("mime", "application/pdf"),
                uri=item.get("uri", ""),
                is_valid=item.get("validFrom") is not None,
                raw=item,
            ))
        return docs

    def _issuer_to_doc_type(self, issuer: str) -> str:
        """Reverse-map DigiLocker issuer URI to ALIS doc_type key."""
        reverse = {v: k for k, v in DIGILOCKER_DOC_TYPES.items()}
        return reverse.get(issuer, "OTHER")
