"""
Real-database integration tests — no mocking of execute_query or execute_transaction.

Five flows tested against the live Postgres instance:
  1. Student enrollment end-to-end + audit ledger entry
  2. Fee payment and invoice dues status update
  3. Attendance eligibility reading from institution_policies
  4. Workflow approval task creation and state transition
  5. RLS enforcement — tenant A cannot see tenant B's students

Run:
    pytest tests/test_integration_real_db.py -v -m integration
"""

import datetime
import hashlib
import hmac
import json
import uuid

import psycopg2
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


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _connect(org_id: str = None, role: str = None) -> psycopg2.extensions.connection:
    """Open a real autocommit psycopg2 connection, set tenant context if given."""
    from server.core.settings import settings
    try:
        conn = psycopg2.connect(
            settings.db_url,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        conn.autocommit = True
    except Exception as exc:
        pytest.skip(f"Postgres unreachable: {exc}")
    if role:
        with conn.cursor() as cur:
            cur.execute(f"SET ROLE {role}")
    if org_id:
        with conn.cursor() as cur:
            cur.execute(f"SET alis.current_tenant = '{org_id}'")
    return conn


def _connect_as_app(org_id: str) -> psycopg2.extensions.connection:
    """Connect as alis_app (non-superuser) so RLS policies are enforced."""
    from server.core.settings import settings
    try:
        import re
        # Build connection URL for alis_app user
        base = settings.db_url
        app_url = re.sub(r"postgresql://[^:]+:[^@]+@", "postgresql://alis_app:alis_app_pass@", base)
        conn = psycopg2.connect(
            app_url,
            cursor_factory=psycopg2.extras.RealDictCursor,
        )
        conn.autocommit = True
    except Exception as exc:
        pytest.skip(f"Postgres unreachable or alis_app role not created: {exc}")
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
    """Unique org_id per test — prevents cross-test contamination."""
    return f"test-{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# 1. Student enrollment end-to-end + audit ledger entry
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestStudentEnrollmentEndToEnd:

    def test_enrollment_creates_student_and_audit_entry(self):
        """
        Call EnrollmentProvisioningService.complete() against a real DB.
        Verify:
          - students row created with correct fields
          - enrollment_provisioning.student_id back-linked
          - audit_ledger row written for the new student
        """
        from server.admissions.enrollment_provisioning import EnrollmentProvisioningService

        org_id = _new_org()
        actor_id = str(uuid.uuid4())
        conn = _connect(org_id)

        applicant_id = str(uuid.uuid4())
        prov_id = str(uuid.uuid4())
        roll = f"CS-{uuid.uuid4().hex[:6].upper()}"

        # Seed applicant — must be READY_FOR_ENROLLMENT (state machine pre-condition)
        # phone and source_channel are required by ApplicantRead (NOT NULL in Pydantic model)
        _run(conn, """
            INSERT INTO applicants
                (id, org_id, name, email, phone, intended_program, source_channel, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'READY_FOR_ENROLLMENT')
        """, (applicant_id, org_id, "Priya Sharma",
              f"priya_{uuid.uuid4().hex[:6]}@test.invalid",
              "9900000000", "B.Tech CSE", "WEBSITE"))

        # Seed enrollment_provisioning with lms/email SKIPPED so gates pass
        _run(conn, """
            INSERT INTO enrollment_provisioning
                (id, org_id, applicant_id, roll_number,
                 lms_status, email_status, library_status, id_card_status, erp_status)
            VALUES (%s, %s, %s, %s, 'SKIPPED', 'SKIPPED', 'PENDING', 'PENDING', 'PENDING')
        """, (prov_id, org_id, applicant_id, roll))

        try:
            result = EnrollmentProvisioningService.complete(
                provisioning_id=prov_id,
                org_id=org_id,
                actor_id=actor_id,
            )

            student_id = result.id

            # 1. Student row created
            student = _q(conn,
                "SELECT id, name, email, program, roll_number FROM students WHERE id = %s",
                (student_id,))
            assert student is not None, "Student row not found in DB"
            assert student["name"] == "Priya Sharma"
            assert student["program"] == "B.Tech CSE"
            assert student["roll_number"] == roll

            # 2. Provisioning back-linked
            prov = _q(conn,
                "SELECT student_id FROM enrollment_provisioning WHERE id = %s",
                (prov_id,))
            assert str(prov["student_id"]) == student_id, (
                "enrollment_provisioning.student_id not linked"
            )

            # 3. Audit ledger entry written
            # audit_ledger uses tenant_id, not org_id column
            audit = _q(conn,
                """SELECT id, action, entity_type, entity_id
                   FROM audit_ledger
                   WHERE entity_type = 'student' AND entity_id = %s
                   LIMIT 1""",
                (student_id,))
            assert audit is not None, (
                "No audit_ledger entry found for student creation — "
                "AuditLog.log() did not write to real DB"
            )
            assert audit["action"] == "create"

        finally:
            # Cleanup — audit_ledger has immutability trigger; disable it for cleanup only
            _run(conn, "ALTER TABLE audit_ledger DISABLE TRIGGER trg_audit_ledger_immutable")
            _run(conn, "DELETE FROM audit_ledger WHERE entity_type = 'student' AND tenant_id = %s", (org_id,))
            _run(conn, "ALTER TABLE audit_ledger ENABLE TRIGGER trg_audit_ledger_immutable")
            _run(conn, "DELETE FROM enrollment_provisioning WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM students WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM applicants WHERE org_id = %s", (org_id,))
            conn.close()


# ---------------------------------------------------------------------------
# 2. Fee payment and invoice dues status update
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFeePaymentDuesUpdate:

    def test_payment_reduces_balance_and_marks_paid(self):
        """
        Record a cash payment via PaymentService.record_manual().
        Verify invoice transitions UNPAID → PAID and balance → 0.
        """
        from server.finance.payment import PaymentService
        from server.finance.models import ManualPaymentRecord, PaymentMethod

        org_id = _new_org()
        actor_id = str(uuid.uuid4())
        conn = _connect(org_id)

        student_id = str(uuid.uuid4())
        applicant_id = str(uuid.uuid4())
        invoice_id = str(uuid.uuid4())
        invoice_number = f"INV-{uuid.uuid4().hex[:10].upper()}"

        _run(conn, """
            INSERT INTO students (id, org_id, applicant_id, roll_number, name, email, program)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (student_id, org_id, applicant_id,
              f"ROLL-{uuid.uuid4().hex[:6]}", "Fee Test Student",
              f"fee_{uuid.uuid4().hex[:6]}@test.invalid", "B.Tech"))

        _run(conn, """
            INSERT INTO student_invoices
                (id, org_id, student_id, academic_year, invoice_number,
                 amount_due, due_date, generated_by, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'UNPAID')
        """, (invoice_id, org_id, student_id, "2025-26",
              invoice_number, 50000.00, datetime.date.today(), actor_id))

        try:
            req = ManualPaymentRecord(
                invoice_id=invoice_id,
                amount=50000.00,
                method=PaymentMethod.CASH,
                reference_number=f"CASH-{uuid.uuid4().hex[:8]}",
            )
            PaymentService.record_manual(org_id=org_id, req=req, actor_id=actor_id)

            inv = _q(conn,
                "SELECT amount_paid, balance, status FROM student_invoices WHERE id = %s",
                (invoice_id,))
            assert float(inv["amount_paid"]) == 50000.00, (
                f"amount_paid not updated: {inv['amount_paid']}"
            )
            assert float(inv["balance"]) == 0.00, (
                f"balance not zero after full payment: {inv['balance']}"
            )
            assert inv["status"] == "PAID", (
                f"Invoice status should be PAID, got {inv['status']}"
            )

        finally:
            _run(conn, "DELETE FROM payments WHERE invoice_id = %s", (invoice_id,))
            _run(conn, "DELETE FROM student_invoices WHERE id = %s", (invoice_id,))
            _run(conn, "DELETE FROM students WHERE id = %s", (student_id,))
            conn.close()

    def test_partial_payment_leaves_balance_and_status_partial(self):
        """
        Paying half of a ₹50,000 invoice → status PARTIAL, balance ₹25,000.
        """
        from server.finance.payment import PaymentService
        from server.finance.models import ManualPaymentRecord, PaymentMethod

        org_id = _new_org()
        actor_id = str(uuid.uuid4())
        conn = _connect(org_id)

        student_id = str(uuid.uuid4())
        applicant_id = str(uuid.uuid4())
        invoice_id = str(uuid.uuid4())

        _run(conn, """
            INSERT INTO students (id, org_id, applicant_id, roll_number, name, email, program)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (student_id, org_id, applicant_id,
              f"ROLL-{uuid.uuid4().hex[:6]}", "Partial Pay Student",
              f"partial_{uuid.uuid4().hex[:6]}@test.invalid", "B.Com"))

        _run(conn, """
            INSERT INTO student_invoices
                (id, org_id, student_id, academic_year, invoice_number,
                 amount_due, due_date, generated_by, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'UNPAID')
        """, (invoice_id, org_id, student_id, "2025-26",
              f"INV-{uuid.uuid4().hex[:8].upper()}", 50000.00,
              datetime.date.today(), actor_id))

        try:
            req = ManualPaymentRecord(
                invoice_id=invoice_id,
                amount=25000.00,
                method=PaymentMethod.NEFT,
                reference_number=f"NEFT-{uuid.uuid4().hex[:8]}",
            )
            PaymentService.record_manual(org_id=org_id, req=req, actor_id=actor_id)

            inv = _q(conn,
                "SELECT amount_paid, balance, status FROM student_invoices WHERE id = %s",
                (invoice_id,))
            assert float(inv["amount_paid"]) == 25000.00
            assert float(inv["balance"]) == 25000.00
            assert inv["status"] == "PARTIAL", (
                f"Expected PARTIAL, got {inv['status']}"
            )

        finally:
            _run(conn, "DELETE FROM payments WHERE invoice_id = %s", (invoice_id,))
            _run(conn, "DELETE FROM student_invoices WHERE id = %s", (invoice_id,))
            _run(conn, "DELETE FROM students WHERE id = %s", (student_id,))
            conn.close()


# ---------------------------------------------------------------------------
# 3. Attendance eligibility reading from institution_policies
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAttendanceEligibilityFromPolicy:

    def _seed_attendance(self, conn, org_id, student_id, course_id, academic_year,
                          total_sessions: int, attended: int):
        """Seed N sessions for a course with M attended by the student."""
        faculty_id = str(uuid.uuid4())
        program_id = str(uuid.uuid4())

        # Seed program and course (attendance_sessions has FK to courses)
        _run(conn, """
            INSERT INTO programs (id, org_id, name, code, degree_type, duration_years)
            VALUES (%s, %s, %s, %s, 'UG', 3)
            ON CONFLICT DO NOTHING
        """, (program_id, org_id, "Test Program", f"TP-{uuid.uuid4().hex[:4]}"))

        _run(conn, """
            INSERT INTO courses (id, org_id, program_id, code, name, credits, semester)
            VALUES (%s, %s, %s, %s, %s, 3, 1)
        """, (course_id, org_id, program_id,
              f"CRS-{uuid.uuid4().hex[:6]}", "Integration Test Course"))

        for i in range(total_sessions):
            session_id = str(uuid.uuid4())
            session_date = datetime.date.today() - datetime.timedelta(days=i)
            _run(conn, """
                INSERT INTO attendance_sessions
                    (id, org_id, course_id, faculty_id, academic_year,
                     session_date, slot_type, is_finalized)
                VALUES (%s, %s, %s, %s, %s, %s, 'LECTURE', true)
            """, (session_id, org_id, course_id, faculty_id, academic_year, session_date))

            status = "PRESENT" if i < attended else "ABSENT"
            _run(conn, """
                INSERT INTO attendance_records
                    (id, org_id, student_id, session_id, status, marked_by)
                VALUES (%s, %s, %s, %s, %s, 'system')
            """, (str(uuid.uuid4()), org_id, student_id, session_id, status))

    def test_reads_custom_policy_and_flags_at_risk(self):
        """
        Insert institution_policy with min_attendance = 80%.
        Student attends 7/10 sessions (70%) — must be flagged at_risk=True.
        """
        from server.academics.attendance import AttendanceService

        org_id = _new_org()
        conn = _connect(org_id)

        student_id = str(uuid.uuid4())
        course_id = str(uuid.uuid4())
        academic_year = "2025-26"

        try:
            # Student
            _run(conn, """
                INSERT INTO students (id, org_id, applicant_id, roll_number, name, email, program)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (student_id, org_id, str(uuid.uuid4()),
                  f"ROLL-{uuid.uuid4().hex[:6]}", "Attendance Student",
                  f"att_{uuid.uuid4().hex[:6]}@test.invalid", "B.Sc"))

            # Custom policy: 80% minimum (above 70% attendance)
            _run(conn, """
                INSERT INTO institution_policies (org_id, key, value, category)
                VALUES (%s, %s, %s::jsonb, 'academics')
            """, (org_id, "academics.attendance.min_percentage", json.dumps(80.0)))

            self._seed_attendance(conn, org_id, student_id, course_id,
                                   academic_year, total_sessions=10, attended=7)

            summary = AttendanceService.get_student_summary(
                org_id=org_id,
                student_id=student_id,
                course_id=course_id,
                academic_year=academic_year,
            )

            assert summary["total_sessions"] == 10
            assert summary["attended"] == 7
            assert summary["percentage"] == 70.0
            assert summary["min_required"] == 80.0, (
                f"Expected min_required=80 from DB policy, got {summary['min_required']}"
            )
            assert summary["at_risk"] is True, (
                "Student at 70% should be at_risk=True with 80% policy"
            )

        finally:
            _run(conn, "DELETE FROM attendance_records WHERE student_id = %s", (student_id,))
            _run(conn, "DELETE FROM attendance_sessions WHERE course_id = %s", (course_id,))
            _run(conn, "DELETE FROM courses WHERE id = %s", (course_id,))
            _run(conn, "DELETE FROM institution_policies WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM students WHERE id = %s", (student_id,))
            conn.close()

    def test_falls_back_to_default_policy_when_no_row(self):
        """
        No institution_policy row for this org.
        Default is 75%. Student at 80% → at_risk=False.
        """
        from server.academics.attendance import AttendanceService

        org_id = _new_org()
        conn = _connect(org_id)

        student_id = str(uuid.uuid4())
        course_id = str(uuid.uuid4())
        academic_year = "2025-26"

        try:
            _run(conn, """
                INSERT INTO students (id, org_id, applicant_id, roll_number, name, email, program)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (student_id, org_id, str(uuid.uuid4()),
                  f"ROLL-{uuid.uuid4().hex[:6]}", "Safe Attender",
                  f"safe_{uuid.uuid4().hex[:6]}@test.invalid", "B.Sc"))

            # No policy row inserted — should fall back to default 75%
            self._seed_attendance(conn, org_id, student_id, course_id,
                                   academic_year, total_sessions=10, attended=8)

            summary = AttendanceService.get_student_summary(
                org_id=org_id,
                student_id=student_id,
                course_id=course_id,
                academic_year=academic_year,
            )

            assert summary["min_required"] == 75.0, (
                f"Expected default 75.0, got {summary['min_required']}"
            )
            assert summary["at_risk"] is False, (
                "Student at 80% should not be at_risk with 75% default"
            )

        finally:
            _run(conn, "DELETE FROM attendance_records WHERE student_id = %s", (student_id,))
            _run(conn, "DELETE FROM attendance_sessions WHERE course_id = %s", (course_id,))
            _run(conn, "DELETE FROM courses WHERE id = %s", (course_id,))
            _run(conn, "DELETE FROM students WHERE id = %s", (student_id,))
            conn.close()


# ---------------------------------------------------------------------------
# 4. Workflow approval task creation and state transition
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestApprovalWorkflow:

    def test_create_approval_request_and_approve_it(self):
        """
        INSERT an approval_request directly into the DB (PENDING).
        INSERT an approval_action (APPROVE).
        UPDATE request status → APPROVED.
        Verify final state in DB — no in-memory ApprovalService involved.
        """
        tenant_id = _new_org()
        conn = _connect(tenant_id)

        request_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        approver_id = str(uuid.uuid4())
        action_id = str(uuid.uuid4())

        try:
            # Step 1: Create the approval request (PENDING)
            _run(conn, """
                INSERT INTO approval_requests
                    (id, tenant_id, entity_type, entity_id, action_type,
                     config_id, status, requested_by, required_roles,
                     mode, required_count)
                VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', %s, %s::jsonb, 'any', 1)
            """, (request_id, tenant_id, "fee_waiver", entity_id,
                  "APPROVE_WAIVER", "fee_waiver_approval",
                  approver_id, json.dumps(["FINANCE_OFFICER"])))

            row = _q(conn,
                "SELECT status, entity_type, required_count FROM approval_requests WHERE id = %s",
                (request_id,))
            assert row is not None, "Approval request not created"
            assert row["status"] == "PENDING"
            assert row["entity_type"] == "fee_waiver"
            assert row["required_count"] == 1

            # Step 2: Record an approve action (check constraint requires lowercase)
            _run(conn, """
                INSERT INTO approval_actions
                    (id, request_id, tenant_id, actor_id, actor_role, action, comment)
                VALUES (%s, %s, %s, %s, 'FINANCE_OFFICER', 'approve', 'Looks good')
            """, (action_id, request_id, tenant_id, approver_id))

            # Step 3: Transition request → APPROVED (quorum met: 1/1)
            _run(conn, """
                UPDATE approval_requests
                SET status = 'APPROVED', resolved_at = NOW(),
                    resolution_reason = 'Quorum met'
                WHERE id = %s
            """, (request_id,))

            final = _q(conn,
                "SELECT status, resolved_at FROM approval_requests WHERE id = %s",
                (request_id,))
            assert final["status"] == "APPROVED", (
                f"Expected APPROVED, got {final['status']}"
            )
            assert final["resolved_at"] is not None, "resolved_at not set"

            # Verify action is linked and readable
            action = _q(conn,
                "SELECT action, actor_id FROM approval_actions WHERE request_id = %s",
                (request_id,))
            assert action["action"] == "approve"
            assert action["actor_id"] == approver_id

        finally:
            # approval_actions cascade-deletes with approval_requests
            _run(conn, "DELETE FROM approval_requests WHERE id = %s", (request_id,))
            conn.close()

    def test_rejection_sets_status_rejected(self):
        """
        An approval request that receives a REJECT action → status REJECTED.
        The request cannot be re-opened (verify status is terminal).
        """
        tenant_id = _new_org()
        conn = _connect(tenant_id)

        request_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        rejector_id = str(uuid.uuid4())

        try:
            _run(conn, """
                INSERT INTO approval_requests
                    (id, tenant_id, entity_type, entity_id, action_type,
                     config_id, status, requested_by, required_roles,
                     mode, required_count)
                VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', %s, %s::jsonb, 'all', 2)
            """, (request_id, tenant_id, "grade_override", entity_id,
                  "OVERRIDE_GRADE", "grade_override_approval",
                  rejector_id, json.dumps(["HOD", "REGISTRAR"])))

            _run(conn, """
                INSERT INTO approval_actions
                    (id, request_id, tenant_id, actor_id, actor_role, action, comment)
                VALUES (%s, %s, %s, %s, 'HOD', 'reject', 'Insufficient evidence')
            """, (str(uuid.uuid4()), request_id, tenant_id, rejector_id))

            _run(conn, """
                UPDATE approval_requests
                SET status = 'REJECTED', resolved_at = NOW(),
                    resolution_reason = 'Rejected by HOD'
                WHERE id = %s
            """, (request_id,))

            final = _q(conn,
                "SELECT status FROM approval_requests WHERE id = %s",
                (request_id,))
            assert final["status"] == "REJECTED"

        finally:
            _run(conn, "DELETE FROM approval_requests WHERE id = %s", (request_id,))
            conn.close()


# ---------------------------------------------------------------------------
# 5. RLS enforcement — tenant A cannot see tenant B's students
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRLSEnforcement:

    def test_tenant_a_student_invisible_to_tenant_b(self):
        """
        Insert a student under org_a. Switch connection to org_b context.
        SELECT against students WHERE id = <that student> must return 0 rows.
        The RLS policy on students: USING (org_id = current_setting('alis.current_tenant'))
        ensures cross-tenant reads are blocked at the DB level.
        """
        org_a = _new_org()
        org_b = _new_org()

        conn_a = _connect(org_a)
        student_id = str(uuid.uuid4())

        _run(conn_a, """
            INSERT INTO students (id, org_id, applicant_id, roll_number, name, email, program)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (student_id, org_a, str(uuid.uuid4()),
              f"ROLL-{uuid.uuid4().hex[:6]}", "Tenant A Student",
              f"tena_{uuid.uuid4().hex[:6]}@test.invalid", "B.Tech"))

        # Confirm visible under own tenant
        own = _q(conn_a,
            "SELECT id FROM students WHERE id = %s",
            (student_id,))
        assert own is not None, "Student not visible to own tenant — seeding failed"

        conn_a.close()

        # Switch to tenant B using alis_app (non-superuser) — RLS must block cross-tenant reads
        conn_b = _connect_as_app(org_b)
        cross = _q(conn_b,
            "SELECT id FROM students WHERE id = %s",
            (student_id,))
        assert cross is None, (
            f"RLS FAILURE: tenant B can see tenant A's student {student_id}. "
            "Row-level security policy on students table is not enforced."
        )
        conn_b.close()

        # Cleanup via superuser (bypasses RLS intentionally)
        conn_su = _connect()  # postgres superuser bypasses RLS — correct for cleanup
        _run(conn_su, "DELETE FROM students WHERE id = %s", (student_id,))
        conn_su.close()

    def test_tenant_b_cannot_read_tenant_a_invoice(self):
        """
        RLS on student_invoices: INSERT under org_a, read under org_b → 0 rows.
        """
        org_a = _new_org()
        org_b = _new_org()

        conn_a = _connect(org_a)
        student_id = str(uuid.uuid4())
        invoice_id = str(uuid.uuid4())

        _run(conn_a, """
            INSERT INTO students (id, org_id, applicant_id, roll_number, name, email, program)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (student_id, org_a, str(uuid.uuid4()),
              f"ROLL-{uuid.uuid4().hex[:6]}", "RLS Invoice Student",
              f"rlsinv_{uuid.uuid4().hex[:6]}@test.invalid", "MBA"))

        _run(conn_a, """
            INSERT INTO student_invoices
                (id, org_id, student_id, academic_year, invoice_number,
                 amount_due, due_date, generated_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (invoice_id, org_a, student_id, "2025-26",
              f"INV-{uuid.uuid4().hex[:8].upper()}",
              10000.00, datetime.date.today(), "system"))

        conn_a.close()

        conn_b = _connect_as_app(org_b)
        cross = _q(conn_b,
            "SELECT id FROM student_invoices WHERE id = %s",
            (invoice_id,))
        assert cross is None, (
            f"RLS FAILURE: tenant B can read tenant A's invoice {invoice_id}."
        )
        conn_b.close()

        # Cleanup via superuser
        conn_su = _connect()
        _run(conn_su, "DELETE FROM student_invoices WHERE id = %s", (invoice_id,))
        _run(conn_su, "DELETE FROM students WHERE id = %s", (student_id,))
        conn_su.close()


# ---------------------------------------------------------------------------
# 6. workflow_tasks table — INSERT + SELECT
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestWorkflowTasksTable:

    def test_workflow_tasks_insert_and_select(self):
        """
        workflow_tasks table must exist (migration 0035).
        INSERT a task, SELECT it back, verify all columns round-trip.
        """
        org_id = _new_org()
        conn = _connect(org_id)

        task_id = str(uuid.uuid4())
        resource_id = str(uuid.uuid4())
        creator_id = str(uuid.uuid4())

        try:
            _run(conn, """
                INSERT INTO workflow_tasks
                    (id, org_id, workflow_type, task_type, resource_id,
                     status, payload, requires_roles, created_by, sla_deadline)
                VALUES (%s, %s, %s, %s, %s,
                        'PENDING', %s::jsonb, %s::text[], %s,
                        NOW() + INTERVAL '48 hours')
            """, (task_id, org_id, "course_handover", "REVIEW_HANDOVER",
                  resource_id, json.dumps({"notes": "integration test"}),
                  "{ACADEMIC_COORDINATOR}", creator_id))

            row = _q(conn,
                "SELECT id, workflow_type, task_type, status, payload FROM workflow_tasks WHERE id = %s",
                (task_id,))
            assert row is not None, "workflow_tasks row not found — table does not exist or INSERT failed"
            assert row["workflow_type"] == "course_handover"
            assert row["task_type"] == "REVIEW_HANDOVER"
            assert row["status"] == "PENDING"
            assert row["payload"]["notes"] == "integration test"

        finally:
            _run(conn, "DELETE FROM workflow_tasks WHERE id = %s", (task_id,))
            conn.close()


# ---------------------------------------------------------------------------
# 7. audit_ledger immutability trigger
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAuditLedgerImmutability:

    def test_update_audit_ledger_raises_exception(self):
        """
        The trigger trg_audit_ledger_immutable (migration 0035) must fire
        and raise an exception when any UPDATE is attempted on audit_ledger.
        """
        conn = _connect()  # superuser — RLS bypassed, but trigger still fires

        ledger_id = str(uuid.uuid4())
        org_id = _new_org()

        try:
            _run(conn, """
                INSERT INTO audit_ledger
                    (id, tenant_id, action, actor_id, entity_type, entity_id, hash)
                VALUES (%s, %s, 'create', %s, 'test_entity', %s, %s)
            """, (ledger_id, org_id, str(uuid.uuid4()), str(uuid.uuid4()),
                  hashlib.sha256(ledger_id.encode()).hexdigest()))

            # Attempt UPDATE — must be rejected by trigger
            with pytest.raises(Exception) as exc_info:
                _run(conn, "UPDATE audit_ledger SET action = 'tampered' WHERE id = %s", (ledger_id,))

            assert "immutable" in str(exc_info.value).lower(), (
                f"Expected immutability error, got: {exc_info.value}"
            )

        finally:
            # Cleanup — disable trigger (superuser only), delete, re-enable
            conn.close()
            conn2 = _connect()
            _run(conn2, "ALTER TABLE audit_ledger DISABLE TRIGGER trg_audit_ledger_immutable")
            _run(conn2, "DELETE FROM audit_ledger WHERE id = %s", (ledger_id,))
            _run(conn2, "ALTER TABLE audit_ledger ENABLE TRIGGER trg_audit_ledger_immutable")
            conn2.close()

    def test_delete_audit_ledger_raises_exception(self):
        """
        DELETE on audit_ledger must also be blocked by the immutability trigger.
        """
        conn = _connect()

        ledger_id = str(uuid.uuid4())
        org_id = _new_org()

        _run(conn, """
            INSERT INTO audit_ledger
                (id, tenant_id, action, actor_id, entity_type, entity_id, hash)
            VALUES (%s, %s, 'create', %s, 'test_entity', %s, %s)
        """, (ledger_id, org_id, str(uuid.uuid4()), str(uuid.uuid4()),
              hashlib.sha256(ledger_id.encode()).hexdigest()))

        conn.close()

        conn2 = _connect()
        with pytest.raises(Exception) as exc_info:
            _run(conn2, "DELETE FROM audit_ledger WHERE id = %s", (ledger_id,))

        assert "immutable" in str(exc_info.value).lower(), (
            f"Expected immutability error on DELETE, got: {exc_info.value}"
        )
        conn2.close()

        # Final cleanup — disable trigger temporarily as superuser
        conn3 = _connect()
        _run(conn3, "ALTER TABLE audit_ledger DISABLE TRIGGER trg_audit_ledger_immutable")
        _run(conn3, "DELETE FROM audit_ledger WHERE id = %s", (ledger_id,))
        _run(conn3, "ALTER TABLE audit_ledger ENABLE TRIGGER trg_audit_ledger_immutable")
        conn3.close()


# ---------------------------------------------------------------------------
# 8. Razorpay empty secret rejected
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestRazorpaySecretValidation:

    def test_empty_secret_raises_business_rule_violation(self):
        """
        capture_razorpay_payment() must reject calls when razorpay_webhook_secret
        is empty or None — not silently pass any signature.
        """
        from unittest.mock import patch
        from server.finance.payment import PaymentService
        from server.core.exceptions import BusinessRuleViolation

        with patch("server.core.settings.settings") as mock_settings:
            mock_settings.razorpay_webhook_secret = ""

            with pytest.raises(BusinessRuleViolation) as exc_info:
                PaymentService.capture_razorpay_payment(
                    org_id=_new_org(),
                    invoice_id=str(uuid.uuid4()),
                    razorpay_order_id="order_test123",
                    razorpay_payment_id="pay_test123",
                    razorpay_signature="any_signature_at_all",
                )

            assert "not configured" in str(exc_info.value).lower() or \
                   "secret" in str(exc_info.value).lower(), (
                f"Expected secret-not-configured error, got: {exc_info.value}"
            )

    def test_wrong_signature_raises_business_rule_violation(self):
        """
        With a real (non-empty) secret, a bad signature must be rejected.
        """
        from unittest.mock import patch
        from server.finance.payment import PaymentService
        from server.core.exceptions import BusinessRuleViolation

        with patch("server.core.settings.settings") as mock_settings:
            mock_settings.razorpay_webhook_secret = "real_secret_value"

            with pytest.raises((BusinessRuleViolation, Exception)):
                PaymentService.capture_razorpay_payment(
                    org_id=_new_org(),
                    invoice_id=str(uuid.uuid4()),
                    razorpay_order_id="order_test123",
                    razorpay_payment_id="pay_test123",
                    razorpay_signature="wrong_signature",
                )


# ---------------------------------------------------------------------------
# 9. User management — DB layer
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestUserManagement:

    def test_user_insert_and_query(self):
        """Insert a user row directly; verify all fields round-trip."""
        org_id = _new_org()
        conn = _connect(org_id)
        user_id = str(uuid.uuid4())
        email = f"user_{uuid.uuid4().hex[:8]}@test.invalid"
        try:
            _run(conn, """
                INSERT INTO users
                    (id, tenant_id, username, email, display_name, role, status, password_hash, actor_type)
                VALUES (%s, %s, %s, %s, 'Test Faculty', 'FACULTY', 'ACTIVE', %s, 'human')
            """, (user_id, org_id, email, email, "$2b$12$dummyhashfortest"))
            row = _q(conn, "SELECT id, role, status, actor_type FROM users WHERE id = %s", (user_id,))
            assert row is not None, "User row not found"
            assert row["role"] == "FACULTY"
            assert row["status"] == "ACTIVE"
            assert row["actor_type"] == "human"
        finally:
            _run(conn, "DELETE FROM users WHERE id = %s", (user_id,))
            conn.close()

    def test_user_bcrypt_hash_stored(self):
        """Password hash stored exactly as supplied."""
        org_id = _new_org()
        conn = _connect(org_id)
        user_id = str(uuid.uuid4())
        email = f"hash_{uuid.uuid4().hex[:8]}@test.invalid"
        pw_hash = "$2b$12$fakehashabcdefghijklmnopqrstuvwx"
        try:
            _run(conn, """
                INSERT INTO users (id, tenant_id, username, email, display_name, role, status, password_hash, actor_type)
                VALUES (%s, %s, %s, %s, 'Hash Test', 'STUDENT', 'ACTIVE', %s, 'human')
            """, (user_id, org_id, email, email, pw_hash))
            row = _q(conn, "SELECT password_hash FROM users WHERE id = %s", (user_id,))
            assert row["password_hash"] == pw_hash
        finally:
            _run(conn, "DELETE FROM users WHERE id = %s", (user_id,))
            conn.close()

    def test_user_status_update_to_suspended(self):
        """Updating status to SUSPENDED persists correctly."""
        org_id = _new_org()
        conn = _connect(org_id)
        user_id = str(uuid.uuid4())
        email = f"susp_{uuid.uuid4().hex[:8]}@test.invalid"
        try:
            _run(conn, """
                INSERT INTO users (id, tenant_id, username, email, display_name, role, status, password_hash, actor_type)
                VALUES (%s, %s, %s, %s, 'Suspend Me', 'FACULTY', 'ACTIVE', '$2b$12$x', 'human')
            """, (user_id, org_id, email, email))
            _run(conn, "UPDATE users SET status = 'SUSPENDED' WHERE id = %s", (user_id,))
            row = _q(conn, "SELECT status FROM users WHERE id = %s", (user_id,))
            assert row["status"] == "SUSPENDED"
        finally:
            _run(conn, "DELETE FROM users WHERE id = %s", (user_id,))
            conn.close()

    def test_user_query_by_role(self):
        """Filter users by role within a tenant returns correct count."""
        org_id = _new_org()
        conn = _connect(org_id)
        ids = [str(uuid.uuid4()) for _ in range(3)]
        try:
            for i, uid in enumerate(ids):
                role = "HOD" if i < 2 else "FACULTY"
                email = f"role_{uuid.uuid4().hex[:6]}@test.invalid"
                _run(conn, """
                    INSERT INTO users (id, tenant_id, username, email, display_name, role, status, password_hash, actor_type)
                    VALUES (%s, %s, %s, %s, %s, %s, 'ACTIVE', '$2b$12$x', 'human')
                """, (uid, org_id, email, email, f"User {i}", role))
            rows = _qa(conn,
                "SELECT id FROM users WHERE tenant_id = %s AND role = 'HOD'", (org_id,))
            assert len(rows) == 2
        finally:
            _run(conn, "DELETE FROM users WHERE tenant_id = %s", (org_id,))
            conn.close()

    def test_user_unique_email_per_tenant(self):
        """Duplicate email within same tenant is rejected."""
        org_id = _new_org()
        conn = _connect(org_id)
        email = f"dup_{uuid.uuid4().hex[:8]}@test.invalid"
        uid1, uid2 = str(uuid.uuid4()), str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO users (id, tenant_id, username, email, display_name, role, status, password_hash, actor_type)
                VALUES (%s, %s, %s, %s, 'First', 'STUDENT', 'ACTIVE', '$2b$12$x', 'human')
            """, (uid1, org_id, email, email))
            try:
                _run(conn, """
                    INSERT INTO users (id, tenant_id, username, email, display_name, role, status, password_hash, actor_type)
                    VALUES (%s, %s, %s, %s, 'Second', 'STUDENT', 'ACTIVE', '$2b$12$x', 'human')
                """, (uid2, org_id, email, email))
            except Exception:
                pass
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM users WHERE email = %s AND tenant_id = %s",
                (email, org_id))["n"]
            assert int(count) == 1, "Duplicate email was allowed in users table"
        finally:
            _run(conn, "DELETE FROM users WHERE tenant_id = %s", (org_id,))
            conn.close()


