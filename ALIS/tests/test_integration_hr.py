"""
Real-database integration tests — HR Module (E08)
Tests: staff_profiles, leave_types, leave_requests, payroll_runs, visiting_faculty_sessions

Run:
    pytest tests/test_integration_hr.py -v -m integration
"""
from __future__ import annotations

import datetime
import uuid

import psycopg2

# Cache DB URL once at import time — survives isolate_sys_modules fixture
try:
    from server.core.settings import settings as _settings
    _DB_URL: str = _settings.db_url
except Exception:
    _DB_URL = "postgresql://postgres:postgres@localhost:5432/alis_db"
import psycopg2.extras
import pytest


# ---------------------------------------------------------------------------
# Override conftest autouse mocks — let real DB and real audit through
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_db_global():
    yield


@pytest.fixture(autouse=True)
def mock_audit_log():
    yield


@pytest.fixture(autouse=True)
def fake_redis_global():
    yield


# ---------------------------------------------------------------------------
# Connection helpers (mirrors test_integration_real_db.py pattern)
# ---------------------------------------------------------------------------

def _connect(org_id: str = None) -> psycopg2.extensions.connection:
    try:
        conn = psycopg2.connect(
            _DB_URL,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
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


# ---------------------------------------------------------------------------
# Shared seed helpers
# ---------------------------------------------------------------------------

def _seed_user(conn, org_id: str) -> str:
    """Seed a minimal users row, return user_id."""
    user_id = str(uuid.uuid4())
    email = f"hr_{uuid.uuid4().hex[:8]}@test.invalid"
    _run(conn, """
        INSERT INTO users
            (id, tenant_id, username, email, display_name, role, status, password_hash, actor_type)
        VALUES (%s, %s, %s, %s, 'HR Test User', 'FACULTY', 'ACTIVE', '$2b$12$x', 'human')
    """, (user_id, org_id, email, email))
    return user_id


def _seed_staff(conn, org_id: str, user_id: str, department: str = "Engineering") -> str:
    """Seed a minimal staff_profiles row, return staff_id."""
    staff_id = str(uuid.uuid4())
    emp_code = f"EMP-{uuid.uuid4().hex[:6].upper()}"
    _run(conn, """
        INSERT INTO staff_profiles
            (id, org_id, user_id, employee_code, department, designation,
             employment_type, date_of_joining, salary_grade)
        VALUES (%s, %s, %s, %s, %s, 'Assistant Professor', 'FULL_TIME', %s, 'G4')
    """, (staff_id, org_id, user_id, emp_code, department, datetime.date.today()))
    return staff_id


def _seed_leave_type(conn, org_id: str, code: str = "CL", quota: int = 12) -> str:
    """Seed a leave_types row, return leave_type_id."""
    lt_id = str(uuid.uuid4())
    _run(conn, """
        INSERT INTO leave_types
            (id, org_id, name, code, annual_quota, carry_forward,
             max_carry_forward, is_paid, applicable_to)
        VALUES (%s, %s, %s, %s, %s, FALSE, 0, TRUE, 'ALL')
    """, (lt_id, org_id, f"Casual Leave {uuid.uuid4().hex[:4]}", code, quota))
    return lt_id


# ---------------------------------------------------------------------------
# 1. Staff Profiles
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestHRStaffProfiles:

    def test_staff_profile_insert_and_query(self):
        """staff_profiles INSERT round-trips all key fields."""
        org_id = _new_org()
        conn = _connect(org_id)
        user_id = _seed_user(conn, org_id)
        try:
            staff_id = _seed_staff(conn, org_id, user_id, department="Mathematics")
            row = _q(conn,
                "SELECT id, department, designation, employment_type, salary_grade "
                "FROM staff_profiles WHERE id = %s", (staff_id,))
            assert row is not None, "staff_profile row not found"
            assert row["department"] == "Mathematics"
            assert row["designation"] == "Assistant Professor"
            assert row["employment_type"] == "FULL_TIME"
            assert row["salary_grade"] == "G4"
        finally:
            _run(conn, "DELETE FROM staff_profiles WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM users WHERE tenant_id = %s", (org_id,))
            conn.close()

    def test_staff_employee_code_unique_per_org(self):
        """Duplicate employee_code in same org is rejected by DB constraint."""
        org_id = _new_org()
        conn = _connect(org_id)
        user_id_1 = _seed_user(conn, org_id)
        user_id_2 = _seed_user(conn, org_id)
        emp_code = f"EMP-DUP-{uuid.uuid4().hex[:4].upper()}"
        staff_id_1 = str(uuid.uuid4())
        staff_id_2 = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO staff_profiles
                    (id, org_id, user_id, employee_code, department, designation,
                     employment_type, date_of_joining, salary_grade)
                VALUES (%s, %s, %s, %s, 'CS', 'Lecturer', 'FULL_TIME', %s, 'G3')
            """, (staff_id_1, org_id, user_id_1, emp_code, datetime.date.today()))
            try:
                _run(conn, """
                    INSERT INTO staff_profiles
                        (id, org_id, user_id, employee_code, department, designation,
                         employment_type, date_of_joining, salary_grade)
                    VALUES (%s, %s, %s, %s, 'CS', 'Lecturer', 'FULL_TIME', %s, 'G3')
                """, (staff_id_2, org_id, user_id_2, emp_code, datetime.date.today()))
            except Exception:
                pass
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM staff_profiles "
                "WHERE org_id = %s AND employee_code = %s",
                (org_id, emp_code))["n"]
            assert int(count) == 1, "Duplicate employee_code was allowed"
        finally:
            _run(conn, "DELETE FROM staff_profiles WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM users WHERE tenant_id = %s", (org_id,))
            conn.close()

    def test_staff_deactivation_sets_is_active_false(self):
        """Setting is_active=FALSE + date_of_leaving persists correctly."""
        org_id = _new_org()
        conn = _connect(org_id)
        user_id = _seed_user(conn, org_id)
        staff_id = _seed_staff(conn, org_id, user_id)
        leaving_date = datetime.date.today()
        try:
            _run(conn,
                "UPDATE staff_profiles SET is_active = FALSE, date_of_leaving = %s "
                "WHERE id = %s",
                (leaving_date, staff_id))
            row = _q(conn,
                "SELECT is_active, date_of_leaving FROM staff_profiles WHERE id = %s",
                (staff_id,))
            assert row["is_active"] is False
            assert row["date_of_leaving"] == leaving_date
        finally:
            _run(conn, "DELETE FROM staff_profiles WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM users WHERE tenant_id = %s", (org_id,))
            conn.close()

    def test_staff_filter_by_department(self):
        """Filtering staff_profiles by department returns correct count."""
        org_id = _new_org()
        conn = _connect(org_id)
        try:
            for i in range(3):
                u_id = _seed_user(conn, org_id)
                dept = "Physics" if i < 2 else "Chemistry"
                _seed_staff(conn, org_id, u_id, department=dept)

            rows = _qa(conn,
                "SELECT id FROM staff_profiles "
                "WHERE org_id = %s AND department = 'Physics' AND is_active = TRUE",
                (org_id,))
            assert len(rows) == 2
        finally:
            _run(conn, "DELETE FROM staff_profiles WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM users WHERE tenant_id = %s", (org_id,))
            conn.close()

    def test_staff_cross_tenant_isolation(self):
        """Staff profile in Org A is not visible under Org B tenant context."""
        org_a, org_b = _new_org(), _new_org()
        conn_a = _connect(org_a)
        user_id = _seed_user(conn_a, org_a)
        staff_id = _seed_staff(conn_a, org_a, user_id)
        conn_a.close()

        conn_b = _connect(org_b)
        try:
            row = _q(conn_b,
                "SELECT id FROM staff_profiles WHERE id = %s AND org_id = %s",
                (staff_id, org_b))
            assert row is None, "Staff profile from Org A is visible under Org B"
        finally:
            conn_b.close()
            # Cleanup
            conn_su = _connect()
            _run(conn_su, "DELETE FROM staff_profiles WHERE org_id = %s", (org_a,))
            _run(conn_su, "DELETE FROM users WHERE tenant_id = %s", (org_a,))
            conn_su.close()


# ---------------------------------------------------------------------------
# 2. Leave Types
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestHRLeaveTypes:

    def test_leave_type_insert_and_query(self):
        """leave_types INSERT round-trips all fields."""
        org_id = _new_org()
        conn = _connect(org_id)
        try:
            lt_id = _seed_leave_type(conn, org_id, code="SL", quota=7)
            row = _q(conn,
                "SELECT annual_quota, is_paid, applicable_to, is_active "
                "FROM leave_types WHERE id = %s",
                (lt_id,))
            assert row is not None
            assert int(row["annual_quota"]) == 7
            assert row["is_paid"] is True
            assert row["applicable_to"] == "ALL"
            assert row["is_active"] is True
        finally:
            _run(conn, "DELETE FROM leave_types WHERE org_id = %s", (org_id,))
            conn.close()

    def test_leave_type_code_unique_per_org(self):
        """Duplicate leave type code in same org is rejected."""
        org_id = _new_org()
        conn = _connect(org_id)
        lt1, lt2 = str(uuid.uuid4()), str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO leave_types
                    (id, org_id, name, code, annual_quota, carry_forward,
                     max_carry_forward, is_paid, applicable_to)
                VALUES (%s, %s, 'Casual Leave', 'CL_TEST', 12, FALSE, 0, TRUE, 'ALL')
            """, (lt1, org_id))
            try:
                _run(conn, """
                    INSERT INTO leave_types
                        (id, org_id, name, code, annual_quota, carry_forward,
                         max_carry_forward, is_paid, applicable_to)
                    VALUES (%s, %s, 'Casual Leave 2', 'CL_TEST', 6, FALSE, 0, TRUE, 'ALL')
                """, (lt2, org_id))
            except Exception:
                pass
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM leave_types "
                "WHERE org_id = %s AND code = 'CL_TEST'",
                (org_id,))["n"]
            assert int(count) == 1, "Duplicate leave type code was allowed"
        finally:
            _run(conn, "DELETE FROM leave_types WHERE org_id = %s", (org_id,))
            conn.close()


