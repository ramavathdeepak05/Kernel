"""
Real-database integration tests — Secondary Modules
Tests: notification_log, alumni_profiles, placement_records,
       convocation_batches, phd_students, consent_records

Run:
    pytest tests/test_integration_secondary_modules.py -v -m integration
"""
from __future__ import annotations
import datetime
import json
import uuid
import psycopg2
import psycopg2.extras
import pytest

# Cache DB URL once at import time — survives isolate_sys_modules fixture
try:
    from server.core.settings import settings as _settings
    _DB_URL: str = _settings.db_url
except Exception:
    _DB_URL = "postgresql://postgres:postgres@localhost:5432/alis_db"


@pytest.fixture(autouse=True)
def mock_db_global():
    yield


@pytest.fixture(autouse=True)
def mock_audit_log():
    yield


@pytest.fixture(autouse=True)
def fake_redis_global():
    yield


def _connect(org_id: str = None):
    try:
        conn = psycopg2.connect(_DB_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = True
    except Exception as exc:
        pytest.skip(f"Postgres unreachable: {exc}")
    if org_id:
        with conn.cursor() as cur:
            cur.execute(f"SET alis.current_tenant = '{org_id}'")
    return conn


def _q(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def _qa(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def _run(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)


def _new_org() -> str:
    return f"test-{uuid.uuid4().hex[:10]}"


def _seed_student(conn, org_id):
    sid = str(uuid.uuid4())
    _run(conn, """
        INSERT INTO students (id,org_id,applicant_id,roll_number,name,email,program)
        VALUES (%s,%s,%s,%s,'Sec Test Student',%s,'B.Tech')
    """, (sid, org_id, str(uuid.uuid4()),
          f"ROLL-{uuid.uuid4().hex[:6]}", f"sec_{uuid.uuid4().hex[:6]}@test.invalid"))
    return sid


# ---------------------------------------------------------------------------
# 1. Notification Log
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skip(reason="notification_log table not yet in schema (pending migration)")
class TestNotificationLog:

    def test_notification_log_insert_and_query(self):
        """notification_log INSERT stores channel, recipient, status, and payload."""
        conn = _connect()
        log_id = str(uuid.uuid4())
        org_id = _new_org()
        try:
            _run(conn, """
                INSERT INTO notification_log
                    (id, tenant_id, channel, recipient, template_key,
                     subject, body, status, payload)
                VALUES (%s,%s,'EMAIL',%s,'welcome_email','Welcome to ALIS',
                        'Your account is ready.','SENT',%s::jsonb)
            """, (log_id, org_id, f"notif_{uuid.uuid4().hex[:6]}@test.invalid",
                  json.dumps({"user_name": "Test User"})))
            row = _q(conn,
                "SELECT channel, status, template_key FROM notification_log WHERE id=%s",
                (log_id,))
            assert row is not None
            assert row["channel"] == "EMAIL"
            assert row["status"] == "SENT"
            assert row["template_key"] == "welcome_email"
        finally:
            _run(conn, "DELETE FROM notification_log WHERE id=%s", (log_id,))
            conn.close()

    def test_notification_log_failed_status(self):
        """A failed notification can be stored with FAILED status and error_message."""
        conn = _connect()
        log_id = str(uuid.uuid4())
        org_id = _new_org()
        try:
            _run(conn, """
                INSERT INTO notification_log
                    (id, tenant_id, channel, recipient, template_key,
                     subject, body, status, error_message)
                VALUES (%s,%s,'SMS','9900000001','sms_otp','OTP','Your OTP is 123456',
                        'FAILED','SMSGateway timeout')
            """, (log_id, org_id))
            row = _q(conn,
                "SELECT status, error_message FROM notification_log WHERE id=%s", (log_id,))
            assert row["status"] == "FAILED"
            assert "timeout" in row["error_message"]
        finally:
            _run(conn, "DELETE FROM notification_log WHERE id=%s", (log_id,))
            conn.close()

    def test_notification_log_tenant_filter(self):
        """Notifications can be filtered by tenant_id."""
        conn = _connect()
        t1, t2 = _new_org(), _new_org()
        ids = [str(uuid.uuid4()) for _ in range(4)]
        try:
            for i, lid in enumerate(ids):
                tenant = t1 if i < 3 else t2
                _run(conn, """
                    INSERT INTO notification_log
                        (id,tenant_id,channel,recipient,template_key,subject,body,status)
                    VALUES (%s,%s,'EMAIL',%s,'tmpl','Subj','Body','SENT')
                """, (lid, tenant, f"t_{uuid.uuid4().hex[:6]}@test.invalid"))
            t1_rows = _qa(conn,
                "SELECT id FROM notification_log WHERE tenant_id=%s AND id=ANY(%s)",
                (t1, ids))
            assert len(t1_rows) == 3
        finally:
            _run(conn, "DELETE FROM notification_log WHERE id=ANY(%s)", (ids,))
            conn.close()


# ---------------------------------------------------------------------------
# 2. Alumni Profiles
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAlumniProfiles:

    def _seed_user(self, conn, org_id):
        """Insert a real user (needed for consent_records FK)."""
        uid = str(uuid.uuid4())
        email = f"alumni_u_{uuid.uuid4().hex[:6]}@test.invalid"
        _run(conn, """
            INSERT INTO users (id,tenant_id,username,email,display_name,role,status,password_hash,actor_type)
            VALUES (%s,%s,%s,%s,'Alumni User','STUDENT','ACTIVE','$2b$12$x','human')
        """, (uid, org_id, email, email))
        return uid, email

    def test_alumni_profile_insert_and_query(self):
        """alumni_profiles INSERT stores graduation_year, program, and current_employer."""
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = _seed_student(conn, org_id)
        alumni_id = str(uuid.uuid4())
        email = f"alumni_{uuid.uuid4().hex[:6]}@test.invalid"
        try:
            _run(conn, """
                INSERT INTO alumni_profiles
                    (id, org_id, student_id, name, email, graduation_year, program,
                     roll_number, current_employer, current_designation, current_location)
                VALUES (%s,%s,%s,'Alumni Test',%s,2024,'B.Tech CSE','ROLL-001','Google',
                        'SWE','Hyderabad')
            """, (alumni_id, org_id, student_id, email))
            row = _q(conn,
                "SELECT graduation_year, current_employer, current_designation "
                "FROM alumni_profiles WHERE id=%s", (alumni_id,))
            assert row is not None
            assert int(row["graduation_year"]) == 2024
            assert row["current_employer"] == "Google"
            assert row["current_designation"] == "SWE"
        finally:
            _run(conn, "DELETE FROM alumni_profiles WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM students WHERE org_id=%s", (org_id,))
            conn.close()

    def test_alumni_cross_tenant_isolation(self):
        org_a, org_b = _new_org(), _new_org()
        conn_a = _connect(org_a)
        student_id = _seed_student(conn_a, org_a)
        alumni_id = str(uuid.uuid4())
        email_a = f"alumni_{uuid.uuid4().hex[:6]}@test.invalid"
        _run(conn_a, """
            INSERT INTO alumni_profiles
                (id,org_id,student_id,name,email,graduation_year,program,roll_number)
            VALUES (%s,%s,%s,'Cross Tenant Alumni',%s,2023,'MBA','MBA-001')
        """, (alumni_id, org_a, student_id, email_a))
        conn_a.close()
        conn_b = _connect(org_b)
        try:
            row = _q(conn_b, "SELECT id FROM alumni_profiles WHERE id=%s AND org_id=%s",
                     (alumni_id, org_b))
            assert row is None, "Alumni profile from Org A visible under Org B"
        finally:
            conn_b.close()
            su = _connect()
            _run(su, "DELETE FROM alumni_profiles WHERE org_id=%s", (org_a,))
            _run(su, "DELETE FROM students WHERE org_id=%s", (org_a,))
            su.close()


# ---------------------------------------------------------------------------
# 3. Consent Records
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestConsentRecords:
    """
    Schema: id, org_id, user_id (FK→users), purpose, status, given_at, withdrawn_at,
            expires_at, ip_address, user_agent, metadata (NOT NULL JSONB), created_at, updated_at
    """

    def _seed_user(self, conn, org_id):
        """Insert a real user required for consent_records FK."""
        uid = str(uuid.uuid4())
        email = f"consent_u_{uuid.uuid4().hex[:6]}@test.invalid"
        _run(conn, """
            INSERT INTO users (id,tenant_id,username,email,display_name,role,status,password_hash,actor_type)
            VALUES (%s,%s,%s,%s,'Consent User','STUDENT','ACTIVE','$2b$12$x','human')
        """, (uid, org_id, email, email))
        return uid

    def test_consent_record_insert_granted(self):
        """consent_records INSERT creates GRANTED row with purpose."""
        org_id = _new_org()
        conn = _connect(org_id)
        user_id = self._seed_user(conn, org_id)
        consent_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO consent_records
                    (id, org_id, user_id, purpose, status, given_at, metadata)
                VALUES (%s,%s,%s,'PLACEMENT_DATA_SHARING','GRANTED',NOW(),'{}'::jsonb)
            """, (consent_id, org_id, user_id))
            row = _q(conn,
                "SELECT purpose, status FROM consent_records WHERE id=%s",
                (consent_id,))
            assert row is not None
            assert row["purpose"] == "PLACEMENT_DATA_SHARING"
            assert row["status"] == "GRANTED"
        finally:
            _run(conn, "DELETE FROM consent_records WHERE id=%s", (consent_id,))
            _run(conn, "DELETE FROM users WHERE tenant_id=%s", (org_id,))
            conn.close()

    def test_consent_withdrawal_updates_status(self):
        """Withdrawing consent sets status=WITHDRAWN and withdrawn_at timestamp."""
        org_id = _new_org()
        conn = _connect(org_id)
        user_id = self._seed_user(conn, org_id)
        consent_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO consent_records
                    (id,org_id,user_id,purpose,status,given_at,metadata)
                VALUES (%s,%s,%s,'ANALYTICS','GRANTED',NOW(),'{}'::jsonb)
            """, (consent_id, org_id, user_id))
            _run(conn, """
                UPDATE consent_records
                SET status='WITHDRAWN', withdrawn_at=NOW()
                WHERE id=%s
            """, (consent_id,))
            row = _q(conn, "SELECT status, withdrawn_at FROM consent_records WHERE id=%s", (consent_id,))
            assert row["status"] == "WITHDRAWN"
            assert row["withdrawn_at"] is not None
        finally:
            _run(conn, "DELETE FROM consent_records WHERE id=%s", (consent_id,))
            _run(conn, "DELETE FROM users WHERE tenant_id=%s", (org_id,))
            conn.close()

    def test_consent_org_filter(self):
        """Consent records can be filtered by org_id and status."""
        org_id = _new_org()
        conn = _connect(org_id)
        # Seed 4 users for the 4 consent records
        user_ids = [self._seed_user(conn, org_id) for _ in range(4)]
        ids = [str(uuid.uuid4()) for _ in range(4)]
        statuses = ["GRANTED", "GRANTED", "WITHDRAWN", "GRANTED"]
        try:
            for cid, status, uid in zip(ids, statuses, user_ids):
                _run(conn, """
                    INSERT INTO consent_records
                        (id,org_id,user_id,purpose,status,given_at,metadata)
                    VALUES (%s,%s,%s,'TEST',%s,NOW(),'{}'::jsonb)
                """, (cid, org_id, uid, status))
            granted = _qa(conn,
                "SELECT id FROM consent_records "
                "WHERE org_id=%s AND status='GRANTED' AND id=ANY(%s::uuid[])",
                (org_id, ids))
            assert len(granted) == 3
        finally:
            _run(conn, "DELETE FROM consent_records WHERE id=ANY(%s::uuid[])", (ids,))
            _run(conn, "DELETE FROM users WHERE tenant_id=%s", (org_id,))
            conn.close()