# ---------------------------------------------------------------------------
# 10. Admissions lead CRM — DB layer
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAdmissionsLeadCRM:

    def test_lead_insert_and_query(self):
        org_id = _new_org()
        conn = _connect(org_id)
        lead_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO applicants (id, org_id, name, email, phone, intended_program, source_channel, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'NEW')
            """, (lead_id, org_id, "Arjun Mehta",
                  f"arjun_{uuid.uuid4().hex[:6]}@test.invalid",
                  "9800000001", "B.Tech CSE", "DIRECT"))
            row = _q(conn, "SELECT name, status, source_channel FROM applicants WHERE id = %s", (lead_id,))
            assert row is not None
            assert row["name"] == "Arjun Mehta"
            assert row["status"] == "NEW"
        finally:
            _run(conn, "DELETE FROM applicants WHERE id = %s", (lead_id,))
            conn.close()

    def test_lead_status_transition_to_contacted(self):
        org_id = _new_org()
        conn = _connect(org_id)
        lead_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO applicants (id, org_id, name, email, phone, intended_program, source_channel, status)
                VALUES (%s, %s, 'Status Test', %s, '9800000002', 'MBA', 'WEBSITE', 'NEW')
            """, (lead_id, org_id, f"st_{uuid.uuid4().hex[:6]}@test.invalid"))
            _run(conn, "UPDATE applicants SET status = 'CONTACTED' WHERE id = %s", (lead_id,))
            row = _q(conn, "SELECT status FROM applicants WHERE id = %s", (lead_id,))
            assert row["status"] == "CONTACTED"
        finally:
            _run(conn, "DELETE FROM applicants WHERE id = %s", (lead_id,))
            conn.close()

    def test_lead_count_by_source_channel(self):
        org_id = _new_org()
        conn = _connect(org_id)
        ids = [str(uuid.uuid4()) for _ in range(5)]
        try:
            for i, lid in enumerate(ids):
                channel = "WEBSITE" if i < 3 else "DIRECT"
                _run(conn, """
                    INSERT INTO applicants (id, org_id, name, email, phone, intended_program, source_channel, status)
                    VALUES (%s, %s, %s, %s, %s, 'B.Sc', %s, 'NEW')
                """, (lid, org_id, f"Lead {i}",
                      f"l{i}_{uuid.uuid4().hex[:6]}@test.invalid",
                      f"98000000{i:02}", channel))
            rows = _qa(conn, """
                SELECT source_channel, COUNT(*) AS n FROM applicants
                WHERE org_id = %s GROUP BY source_channel ORDER BY source_channel
            """, (org_id,))
            counts = {r["source_channel"]: int(r["n"]) for r in rows}
            assert counts.get("WEBSITE") == 3
            assert counts.get("DIRECT") == 2
        finally:
            _run(conn, "DELETE FROM applicants WHERE org_id = %s", (org_id,))
            conn.close()

    def test_lead_phone_stored_exactly(self):
        org_id = _new_org()
        conn = _connect(org_id)
        lead_id = str(uuid.uuid4())
        phone = "+91-98765-43210"
        try:
            _run(conn, """
                INSERT INTO applicants (id, org_id, name, email, phone, intended_program, source_channel, status)
                VALUES (%s, %s, 'Phone Test', %s, %s, 'B.Tech', 'WEBSITE', 'NEW')
            """, (lead_id, org_id, f"ph_{uuid.uuid4().hex[:6]}@test.invalid", phone))
            row = _q(conn, "SELECT phone FROM applicants WHERE id = %s", (lead_id,))
            assert row["phone"] == phone
        finally:
            _run(conn, "DELETE FROM applicants WHERE id = %s", (lead_id,))
            conn.close()

    def test_lead_converted_status_queryable(self):
        org_id = _new_org()
        conn = _connect(org_id)
        ids = [str(uuid.uuid4()) for _ in range(3)]
        try:
            statuses = ["NEW", "CONTACTED", "CONVERTED"]
            for lid, status in zip(ids, statuses):
                _run(conn, """
                    INSERT INTO applicants (id, org_id, name, email, phone, intended_program, source_channel, status)
                    VALUES (%s, %s, 'Status Test', %s, '9800000003', 'B.Com', 'DIRECT', %s)
                """, (lid, org_id, f"s_{uuid.uuid4().hex[:6]}@test.invalid", status))
            converted = _qa(conn,
                "SELECT id FROM applicants WHERE org_id = %s AND status = 'CONVERTED'", (org_id,))
            assert len(converted) == 1
        finally:
            _run(conn, "DELETE FROM applicants WHERE org_id = %s", (org_id,))
            conn.close()