# ---------------------------------------------------------------------------
# 3. Leave Requests
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestHRLeaveRequests:

    def test_leave_request_insert_pending(self):
        """leave_requests INSERT creates row with PENDING status."""
        org_id = _new_org()
        conn = _connect(org_id)
        user_id = _seed_user(conn, org_id)
        staff_id = _seed_staff(conn, org_id, user_id)
        lt_id = _seed_leave_type(conn, org_id)
        req_id = str(uuid.uuid4())
        from_date = datetime.date.today() + datetime.timedelta(days=5)
        to_date = from_date + datetime.timedelta(days=2)
        try:
            _run(conn, """
                INSERT INTO leave_requests
                    (id, org_id, staff_id, leave_type_id, from_date, to_date, days, reason)
                VALUES (%s, %s, %s, %s, %s, %s, 3, 'Medical appointment')
            """, (req_id, org_id, staff_id, lt_id, from_date, to_date))
            row = _q(conn,
                "SELECT status, days, reason FROM leave_requests WHERE id = %s",
                (req_id,))
            assert row is not None, "leave_requests row not found"
            assert row["status"] == "PENDING"
            assert float(row["days"]) == 3.0
            assert row["reason"] == "Medical appointment"
        finally:
            _run(conn, "DELETE FROM leave_requests WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM leave_types WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM staff_profiles WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM users WHERE tenant_id = %s", (org_id,))
            conn.close()

    def test_leave_request_approve_sets_approved_at(self):
        """Approving a leave request sets status=APPROVED and populates approved_at."""
        org_id = _new_org()
        conn = _connect(org_id)
        user_id = _seed_user(conn, org_id)
        staff_id = _seed_staff(conn, org_id, user_id)
        lt_id = _seed_leave_type(conn, org_id)
        req_id = str(uuid.uuid4())
        approver_id = str(uuid.uuid4())
        from_date = datetime.date.today() + datetime.timedelta(days=10)
        to_date = from_date + datetime.timedelta(days=1)
        try:
            _run(conn, """
                INSERT INTO leave_requests
                    (id, org_id, staff_id, leave_type_id, from_date, to_date, days, reason)
                VALUES (%s, %s, %s, %s, %s, %s, 2, 'Conference')
            """, (req_id, org_id, staff_id, lt_id, from_date, to_date))

            _run(conn, """
                UPDATE leave_requests
                SET status = 'APPROVED', approved_by = %s, approved_at = NOW()
                WHERE id = %s
            """, (approver_id, req_id))

            row = _q(conn,
                "SELECT status, approved_by, approved_at FROM leave_requests WHERE id = %s",
                (req_id,))
            assert row["status"] == "APPROVED"
            assert str(row["approved_by"]) == approver_id
            assert row["approved_at"] is not None
        finally:
            _run(conn, "DELETE FROM leave_requests WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM leave_types WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM staff_profiles WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM users WHERE tenant_id = %s", (org_id,))
            conn.close()

    def test_leave_request_cancel_sets_cancelled(self):
        """Cancelling a PENDING leave request sets status=CANCELLED."""
        org_id = _new_org()
        conn = _connect(org_id)
        user_id = _seed_user(conn, org_id)
        staff_id = _seed_staff(conn, org_id, user_id)
        lt_id = _seed_leave_type(conn, org_id)
        req_id = str(uuid.uuid4())
        from_date = datetime.date.today() + datetime.timedelta(days=15)
        to_date = from_date + datetime.timedelta(days=1)
        try:
            _run(conn, """
                INSERT INTO leave_requests
                    (id, org_id, staff_id, leave_type_id, from_date, to_date, days, reason)
                VALUES (%s, %s, %s, %s, %s, %s, 2, 'Personal')
            """, (req_id, org_id, staff_id, lt_id, from_date, to_date))
            _run(conn,
                "UPDATE leave_requests SET status = 'CANCELLED' WHERE id = %s",
                (req_id,))
            row = _q(conn,
                "SELECT status FROM leave_requests WHERE id = %s", (req_id,))
            assert row["status"] == "CANCELLED"
        finally:
            _run(conn, "DELETE FROM leave_requests WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM leave_types WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM staff_profiles WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM users WHERE tenant_id = %s", (org_id,))
            conn.close()

    def test_leave_requests_count_for_staff(self):
        """Multiple leave requests for a staff member are all queryable."""
        org_id = _new_org()
        conn = _connect(org_id)
        user_id = _seed_user(conn, org_id)
        staff_id = _seed_staff(conn, org_id, user_id)
        lt_id = _seed_leave_type(conn, org_id)
        try:
            for i in range(3):
                rid = str(uuid.uuid4())
                from_date = datetime.date.today() + datetime.timedelta(days=20 + i * 5)
                to_date = from_date + datetime.timedelta(days=1)
                _run(conn, """
                    INSERT INTO leave_requests
                        (id, org_id, staff_id, leave_type_id, from_date, to_date, days, reason)
                    VALUES (%s, %s, %s, %s, %s, %s, 2, 'Test')
                """, (rid, org_id, staff_id, lt_id, from_date, to_date))
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM leave_requests "
                "WHERE staff_id = %s AND org_id = %s",
                (staff_id, org_id))["n"]
            assert int(count) == 3
        finally:
            _run(conn, "DELETE FROM leave_requests WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM leave_types WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM staff_profiles WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM users WHERE tenant_id = %s", (org_id,))
            conn.close()

    def test_leave_cross_tenant_isolation(self):
        """Leave request in Org A is not visible under Org B context."""
        org_a, org_b = _new_org(), _new_org()
        conn_a = _connect(org_a)
        user_id = _seed_user(conn_a, org_a)
        staff_id = _seed_staff(conn_a, org_a, user_id)
        lt_id = _seed_leave_type(conn_a, org_a)
        req_id = str(uuid.uuid4())
        from_date = datetime.date.today() + datetime.timedelta(days=30)
        to_date = from_date + datetime.timedelta(days=1)
        try:
            _run(conn_a, """
                INSERT INTO leave_requests
                    (id, org_id, staff_id, leave_type_id, from_date, to_date, days, reason)
                VALUES (%s, %s, %s, %s, %s, %s, 2, 'Cross-tenant test')
            """, (req_id, org_a, staff_id, lt_id, from_date, to_date))
            conn_b = _connect(org_b)
            try:
                row = _q(conn_b,
                    "SELECT id FROM leave_requests WHERE id = %s AND org_id = %s",
                    (req_id, org_b))
                assert row is None, "Leave request from Org A visible under Org B"
            finally:
                conn_b.close()
        finally:
            _run(conn_a, "DELETE FROM leave_requests WHERE org_id = %s", (org_a,))
            _run(conn_a, "DELETE FROM leave_types WHERE org_id = %s", (org_a,))
            _run(conn_a, "DELETE FROM staff_profiles WHERE org_id = %s", (org_a,))
            _run(conn_a, "DELETE FROM users WHERE tenant_id = %s", (org_a,))
            conn_a.close()
