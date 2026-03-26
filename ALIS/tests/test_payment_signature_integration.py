"""
Integration test — PaymentService.capture_razorpay_payment

Tests HMAC signature verification against the real production code path.
No mocking of execute_query / execute_transaction — real Postgres.

Strategy:
  - Override conftest autouse mock_db_global and mock_audit_log with no-ops,
    so the service layer uses the real psycopg2 pool.
  - Seed test data via a direct autocommit connection; clean up after.
  - Unique org_id per test run so parallel runs don't collide.

Three scenarios:
  1. Correct signature + secret set  → payment CAPTURED, invoice updated
  2. Wrong signature + secret set    → BusinessRuleViolation, DB untouched
  3. Wrong signature + NO secret set → silently accepted (documents the bug)
  4. Duplicate capture               → idempotent, invoice not double-charged

Run:
    pytest tests/test_payment_signature_integration.py -v -m integration
"""

import datetime
import hashlib
import hmac
import uuid
from unittest.mock import patch

import psycopg2
import psycopg2.extras
import pytest

from server.core.exceptions import BusinessRuleViolation

# ---------------------------------------------------------------------------
# Override conftest autouse fixtures — let real DB calls through
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_db_global():
    """No-op override of conftest mock_db_global: use the real DB."""
    yield


@pytest.fixture(autouse=True)
def mock_audit_log():
    """No-op override of conftest mock_audit_log: let audit writes hit real DB."""
    yield


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WEBHOOK_SECRET = "test-webhook-secret-32-chars-long!!"
RAZORPAY_PAYMENT_ID = f"pay_test_{uuid.uuid4().hex[:14]}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _correct_signature(order_id: str, payment_id: str, secret: str) -> str:
    """Reproduce Razorpay's HMAC-SHA256 signature exactly as the service computes it."""
    return hmac.new(
        secret.encode(),
        f"{order_id}|{payment_id}".encode(),
        "sha256",
    ).hexdigest()


def _wrong_signature() -> str:
    return "0" * 64


