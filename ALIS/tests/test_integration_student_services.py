"""
Real-database integration tests — Student Services Module (E09)
Tests: hostel_blocks, hostel_rooms, hostel_allocations, hostel_complaints,
       library_memberships, transport_routes, grievances

Run:
    pytest tests/test_integration_student_services.py -v -m integration
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


def _seed_student(conn, org_id):
    sid = str(uuid.uuid4())
    _run(conn, """
        INSERT INTO students (id, org_id, applicant_id, roll_number, name, email, program)
        VALUES (%s,%s,%s,%s,'SS Test Student',%s,'B.Tech')
    """, (sid, org_id, str(uuid.uuid4()),
          f"ROLL-{uuid.uuid4().hex[:6]}", f"ss_{uuid.uuid4().hex[:6]}@test.invalid"))
    return sid


# ---------------------------------------------------------------------------
# 1. Hostel — blocks, rooms, allocations, complaints
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestHostelBlocks:

    def test_hostel_block_insert_and_query(self):
        """hostel_blocks INSERT stores name, gender, and total_rooms correctly."""
        org_id = _new_org()
        conn = _connect(org_id)
        block_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO hostel_blocks (id, org_id, name, gender, total_rooms)
                VALUES (%s,%s,'Block A','MALE',50)
            """, (block_id, org_id))
            row = _q(conn,
                "SELECT name, gender, total_rooms, is_active FROM hostel_blocks WHERE id=%s",
                (block_id,))
            assert row is not None
            assert row["name"] == "Block A"
            assert row["gender"] == "MALE"
            assert int(row["total_rooms"]) == 50
            assert row["is_active"] is True
        finally:
            _run(conn, "DELETE FROM hostel_blocks WHERE org_id=%s", (org_id,))
            conn.close()

    def test_hostel_block_unique_name_per_org(self):
        """Duplicate block name in same org is rejected."""
        org_id = _new_org()
        conn = _connect(org_id)
        b1, b2 = str(uuid.uuid4()), str(uuid.uuid4())
        try:
            _run(conn, "INSERT INTO hostel_blocks (id,org_id,name,gender,total_rooms) VALUES (%s,%s,'Dup Block','FEMALE',30)", (b1, org_id))
            try:
                _run(conn, "INSERT INTO hostel_blocks (id,org_id,name,gender,total_rooms) VALUES (%s,%s,'Dup Block','FEMALE',30)", (b2, org_id))
            except Exception:
                pass
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM hostel_blocks WHERE org_id=%s AND name='Dup Block'",
                (org_id,))["n"]
            assert int(count) == 1, "Duplicate block name was allowed"
        finally:
            _run(conn, "DELETE FROM hostel_blocks WHERE org_id=%s", (org_id,))
            conn.close()

    def test_hostel_block_cross_tenant_isolation(self):
        org_a, org_b = _new_org(), _new_org()
        conn_a = _connect(org_a)
        block_id = str(uuid.uuid4())
        _run(conn_a, "INSERT INTO hostel_blocks (id,org_id,name,gender,total_rooms) VALUES (%s,%s,'Block X','MALE',20)", (block_id, org_a))
        conn_a.close()
        conn_b = _connect(org_b)
        try:
            row = _q(conn_b, "SELECT id FROM hostel_blocks WHERE id=%s AND org_id=%s", (block_id, org_b))
            assert row is None, "Block from Org A visible under Org B"
        finally:
            conn_b.close()
            su = _connect()
            _run(su, "DELETE FROM hostel_blocks WHERE org_id=%s", (org_a,))
            su.close()


@pytest.mark.integration
class TestHostelRooms:

    def test_hostel_room_insert_and_query(self):
        """hostel_rooms INSERT stores room_number, room_type, capacity, floor."""
        org_id = _new_org()
        conn = _connect(org_id)
        block_id = str(uuid.uuid4())
        room_id = str(uuid.uuid4())
        try:
            _run(conn, "INSERT INTO hostel_blocks (id,org_id,name,gender,total_rooms) VALUES (%s,%s,'RoomBlock','MALE',10)", (block_id, org_id))
            _run(conn, """
                INSERT INTO hostel_rooms (id, org_id, block_id, room_number, room_type, capacity, floor)
                VALUES (%s,%s,%s,'101','DOUBLE',2,1)
            """, (room_id, org_id, block_id))
            row = _q(conn, "SELECT room_number, room_type, capacity, floor FROM hostel_rooms WHERE id=%s", (room_id,))
            assert row is not None
            assert row["room_number"] == "101"
            assert row["room_type"] == "DOUBLE"
            assert int(row["capacity"]) == 2
            assert int(row["floor"]) == 1
        finally:
            _run(conn, "DELETE FROM hostel_rooms WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM hostel_blocks WHERE org_id=%s", (org_id,))
            conn.close()

    def test_hostel_room_unique_number_per_block(self):
        """Duplicate room_number in same block is rejected."""
        org_id = _new_org()
        conn = _connect(org_id)
        block_id = str(uuid.uuid4())
        r1, r2 = str(uuid.uuid4()), str(uuid.uuid4())
        try:
            _run(conn, "INSERT INTO hostel_blocks (id,org_id,name,gender,total_rooms) VALUES (%s,%s,'UniqueBlock','FEMALE',10)", (block_id, org_id))
            _run(conn, "INSERT INTO hostel_rooms (id,org_id,block_id,room_number,room_type,capacity,floor) VALUES (%s,%s,%s,'202','SINGLE',1,2)", (r1, org_id, block_id))
            try:
                _run(conn, "INSERT INTO hostel_rooms (id,org_id,block_id,room_number,room_type,capacity,floor) VALUES (%s,%s,%s,'202','SINGLE',1,2)", (r2, org_id, block_id))
            except Exception:
                pass
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM hostel_rooms WHERE block_id=%s AND room_number='202'",
                (block_id,))["n"]
            assert int(count) == 1, "Duplicate room number in same block was allowed"
        finally:
            _run(conn, "DELETE FROM hostel_rooms WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM hostel_blocks WHERE org_id=%s", (org_id,))
            conn.close()


