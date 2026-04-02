"""
P14 Integration Tests

Tests for all 7 integration clients and the integrations router.
All external HTTP calls are mocked — no real network calls required.

Coverage:
  - DigiLockerClient: auth URL, code exchange, doc pull, file download
  - NTAScoreClient: fetch score, verify candidate, parse scorecard
  - LMSSyncClient: create student (live + stub), deactivate
  - EmailProvisionClient: Google, Microsoft, stub
  - PaymentGatewayClient: Razorpay create/verify/refund, PayU hash
  - SMSGatewayClient: MSG91/Twilio OTP send/verify, bulk SMS
  - DocumentStorageClient: upload/download/delete/list/presign (S3 + local)
  - IntegrationsRouter: health, DigiLocker, NTA, SMS, presign endpoints
"""

from __future__ import annotations

import hashlib
import hmac
from decimal import Decimal
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

import pytest


# =============================================================================
# HELPERS
# =============================================================================

def _mock_settings(**overrides):
    """Return a mock settings object with safe defaults + overrides."""
    defaults = {
        # DigiLocker
        "digilocker_enabled": True,
        "digilocker_client_id": "test-client-id",
        "digilocker_client_secret": "test-client-secret",
        "digilocker_base_url": "https://api.digitallocker.gov.in/public/oauth2/1",
        "digilocker_redirect_uri": "https://alis.test/callback",
        "digilocker_timeout_seconds": 5,
        # NTA
        "nta_enabled": True,
        "nta_api_key": "nta-test-key",
        "nta_base_url": "https://api.nta.ac.in/v1",
        "nta_timeout_seconds": 5,
        # LMS
        "lms_enabled": True,
        "lms_base_url": "https://moodle.test",
        "lms_api_token": "moodle-test-token",
        "lms_timeout_seconds": 5,
        # Email Provision
        "email_provision_enabled": False,
        "email_provider": "",
        "google_domain": "university.edu",
        "google_admin_email": "admin@university.edu",
        "google_service_account_json": "{}",
        "ms_domain": "university.edu",
        "ms_tenant_id": "tenant-id",
        "ms_client_id": "client-id",
        "ms_client_secret": "client-secret",
        # Payment
        "payment_gateway_enabled": True,
        "payment_gateway_provider": "RAZORPAY",
        "payment_gateway_timeout_seconds": 5,
        "razorpay_key_id": "rzp_test_key",
        "razorpay_key_secret": "rzp_test_secret",
        "payu_merchant_key": "payu_key",
        "payu_merchant_salt": "payu_salt",
        # SMS
        "sms_gateway_enabled": True,
        "sms_provider": "MSG91",
        "sms_timeout_seconds": 5,
        "msg91_auth_key": "msg91-key",
        "msg91_otp_template_id": "tmpl-001",
        "msg91_sender_id": "ALISUN",
        "twilio_account_sid": "ACxxxxxxx",
        "twilio_auth_token": "twilio-token",
        "twilio_verify_service_sid": "VAxxxxxxx",
        "twilio_from_number": "+15005550006",
        # Storage
        "storage_provider": "LOCAL",
        "storage_bucket": "alis-test",
        "storage_region": "ap-south-1",
        "alis_data_dir": "/tmp/alis-test",
        "aws_access_key_id": "",
        "aws_secret_access_key": "",
        "azure_storage_connection_string": "",
        "azure_storage_account_name": "",
        "azure_storage_account_key": "",
    }
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


# =============================================================================
# DIGILOCKER CLIENT
# =============================================================================

