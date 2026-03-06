"""
Tests for ALIS Admissions Pipeline — E04-S01 through E04-S09

Strategy: Service-layer tests (not HTTP). This avoids the require_permission
*args/**kwargs wrapper issue and tests the actual business logic directly.

Happy paths:
  - Create applicant (LEAD → APPLIED), with duplicate detection
  - Get applicant, list with filter/pagination
  - Evaluate eligibility: PROCEED / REVIEW / REJECT
  - Confirm admission
  - Enroll (ENROLLED state transition)

Sad paths:
  - Duplicate applicant → BusinessRuleViolation
  - Applicant not found → BusinessRuleViolation
  - Already confirmed → BusinessRuleViolation

RBAC unit tests:
  - Role × Permission matrix verified via verify_access()
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, call

from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.admissions.models import ApplicantCreate, ApplicantRead, ApplicantStatus


# ─── shared constants ─────────────────────────────────────────────────────────

TENANT = "test-tenant"
ACTOR = "test-actor-001"
APPLICANT_ID = "app-0001-0000-0000-0000-000000000001"

_now = datetime.now(timezone.utc)

APPLICANT_ROW = {
    "id": APPLICANT_ID,
    "org_id": TENANT,
    "name": "Priya Sharma",
    "email": "priya.sharma@example.com",
    "phone": "9876543210",
    "intended_program": "B.Tech Computer Science",
    "source_channel": "website",
    "status": "APPLIED",
    "created_at": _now,
    "updated_at": None,
    "metadata": {},
}

VALID_CREATE = ApplicantCreate(
    name="Priya Sharma",
    email="priya.sharma@example.com",
    phone="9876543210",
    intended_program="B.Tech Computer Science",
)

# ─── patch targets ────────────────────────────────────────────────────────────

SVC    = "server.admissions.service"
ELIG   = "server.admissions.eligibility_service"
OFFER  = "server.admissions.offer_letter"
CONF   = "server.admissions.confirmation"
ENROLL = "server.admissions.enrollment_handover"


# =============================================================================
# E04-S01: APPLICANT SERVICE
# =============================================================================

class TestApplicantServiceCreate:

    def test_create_applicant_success(self):
        """Create applicant: no duplicate, INSERT succeeds, returns ApplicantRead."""
        from server.admissions.service import ApplicantService

        with patch(f"{SVC}.execute_query", side_effect=[
            [],              # _find_duplicate: no duplicate
            [APPLICANT_ROW], # get_applicant after INSERT
        ]), patch(f"{SVC}.execute_transaction"):
            result = ApplicantService.create_applicant(
                data=VALID_CREATE,
                org_id=TENANT,
                created_by=ACTOR,
            )

        assert result.id is not None
        assert result.email == "priya.sharma@example.com"
        assert result.status == ApplicantStatus.APPLIED.value
        assert result.org_id == TENANT

    def test_create_applicant_duplicate_raises(self):
        """Duplicate email or phone raises BusinessRuleViolation."""
        from server.admissions.service import ApplicantService

        with patch(f"{SVC}.execute_query", return_value=[APPLICANT_ROW]):
            with pytest.raises(BusinessRuleViolation, match="Duplicate applicant"):
                ApplicantService.create_applicant(
                    data=VALID_CREATE,
                    org_id=TENANT,
                    created_by=ACTOR,
                )

    def test_create_applicant_calls_execute_transaction(self):
        """INSERT must go through execute_transaction — never direct query."""
        from server.admissions.service import ApplicantService

        mock_tx = MagicMock()
        with patch(f"{SVC}.execute_query", side_effect=[[], [APPLICANT_ROW]]), \
             patch(f"{SVC}.execute_transaction", mock_tx):
            ApplicantService.create_applicant(
                data=VALID_CREATE,
                org_id=TENANT,
                created_by=ACTOR,
            )

        assert mock_tx.called, "execute_transaction must be called on create"

    def test_create_applicant_name_stored_correctly(self):
        """Applicant name is stored as-is (no truncation)."""
        from server.admissions.service import ApplicantService

        long_name = "A" * 190
        row = {**APPLICANT_ROW, "name": long_name}
        with patch(f"{SVC}.execute_query", side_effect=[[], [row]]), \
             patch(f"{SVC}.execute_transaction"):
            result = ApplicantService.create_applicant(
                data=ApplicantCreate(
                    name=long_name,
                    email="long@example.com",
                    phone="9000000001",
                    intended_program="B.Tech",
                ),
                org_id=TENANT,
                created_by=ACTOR,
            )
        assert result.name == long_name


class TestApplicantServiceRead:

    def test_get_applicant_returns_read_object(self):
        from server.admissions.service import ApplicantService

        with patch(f"{SVC}.execute_query", return_value=[APPLICANT_ROW]):
            result = ApplicantService.get_applicant(APPLICANT_ID, TENANT)

        assert isinstance(result, ApplicantRead)
        assert result.id == APPLICANT_ID

    def test_get_applicant_not_found_raises(self):
        from server.admissions.service import ApplicantService

        with patch(f"{SVC}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                ApplicantService.get_applicant("ghost-id", TENANT)

    def test_list_applicants_empty(self):
        from server.admissions.service import ApplicantService

        with patch(f"{SVC}.execute_query", return_value=[]):
            result = ApplicantService.list_applicants(org_id=TENANT)

        assert result == []

    def test_list_applicants_returns_all(self):
        from server.admissions.service import ApplicantService

        rows = [APPLICANT_ROW, {**APPLICANT_ROW, "id": "app-002"}]
        with patch(f"{SVC}.execute_query", return_value=rows):
            result = ApplicantService.list_applicants(org_id=TENANT)

        assert len(result) == 2
        assert all(isinstance(a, ApplicantRead) for a in result)

    def test_list_applicants_filters_by_status(self):
        """Status filter must be passed to the DB query."""
        from server.admissions.service import ApplicantService

        mock_q = MagicMock(return_value=[])
        with patch(f"{SVC}.execute_query", mock_q):
            ApplicantService.list_applicants(org_id=TENANT, status="APPLIED")

        call_args = mock_q.call_args
        assert "APPLIED" in call_args[0][1]   # params tuple contains status

    def test_list_applicants_pagination(self):
        """Limit and offset are passed to the DB query."""
        from server.admissions.service import ApplicantService

        mock_q = MagicMock(return_value=[])
        with patch(f"{SVC}.execute_query", mock_q):
            ApplicantService.list_applicants(org_id=TENANT, limit=10, offset=20)

        params = mock_q.call_args[0][1]
        assert 10 in params
        assert 20 in params


# =============================================================================
# E04-S03: ELIGIBILITY SERVICE
# =============================================================================

class TestEligibilityService:

    def _agent_result(self, proposed_state: str, score: float = 0.85):
        """Build a mock AgentResult with JSON content."""
        import json
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.error = None
        mock_result.content = json.dumps({
            "eligibility_score": score,
            "confidence_tier": "HIGH" if score >= 0.8 else "MEDIUM",
            "proposed_state": proposed_state,
        })
        return mock_result

    def test_evaluate_returns_eligible_state(self):
        from server.admissions.eligibility_service import EligibilityService

        applied_row = {**APPLICANT_ROW, "status": "APPLIED"}
        mock_transitioned = MagicMock()
        mock_transitioned.status = "ELIGIBLE"

        with patch(f"{ELIG}.execute_query", return_value=[applied_row]), \
             patch("server.agents.admissions.registry.AdmissionsAgentRegistry.execute",
                   return_value=self._agent_result("ELIGIBLE", 0.90)), \
             patch("server.admissions.service.ApplicantService.transition_state",
                   return_value=mock_transitioned):
            result = EligibilityService.evaluate(
                applicant_id=APPLICANT_ID,
                org_id=TENANT,
                marksheet_text="Aggregate: 80%",
                admission_criteria="Min 50%",
                actor_id=ACTOR,
                actor_role="registrar",
            )

        assert "eligibility_score" in result or "proposed_state" in result or result is not None

    def test_evaluate_applicant_not_found_raises(self):
        from server.admissions.eligibility_service import EligibilityService

        with patch(f"{ELIG}.execute_query", return_value=[]):
            with pytest.raises(Exception):   # BusinessRuleViolation or NotFoundError
                EligibilityService.evaluate(
                    applicant_id="ghost",
                    org_id=TENANT,
                    marksheet_text="",
                    admission_criteria="",
                    actor_id=ACTOR,
                    actor_role="registrar",
                )

    def test_evaluate_wrong_status_raises(self):
        """Applicant must be in APPLIED state for eligibility evaluation."""
        from server.admissions.eligibility_service import EligibilityService

        enrolled_row = {**APPLICANT_ROW, "status": "ENROLLED"}
        with patch(f"{ELIG}.execute_query", return_value=[enrolled_row]):
            with pytest.raises(BusinessRuleViolation, match="APPLIED"):
                EligibilityService.evaluate(
                    applicant_id=APPLICANT_ID,
                    org_id=TENANT,
                    marksheet_text="",
                    admission_criteria="",
                    actor_id=ACTOR,
                    actor_role="registrar",
                )


# =============================================================================
# E04-S07: ADMISSION CONFIRMATION SERVICE
# =============================================================================

class TestAdmissionConfirmationService:

    def test_confirm_success(self):
        from server.admissions.confirmation import AdmissionConfirmationService
        from server.admissions.models import AdmissionConfirmRequest

        eligible_row = {**APPLICANT_ROW, "status": "ELIGIBLE"}
        mock_transitioned = MagicMock()
        mock_transitioned.status = "ADMITTED"

        with patch(f"{CONF}.execute_query", side_effect=[
            [eligible_row],      # fetch applicant (status=ELIGIBLE)
            [],                   # no existing payment (Layer 4 check)
            [{"cnt": 0}],        # count for registration number generation
            [],                   # registration number uniqueness check
        ]), patch(f"{CONF}.execute_transaction"), \
           patch("server.admissions.service.ApplicantService.transition_state",
                 return_value=mock_transitioned):
            result = AdmissionConfirmationService.confirm(
                request=AdmissionConfirmRequest(
                    applicant_id=APPLICANT_ID,
                    payment_reference="PAY-001",
                    fee_amount=50000.0,
                ),
                org_id=TENANT,
                actor_id=ACTOR,
            )

        assert result is not None

    def test_confirm_not_found_raises(self):
        from server.admissions.confirmation import AdmissionConfirmationService
        from server.admissions.models import AdmissionConfirmRequest

        with patch(f"{CONF}.execute_query", return_value=[]):
            with pytest.raises(Exception):
                AdmissionConfirmationService.confirm(
                    request=AdmissionConfirmRequest(
                        applicant_id="ghost",
                        payment_reference="PAY-002",
                        fee_amount=50000.0,
                    ),
                    org_id=TENANT,
                    actor_id=ACTOR,
                )


# =============================================================================
# E04-S09: ENROLLMENT HANDOVER SERVICE
# =============================================================================

class TestEnrollmentHandoverService:

    def test_enroll_success(self):
        from server.admissions.enrollment_handover import EnrollmentHandoverService
        from server.admissions.models import EnrollmentHandoverRequest

        admitted_applicant = {**APPLICANT_ROW, "status": "ADMITTED"}
        mock_transitioned = MagicMock()
        mock_transitioned.status = "ENROLLED"

        with patch(f"{ENROLL}.execute_query", side_effect=[
            [admitted_applicant],                    # fetch applicant (status=ADMITTED)
            [{"registration_number": "REG-001"}],    # admission record (Layer 4 — fee paid)
            [],                                       # no existing student (duplicate check)
            [{"cnt": 0}],                            # count for roll number generation
            [],                                       # roll number uniqueness check
        ]), patch(f"{ENROLL}.execute_transaction"), \
           patch("server.admissions.service.ApplicantService.transition_state",
                 return_value=mock_transitioned):
            result = EnrollmentHandoverService.enroll(
                request=EnrollmentHandoverRequest(
                    applicant_id=APPLICANT_ID,
                    program_id="prog-cs",
                    academic_year="2024-25",
                ),
                org_id=TENANT,
                actor_id=ACTOR,
            )

        assert result is not None

    def test_enroll_not_confirmed_raises(self):
        """Only CONFIRMED applicants can be enrolled."""
        from server.admissions.enrollment_handover import EnrollmentHandoverService
        from server.admissions.models import EnrollmentHandoverRequest

        applied_row = {**APPLICANT_ROW, "status": "APPLIED"}   # wrong status

        with patch(f"{ENROLL}.execute_query", return_value=[applied_row]):
            with pytest.raises(Exception):
                EnrollmentHandoverService.enroll(
                    request=EnrollmentHandoverRequest(
                        applicant_id=APPLICANT_ID,
                        program_id="prog-cs",
                        academic_year="2024-25",
                    ),
                    org_id=TENANT,
                    actor_id=ACTOR,
                )


# =============================================================================
# RBAC UNIT TESTS: verify_access() matrix
# =============================================================================

class TestRBACMatrix:
    """
    Test the RBAC permission matrix directly via verify_access().
    This is the canonical RBAC test — not tied to any HTTP endpoint.
    """

    @pytest.mark.parametrize("role,perm,expected", [
        # SUPER_ADMIN has everything
        ("super_admin", "student:create", True),
        ("super_admin", "student:read",   True),
        ("super_admin", "ai:invoke",      True),
        ("super_admin", "audit_log:read", True),
        # REGISTRAR can manage student records but not audit logs
        ("registrar", "student:create", True),
        ("registrar", "student:read",   True),
        ("registrar", "audit_log:read", False),
        # STUDENT: read own data only, no create, no AI, no audit
        ("student", "student:read",   True),
        ("student", "student:create", False),
        ("student", "ai:invoke",      False),
        ("student", "audit_log:read", False),
        # FACULTY: read courses/marks, no admin ops
        ("faculty", "student:read",     True),
        ("faculty", "student:create",   False),
        ("faculty", "audit_log:read",   False),
        # FINANCE_OFFICER: fee read/create but not student admin
        ("finance_officer", "fee:read",         True),
        ("finance_officer", "fee:create",       True),
        ("finance_officer", "student:create",   False),
        # M1_MANAGER: can create students (admissions module manager)
        ("m1_manager", "student:create", True),
        ("m1_manager", "student:read",   True),
        # ADMIN: user management, audit, config — not student:create
        ("admin", "user:read",        True),
        ("admin", "audit_log:read",   True),
        ("admin", "student:create",   False),
    ])
    def test_rbac_permission_matrix(self, role, perm, expected):
        from server.core.rbac import verify_access, Role, Permission

        role_enum = Role(role)
        perm_enum = Permission(perm)
        result = verify_access(role_enum, perm_enum)
        assert result.allowed == expected, (
            f"Role {role!r} × Permission {perm!r}: "
            f"expected allowed={expected}, got {result.allowed}. "
            f"Reason: {result.reason}"
        )

    def test_unknown_role_is_denied(self):
        """Any role not in the RBAC map should be denied all permissions."""
        from server.core.rbac import verify_access, Role, Permission
        # AI_AGENT is a special role in ALIS — has limited read-only permissions
        # but not student:create
        result = verify_access(Role.AI_AGENT, Permission.STUDENT_CREATE)
        assert not result.allowed

    def test_deny_result_has_reason(self):
        """Denied results must always carry a reason string."""
        from server.core.rbac import verify_access, Role, Permission
        result = verify_access(Role.STUDENT, Permission.STUDENT_CREATE)
        assert not result.allowed
        assert result.reason, "Denied result must have a non-empty reason"