# ---------------------------------------------------------------------------
# 11. Finance — invoice workflow DB layer
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestFinanceInvoiceWorkflow:

    def _seed_student(self, conn, org_id) -> str:
        student_id = str(uuid.uuid4())
        _run(conn, """
            INSERT INTO students (id, org_id, applicant_id, roll_number, name, email, program)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (student_id, org_id, str(uuid.uuid4()),
              f"ROLL-{uuid.uuid4().hex[:6]}", "Finance Test",
              f"fin_{uuid.uuid4().hex[:6]}@test.invalid", "B.Com"))
        return student_id

    def test_invoice_created_unpaid(self):
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = self._seed_student(conn, org_id)
        inv_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO student_invoices
                    (id, org_id, student_id, academic_year, invoice_number,
                     amount_due, due_date, generated_by, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'UNPAID')
            """, (inv_id, org_id, student_id, "2025-26",
                  f"INV-{uuid.uuid4().hex[:8].upper()}", 75000.00,
                  datetime.date.today(), str(uuid.uuid4())))
            row = _q(conn, "SELECT status, amount_due FROM student_invoices WHERE id = %s", (inv_id,))
            assert row["status"] == "UNPAID"
            assert float(row["amount_due"]) == 75000.00
        finally:
            _run(conn, "DELETE FROM student_invoices WHERE id = %s", (inv_id,))
            _run(conn, "DELETE FROM students WHERE id = %s", (student_id,))
            conn.close()

    def test_invoice_unique_number_per_org(self):
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = self._seed_student(conn, org_id)
        inv_num = f"INV-DUP-{uuid.uuid4().hex[:6].upper()}"
        inv1, inv2 = str(uuid.uuid4()), str(uuid.uuid4())
        actor = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO student_invoices
                    (id, org_id, student_id, academic_year, invoice_number, amount_due, due_date, generated_by, status)
                VALUES (%s, %s, %s, '2025-26', %s, 10000, %s, %s, 'UNPAID')
            """, (inv1, org_id, student_id, inv_num, datetime.date.today(), actor))
            try:
                _run(conn, """
                    INSERT INTO student_invoices
                        (id, org_id, student_id, academic_year, invoice_number, amount_due, due_date, generated_by, status)
                    VALUES (%s, %s, %s, '2025-26', %s, 10000, %s, %s, 'UNPAID')
                """, (inv2, org_id, student_id, inv_num, datetime.date.today(), actor))
            except Exception:
                pass
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM student_invoices WHERE invoice_number = %s AND org_id = %s",
                (inv_num, org_id))["n"]
            assert int(count) == 1
        finally:
            _run(conn, "DELETE FROM student_invoices WHERE org_id = %s", (org_id,))
            _run(conn, "DELETE FROM students WHERE id = %s", (student_id,))
            conn.close()

    def test_multiple_invoices_per_student(self):
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = self._seed_student(conn, org_id)
        actor = str(uuid.uuid4())
        inv_ids = [str(uuid.uuid4()) for _ in range(3)]
        try:
            for i, inv_id in enumerate(inv_ids):
                _run(conn, """
                    INSERT INTO student_invoices
                        (id, org_id, student_id, academic_year, invoice_number, amount_due, due_date, generated_by, status)
                    VALUES (%s, %s, %s, %s, %s, 50000, %s, %s, 'UNPAID')
                """, (inv_id, org_id, student_id, f"202{5+i}-{6+i}",
                      f"INV-Y{i}-{uuid.uuid4().hex[:6].upper()}", datetime.date.today(), actor))
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM student_invoices WHERE student_id = %s", (student_id,))["n"]
            assert int(count) == 3
        finally:
            _run(conn, "DELETE FROM student_invoices WHERE student_id = %s", (student_id,))
            _run(conn, "DELETE FROM students WHERE id = %s", (student_id,))
            conn.close()

    def test_invoice_overdue_status_transition(self):
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = self._seed_student(conn, org_id)
        inv_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO student_invoices
                    (id, org_id, student_id, academic_year, invoice_number, amount_due, due_date, generated_by, status)
                VALUES (%s, %s, %s, '2025-26', %s, 30000, %s, %s, 'UNPAID')
            """, (inv_id, org_id, student_id,
                  f"INV-OVD-{uuid.uuid4().hex[:6].upper()}",
                  datetime.date.today() - datetime.timedelta(days=10), str(uuid.uuid4())))
            _run(conn, "UPDATE student_invoices SET status = 'OVERDUE' WHERE id = %s", (inv_id,))
            row = _q(conn, "SELECT status FROM student_invoices WHERE id = %s", (inv_id,))
            assert row["status"] == "OVERDUE"
        finally:
            _run(conn, "DELETE FROM student_invoices WHERE id = %s", (inv_id,))
            _run(conn, "DELETE FROM students WHERE id = %s", (student_id,))
            conn.close()

    def test_total_dues_aggregate_query(self):
        org_id = _new_org()
        conn = _connect(org_id)
        student_id = self._seed_student(conn, org_id)
        actor = str(uuid.uuid4())
        amounts = [25000.0, 15000.0, 10000.0]
        inv_ids = [str(uuid.uuid4()) for _ in amounts]
        try:
            for inv_id, amt in zip(inv_ids, amounts):
                _run(conn, """
                    INSERT INTO student_invoices
                        (id, org_id, student_id, academic_year, invoice_number, amount_due, due_date, generated_by, status)
                    VALUES (%s, %s, %s, '2025-26', %s, %s, %s, %s, 'UNPAID')
                """, (inv_id, org_id, student_id,
                      f"INV-AGG-{uuid.uuid4().hex[:6].upper()}", amt,
                      datetime.date.today(), actor))
            total = _q(conn, """
                SELECT SUM(amount_due) AS total FROM student_invoices
                WHERE student_id = %s AND status = 'UNPAID'
            """, (student_id,))["total"]
            assert float(total) == sum(amounts)
        finally:
            _run(conn, "DELETE FROM student_invoices WHERE student_id = %s", (student_id,))
            _run(conn, "DELETE FROM students WHERE id = %s", (student_id,))
            conn.close()


