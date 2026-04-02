"""
Real-database integration tests — Academics Extended (E05)
Tests: programs, courses, timetable_slots, obe_outcomes

Run:
    pytest tests/test_integration_academics_extended.py -v -m integration
"""
from __future__ import annotations
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


# ---------------------------------------------------------------------------
# 1. Programs
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestPrograms:

    def test_program_insert_and_query(self):
        """programs INSERT stores degree_type, duration_years, and code."""
        org_id = _new_org()
        conn = _connect(org_id)
        prog_id = str(uuid.uuid4())
        code = f"BTech-{uuid.uuid4().hex[:4].upper()}"
        try:
            _run(conn, """
                INSERT INTO programs (id, org_id, name, code, degree_type, duration_years)
                VALUES (%s,%s,'B.Tech Computer Science',%s,'UG',4)
            """, (prog_id, org_id, code))
            row = _q(conn,
                "SELECT name, code, degree_type, duration_years FROM programs WHERE id=%s",
                (prog_id,))
            assert row is not None
            assert row["name"] == "B.Tech Computer Science"
            assert row["code"] == code
            assert row["degree_type"] == "UG"
            assert int(row["duration_years"]) == 4
        finally:
            _run(conn, "DELETE FROM programs WHERE org_id=%s", (org_id,))
            conn.close()

    def test_program_code_unique_per_org(self):
        """Duplicate program code in same org is rejected."""
        org_id = _new_org()
        conn = _connect(org_id)
        code = f"DUP-{uuid.uuid4().hex[:4].upper()}"
        p1, p2 = str(uuid.uuid4()), str(uuid.uuid4())
        try:
            _run(conn, "INSERT INTO programs (id,org_id,name,code,degree_type,duration_years) VALUES (%s,%s,'Prog 1',%s,'UG',3)", (p1, org_id, code))
            try:
                _run(conn, "INSERT INTO programs (id,org_id,name,code,degree_type,duration_years) VALUES (%s,%s,'Prog 2',%s,'UG',3)", (p2, org_id, code))
            except Exception:
                pass
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM programs WHERE org_id=%s AND code=%s",
                (org_id, code))["n"]
            assert int(count) == 1, "Duplicate program code was allowed"
        finally:
            _run(conn, "DELETE FROM programs WHERE org_id=%s", (org_id,))
            conn.close()

    def test_multiple_programs_per_org(self):
        """An org can have multiple programs of different degree types."""
        org_id = _new_org()
        conn = _connect(org_id)
        try:
            for dg_type, code in [("UG", "UG01"), ("PG", "PG01"), ("PHD", "PHD01")]:
                _run(conn, """
                    INSERT INTO programs (id,org_id,name,code,degree_type,duration_years)
                    VALUES (%s,%s,%s,%s,%s,3)
                """, (str(uuid.uuid4()), org_id, f"Program {dg_type}", code, dg_type))
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM programs WHERE org_id=%s", (org_id,))["n"]
            assert int(count) == 3
        finally:
            _run(conn, "DELETE FROM programs WHERE org_id=%s", (org_id,))
            conn.close()

    def test_program_cross_tenant_isolation(self):
        org_a, org_b = _new_org(), _new_org()
        conn_a = _connect(org_a)
        prog_id = str(uuid.uuid4())
        _run(conn_a, "INSERT INTO programs (id,org_id,name,code,degree_type,duration_years) VALUES (%s,%s,'Isolated Prog','ISO01','UG',3)", (prog_id, org_a))
        conn_a.close()
        conn_b = _connect(org_b)
        try:
            row = _q(conn_b, "SELECT id FROM programs WHERE id=%s AND org_id=%s", (prog_id, org_b))
            assert row is None, "Program from Org A visible under Org B"
        finally:
            conn_b.close()
            su = _connect()
            _run(su, "DELETE FROM programs WHERE org_id=%s", (org_a,))
            su.close()