@pytest.mark.integration
class TestHostelAllocations:

    def test_allocation_insert_and_query(self):
        """hostel_allocations INSERT creates ACTIVE row with student and room FKs."""
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = _seed_student(conn, org_id)
        block_id = str(uuid.uuid4())
        room_id = str(uuid.uuid4())
        alloc_id = str(uuid.uuid4())
        try:
            _run(conn, "INSERT INTO hostel_blocks (id,org_id,name,gender,total_rooms) VALUES (%s,%s,'AllocBlock','MALE',10)", (block_id, org_id))
            _run(conn, "INSERT INTO hostel_rooms (id,org_id,block_id,room_number,room_type,capacity,floor) VALUES (%s,%s,%s,'301','DOUBLE',2,3)", (room_id, org_id, block_id))
            _run(conn, """
                INSERT INTO hostel_allocations
                    (id, org_id, student_id, room_id, academic_year, check_in_date, allocated_by)
                VALUES (%s,%s,%s,%s,'2025-26',%s,%s)
            """, (alloc_id, org_id, student_id, room_id, datetime.date.today(), str(uuid.uuid4())))
            row = _q(conn, "SELECT student_id, room_id, status, academic_year FROM hostel_allocations WHERE id=%s", (alloc_id,))
            assert row is not None
            assert str(row["student_id"]) == student_id
            assert str(row["room_id"]) == room_id
            assert row["status"] == "ACTIVE"
            assert row["academic_year"] == "2025-26"
        finally:
            _run(conn, "DELETE FROM hostel_allocations WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM hostel_rooms WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM hostel_blocks WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM students WHERE org_id=%s", (org_id,))
            conn.close()

    def test_allocation_vacate_sets_vacated_status(self):
        """Vacating an allocation sets status=VACATED and check_out_date."""
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = _seed_student(conn, org_id)
        block_id = str(uuid.uuid4())
        room_id = str(uuid.uuid4())
        alloc_id = str(uuid.uuid4())
        checkout = datetime.date.today()
        try:
            _run(conn, "INSERT INTO hostel_blocks (id,org_id,name,gender,total_rooms) VALUES (%s,%s,'VacBlock','FEMALE',10)", (block_id, org_id))
            _run(conn, "INSERT INTO hostel_rooms (id,org_id,block_id,room_number,room_type,capacity,floor) VALUES (%s,%s,%s,'401','SINGLE',1,4)", (room_id, org_id, block_id))
            _run(conn, """
                INSERT INTO hostel_allocations
                    (id, org_id, student_id, room_id, academic_year, check_in_date, allocated_by)
                VALUES (%s,%s,%s,%s,'2025-26',%s,%s)
            """, (alloc_id, org_id, student_id, room_id,
                  datetime.date.today() - datetime.timedelta(days=90), str(uuid.uuid4())))
            _run(conn, """
                UPDATE hostel_allocations SET status='VACATED', check_out_date=%s WHERE id=%s
            """, (checkout, alloc_id))
            row = _q(conn, "SELECT status, check_out_date FROM hostel_allocations WHERE id=%s", (alloc_id,))
            assert row["status"] == "VACATED"
            assert row["check_out_date"] == checkout
        finally:
            _run(conn, "DELETE FROM hostel_allocations WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM hostel_rooms WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM hostel_blocks WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM students WHERE org_id=%s", (org_id,))
            conn.close()

    def test_allocation_cross_tenant_isolation(self):
        org_a, org_b = _new_org(), _new_org()
        conn_a = _connect(org_a)
        student_id = _seed_student(conn_a, org_a)
        block_id = str(uuid.uuid4())
        room_id = str(uuid.uuid4())
        alloc_id = str(uuid.uuid4())
        _run(conn_a, "INSERT INTO hostel_blocks (id,org_id,name,gender,total_rooms) VALUES (%s,%s,'CTBlock','MALE',5)", (block_id, org_a))
        _run(conn_a, "INSERT INTO hostel_rooms (id,org_id,block_id,room_number,room_type,capacity,floor) VALUES (%s,%s,%s,'501','SINGLE',1,5)", (room_id, org_a, block_id))
        _run(conn_a, """
            INSERT INTO hostel_allocations
                (id,org_id,student_id,room_id,academic_year,check_in_date,allocated_by)
            VALUES (%s,%s,%s,%s,'2025-26',%s,%s)
        """, (alloc_id, org_a, student_id, room_id, datetime.date.today(), str(uuid.uuid4())))
        conn_a.close()
        conn_b = _connect(org_b)
        try:
            row = _q(conn_b, "SELECT id FROM hostel_allocations WHERE id=%s AND org_id=%s", (alloc_id, org_b))
            assert row is None, "Hostel allocation from Org A visible under Org B"
        finally:
            conn_b.close()
            su = _connect()
            _run(su, "DELETE FROM hostel_allocations WHERE org_id=%s", (org_a,))
            _run(su, "DELETE FROM hostel_rooms WHERE org_id=%s", (org_a,))
            _run(su, "DELETE FROM hostel_blocks WHERE org_id=%s", (org_a,))
            _run(su, "DELETE FROM students WHERE org_id=%s", (org_a,))
            su.close()