class TestDigiLockerClient:
    def _make_client(self, **kw):
        from server.admissions.integrations.digilocker import DigiLockerClient
        client = DigiLockerClient.__new__(DigiLockerClient)
        client._settings = _mock_settings(**kw)
        client.BASE_URL = client._settings.digilocker_base_url
        return client

    def test_is_enabled_true(self):
        client = self._make_client()
        assert client.is_enabled() is True

    def test_is_enabled_false(self):
        client = self._make_client(digilocker_enabled=False)
        assert client.is_enabled() is False

    def test_get_auth_url_contains_client_id(self):
        client = self._make_client()
        url = client.get_auth_url(state="test-state")
        assert "client_id=test-client-id" in url
        assert "state=test-state" in url
        assert "response_type=code" in url

    def test_get_auth_url_raises_when_disabled(self):
        client = self._make_client(digilocker_enabled=False)
        with pytest.raises(RuntimeError, match="not configured"):
            client.get_auth_url(state="s")

    def test_exchange_code_success(self):
        client = self._make_client()
        mock_resp = Mock()
        mock_resp.json.return_value = {"access_token": "tok123", "expires_in": 3600}
        mock_resp.raise_for_status = Mock()

        with patch("httpx.post", return_value=mock_resp):
            result = client.exchange_code(code="auth-code-abc")

        assert result["access_token"] == "tok123"

    def test_exchange_code_raises_when_disabled(self):
        client = self._make_client(digilocker_enabled=False)
        with pytest.raises(RuntimeError, match="not configured"):
            client.exchange_code(code="x")

    def test_pull_documents_success(self):
        client = self._make_client()
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "items": [
                {
                    "issuer": "in.gov.cbse.12-marksheet",
                    "name": "Class XII Marksheet",
                    "size": 102400,
                    "mime": "application/pdf",
                    "uri": "https://digilocker.gov.in/docs/abc",
                    "validFrom": "2023-01-01",
                }
            ]
        }
        with patch("httpx.get", return_value=mock_resp):
            result = client.pull_documents(access_token="tok123")

        assert result.success is True
        assert len(result.documents) == 1
        assert result.documents[0].doc_type == "MARKSHEET_12"

    def test_pull_documents_disabled_returns_failure(self):
        client = self._make_client(digilocker_enabled=False)
        result = client.pull_documents(access_token="tok")
        assert result.success is False

    def test_fetch_document_file_success(self):
        client = self._make_client()
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.content = b"%PDF-fake-content"
        with patch("httpx.get", return_value=mock_resp):
            content = client.fetch_document_file("tok123", "https://digilocker.gov.in/doc/x")
        assert content == b"%PDF-fake-content"

    def test_fetch_document_file_disabled_returns_none(self):
        client = self._make_client(digilocker_enabled=False)
        result = client.fetch_document_file("tok", "https://example.com/doc")
        assert result is None


# =============================================================================
# NTA SCORE CLIENT
# =============================================================================

class TestNTAScoreClient:
    def _make_client(self, **kw):
        from server.admissions.integrations.nta_scores import NTAScoreClient
        client = NTAScoreClient.__new__(NTAScoreClient)
        client._settings = _mock_settings(**kw)
        return client

    def test_is_enabled_true(self):
        assert self._make_client().is_enabled() is True

    def test_is_enabled_false(self):
        assert self._make_client(nta_enabled=False).is_enabled() is False

    def test_fetch_score_success(self):
        client = self._make_client()
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "candidate_name": "Priya Sharma",
            "dob": "2004-05-14",
            "roll_number": "240110012345",
            "total_marks": 285.0,
            "percentile": 99.5,
            "rank": 1200,
            "category_rank": 300,
            "subjects": [
                {"name": "Physics", "marks": 90.0},
                {"name": "Chemistry", "marks": 95.0},
                {"name": "Mathematics", "marks": 100.0},
            ],
        }
        with patch("httpx.get", return_value=mock_resp):
            result = client.fetch_score("JEE_MAIN", "240110012345", "2004-05-14")

        assert result.success is True
        assert result.score_card.percentile == 99.5
        assert result.score_card.rank == 1200
        assert result.score_card.subject_scores["Mathematics"] == 100.0

    def test_fetch_score_disabled(self):
        client = self._make_client(nta_enabled=False)
        result = client.fetch_score("JEE_MAIN", "app-num", "2004-01-01")
        assert result.success is False
        assert "not configured" in result.error

    def test_fetch_score_invalid_exam_type(self):
        client = self._make_client()
        result = client.fetch_score("INVALID_EXAM", "app-num", "2004-01-01")
        assert result.success is False
        assert "Unknown exam type" in result.error

    def test_verify_candidate_true(self):
        client = self._make_client()
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "candidate_name": "Test", "dob": "2004-01-01",
            "roll_number": "R001", "total_marks": 200.0,
            "percentile": 80.0, "rank": 5000, "category_rank": None,
            "subjects": [],
        }
        with patch("httpx.get", return_value=mock_resp):
            assert client.verify_candidate("NEET_UG", "app-001", "2004-01-01") is True

    def test_verify_candidate_false_on_error(self):
        client = self._make_client()
        with patch("httpx.get", side_effect=Exception("timeout")):
            assert client.verify_candidate("JEE_MAIN", "bad-app", "2004-01-01") is False