def _open_conn() -> psycopg2.extensions.connection:
    """Open a real autocommit psycopg2 connection. Skips if DB unreachable."""
    from server.core.settings import settings
    try:
        conn = psycopg2.connect(
            settings.db_url,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        conn.autocommit = True
        return conn
    except Exception as exc:
        pytest.skip(f"Postgres unreachable — skipping: {exc}")


def _query(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def seeded():
    """
    Seed a unique org → student → invoice → PENDING payment in the real DB.
    Yields IDs for the test; cleans up via DELETE after the test completes.

    Uses autocommit=True so data is immediately visible to the service's
    own psycopg2 connections (which open independently via get_db_connection).
    """
    conn = _open_conn()

    # Unique per-test org_id prevents cross-test contamination
    org_id = f"test-{uuid.uuid4().hex[:8]}"
    student_id = str(uuid.uuid4())
    applicant_id = str(uuid.uuid4())
    invoice_id = str(uuid.uuid4())
    order_id = f"order_test_{uuid.uuid4().hex[:14]}"
    db_payment_id = str(uuid.uuid4())
    invoice_number = f"INV-TEST-{uuid.uuid4().hex[:8]}"
    roll = f"ROLL-{uuid.uuid4().hex[:6]}"
    email = f"inttest_{uuid.uuid4().hex[:8]}@test.invalid"

    # Set tenant so RLS passes on this connection
    with conn.cursor() as cur:
        cur.execute(f"SET LOCAL alis.current_tenant = '{org_id}'")

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO students
                (id, org_id, applicant_id, roll_number, name, email, program)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (student_id, org_id, applicant_id, roll,
              "Integration Test Student", email, "B.Tech"))

        cur.execute("""
            INSERT INTO student_invoices
                (id, org_id, student_id, academic_year, invoice_number,
                 amount_due, due_date, generated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (invoice_id, org_id, student_id, "2025-26",
              invoice_number, 25000.00, datetime.date.today(), "test-actor"))

        cur.execute("""
            INSERT INTO payments
                (id, org_id, student_id, invoice_id, amount,
                 method, status, razorpay_order_id)
            VALUES (%s, %s, %s, %s, %s, 'RAZORPAY', 'PENDING', %s)
        """, (db_payment_id, org_id, student_id, invoice_id, 25000.00, order_id))

    # Expose IDs to test; also expose conn for post-test assertions
    data = {
        "org_id": org_id,
        "student_id": student_id,
        "invoice_id": invoice_id,
        "order_id": order_id,
        "db_payment_id": db_payment_id,
        "_conn": conn,
    }

    yield data

    # Teardown: delete all test data (FK order: payments → invoices → students)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM payments WHERE org_id = %s", (org_id,))
        cur.execute("DELETE FROM student_invoices WHERE org_id = %s", (org_id,))
        cur.execute("DELETE FROM students WHERE org_id = %s", (org_id,))

    conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRazorpaySignatureVerification:

    def test_correct_signature_captures_payment(self, seeded):
        """
        Correct HMAC-SHA256 signature + webhook secret set
        → payment becomes CAPTURED, invoice amount_paid updated to 25000.
        """
        from server.finance.payment import PaymentService

        org_id = seeded["org_id"]
        invoice_id = seeded["invoice_id"]
        order_id = seeded["order_id"]
        conn = seeded["_conn"]
        sig = _correct_signature(order_id, RAZORPAY_PAYMENT_ID, WEBHOOK_SECRET)

        with patch("server.core.settings.settings.razorpay_webhook_secret", WEBHOOK_SECRET):
            result = PaymentService.capture_razorpay_payment(
                org_id=org_id,
                invoice_id=invoice_id,
                razorpay_order_id=order_id,
                razorpay_payment_id=RAZORPAY_PAYMENT_ID,
                razorpay_signature=sig,
            )

        assert result["status"] == "captured"
        assert result["invoice_id"] == invoice_id

        payment_row = _query(
            conn,
            "SELECT status, razorpay_payment_id FROM payments WHERE razorpay_order_id = %s",
            (order_id,),
        )
        assert payment_row is not None
        assert payment_row["status"] == "CAPTURED", (
            f"Expected CAPTURED, got {payment_row['status']}"
        )
        assert payment_row["razorpay_payment_id"] == RAZORPAY_PAYMENT_ID

        invoice_row = _query(
            conn,
            "SELECT amount_paid, status FROM student_invoices WHERE id = %s",
            (invoice_id,),
        )
        assert float(invoice_row["amount_paid"]) == 25000.00
        assert invoice_row["status"] == "PAID"

    def test_wrong_signature_with_secret_set_raises_and_leaves_db_untouched(self, seeded):
        """
        Wrong signature + webhook secret configured
        → BusinessRuleViolation raised, payment row stays PENDING.
        """
        from server.finance.payment import PaymentService

        org_id = seeded["org_id"]
        invoice_id = seeded["invoice_id"]
        order_id = seeded["order_id"]
        conn = seeded["_conn"]

        with patch("server.core.settings.settings.razorpay_webhook_secret", WEBHOOK_SECRET):
            with pytest.raises(BusinessRuleViolation, match="Invalid Razorpay signature"):
                PaymentService.capture_razorpay_payment(
                    org_id=org_id,
                    invoice_id=invoice_id,
                    razorpay_order_id=order_id,
                    razorpay_payment_id=RAZORPAY_PAYMENT_ID,
                    razorpay_signature=_wrong_signature(),
                )

        # DB must be untouched
        payment_row = _query(
            conn,
            "SELECT status FROM payments WHERE razorpay_order_id = %s",
            (order_id,),
        )
        assert payment_row["status"] == "PENDING", (
            f"Payment mutated despite bad signature — got {payment_row['status']}"
        )

    def test_missing_secret_raises_business_rule_violation(self, seeded):
        """
        Payment rejected when RAZORPAY_WEBHOOK_SECRET is not configured — security fix verified.

        When razorpay_webhook_secret is empty, capture_razorpay_payment must raise
        BusinessRuleViolation immediately, before any DB write. No webhook should be
        accepted without a configured secret.
        """
        from server.finance.payment import PaymentService

        org_id = seeded["org_id"]
        invoice_id = seeded["invoice_id"]
        order_id = seeded["order_id"]
        conn = seeded["_conn"]

        # Secret is "" — default when RAZORPAY_WEBHOOK_SECRET is not in .env
        with patch("server.core.settings.settings.razorpay_webhook_secret", ""):
            with pytest.raises(BusinessRuleViolation, match="Razorpay webhook secret not configured"):
                PaymentService.capture_razorpay_payment(
                    org_id=org_id,
                    invoice_id=invoice_id,
                    razorpay_order_id=order_id,
                    razorpay_payment_id=RAZORPAY_PAYMENT_ID,
                    razorpay_signature=_wrong_signature(),
                )

        # DB must be untouched — no payment captured
        payment_row = _query(
            conn,
            "SELECT status FROM payments WHERE razorpay_order_id = %s",
            (order_id,),
        )
        assert payment_row["status"] == "PENDING", (
            f"Payment should remain PENDING when secret is missing, got {payment_row['status']}"
        )

    def test_idempotent_second_capture_does_not_double_charge(self, seeded):
        """
        Calling capture_razorpay_payment twice with the same razorpay_payment_id
        → second call returns 'already_captured'.
        → invoice amount_paid is 25000, not 50000.
        """
        from server.finance.payment import PaymentService

        org_id = seeded["org_id"]
        invoice_id = seeded["invoice_id"]
        order_id = seeded["order_id"]
        conn = seeded["_conn"]
        sig = _correct_signature(order_id, RAZORPAY_PAYMENT_ID, WEBHOOK_SECRET)

        with patch("server.core.settings.settings.razorpay_webhook_secret", WEBHOOK_SECRET):
            result1 = PaymentService.capture_razorpay_payment(
                org_id=org_id,
                invoice_id=invoice_id,
                razorpay_order_id=order_id,
                razorpay_payment_id=RAZORPAY_PAYMENT_ID,
                razorpay_signature=sig,
            )
            result2 = PaymentService.capture_razorpay_payment(
                org_id=org_id,
                invoice_id=invoice_id,
                razorpay_order_id=order_id,
                razorpay_payment_id=RAZORPAY_PAYMENT_ID,
                razorpay_signature=sig,
            )

        assert result1["status"] == "captured"
        assert result2["status"] == "already_captured"

        invoice_row = _query(
            conn,
            "SELECT amount_paid FROM student_invoices WHERE id = %s",
            (invoice_id,),
        )
        assert float(invoice_row["amount_paid"]) == 25000.00, (
            f"Double-charge detected — amount_paid is {invoice_row['amount_paid']}, expected 25000.00"
        )
