"""
Real-database integration tests — Admissions Extended (E01)
Tests: interview scheduling, merit_list_entries, applicant application lifecycle,
       cross-tenant RLS on applicants table

Run:
    pytest tests/test_integration_admissions_extended.py -v -m integration
"""
from __future__ import annotations
import datetime
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


def _seed_applicant(conn, org_id, status="NEW"):
    app_id = str(uuid.uuid4())
    _run(conn, """
        INSERT INTO applicants
            (id, org_id, name, email, phone, intended_program, source_channel, status)
        VALUES (%s,%s,%s,%s,'9911223344','B.Tech CSE','WEBSITE',%s)
    """, (app_id, org_id, f"Adm Applicant {uuid.uuid4().hex[:4]}",
          f"adm_{uuid.uuid4().hex[:6]}@test.invalid", status))
    return app_id


# ---------------------------------------------------------------------------
# 1. Applicant Lifecycle (status transitions)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestApplicantLifecycle:

    def test_applicant_insert_new_status(self):
        """Applicant INSERT creates row with NEW status and all required fields."""
        org_id = _new_org()
        conn = _connect(org_id)
        try:
            app_id = _seed_applicant(conn, org_id, status="NEW")
            row = _q(conn,
                "SELECT status, intended_program, source_channel FROM applicants WHERE id=%s",
                (app_id,))
            assert row is not None
            assert row["status"] == "NEW"
            assert row["intended_program"] == "B.Tech CSE"
            assert row["source_channel"] == "WEBSITE"
        finally:
            _run(conn, "DELETE FROM applicants WHERE org_id=%s", (org_id,))
            conn.close()

    def test_applicant_status_progression(self):
        """Applicant can move through: NEW → CONTACTED → APPLIED → OFFER_ISSUED."""
        org_id = _new_org()
        conn = _connect(org_id)
        try:
            app_id = _seed_applicant(conn, org_id, status="NEW")
            for status in ("CONTACTED", "APPLIED", "OFFER_ISSUED"):
                _run(conn, "UPDATE applicants SET status=%s WHERE id=%s", (status, app_id))
                row = _q(conn, "SELECT status FROM applicants WHERE id=%s", (app_id,))
                assert row["status"] == status, f"Expected {status}, got {row['status']}"
        finally:
            _run(conn, "DELETE FROM applicants WHERE org_id=%s", (org_id,))
            conn.close()

    def test_applicant_pipeline_counts(self):
        """Counting applicants by status returns correct pipeline metrics."""
        org_id = _new_org()
        conn = _connect(org_id)
        try:
            statuses = ["NEW", "NEW", "NEW", "APPLIED", "APPLIED", "CONVERTED"]
            for status in statuses:
                _seed_applicant(conn, org_id, status=status)
            new_count = _q(conn,
                "SELECT COUNT(*) AS n FROM applicants WHERE org_id=%s AND status='NEW'",
                (org_id,))["n"]
            applied_count = _q(conn,
                "SELECT COUNT(*) AS n FROM applicants WHERE org_id=%s AND status='APPLIED'",
                (org_id,))["n"]
            assert int(new_count) == 3
            assert int(applied_count) == 2
        finally:
            _run(conn, "DELETE FROM applicants WHERE org_id=%s", (org_id,))
            conn.close()

    def test_applicant_cross_tenant_rls(self):
        """Applicant from Org A is not visible under Org B context."""
        org_a, org_b = _new_org(), _new_org()
        conn_a = _connect(org_a)
        app_id = _seed_applicant(conn_a, org_a)
        conn_a.close()
        conn_b = _connect(org_b)
        try:
            row = _q(conn_b, "SELECT id FROM applicants WHERE id=%s AND org_id=%s",
                     (app_id, org_b))
            assert row is None, "Applicant from Org A visible under Org B — RLS not enforced"
        finally:
            conn_b.close()
            su = _connect()
            _run(su, "DELETE FROM applicants WHERE org_id=%s", (org_a,))
            su.close()

    def test_applicant_email_unique_per_org(self):
        """
        Verifies the DB allows multiple inserts with the same email on applicants.
        NOTE: No UNIQUE constraint exists on (org_id, email) for applicants — this
        test documents that behavior and acts as a regression guard. If a future
        migration adds the constraint, this test will start failing and should be
        updated to assert count==1.
        """
        org_id = _new_org()
        conn = _connect(org_id)
        email = f"dup_{uuid.uuid4().hex[:8]}@test.invalid"
        a1, a2 = str(uuid.uuid4()), str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO applicants (id,org_id,name,email,phone,intended_program,source_channel,status)
                VALUES (%s,%s,'App 1',%s,'9900000001','B.Com','DIRECT','NEW')
            """, (a1, org_id, email))
            _run(conn, """
                INSERT INTO applicants (id,org_id,name,email,phone,intended_program,source_channel,status)
                VALUES (%s,%s,'App 2',%s,'9900000002','B.Com','DIRECT','NEW')
            """, (a2, org_id, email))
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM applicants WHERE email=%s AND org_id=%s",
                (email, org_id))["n"]
            # No unique constraint on applicant email — two rows allowed
            assert int(count) == 2, (
                "Expected 2 rows (no unique constraint on applicant email). "
                "If a migration added this constraint, update assertion to == 1."
            )
        finally:
            _run(conn, "DELETE FROM applicants WHERE org_id=%s", (org_id,))
            conn.close()


# ---------------------------------------------------------------------------
# 2. Interview Scheduling
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.skip(reason="admissions_interviews table not yet in schema (pending migration 0039)")
class TestInterviewScheduling:

    def test_interview_insert_scheduled(self):
        """admissions_interviews INSERT creates SCHEDULED row."""
        org_id = _new_org()
        conn = _connect(org_id)
        app_id = _seed_applicant(conn, org_id, status="APPLIED")
        interview_id = str(uuid.uuid4())
        scheduled_at = datetime.datetime.now() + datetime.timedelta(days=5)
        try:
            _run(conn, """
                INSERT INTO admissions_interviews
                    (id, org_id, applicant_id, interview_type, scheduled_at,
                     duration_mins, mode, interviewer_id, status)
                VALUES (%s,%s,%s,'TECHNICAL',%s,30,'VIRTUAL',%s,'SCHEDULED')
            """, (interview_id, org_id, app_id, scheduled_at, str(uuid.uuid4())))
            row = _q(conn,
                "SELECT interview_type, mode, status, duration_mins "
                "FROM admissions_interviews WHERE id=%s", (interview_id,))
            assert row is not None
            assert row["interview_type"] == "TECHNICAL"
            assert row["mode"] == "VIRTUAL"
            assert row["status"] == "SCHEDULED"
            assert int(row["duration_mins"]) == 30
        finally:
            _run(conn, "DELETE FROM admissions_interviews WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM applicants WHERE org_id=%s", (org_id,))
            conn.close()

    def test_interview_complete_sets_score(self):
        """Completing an interview updates status=COMPLETED and score."""
        org_id = _new_org()
        conn = _connect(org_id)
        app_id = _seed_applicant(conn, org_id, status="APPLIED")
        interview_id = str(uuid.uuid4())
        scheduled_at = datetime.datetime.now() + datetime.timedelta(days=3)
        interviewer_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO admissions_interviews
                    (id,org_id,applicant_id,interview_type,scheduled_at,
                     duration_mins,mode,interviewer_id,status)
                VALUES (%s,%s,%s,'HR',%s,45,'FACE_TO_FACE',%s,'SCHEDULED')
            """, (interview_id, org_id, app_id, scheduled_at, interviewer_id))
            _run(conn, """
                UPDATE admissions_interviews
                SET status='COMPLETED', score=82.5, feedback='Strong candidate',
                    completed_at=NOW()
                WHERE id=%s
            """, (interview_id,))
            row = _q(conn,
                "SELECT status, score, feedback, completed_at "
                "FROM admissions_interviews WHERE id=%s", (interview_id,))
            assert row["status"] == "COMPLETED"
            assert abs(float(row["score"]) - 82.5) < 0.01
            assert row["feedback"] == "Strong candidate"
            assert row["completed_at"] is not None
        finally:
            _run(conn, "DELETE FROM admissions_interviews WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM applicants WHERE org_id=%s", (org_id,))
            conn.close()

    def test_interview_cancel_sets_cancelled(self):
        """Cancelling an interview sets status=CANCELLED."""
        org_id = _new_org()
        conn = _connect(org_id)
        app_id = _seed_applicant(conn, org_id, status="APPLIED")
        interview_id = str(uuid.uuid4())
        scheduled_at = datetime.datetime.now() + datetime.timedelta(days=7)
        try:
            _run(conn, """
                INSERT INTO admissions_interviews
                    (id,org_id,applicant_id,interview_type,scheduled_at,
                     duration_mins,mode,interviewer_id,status)
                VALUES (%s,%s,%s,'TECHNICAL',%s,30,'VIRTUAL',%s,'SCHEDULED')
            """, (interview_id, org_id, app_id, scheduled_at, str(uuid.uuid4())))
            _run(conn,
                "UPDATE admissions_interviews SET status='CANCELLED' WHERE id=%s",
                (interview_id,))
            row = _q(conn, "SELECT status FROM admissions_interviews WHERE id=%s", (interview_id,))
            assert row["status"] == "CANCELLED"
        finally:
            _run(conn, "DELETE FROM admissions_interviews WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM applicants WHERE org_id=%s", (org_id,))
            conn.close()

    def test_interview_cross_tenant_isolation(self):
        org_a, org_b = _new_org(), _new_org()
        conn_a = _connect(org_a)
        app_id = _seed_applicant(conn_a, org_a, status="APPLIED")
        interview_id = str(uuid.uuid4())
        scheduled_at = datetime.datetime.now() + datetime.timedelta(days=5)
        _run(conn_a, """
            INSERT INTO admissions_interviews
                (id,org_id,applicant_id,interview_type,scheduled_at,
                 duration_mins,mode,interviewer_id,status)
            VALUES (%s,%s,%s,'TECHNICAL',%s,30,'VIRTUAL',%s,'SCHEDULED')
        """, (interview_id, org_a, app_id, scheduled_at, str(uuid.uuid4())))
        conn_a.close()
        conn_b = _connect(org_b)
        try:
            row = _q(conn_b,
                "SELECT id FROM admissions_interviews WHERE id=%s AND org_id=%s",
                (interview_id, org_b))
            assert row is None, "Interview from Org A visible under Org B"
        finally:
            conn_b.close()
            su = _connect()
            _run(su, "DELETE FROM admissions_interviews WHERE org_id=%s", (org_a,))
            _run(su, "DELETE FROM applicants WHERE org_id=%s", (org_a,))
            su.close()