# =============================================================================
# LMS SYNC CLIENT
# =============================================================================

class TestLMSSyncClient:
    """P40: LMS tombstoned — Moodle replaced by in-house LMS."""

    def test_stub_mode_returns_success(self):
        from server.admissions.integrations.lms_sync import LMSSyncClient
        client = LMSSyncClient()
        result = client.create_student(
            roll_number="CS-2025-0001",
            email="student@test.com",
            full_name="John Doe",
            program="Computer Science",
        )
        assert result.success is True
        assert result.is_stub is True

    def test_tombstone_is_never_enabled(self):
        from server.admissions.integrations.lms_sync import LMSSyncClient
        client = LMSSyncClient()
        assert client.is_enabled() is False

    def test_deactivate_student_stub_returns_true(self):
        from server.admissions.integrations.lms_sync import LMSSyncClient
        client = LMSSyncClient()
        assert client.deactivate_student("STUB-CS-2025-0001") is True

    def test_create_student_returns_no_user_object(self):
        from server.admissions.integrations.lms_sync import LMSSyncClient
        client = LMSSyncClient()
        result = client.create_student("CS-2025-0001", "a@b.com", "Test", "CS")
        assert result.user is None


# =============================================================================
# EMAIL PROVISION CLIENT
# =============================================================================

class TestEmailProvisionClient:
    def _make_client(self, **kw):
        from server.admissions.integrations.email_provision import EmailProvisionClient
        client = EmailProvisionClient.__new__(EmailProvisionClient)
        client._settings = _mock_settings(**kw)
        return client

    def test_stub_mode(self):
        client = self._make_client(email_provider="")
        result = client.create_student_email("Priya Sharma", "CS-2025-0001")
        assert result.success is True
        assert result.provider == "STUB"
        assert "@university.local" in result.university_email

    def test_google_mode(self):
        client = self._make_client(email_provision_enabled=True, email_provider="GOOGLE")
        mock_service = MagicMock()
        mock_service.users.return_value.insert.return_value.execute.return_value = {}
        with patch.object(client, "_google_directory_service", return_value=mock_service):
            result = client.create_student_email("Priya Sharma", "CS-2025-0001")
        assert result.success is True
        assert result.provider == "GOOGLE"
        assert "@university.edu" in result.university_email

    def test_microsoft_mode(self):
        client = self._make_client(email_provision_enabled=True, email_provider="MICROSOFT")
        mock_token_resp = Mock()
        mock_token_resp.raise_for_status = Mock()
        mock_token_resp.json.return_value = {"access_token": "ms-token"}
        mock_create_resp = Mock()
        mock_create_resp.raise_for_status = Mock()
        mock_create_resp.status_code = 201

        with patch("httpx.post", side_effect=[mock_token_resp, mock_create_resp]):
            result = client.create_student_email("Rahul Kumar", "MBA-2025-0010")

        assert result.success is True
        assert result.provider == "MICROSOFT"

    def test_username_derivation(self):
        from server.admissions.integrations.email_provision import _derive_username
        username = _derive_username("Priya Sharma", "CS-2025-0001")
        assert username.startswith("priya.sharma.")


# =============================================================================
# PAYMENT GATEWAY CLIENT
# =============================================================================