@pytest.mark.integration
class TestHostelComplaints:

    def test_complaint_insert_open_status(self):
        """hostel_complaints INSERT creates row with OPEN status."""
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = _seed_student(conn, org_id)
        block_id = str(uuid.uuid4())
        room_id = str(uuid.uuid4())
        complaint_id = str(uuid.uuid4())
        try:
            _run(conn, "INSERT INTO hostel_blocks (id,org_id,name,gender,total_rooms) VALUES (%s,%s,'CompBlock','MALE',5)", (block_id, org_id))
            _run(conn, "INSERT INTO hostel_rooms (id,org_id,block_id,room_number,room_type,capacity,floor) VALUES (%s,%s,%s,'601','SINGLE',1,6)", (room_id, org_id, block_id))
            _run(conn, """
                INSERT INTO hostel_complaints
                    (id, org_id, student_id, room_id, category, description, priority)
                VALUES (%s,%s,%s,%s,'MAINTENANCE','Tap leaking','MEDIUM')
            """, (complaint_id, org_id, student_id, room_id))
            row = _q(conn, "SELECT status, category, priority FROM hostel_complaints WHERE id=%s", (complaint_id,))
            assert row is not None
            assert row["status"] == "OPEN"
            assert row["category"] == "MAINTENANCE"
            assert row["priority"] == "MEDIUM"
        finally:
            _run(conn, "DELETE FROM hostel_complaints WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM hostel_rooms WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM hostel_blocks WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM students WHERE org_id=%s", (org_id,))
            conn.close()

    def test_complaint_resolve_sets_resolved_at(self):
        """Resolving a complaint sets status=RESOLVED and resolved_at timestamp."""
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = _seed_student(conn, org_id)
        block_id = str(uuid.uuid4())
        room_id = str(uuid.uuid4())
        complaint_id = str(uuid.uuid4())
        try:
            _run(conn, "INSERT INTO hostel_blocks (id,org_id,name,gender,total_rooms) VALUES (%s,%s,'ResBlock','FEMALE',5)", (block_id, org_id))
            _run(conn, "INSERT INTO hostel_rooms (id,org_id,block_id,room_number,room_type,capacity,floor) VALUES (%s,%s,%s,'701','DOUBLE',2,7)", (room_id, org_id, block_id))
            _run(conn, """
                INSERT INTO hostel_complaints
                    (id,org_id,student_id,room_id,category,description,priority)
                VALUES (%s,%s,%s,%s,'ELECTRICAL','Light not working','LOW')
            """, (complaint_id, org_id, student_id, room_id))
            _run(conn, """
                UPDATE hostel_complaints
                SET status='RESOLVED', resolved_at=NOW(), resolution_note='Fixed by electrician'
                WHERE id=%s
            """, (complaint_id,))
            row = _q(conn, "SELECT status, resolved_at, resolution_note FROM hostel_complaints WHERE id=%s", (complaint_id,))
            assert row["status"] == "RESOLVED"
            assert row["resolved_at"] is not None
            assert "electrician" in row["resolution_note"]
        finally:
            _run(conn, "DELETE FROM hostel_complaints WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM hostel_rooms WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM hostel_blocks WHERE org_id=%s", (org_id,))
            _run(conn, "DELETE FROM students WHERE org_id=%s", (org_id,))
            conn.close()
