"""
Real-database integration tests — Examinations Module (E06)
Tests: exam_schedules, grades, semester_results

Run:
    pytest tests/test_integration_examinations.py -v -m integration
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


def _seed_program(conn, org_id):
    pid = str(uuid.uuid4())
    _run(conn, """
        INSERT INTO programs (id, org_id, name, code, degree_type, duration_years)
        VALUES (%s,%s,%s,%s,'UG',4) ON CONFLICT DO NOTHING
    """, (pid, org_id, f"Prog-{uuid.uuid4().hex[:4]}", f"P-{uuid.uuid4().hex[:4]}"))
    return pid


def _seed_course(conn, org_id, program_id):
    cid = str(uuid.uuid4())
    _run(conn, """
        INSERT INTO courses (id, org_id, program_id, code, name, credits, semester)
        VALUES (%s,%s,%s,%s,'Exam Test Course',3,1)
    """, (cid, org_id, program_id, f"CRS-{uuid.uuid4().hex[:6]}"))
    return cid


def _seed_student(conn, org_id):
    sid = str(uuid.uuid4())
    _run(conn, """
        INSERT INTO students (id, org_id, applicant_id, roll_number, name, email, program)
        VALUES (%s,%s,%s,%s,'Exam Student',%s,'B.Tech')
    """, (sid, org_id, str(uuid.uuid4()),
          f"ROLL-{uuid.uuid4().hex[:6]}", f"ex_{uuid.uuid4().hex[:6]}@test.invalid"))
    return sid


def _seed_schedule(conn, org_id, course_id):
    sid = str(uuid.uuid4())
    exam_date = datetime.date.today() + datetime.timedelta(days=30)
    _run(conn, """
        INSERT INTO exam_schedules
            (id, org_id, course_id, academic_year, semester,
             exam_date, exam_type, max_marks, pass_marks, start_time, end_time)
        VALUES (%s,%s,%s,'2025-26',1,%s,'THEORY',100,40,'09:00','12:00')
    """, (sid, org_id, course_id, exam_date))
    return sid


@pytest.mark.integration
class TestExamSchedules:

    def test_schedule_insert_and_query(self):
        org_id = _new_org()
        conn = _connect(org_id)
        prog_id = _seed_program(conn, org_id)
        course_id = _seed_course(conn, org_id, prog_id)
        try:
            sched_id = _seed_schedule(conn, org_id, course_id)
            row = _q(conn,
                "SELECT exam_type, max_marks, pass_marks FROM exam_schedules WHERE id=%s",
                (sched_id,))
            assert row is not None
            assert row["exam_type"] == "THEORY"
            assert int(row["max_marks"]) == 100
            assert int(row["pass_marks"]) == 40
        finally:
            _run(conn, "DELETE FROM exam_schedules WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM courses WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM programs WHERE org_id=%s", (org_id,))
            conn.close()

    def test_multiple_schedules_per_course(self):
        org_id = _new_org()
        conn = _connect(org_id)
        prog_id = _seed_program(conn, org_id)
        course_id = _seed_course(conn, org_id, prog_id)
        exam_date = datetime.date.today() + datetime.timedelta(days=30)
        try:
            for exam_type in ("MID", "FINAL", "SUPPLEMENTARY"):
                _run(conn, """
                    INSERT INTO exam_schedules
                        (id, org_id, course_id, academic_year, semester,
                         exam_date, exam_type, max_marks, pass_marks, start_time, end_time)
                    VALUES (%s,%s,%s,'2025-26',1,%s,%s,100,40,'09:00','12:00')
                """, (str(uuid.uuid4()), org_id, course_id, exam_date, exam_type))
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM exam_schedules WHERE course_id=%s AND org_id=%s",
                (course_id, org_id))["n"]
            assert int(count) == 3
        finally:
            _run(conn, "DELETE FROM exam_schedules WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM courses WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM programs WHERE org_id=%s", (org_id,))
            conn.close()

    def test_schedule_cross_tenant_isolation(self):
        org_a, org_b = _new_org(), _new_org()
        conn_a = _connect(org_a)
        prog_id = _seed_program(conn_a, org_a)
        course_id = _seed_course(conn_a, org_a, prog_id)
        sched_id = _seed_schedule(conn_a, org_a, course_id)
        conn_a.close()
        conn_b = _connect(org_b)
        try:
            row = _q(conn_b, "SELECT id FROM exam_schedules WHERE id=%s AND org_id=%s",
                     (sched_id, org_b))
            assert row is None, "Schedule from Org A visible under Org B"
        finally:
            conn_b.close()
            su = _connect()
            _run(su, "DELETE FROM exam_schedules WHERE org_id=%s", (org_a,))
            _run(su, "DELETE FROM courses WHERE org_id=%s", (org_a,))
            _run(su, "DELETE FROM programs WHERE org_id=%s", (org_a,))
            su.close()


@pytest.mark.integration
class TestGrades:

    def test_grade_insert_pass(self):
        """75/100 → B+, grade_points=7.0, is_pass=TRUE."""
        org_id = _new_org()
        conn = _connect(org_id)
        prog_id = _seed_program(conn, org_id)
        course_id = _seed_course(conn, org_id, prog_id)
        student_id = _seed_student(conn, org_id)
        sched_id = _seed_schedule(conn, org_id, course_id)
        gid = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO grades
                    (id, org_id, student_id, course_id, exam_schedule_id,
                     academic_year, semester, marks_obtained, max_marks,
                     grade, grade_points, is_absent, is_pass, entered_by)
                VALUES (%s,%s,%s,%s,%s,'2025-26',1,75,100,'B+',7.0,FALSE,TRUE,%s)
            """, (gid, org_id, student_id, course_id, sched_id, str(uuid.uuid4())))
            row = _q(conn,
                "SELECT marks_obtained, grade, grade_points, is_pass FROM grades WHERE id=%s",
                (gid,))
            assert row is not None
            assert float(row["marks_obtained"]) == 75.0
            assert row["grade"] == "B+"
            assert float(row["grade_points"]) == 7.0
            assert row["is_pass"] is True
        finally:
            _run(conn, "DELETE FROM grades WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM exam_schedules WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM students WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM courses WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM programs WHERE org_id=%s", (org_id,))
            conn.close()

    def test_grade_insert_absent(self):
        """Absent student has NULL marks, is_pass=FALSE."""
        org_id = _new_org()
        conn = _connect(org_id)
        prog_id = _seed_program(conn, org_id)
        course_id = _seed_course(conn, org_id, prog_id)
        student_id = _seed_student(conn, org_id)
        sched_id = _seed_schedule(conn, org_id, course_id)
        gid = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO grades
                    (id, org_id, student_id, course_id, exam_schedule_id,
                     academic_year, semester, marks_obtained, max_marks,
                     grade, grade_points, is_absent, is_pass, entered_by)
                VALUES (%s,%s,%s,%s,%s,'2025-26',1,NULL,100,NULL,NULL,TRUE,FALSE,%s)
            """, (gid, org_id, student_id, course_id, sched_id, str(uuid.uuid4())))
            row = _q(conn,
                "SELECT marks_obtained, is_absent, is_pass FROM grades WHERE id=%s", (gid,))
            assert row["marks_obtained"] is None
            assert row["is_absent"] is True
            assert row["is_pass"] is False
        finally:
            _run(conn, "DELETE FROM grades WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM exam_schedules WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM students WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM courses WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM programs WHERE org_id=%s", (org_id,))
            conn.close()

    def test_grade_upsert_updates_marks(self):
        """ON CONFLICT upsert replaces original 35 with corrected 60."""
        org_id = _new_org()
        conn = _connect(org_id)
        prog_id = _seed_program(conn, org_id)
        course_id = _seed_course(conn, org_id, prog_id)
        student_id = _seed_student(conn, org_id)
        sched_id = _seed_schedule(conn, org_id, course_id)
        try:
            for marks, grade, is_pass in [(35, "F", False), (60, "B", True)]:
                _run(conn, """
                    INSERT INTO grades
                        (id, org_id, student_id, course_id, exam_schedule_id,
                         academic_year, semester, marks_obtained, max_marks,
                         grade, grade_points, is_absent, is_pass, entered_by)
                    VALUES (%s,%s,%s,%s,%s,'2025-26',1,%s,100,%s,6.0,FALSE,%s,%s)
                    ON CONFLICT (student_id, course_id, academic_year, semester)
                    DO UPDATE SET marks_obtained=EXCLUDED.marks_obtained,
                                  grade=EXCLUDED.grade, is_pass=EXCLUDED.is_pass
                """, (str(uuid.uuid4()), org_id, student_id, course_id, sched_id,
                      marks, grade, is_pass, str(uuid.uuid4())))
            row = _q(conn,
                "SELECT marks_obtained, grade, is_pass FROM grades "
                "WHERE student_id=%s AND course_id=%s AND academic_year='2025-26'",
                (student_id, course_id))
            assert float(row["marks_obtained"]) == 60.0
            assert row["grade"] == "B"
            assert row["is_pass"] is True
        finally:
            _run(conn, "DELETE FROM grades WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM exam_schedules WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM students WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM courses WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM programs WHERE org_id=%s", (org_id,))
            conn.close()

    def test_grade_cross_tenant_isolation(self):
        org_a, org_b = _new_org(), _new_org()
        conn_a = _connect(org_a)
        prog_id = _seed_program(conn_a, org_a)
        course_id = _seed_course(conn_a, org_a, prog_id)
        student_id = _seed_student(conn_a, org_a)
        sched_id = _seed_schedule(conn_a, org_a, course_id)
        gid = str(uuid.uuid4())
        _run(conn_a, """
            INSERT INTO grades
                (id, org_id, student_id, course_id, exam_schedule_id,
                 academic_year, semester, marks_obtained, max_marks,
                 grade, grade_points, is_absent, is_pass, entered_by)
            VALUES (%s,%s,%s,%s,%s,'2025-26',1,80,100,'A',8.0,FALSE,TRUE,%s)
        """, (gid, org_a, student_id, course_id, sched_id, str(uuid.uuid4())))
        conn_a.close()
        conn_b = _connect(org_b)
        try:
            row = _q(conn_b, "SELECT id FROM grades WHERE id=%s AND org_id=%s",
                     (gid, org_b))
            assert row is None, "Grade from Org A visible under Org B"
        finally:
            conn_b.close()
            su = _connect()
            _run(su, "DELETE FROM grades WHERE org_id=%s", (org_a,))
            _run(su, "DELETE FROM exam_schedules WHERE org_id=%s", (org_a,))
            _run(su, "DELETE FROM students WHERE org_id=%s", (org_a,))
            _run(su, "DELETE FROM courses WHERE org_id=%s", (org_a,))
            _run(su, "DELETE FROM programs WHERE org_id=%s", (org_a,))
            su.close()


@pytest.mark.integration
class TestSemesterResults:

    def test_result_insert_pass(self):
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = _seed_student(conn, org_id)
        rid = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO semester_results
                    (id, org_id, student_id, academic_year, semester,
                     sgpa, cgpa, total_credits, credits_earned, status)
                VALUES (%s,%s,%s,'2025-26',1,8.23,8.23,20,20,'PASS')
            """, (rid, org_id, student_id))
            row = _q(conn,
                "SELECT sgpa, cgpa, status FROM semester_results WHERE id=%s", (rid,))
            assert row is not None
            assert abs(float(row["sgpa"]) - 8.23) < 0.01
            assert row["status"] == "PASS"
        finally:
            _run(conn, "DELETE FROM semester_results WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM students WHERE org_id=%s", (org_id,))
            conn.close()

    def test_result_publish_sets_declared_at(self):
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = _seed_student(conn, org_id)
        rid = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO semester_results
                    (id, org_id, student_id, academic_year, semester,
                     sgpa, cgpa, total_credits, credits_earned, status)
                VALUES (%s,%s,%s,'2025-26',2,7.50,7.50,18,18,'PASS')
            """, (rid, org_id, student_id))
            _run(conn, """
                UPDATE semester_results
                SET is_published=TRUE, declared_at=NOW() WHERE id=%s
            """, (rid,))
            row = _q(conn,
                "SELECT is_published, declared_at FROM semester_results WHERE id=%s",
                (rid,))
            assert row["is_published"] is True
            assert row["declared_at"] is not None
        finally:
            _run(conn, "DELETE FROM semester_results WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM students WHERE org_id=%s", (org_id,))
            conn.close()

    def test_result_fail_status(self):
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = _seed_student(conn, org_id)
        rid = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO semester_results
                    (id, org_id, student_id, academic_year, semester,
                     sgpa, cgpa, total_credits, credits_earned, status)
                VALUES (%s,%s,%s,'2025-26',3,3.50,5.87,20,14,'FAIL')
            """, (rid, org_id, student_id))
            row = _q(conn, "SELECT status FROM semester_results WHERE id=%s", (rid,))
            assert row["status"] == "FAIL"
        finally:
            _run(conn, "DELETE FROM semester_results WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM students WHERE org_id=%s", (org_id,))
            conn.close()