class TestPaymentGatewayClient:
    def _make_client(self, **kw):
        from server.admissions.integrations.payment_gateway import PaymentGatewayClient
        client = PaymentGatewayClient.__new__(PaymentGatewayClient)
        client._settings = _mock_settings(**kw)
        client._provider = kw.get("payment_gateway_provider", "RAZORPAY")
        return client

    def test_is_enabled(self):
        assert self._make_client().is_enabled() is True
        assert self._make_client(payment_gateway_enabled=False).is_enabled() is False

    def test_razorpay_create_order(self):
        client = self._make_client()
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "id": "order_test123",
            "amount": 2500000,
            "currency": "INR",
            "status": "created",
        }
        with patch("httpx.post", return_value=mock_resp):
            order = client.create_order(
                amount=Decimal("25000.00"),
                receipt="APP-2025-000001",
            )
        assert order.order_id == "order_test123"
        assert order.amount_paise == 2500000
        assert order.provider == "RAZORPAY"

    def test_payu_create_order(self):
        client = self._make_client(payment_gateway_provider="PAYU")
        client._provider = "PAYU"
        order = client.create_order(
            amount=Decimal("15000.00"),
            receipt="APP-2025-000002",
        )
        assert order.provider == "PAYU"
        assert "hash" in order.raw
        assert order.amount_paise == 1500000

    def test_razorpay_verify_payment_valid(self):
        client = self._make_client()
        order_id = "order_test123"
        payment_id = "pay_test456"
        # Generate correct signature
        message = f"{order_id}|{payment_id}"
        expected_sig = hmac.new(
            b"rzp_test_secret",
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        mock_fetch = Mock()
        mock_fetch.raise_for_status = Mock()
        mock_fetch.json.return_value = {"amount": 2500000, "method": "upi"}
        with patch("httpx.get", return_value=mock_fetch):
            result = client.verify_payment(order_id, payment_id, expected_sig)

        assert result.is_valid is True
        assert result.method == "upi"

    def test_razorpay_verify_payment_invalid_signature(self):
        client = self._make_client()
        result = client.verify_payment("order_x", "pay_x", "bad-signature")
        assert result.is_valid is False

    def test_razorpay_refund(self):
        client = self._make_client()
        mock_resp = Mock()
        mock_resp.raise_for_status = Mock()
        mock_resp.json.return_value = {
            "id": "rfnd_test001",
            "amount": 500000,
            "status": "processed",
        }
        with patch("httpx.post", return_value=mock_resp):
            result = client.refund_payment("pay_test456", amount=Decimal("5000.00"))

        assert result.refund_id == "rfnd_test001"
        assert result.status == "processed"

    def test_require_enabled_raises(self):
        client = self._make_client(payment_gateway_enabled=False)
        with pytest.raises(RuntimeError, match="not configured"):
            client._require_enabled()


# =============================================================================
# SMS GATEWAY CLIENT
# =============================================================================

class TestSMSGatewayClient:
    def _make_client(self, **kw):
        from server.admissions.integrations.sms_gateway import SMSGatewayClient
        client = SMSGatewayClient.__new__(SMSGatewayClient)
        client._settings = _mock_settings(**kw)
        client._provider = kw.get("sms_provider", "MSG91")
        return client

    def test_is_enabled(self):
        assert self._make_client().is_enabled() is True
        assert self._make_client(sms_gateway_enabled=False).is_enabled() is False

    def test_msg91_send_otp_success(self):
        client = self._make_client()
        mock_resp = Mock()
        mock_resp.json.return_value = {"type": "success", "request_id": "req-001"}
        with patch("httpx.post", return_value=mock_resp):
            result = client.send_otp(phone="+919876543210")
        assert result.success is True
        assert result.request_id == "req-001"

    def test_msg91_send_otp_failure(self):
        client = self._make_client()
        mock_resp = Mock()
        mock_resp.json.return_value = {"type": "error", "message": "Invalid auth key"}
        with patch("httpx.post", return_value=mock_resp):
            result = client.send_otp(phone="+919876543210")
        assert result.success is False

    def test_msg91_verify_otp_valid(self):
        client = self._make_client()
        mock_resp = Mock()
        mock_resp.json.return_value = {"type": "success"}
        with patch("httpx.get", return_value=mock_resp):
            result = client.verify_otp(phone="+919876543210", otp="123456")
        assert result.is_valid is True

    def test_msg91_verify_otp_invalid(self):
        client = self._make_client()
        mock_resp = Mock()
        mock_resp.json.return_value = {"type": "error", "message": "OTP mismatch"}
        with patch("httpx.get", return_value=mock_resp):
            result = client.verify_otp(phone="+919876543210", otp="000000")
        assert result.is_valid is False

    def test_twilio_send_otp_success(self):
        client = self._make_client(sms_provider="TWILIO")
        client._provider = "TWILIO"
        mock_resp = Mock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"sid": "VE-twilio-sid"}
        with patch("httpx.post", return_value=mock_resp):
            result = client.send_otp(phone="+15005550006")
        assert result.success is True

    def test_twilio_verify_otp_approved(self):
        client = self._make_client(sms_provider="TWILIO")
        client._provider = "TWILIO"
        mock_resp = Mock()
        mock_resp.json.return_value = {"status": "approved"}
        with patch("httpx.post", return_value=mock_resp):
            result = client.verify_otp(phone="+15005550006", otp="123456")
        assert result.is_valid is True

    def test_sms_disabled_returns_failure(self):
        client = self._make_client(sms_gateway_enabled=False)
        result = client.send_otp(phone="+919876543210")
        assert result.success is False

    def test_bulk_sms_all_success(self):
        client = self._make_client()
        mock_resp = Mock()
        mock_resp.json.return_value = {"type": "success", "request_id": "req-x"}
        with patch("httpx.post", return_value=mock_resp):
            bulk = client.send_bulk(
                recipients=[
                    {"phone": "+919876543210", "message": "Offer ready"},
                    {"phone": "+919876543211", "message": "Offer ready"},
                ]
            )
        assert bulk.total == 2
        assert bulk.sent == 2
        assert bulk.failed == 0

    def test_bulk_sms_disabled(self):
        client = self._make_client(sms_gateway_enabled=False)
        bulk = client.send_bulk(recipients=[{"phone": "+91x", "message": "x"}])
        assert bulk.total == 1
        assert bulk.sent == 0