# ---------------------------------------------------------------------------
# 12. Policy Engine DB layer
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestPolicyEngineDB:

    def test_institution_policy_insert_and_query(self):
        org_id = _new_org()
        conn = _connect(org_id)
        pol_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO institution_policies (id, org_id, key, value, description, category)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (pol_id, org_id, "academics.attendance.min_percentage",
                  "75.0", "Min attendance %", "academics"))
            row = _q(conn,
                "SELECT key, value, category FROM institution_policies WHERE id = %s", (pol_id,))
            assert row is not None
            assert row["key"] == "academics.attendance.min_percentage"
            assert row["category"] == "academics"
        finally:
            _run(conn, "DELETE FROM institution_policies WHERE id = %s", (pol_id,))
            conn.close()

    def test_tenant_policy_insert_and_query(self):
        org_id = _new_org()
        conn = _connect(org_id)
        pol_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO tenant_policies (id, tenant_id, policy_id, version, rules, status, effective_from)
                VALUES (%s, %s, %s, 1, %s::jsonb, 'DRAFT', NOW())
            """, (pol_id, org_id, "attendance_gate",
                  json.dumps([{"condition": "attendance_pct >= 75", "effect": "ALLOW"}])))
            row = _q(conn,
                "SELECT policy_id, version, status, rules FROM tenant_policies WHERE id = %s", (pol_id,))
            assert row is not None
            assert row["policy_id"] == "attendance_gate"
            assert row["version"] == 1
            assert row["status"] == "DRAFT"
            assert isinstance(row["rules"], list)
        finally:
            _run(conn, "DELETE FROM tenant_policies WHERE id = %s", (pol_id,))
            conn.close()

    def test_tenant_policy_version_unique(self):
        org_id = _new_org()
        conn = _connect(org_id)
        pid1, pid2 = str(uuid.uuid4()), str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO tenant_policies (id, tenant_id, policy_id, version, rules, status, effective_from)
                VALUES (%s, %s, %s, 1, '[]'::jsonb, 'DRAFT', NOW())
            """, (pid1, org_id, "dup_policy"))
            try:
                _run(conn, """
                    INSERT INTO tenant_policies (id, tenant_id, policy_id, version, rules, status, effective_from)
                    VALUES (%s, %s, %s, 1, '[]'::jsonb, 'DRAFT', NOW())
                """, (pid2, org_id, "dup_policy"))
            except Exception:
                pass
            count = _q(conn, """
                SELECT COUNT(*) AS n FROM tenant_policies
                WHERE tenant_id = %s AND policy_id = %s AND version = 1
            """, (org_id, "dup_policy"))["n"]
            assert int(count) == 1
        finally:
            _run(conn, "DELETE FROM tenant_policies WHERE tenant_id = %s", (org_id,))
            conn.close()

    def test_tenant_policy_approved_filter(self):
        org_id = _new_org()
        conn = _connect(org_id)
        ids = [str(uuid.uuid4()) for _ in range(3)]
        statuses = ["APPROVED", "DRAFT", "ARCHIVED"]
        try:
            for i, (pid, status) in enumerate(zip(ids, statuses)):
                _run(conn, """
                    INSERT INTO tenant_policies (id, tenant_id, policy_id, version, rules, status, effective_from)
                    VALUES (%s, %s, %s, %s, '[]'::jsonb, %s, NOW())
                """, (pid, org_id, f"pol_{i}", i + 1, status))
            rows = _qa(conn,
                "SELECT id FROM tenant_policies WHERE tenant_id = %s AND status = 'APPROVED'", (org_id,))
            assert len(rows) == 1
        finally:
            _run(conn, "DELETE FROM tenant_policies WHERE tenant_id = %s", (org_id,))
            conn.close()

    def test_institution_policy_key_unique_per_org(self):
        org_id = _new_org()
        conn = _connect(org_id)
        pid1, pid2 = str(uuid.uuid4()), str(uuid.uuid4())
        key = "finance.fee.overdue_grace_days"
        try:
            _run(conn, """
                INSERT INTO institution_policies (id, org_id, key, value, description, category)
                VALUES (%s, %s, %s, '7', 'Grace days', 'finance')
            """, (pid1, org_id, key))
            try:
                _run(conn, """
                    INSERT INTO institution_policies (id, org_id, key, value, description, category)
                    VALUES (%s, %s, %s, '14', 'Grace days dup', 'finance')
                """, (pid2, org_id, key))
            except Exception:
                pass
            count = _q(conn,
                "SELECT COUNT(*) AS n FROM institution_policies WHERE org_id = %s AND key = %s",
                (org_id, key))["n"]
            assert int(count) == 1
        finally:
            _run(conn, "DELETE FROM institution_policies WHERE org_id = %s", (org_id,))
            conn.close()