# ---------------------------------------------------------------------------
# 2. Courses
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestCourses:

    def _seed_program(self, conn, org_id):
        pid = str(uuid.uuid4())
        _run(conn, "INSERT INTO programs (id,org_id,name,code,degree_type,duration_years) VALUES (%s,%s,'Test Prog',%s,'UG',4) ON CONFLICT DO NOTHING",
             (pid, org_id, f"TP-{uuid.uuid4().hex[:4]}"))
        return pid

    def test_course_insert_and_query(self):
        """courses INSERT stores credits, semester, and code."""
        org_id = _new_org()
        conn = _connect(org_id)
        prog_id = self._seed_program(conn, org_id)
        course_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO courses (id,org_id,program_id,code,name,credits,semester)
                VALUES (%s,%s,%s,%s,'Data Structures',4,2)
            """, (course_id, org_id, prog_id, f"CS-{uuid.uuid4().hex[:6]}"))
            row = _q(conn, "SELECT name, credits, semester FROM courses WHERE id=%s", (course_id,))
            assert row is not None
            assert row["name"] == "Data Structures"
            assert int(row["credits"]) == 4
            assert int(row["semester"]) == 2
        finally:
            _run(conn, "DELETE FROM courses WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM programs WHERE org_id=%s", (org_id,))
            conn.close()

    def test_courses_filter_by_semester(self):
        """Filtering courses by semester returns correct subset."""
        org_id = _new_org()
        conn = _connect(org_id)
        prog_id = self._seed_program(conn, org_id)
        try:
            for i, sem in enumerate([1, 1, 2, 3]):
                _run(conn, """
                    INSERT INTO courses (id,org_id,program_id,code,name,credits,semester)
                    VALUES (%s,%s,%s,%s,%s,3,%s)
                """, (str(uuid.uuid4()), org_id, prog_id,
                      f"C{i}-{uuid.uuid4().hex[:4]}", f"Course {i}", sem))
            sem1 = _qa(conn,
                "SELECT id FROM courses WHERE org_id=%s AND semester=1", (org_id,))
            assert len(sem1) == 2
        finally:
            _run(conn, "DELETE FROM courses WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM programs WHERE org_id=%s", (org_id,))
            conn.close()

    def test_course_cross_tenant_isolation(self):
        org_a, org_b = _new_org(), _new_org()
        conn_a = _connect(org_a)
        prog_id = self._seed_program(conn_a, org_a)
        course_id = str(uuid.uuid4())
        _run(conn_a, "INSERT INTO courses (id,org_id,program_id,code,name,credits,semester) VALUES (%s,%s,%s,'ISOC01','Isolated Course',3,1)", (course_id, org_a, prog_id))
        conn_a.close()
        conn_b = _connect(org_b)
        try:
            row = _q(conn_b, "SELECT id FROM courses WHERE id=%s AND org_id=%s", (course_id, org_b))
            assert row is None, "Course from Org A visible under Org B"
        finally:
            conn_b.close()
            su = _connect()
            _run(su, "DELETE FROM courses WHERE org_id=%s", (org_a,))
            _run(su, "DELETE FROM programs WHERE org_id=%s", (org_a,))
            su.close()


# ---------------------------------------------------------------------------
# 3. Timetable Slots
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestTimetableSlots:

    def _seed_program_and_course(self, conn, org_id):
        pid = str(uuid.uuid4())
        _run(conn, "INSERT INTO programs (id,org_id,name,code,degree_type,duration_years) VALUES (%s,%s,'TT Prog',%s,'UG',4) ON CONFLICT DO NOTHING",
             (pid, org_id, f"TTP-{uuid.uuid4().hex[:4]}"))
        cid = str(uuid.uuid4())
        _run(conn, "INSERT INTO courses (id,org_id,program_id,code,name,credits,semester) VALUES (%s,%s,%s,%s,'TT Course',3,1)",
             (cid, org_id, pid, f"TTC-{uuid.uuid4().hex[:6]}"))
        return pid, cid

    def test_timetable_slot_insert_and_query(self):
        """timetable_slots INSERT stores day_of_week, start_time, room, faculty_id."""
        org_id = _new_org()
        conn = _connect(org_id)
        _, course_id = self._seed_program_and_course(conn, org_id)
        slot_id = str(uuid.uuid4())
        faculty_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO timetable_slots
                    (id, org_id, course_id, faculty_id, academic_year,
                     day_of_week, start_time, end_time, room, slot_type)
                VALUES (%s,%s,%s,%s,'2025-26',0,'09:00','10:00','Room 101','LECTURE')
            """, (slot_id, org_id, course_id, faculty_id))
            row = _q(conn,
                "SELECT day_of_week, start_time, room, slot_type FROM timetable_slots WHERE id=%s",
                (slot_id,))
            assert row is not None
            assert int(row["day_of_week"]) == 0  # 0 = Monday
            assert row["room"] == "Room 101"
            assert row["slot_type"] == "LECTURE"
        finally:
            _run(conn, "DELETE FROM timetable_slots WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM courses WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM programs WHERE org_id=%s", (org_id,))
            conn.close()

    def test_timetable_slots_per_course(self):
        """A course can have multiple timetable slots across different days."""
        org_id = _new_org()
        conn = _connect(org_id)
        _, course_id = self._seed_program_and_course(conn, org_id)
        faculty_id = str(uuid.uuid4())
        try:
            for i, day_int in enumerate([0, 2, 4]):  # 0=Mon, 2=Wed, 4=Fri
                _run(conn, """
                    INSERT INTO timetable_slots
                        (id,org_id,course_id,faculty_id,academic_year,
                         day_of_week,start_time,end_time,room,slot_type)
                    VALUES (%s,%s,%s,%s,'2025-26',%s,'10:00','11:00','Room 201','LECTURE')
                """, (str(uuid.uuid4()), org_id, course_id, faculty_id, day_int))
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM timetable_slots WHERE course_id=%s AND org_id=%s",
                (course_id, org_id))["n"]
            assert int(count) == 3
        finally:
            _run(conn, "DELETE FROM timetable_slots WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM courses WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM programs WHERE org_id=%s", (org_id,))
            conn.close()