# =============================================================================
# DOCUMENT STORAGE CLIENT
# =============================================================================

class TestDocumentStorageClient:
    def _make_client(self, tmp_path, **kw):
        from server.admissions.integrations.document_storage import DocumentStorageClient
        client = DocumentStorageClient.__new__(DocumentStorageClient)
        client._settings = _mock_settings(alis_data_dir=str(tmp_path), **kw)
        client._provider = kw.get("storage_provider", "LOCAL")
        client._bucket = "alis-test"
        client._region = "ap-south-1"
        client._local_root = tmp_path / "uploads"
        client._local_root.mkdir(parents=True, exist_ok=True)
        return client

    def test_local_upload_and_download(self, tmp_path):
        client = self._make_client(tmp_path)
        content = b"PDF content here"
        result = client.upload(
            org_id="org-001",
            applicant_id="app-001",
            file_name="marksheet.pdf",
            content=content,
            content_type="application/pdf",
            doc_type="MARKSHEET_12",
        )
        assert result.success is True
        assert result.provider == "LOCAL"
        assert result.size_bytes == len(content)

        dl = client.download(result.storage_key)
        assert dl.success is True
        assert dl.content == content

    def test_local_delete(self, tmp_path):
        client = self._make_client(tmp_path)
        result = client.upload("org-001", "app-001", "doc.pdf", b"data", doc_type="OTHER")
        assert result.success is True
        assert client.delete(result.storage_key) is True

    def test_local_delete_missing_file(self, tmp_path):
        client = self._make_client(tmp_path)
        assert client.delete("nonexistent/file.pdf") is False

    def test_local_list_files(self, tmp_path):
        client = self._make_client(tmp_path)
        client.upload("org-001", "app-001", "a.pdf", b"aaa", doc_type="MARKSHEET_10")
        client.upload("org-001", "app-001", "b.pdf", b"bbb", doc_type="MARKSHEET_12")
        files = client.list_files(org_id="org-001", applicant_id="app-001")
        assert len(files) == 2

    def test_local_download_missing(self, tmp_path):
        client = self._make_client(tmp_path)
        dl = client.download("org-001/app-001/NONE/missing.pdf")
        assert dl.success is False
        assert "not found" in dl.error.lower()

    def test_s3_upload(self, tmp_path):
        import sys
        mock_boto3 = MagicMock()
        mock_s3_client = MagicMock()
        mock_boto3.client.return_value = mock_s3_client

        client = self._make_client(tmp_path, storage_provider="S3")
        client._provider = "S3"

        with patch.dict(sys.modules, {"boto3": mock_boto3}):
            result = client.upload(
                org_id="org-001",
                applicant_id="app-001",
                file_name="cert.pdf",
                content=b"S3 content",
                doc_type="DEGREE",
            )
        assert result.success is True
        assert result.provider == "S3"
        mock_s3_client.put_object.assert_called_once()

    def test_presigned_url_local_returns_none(self, tmp_path):
        client = self._make_client(tmp_path)
        assert client.get_download_url("some/key") is None
        assert client.get_upload_url("some/key") is None

    def test_presigned_url_s3(self, tmp_path):
        import sys
        mock_boto3 = MagicMock()
        mock_s3_client = MagicMock()
        mock_s3_client.generate_presigned_url.return_value = "https://s3.test/presigned"
        mock_boto3.client.return_value = mock_s3_client

        client = self._make_client(tmp_path, storage_provider="S3")
        client._provider = "S3"

        with patch.dict(sys.modules, {"boto3": mock_boto3}):
            url_obj = client.get_download_url("org-001/app-001/DEGREE/abc_cert.pdf", expires_in=3600)
        assert url_obj is not None
        assert url_obj.url == "https://s3.test/presigned"
        assert url_obj.method == "GET"