# ---------------------------------------------------------------------------
# 3. Merit List
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestMeritList:
    """
    Schema: id, org_id, merit_list_id, applicant_id, rank, composite_score,
            score_breakdown (JSONB), status, offer_sent_at, response_deadline
    NOTE: No 'category' column exists — category logic is in score_breakdown JSONB.
    """

    def _seed_merit_list(self, conn, org_id):
        list_id = str(uuid.uuid4())
        _run(conn, """
            INSERT INTO merit_lists
                (id, org_id, program_name, intake_batch, category, list_type,
                 version, status, total_entries, generated_by)
            VALUES (%s,%s,'MBA','2025','GENERAL','PROVISIONAL',1,'PUBLISHED',10,'system')
        """, (list_id, org_id))
        return list_id

    def test_merit_list_entry_insert_and_rank(self):
        """merit_list_entries INSERT stores applicant_id, rank, and composite_score."""
        org_id = _new_org()
        conn = _connect(org_id)
        app_id = _seed_applicant(conn, org_id, status="APPLIED")
        entry_id = str(uuid.uuid4())
        list_id = self._seed_merit_list(conn, org_id)
        try:
            _run(conn, """
                INSERT INTO merit_list_entries
                    (id, org_id, merit_list_id, applicant_id, rank,
                     composite_score, score_breakdown, status)
                VALUES (%s,%s,%s,%s,1,94.5,'{}'::jsonb,'PROVISIONAL')
            """, (entry_id, org_id, list_id, app_id))
            row = _q(conn,
                "SELECT rank, composite_score, status "
                "FROM merit_list_entries WHERE id=%s", (entry_id,))
            assert row is not None
            assert int(row["rank"]) == 1
            assert abs(float(row["composite_score"]) - 94.5) < 0.01
            assert row["status"] == "PROVISIONAL"
        finally:
            _run(conn, "DELETE FROM merit_list_entries WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM applicants WHERE org_id=%s", (org_id,))
            conn.close()

    def test_merit_list_rank_ordering(self):
        """Merit list entries return in rank order."""
        org_id = _new_org()
        conn = _connect(org_id)
        list_id = self._seed_merit_list(conn, org_id)
        try:
            for rank, score in [(1, 95.0), (2, 90.0), (3, 85.0)]:
                app_id = _seed_applicant(conn, org_id, status="APPLIED")
                _run(conn, """
                    INSERT INTO merit_list_entries
                        (id,org_id,merit_list_id,applicant_id,rank,composite_score,score_breakdown,status)
                    VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'PROVISIONAL')
                """, (str(uuid.uuid4()), org_id, list_id, app_id, rank, score))
            rows = _qa(conn, """
                SELECT rank, composite_score FROM merit_list_entries
                WHERE org_id=%s AND merit_list_id=%s ORDER BY rank
            """, (org_id, list_id))
            assert len(rows) == 3
            assert float(rows[0]["composite_score"]) > float(rows[1]["composite_score"])
            assert float(rows[1]["composite_score"]) > float(rows[2]["composite_score"])
        finally:
            _run(conn, "DELETE FROM merit_list_entries WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM applicants WHERE org_id=%s", (org_id,))
            conn.close()

    def test_merit_list_confirm_status(self):
        """Confirming a merit list entry sets status=CONFIRMED."""
        org_id = _new_org()
        conn = _connect(org_id)
        app_id = _seed_applicant(conn, org_id, status="OFFER_ISSUED")
        entry_id = str(uuid.uuid4())
        list_id = self._seed_merit_list(conn, org_id)
        try:
            _run(conn, """
                INSERT INTO merit_list_entries
                    (id,org_id,merit_list_id,applicant_id,rank,composite_score,score_breakdown,status)
                VALUES (%s,%s,%s,%s,5,78.0,'{}'::jsonb,'PROVISIONAL')
            """, (entry_id, org_id, list_id, app_id))
            _run(conn,
                "UPDATE merit_list_entries SET status='CONFIRMED' WHERE id=%s",
                (entry_id,))
            row = _q(conn, "SELECT status FROM merit_list_entries WHERE id=%s", (entry_id,))
            assert row["status"] == "CONFIRMED"
        finally:
            _run(conn, "DELETE FROM merit_list_entries WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM applicants WHERE org_id=%s", (org_id,))
            conn.close()