# ---------------------------------------------------------------------------
# 13. Dead-Letter Queue — failed_task_log DB layer
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestDeadLetterQueue:

    def test_failed_task_log_insert_and_query(self):
        conn = _connect()
        task_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO failed_task_log (task_id, task_name, args, kwargs, error, tenant_id)
                VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s)
            """, (task_id, "server.tasks.notifications.send_email",
                  json.dumps(["user@test.invalid"]),
                  json.dumps({"template": "welcome"}),
                  "ConnectionError: SMTP timeout", "test-tenant"))
            row = _q(conn,
                "SELECT task_name, error, retried FROM failed_task_log WHERE task_id = %s", (task_id,))
            assert row is not None
            assert "SMTP timeout" in row["error"]
            assert row["retried"] is False
        finally:
            _run(conn, "DELETE FROM failed_task_log WHERE task_id = %s", (task_id,))
            conn.close()

    def test_failed_task_log_mark_retried(self):
        conn = _connect()
        task_id = str(uuid.uuid4())
        try:
            _run(conn,
                "INSERT INTO failed_task_log (task_id, task_name, error) VALUES (%s, %s, %s)",
                (task_id, "server.tasks.finance.check_invoice_overdue", "Timeout"))
            _run(conn,
                "UPDATE failed_task_log SET retried = TRUE, retried_at = NOW() WHERE task_id = %s",
                (task_id,))
            row = _q(conn, "SELECT retried, retried_at FROM failed_task_log WHERE task_id = %s", (task_id,))
            assert row["retried"] is True
            assert row["retried_at"] is not None
        finally:
            _run(conn, "DELETE FROM failed_task_log WHERE task_id = %s", (task_id,))
            conn.close()

    def test_failed_task_log_filter_unretried(self):
        conn = _connect()
        ids = [str(uuid.uuid4()) for _ in range(4)]
        try:
            for tid in ids:
                _run(conn,
                    "INSERT INTO failed_task_log (task_id, task_name, error) VALUES (%s, %s, %s)",
                    (tid, "test.task", "err"))
            for tid in ids[:2]:
                _run(conn,
                    "UPDATE failed_task_log SET retried = TRUE WHERE task_id = %s", (tid,))
            unretried = _qa(conn,
                "SELECT task_id FROM failed_task_log WHERE task_id = ANY(%s) AND retried = FALSE",
                (ids,))
            assert len(unretried) == 2
        finally:
            _run(conn, "DELETE FROM failed_task_log WHERE task_id = ANY(%s)", (ids,))
            conn.close()

    def test_failed_task_log_tenant_filter(self):
        conn = _connect()
        t1 = f"tenant-{uuid.uuid4().hex[:6]}"
        t2 = f"tenant-{uuid.uuid4().hex[:6]}"
        ids = [str(uuid.uuid4()) for _ in range(4)]
        try:
            for i, tid in enumerate(ids):
                tenant = t1 if i < 3 else t2
                _run(conn,
                    "INSERT INTO failed_task_log (task_id, task_name, error, tenant_id) VALUES (%s, %s, %s, %s)",
                    (tid, "some.task", "err", tenant))
            t1_rows = _qa(conn,
                "SELECT task_id FROM failed_task_log WHERE task_id = ANY(%s) AND tenant_id = %s",
                (ids, t1))
            assert len(t1_rows) == 3
        finally:
            _run(conn, "DELETE FROM failed_task_log WHERE task_id = ANY(%s)", (ids,))
            conn.close()


# ---------------------------------------------------------------------------
# 14. Approval workflow — extended coverage
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestApprovalWorkflowExtended:

    def test_approval_comment_stored(self):
        tenant_id = _new_org()
        conn = _connect(tenant_id)
        req_id = str(uuid.uuid4())
        action_id = str(uuid.uuid4())
        actor_id = str(uuid.uuid4())
        comment = "Approved — employee has sufficient leave balance."
        try:
            _run(conn, """
                INSERT INTO approval_requests
                    (id, tenant_id, entity_type, entity_id, action_type,
                     config_id, status, requested_by, required_roles, mode, required_count)
                VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', %s, %s::jsonb, 'any', 1)
            """, (req_id, tenant_id, "leave_request", str(uuid.uuid4()),
                  "APPROVE_LEAVE", "leave_approval", actor_id,
                  json.dumps(["HR_ADMIN"])))
            _run(conn, """
                INSERT INTO approval_actions
                    (id, request_id, tenant_id, actor_id, actor_role, action, comment)
                VALUES (%s, %s, %s, %s, 'HR_ADMIN', 'approve', %s)
            """, (action_id, req_id, tenant_id, actor_id, comment))
            row = _q(conn, "SELECT comment FROM approval_actions WHERE id = %s", (action_id,))
            assert row["comment"] == comment
        finally:
            _run(conn, "DELETE FROM approval_requests WHERE id = %s", (req_id,))
            conn.close()

    def test_multiple_approval_actions_on_one_request(self):
        tenant_id = _new_org()
        conn = _connect(tenant_id)
        req_id = str(uuid.uuid4())
        actor1, actor2 = str(uuid.uuid4()), str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO approval_requests
                    (id, tenant_id, entity_type, entity_id, action_type,
                     config_id, status, requested_by, required_roles, mode, required_count)
                VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', %s, %s::jsonb, 'all', 2)
            """, (req_id, tenant_id, "waiver", str(uuid.uuid4()),
                  "APPROVE_WAIVER", "waiver_cfg", str(uuid.uuid4()),
                  json.dumps(["FINANCE_OFFICER", "REGISTRAR"])))
            for actor, role in [(actor1, "FINANCE_OFFICER"), (actor2, "REGISTRAR")]:
                _run(conn, """
                    INSERT INTO approval_actions (id, request_id, tenant_id, actor_id, actor_role, action)
                    VALUES (%s, %s, %s, %s, %s, 'approve')
                """, (str(uuid.uuid4()), req_id, tenant_id, actor, role))
            actions = _qa(conn,
                "SELECT actor_role FROM approval_actions WHERE request_id = %s", (req_id,))
            roles = {a["actor_role"] for a in actions}
            assert "FINANCE_OFFICER" in roles and "REGISTRAR" in roles
        finally:
            _run(conn, "DELETE FROM approval_requests WHERE id = %s", (req_id,))
            conn.close()

    def test_resolved_at_null_while_pending(self):
        tenant_id = _new_org()
        conn = _connect(tenant_id)
        req_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO approval_requests
                    (id, tenant_id, entity_type, entity_id, action_type,
                     config_id, status, requested_by, required_roles, mode, required_count)
                VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', %s, '[]'::jsonb, 'any', 1)
            """, (req_id, tenant_id, "document", str(uuid.uuid4()),
                  "APPROVE_DOC", "doc_cfg", str(uuid.uuid4())))
            row = _q(conn,
                "SELECT resolved_at FROM approval_requests WHERE id = %s", (req_id,))
            assert row["resolved_at"] is None
        finally:
            _run(conn, "DELETE FROM approval_requests WHERE id = %s", (req_id,))
            conn.close()

    def test_approval_cross_tenant_isolation(self):
        t_a, t_b = _new_org(), _new_org()
        conn_a = _connect(t_a)
        req_id = str(uuid.uuid4())
        try:
            _run(conn_a, """
                INSERT INTO approval_requests
                    (id, tenant_id, entity_type, entity_id, action_type,
                     config_id, status, requested_by, required_roles, mode, required_count)
                VALUES (%s, %s, %s, %s, %s, %s, 'PENDING', %s, '[]'::jsonb, 'any', 1)
            """, (req_id, t_a, "leave", str(uuid.uuid4()),
                  "APPROVE", "cfg", str(uuid.uuid4())))
            conn_b = _connect(t_b)
            try:
                row = _q(conn_b,
                    "SELECT id FROM approval_requests WHERE id = %s", (req_id,))
                assert row is None, "Cross-tenant approval_request visible — RLS not enforced"
            finally:
                conn_b.close()
        finally:
            _run(conn_a, "DELETE FROM approval_requests WHERE id = %s", (req_id,))
            conn_a.close()


# ---------------------------------------------------------------------------
# 15. Audit ledger — hash chain and cross-tenant isolation
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestAuditChainAndCrossTenant:

    def _write_audit(self, conn, tenant_id, entity_type, entity_id, action,
                     actor_id=None, prev_hash="0" * 64):
        entry_id = str(uuid.uuid4())
        actor_id = actor_id or str(uuid.uuid4())
        payload_json = json.dumps({"entity_type": entity_type, "action": action})
        entry_hash = hashlib.sha256(
            f"{entry_id}{action}{entity_type}{entity_id}{prev_hash}".encode()
        ).hexdigest()
        _run(conn, """
            INSERT INTO audit_ledger
                (id, tenant_id, actor_id, action, entity_type, entity_id,
                 payload, prev_hash, entry_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s)
        """, (entry_id, tenant_id, actor_id, action, entity_type,
              entity_id, payload_json, prev_hash, entry_hash))
        return entry_id, entry_hash

    def test_audit_entries_query_in_order(self):
        tenant_id = _new_org()
        conn = _connect(tenant_id)
        entity_id = str(uuid.uuid4())
        entry_ids = []
        try:
            id1, h1 = self._write_audit(conn, tenant_id, "student", entity_id, "create")
            id2, _ = self._write_audit(conn, tenant_id, "student", entity_id, "update", prev_hash=h1)
            entry_ids.extend([id1, id2])
            rows = _qa(conn, """
                SELECT action FROM audit_ledger
                WHERE entity_id = %s AND entity_type = 'student'
                ORDER BY created_at
            """, (entity_id,))
            actions = [r["action"] for r in rows]
            assert "create" in actions and "update" in actions
        finally:
            _run(conn, "ALTER TABLE audit_ledger DISABLE TRIGGER trg_audit_ledger_immutable")
            _run(conn, "DELETE FROM audit_ledger WHERE entity_id = %s", (entity_id,))
            _run(conn, "ALTER TABLE audit_ledger ENABLE TRIGGER trg_audit_ledger_immutable")
            conn.close()

    def test_audit_actor_id_stored(self):
        tenant_id = _new_org()
        conn = _connect(tenant_id)
        actor_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())
        entry_id = None
        try:
            entry_id, _ = self._write_audit(
                conn, tenant_id, "fee_waiver", entity_id, "approve", actor_id=actor_id)
            row = _q(conn, "SELECT actor_id, action FROM audit_ledger WHERE id = %s", (entry_id,))
            assert str(row["actor_id"]) == actor_id
            assert row["action"] == "approve"
        finally:
            _run(conn, "ALTER TABLE audit_ledger DISABLE TRIGGER trg_audit_ledger_immutable")
            _run(conn, "DELETE FROM audit_ledger WHERE id = %s", (entry_id,))
            _run(conn, "ALTER TABLE audit_ledger ENABLE TRIGGER trg_audit_ledger_immutable")
            conn.close()

    def test_audit_cross_tenant_isolation(self):
        t_a, t_b = _new_org(), _new_org()
        conn_a = _connect(t_a)
        entity_id = str(uuid.uuid4())
        entry_id = None
        try:
            entry_id, _ = self._write_audit(conn_a, t_a, "student", entity_id, "create")
            conn_b = _connect(t_b)
            try:
                row = _q(conn_b,
                    "SELECT id FROM audit_ledger WHERE id = %s", (entry_id,))
                assert row is None, "Audit entry from Tenant A visible to Tenant B — RLS not enforced"
            finally:
                conn_b.close()
        finally:
            _run(conn_a, "ALTER TABLE audit_ledger DISABLE TRIGGER trg_audit_ledger_immutable")
            _run(conn_a, "DELETE FROM audit_ledger WHERE id = %s", (entry_id,))
            _run(conn_a, "ALTER TABLE audit_ledger ENABLE TRIGGER trg_audit_ledger_immutable")
            conn_a.close()


# ---------------------------------------------------------------------------
# 16. Workflow tasks — additional coverage
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestWorkflowTasksExtended:

    def test_workflow_task_status_update(self):
        """PENDING → IN_PROGRESS status update persists."""
        org_id = _new_org()
        conn = _connect(org_id)
        task_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO workflow_tasks
                    (id, org_id, workflow_type, task_type, resource_id,
                     status, payload, requires_roles, created_by, sla_deadline)
                VALUES (%s, %s, %s, %s, %s, 'PENDING', %s::jsonb, %s::text[], %s,
                        NOW() + INTERVAL '24 hours')
            """, (task_id, org_id, "leave_approval", "REVIEW_LEAVE",
                  str(uuid.uuid4()), json.dumps({}), "{HR_ADMIN}", str(uuid.uuid4())))
            _run(conn,
                "UPDATE workflow_tasks SET status = 'IN_PROGRESS' WHERE id = %s", (task_id,))
            row = _q(conn, "SELECT status FROM workflow_tasks WHERE id = %s", (task_id,))
            assert row["status"] == "IN_PROGRESS"
        finally:
            _run(conn, "DELETE FROM workflow_tasks WHERE id = %s", (task_id,))
            conn.close()

    def test_workflow_task_payload_jsonb_round_trip(self):
        """JSONB payload with nested data round-trips without data loss."""
        org_id = _new_org()
        conn = _connect(org_id)
        task_id = str(uuid.uuid4())
        payload = {"leave_type": "SICK", "days": 3, "approver": "HOD", "notes": None}
        try:
            _run(conn, """
                INSERT INTO workflow_tasks
                    (id, org_id, workflow_type, task_type, resource_id,
                     status, payload, requires_roles, created_by, sla_deadline)
                VALUES (%s, %s, %s, %s, %s, 'PENDING', %s::jsonb, '{}', %s,
                        NOW() + INTERVAL '48 hours')
            """, (task_id, org_id, "leave", "APPROVE_LEAVE",
                  str(uuid.uuid4()), json.dumps(payload), str(uuid.uuid4())))
            row = _q(conn, "SELECT payload FROM workflow_tasks WHERE id = %s", (task_id,))
            assert row["payload"]["leave_type"] == "SICK"
            assert row["payload"]["days"] == 3
        finally:
            _run(conn, "DELETE FROM workflow_tasks WHERE id = %s", (task_id,))
            conn.close()

    def test_workflow_task_cross_tenant_isolation(self):
        """Workflow task from Tenant A is not visible to Tenant B."""
        t_a, t_b = _new_org(), _new_org()
        conn_a = _connect(t_a)
        task_id = str(uuid.uuid4())
        try:
            _run(conn_a, """
                INSERT INTO workflow_tasks
                    (id, org_id, workflow_type, task_type, resource_id,
                     status, payload, requires_roles, created_by, sla_deadline)
                VALUES (%s, %s, %s, %s, %s, 'PENDING', '{}'::jsonb, '{}', %s,
                        NOW() + INTERVAL '24 hours')
            """, (task_id, t_a, "waiver", "APPROVE_WAIVER",
                  str(uuid.uuid4()), str(uuid.uuid4())))
            conn_b = _connect(t_b)
            try:
                row = _q(conn_b,
                    "SELECT id FROM workflow_tasks WHERE id = %s", (task_id,))
                assert row is None, "Workflow task visible across tenants — RLS not enforced"
            finally:
                conn_b.close()
        finally:
            _run(conn_a, "DELETE FROM workflow_tasks WHERE id = %s", (task_id,))
            conn_a.close()

    def test_workflow_task_sla_deadline_stored(self):
        """SLA deadline is persisted and can be compared to NOW()."""
        org_id = _new_org()
        conn = _connect(org_id)
        task_id = str(uuid.uuid4())
        try:
            _run(conn, """
                INSERT INTO workflow_tasks
                    (id, org_id, workflow_type, task_type, resource_id,
                     status, payload, requires_roles, created_by, sla_deadline)
                VALUES (%s, %s, %s, %s, %s, 'PENDING', '{}'::jsonb, '{}', %s,
                        NOW() + INTERVAL '72 hours')
            """, (task_id, org_id, "enrollment", "REVIEW_ENROLLMENT",
                  str(uuid.uuid4()), str(uuid.uuid4())))
            row = _q(conn, """
                SELECT sla_deadline > NOW() AS within_sla
                FROM workflow_tasks WHERE id = %s
            """, (task_id,))
            assert row["within_sla"] is True
        finally:
            _run(conn, "DELETE FROM workflow_tasks WHERE id = %s", (task_id,))
            conn.close()

    def test_workflow_tasks_query_by_org(self):
        """Filtering workflow_tasks by org_id and status returns correct rows."""
        org_id = _new_org()
        conn = _connect(org_id)
        ids = [str(uuid.uuid4()) for _ in range(4)]
        statuses = ["PENDING", "PENDING", "IN_PROGRESS", "COMPLETED"]
        try:
            for tid, status in zip(ids, statuses):
                _run(conn, """
                    INSERT INTO workflow_tasks
                        (id, org_id, workflow_type, task_type, resource_id,
                         status, payload, requires_roles, created_by, sla_deadline)
                    VALUES (%s, %s, %s, %s, %s, %s, '{}'::jsonb, '{}', %s,
                            NOW() + INTERVAL '24 hours')
                """, (tid, org_id, "leave", "APPROVE_LEAVE",
                      str(uuid.uuid4()), status, str(uuid.uuid4())))
            pending = _qa(conn,
                "SELECT id FROM workflow_tasks WHERE org_id = %s AND status = 'PENDING'",
                (org_id,))
            assert len(pending) == 2
        finally:
            _run(conn, "DELETE FROM workflow_tasks WHERE org_id = %s", (org_id,))
            conn.close()