# =============================================================================
# INTEGRATIONS ROUTER
# =============================================================================

class TestIntegrationsRouter:
    @pytest.fixture(autouse=True)
    def _setup(self, test_client):
        # require_permission passes through without auth in test env (no JWT middleware)
        self.client = test_client
        self.headers = {}

    def test_health_returns_all_integrations(self):
        resp = self.client.get("/api/v1/integrations/health")
        assert resp.status_code == 200
        body = resp.json()
        names = [i["name"] for i in body["integrations"]]
        assert "DigiLocker" in names
        assert "NTA Score Import" in names
        assert "LMS (Moodle)" in names
        assert "Email Provisioning" in names
        assert "Payment Gateway" in names
        assert "SMS Gateway" in names
        assert "Document Storage" in names

    def test_health_document_storage_always_present(self):
        resp = self.client.get("/api/v1/integrations/health", headers=self.headers)
        storage = next(i for i in resp.json()["integrations"] if i["name"] == "Document Storage")
        assert storage["enabled"] is True
        assert storage["status"] == "configured"

    def test_digilocker_auth_url_disabled_returns_503(self):
        resp = self.client.post(
            "/api/v1/integrations/digilocker/auth-url",
            headers={},
            json={"applicant_id": "app-001", "state": "csrf-token"},
        )
        # DigiLocker not configured in test settings → 503
        assert resp.status_code == 503

    def test_nta_import_score_disabled_returns_503(self):
        resp = self.client.post(
            "/api/v1/integrations/nta/import-score",
            headers={},
            json={
                "applicant_id": "app-001",
                "exam_type": "JEE_MAIN",
                "application_number": "240110012345",
                "dob": "2004-05-14",
            },
        )
        # NTA not configured in test env → 503
        assert resp.status_code == 503

    def test_send_otp_disabled_returns_200_with_failure(self):
        """SMS disabled → client returns success=False, not HTTP error."""
        resp = self.client.post(
            "/api/v1/integrations/sms/send-otp",
            headers={},
            json={"phone": "+919876543210"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    def test_verify_otp_disabled_returns_200_with_invalid(self):
        resp = self.client.post(
            "/api/v1/integrations/sms/verify-otp",
            headers={},
            json={"phone": "+919876543210", "otp": "123456"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_valid"] is False

    def test_presign_local_returns_501(self):
        resp = self.client.get(
            "/api/v1/integrations/storage/presign",
            headers={},
            params={
                "org_id": "org-001",
                "applicant_id": "app-001",
                "file_name": "test.pdf",
            },
        )
        # LOCAL storage → no pre-signed URLs → 501
        assert resp.status_code == 501

    def test_health_unauthenticated_still_responds(self):
        """require_permission only blocks roles lacking permission, not missing auth.
        In the test environment (no JWT middleware), unauthenticated requests pass through.
        Production enforcement happens at the gateway/nginx layer.
        """
        resp = self.client.get("/api/v1/integrations/health")
        assert resp.status_code == 200
        assert "integrations" in resp.json()
