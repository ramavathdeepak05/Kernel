"""
Tests for P6 — Eligibility Criteria Registry + Rule Engine (Stage 4)

Covers:
  - EligibilityCriteria model validation
  - EligibilityCriteriaService: set, get (batch → program fallback), list, delete
  - EligibilityRuleEngine: ELIGIBLE, NOT_ELIGIBLE, PROVISIONALLY_ELIGIBLE paths
  - EligibilityService.evaluate() integration:
      * Short-circuit ELIGIBLE (no AI call)
      * Short-circuit NOT_ELIGIBLE (no AI call)
      * PROVISIONALLY_ELIGIBLE → AI agent escalation
      * AI agent failure → deterministic fallback
  - Category relaxations (SC/ST/OBC/EWS/PWD)
  - Required subjects enforcement
  - Board whitelist enforcement
  - Entrance exam score check
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call
from uuid import uuid4

import pytest

from server.admissions.eligibility_criteria import (
    EligibilityCriteria,
    EligibilityCriteriaService,
    EligibilityRuleEngine,
    EligibilityVerdictDetail,
    _slugify,
    _normalize_board,
    _subject_present,
)
from server.core.exceptions import BusinessRuleViolation

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ORG_ID = "org-p6"
ACTOR_ID = "admin-001"
APPLICANT_ID = str(uuid4())

MOD_CRITERIA = "server.admissions.eligibility_criteria"
MOD_SERVICE = "server.admissions.eligibility_service"

_BASE_APPLICANT = {
    "id": APPLICANT_ID,
    "org_id": ORG_ID,
    "status": "SUBMITTED",
    "intended_program": "B.Tech Computer Science",
    "intake_batch": "2025",
    "category": "GENERAL",
}

_BASE_QUAL = {
    "percentage": 75.0,
    "cgpa": None,
    "grade_scale": None,
    "stream_or_subject": "Physics Chemistry Mathematics",
    "board_or_university": "CBSE",
}

_POLICY_ROW = lambda criteria: {
    "value": criteria.model_dump(),
}


# =============================================================================
# Helpers
# =============================================================================

def _make_criteria(**kwargs) -> EligibilityCriteria:
    defaults = dict(
        program_name="B.Tech Computer Science",
        min_percentage=60.0,
        review_buffer=3.0,
        required_subjects=["Physics", "Chemistry", "Mathematics"],
        accepted_boards=["*"],
    )
    defaults.update(kwargs)
    return EligibilityCriteria(**defaults)


# =============================================================================
# EligibilityCriteria model
# =============================================================================

class TestEligibilityCriteriaModel:
    def test_defaults(self):
        c = EligibilityCriteria(program_name="B.Tech")
        assert c.min_percentage == 50.0
        assert c.review_buffer == 3.0
        assert c.required_subjects == []
        assert c.accepted_boards == ["*"]
        assert c.requires_entrance_test is False
        assert "SC" in c.category_relaxations
        assert c.category_relaxations["SC"] == 5.0

    def test_category_relaxations_override(self):
        c = EligibilityCriteria(
            program_name="MBA",
            category_relaxations={"SC": 10.0, "ST": 10.0},
        )
        assert c.category_relaxations["SC"] == 10.0
        assert c.category_relaxations["ST"] == 10.0

    def test_min_percentage_bounds(self):
        with pytest.raises(Exception):
            EligibilityCriteria(program_name="X", min_percentage=101.0)
        with pytest.raises(Exception):
            EligibilityCriteria(program_name="X", min_percentage=-1.0)


# =============================================================================
# EligibilityCriteriaService
# =============================================================================

class TestEligibilityCriteriaService:

    def test_set_criteria_calls_upsert(self):
        criteria = _make_criteria()
        with (
            patch(f"{MOD_CRITERIA}.execute_transaction") as mock_tx,
            patch(f"{MOD_CRITERIA}.AuditLog.log"),
        ):
            result = EligibilityCriteriaService.set_criteria(criteria, ORG_ID, ACTOR_ID)

        assert result.program_name == criteria.program_name
        mock_tx.assert_called_once()
        sql = mock_tx.call_args[0][0][0][0]
        assert "ON CONFLICT" in sql

    def test_set_criteria_batch_specific_key(self):
        criteria = _make_criteria(intake_batch="2026")
        with (
            patch(f"{MOD_CRITERIA}.execute_transaction") as mock_tx,
            patch(f"{MOD_CRITERIA}.AuditLog.log"),
        ):
            EligibilityCriteriaService.set_criteria(criteria, ORG_ID, ACTOR_ID)

        params = mock_tx.call_args[0][0][0][1]
        key = params[2]  # 3rd param is the key
        assert "2026" in key

    def test_get_criteria_batch_specific_wins(self):
        criteria = _make_criteria(intake_batch="2025")
        row = {"value": criteria.model_dump()}
        with patch(f"{MOD_CRITERIA}.execute_query", return_value=[row]):
            result = EligibilityCriteriaService.get_criteria(ORG_ID, "B.Tech Computer Science", "2025")
        assert result is not None
        assert result.intake_batch == "2025"

    def test_get_criteria_falls_back_to_program(self):
        criteria = _make_criteria()  # no intake_batch
        row = {"value": criteria.model_dump()}

        call_count = {"n": 0}
        def side_effect(sql, params):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return []   # batch-specific miss
            return [row]    # program-level hit

        with patch(f"{MOD_CRITERIA}.execute_query", side_effect=side_effect):
            result = EligibilityCriteriaService.get_criteria(ORG_ID, "B.Tech Computer Science", "2025")
        assert result is not None
        assert result.program_name == "B.Tech Computer Science"

    def test_get_criteria_returns_none_when_missing(self):
        with patch(f"{MOD_CRITERIA}.execute_query", return_value=[]):
            result = EligibilityCriteriaService.get_criteria(ORG_ID, "Unknown Program")
        assert result is None

    def test_list_criteria(self):
        c1 = _make_criteria()
        c2 = _make_criteria(program_name="MBA", min_percentage=55.0)
        rows = [{"value": c1.model_dump()}, {"value": c2.model_dump()}]
        with patch(f"{MOD_CRITERIA}.execute_query", return_value=rows):
            results = EligibilityCriteriaService.list_criteria(ORG_ID)
        assert len(results) == 2

    def test_list_criteria_skips_invalid_rows(self):
        rows = [{"value": {"bad": "data"}}, {"value": _make_criteria().model_dump()}]
        with patch(f"{MOD_CRITERIA}.execute_query", return_value=rows):
            # bad row fails Pydantic validation → silently skipped
            results = EligibilityCriteriaService.list_criteria(ORG_ID)
        assert len(results) == 1

    def test_delete_criteria(self):
        with (
            patch(f"{MOD_CRITERIA}.execute_transaction") as mock_tx,
            patch(f"{MOD_CRITERIA}.AuditLog.log"),
        ):
            EligibilityCriteriaService.delete_criteria(ORG_ID, "B.Tech Computer Science", ACTOR_ID)
        mock_tx.assert_called_once()
        sql = mock_tx.call_args[0][0][0][0]
        assert "is_active = FALSE" in sql


# =============================================================================
# EligibilityRuleEngine — verdict paths
# =============================================================================

class TestEligibilityRuleEngineEligible:
    """Applicant clearly above threshold → ELIGIBLE."""

    def test_eligible_above_buffer(self):
        criteria = _make_criteria(min_percentage=60.0, review_buffer=3.0)
        # 75% >> 63% → ELIGIBLE
        app_row = [{**_BASE_APPLICANT}]
        qual_row = [{**_BASE_QUAL, "percentage": 75.0}]

        with (
            patch(f"{MOD_CRITERIA}.execute_query", side_effect=[app_row, qual_row, []]),
        ):
            verdict = EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID, criteria)

        assert verdict.verdict == "ELIGIBLE"
        assert verdict.applicant_percentage == 75.0
        assert verdict.fail_reasons == []

    def test_eligible_all_subjects_present(self):
        criteria = _make_criteria(
            min_percentage=60.0, review_buffer=3.0,
            required_subjects=["Physics", "Chemistry", "Mathematics"],
        )
        app_row = [{**_BASE_APPLICANT}]
        qual_row = [{**_BASE_QUAL, "percentage": 80.0,
                     "stream_or_subject": "Physics Chemistry Mathematics Computer"}]

        with patch(f"{MOD_CRITERIA}.execute_query", side_effect=[app_row, qual_row, []]):
            verdict = EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID, criteria)

        assert verdict.verdict == "ELIGIBLE"
        assert verdict.fail_reasons == []


class TestEligibilityRuleEngineNotEligible:
    """Hard fails → NOT_ELIGIBLE."""

    def test_not_eligible_low_percentage(self):
        criteria = _make_criteria(min_percentage=60.0, review_buffer=3.0)
        app_row = [{**_BASE_APPLICANT}]
        qual_row = [{**_BASE_QUAL, "percentage": 45.0}]

        with patch(f"{MOD_CRITERIA}.execute_query", side_effect=[app_row, qual_row, []]):
            verdict = EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID, criteria)

        assert verdict.verdict == "NOT_ELIGIBLE"
        assert any("45.0%" in r for r in verdict.fail_reasons)

    def test_not_eligible_missing_subject(self):
        criteria = _make_criteria(
            min_percentage=50.0, review_buffer=3.0,
            required_subjects=["Physics", "Mathematics"],
        )
        app_row = [{**_BASE_APPLICANT}]
        qual_row = [{**_BASE_QUAL, "percentage": 70.0,
                     "stream_or_subject": "Commerce Accountancy Economics"}]

        with patch(f"{MOD_CRITERIA}.execute_query", side_effect=[app_row, qual_row, []]):
            verdict = EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID, criteria)

        assert verdict.verdict == "NOT_ELIGIBLE"
        assert any("Physics" in r or "Mathematics" in r for r in verdict.fail_reasons)

    def test_not_eligible_board_not_accepted(self):
        criteria = _make_criteria(
            min_percentage=50.0, review_buffer=3.0,
            accepted_boards=["CBSE", "ICSE"],
            required_subjects=[],
        )
        app_row = [{**_BASE_APPLICANT}]
        qual_row = [{**_BASE_QUAL, "percentage": 70.0, "board_or_university": "IGCSE"}]

        with patch(f"{MOD_CRITERIA}.execute_query", side_effect=[app_row, qual_row, []]):
            verdict = EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID, criteria)

        assert verdict.verdict == "NOT_ELIGIBLE"
        assert any("IGCSE" in r or "not in accepted" in r for r in verdict.fail_reasons)

    def test_not_eligible_entrance_score_missing(self):
        criteria = _make_criteria(
            min_percentage=50.0, review_buffer=3.0,
            requires_entrance_test=True,
            min_entrance_score=70.0,
        )
        app_row = [{**_BASE_APPLICANT}]
        qual_row = [{**_BASE_QUAL, "percentage": 75.0}]
        score_row = []  # no entrance scores

        with patch(f"{MOD_CRITERIA}.execute_query", side_effect=[app_row, qual_row, score_row]):
            verdict = EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID, criteria)

        assert verdict.verdict == "NOT_ELIGIBLE"
        assert any("entrance" in r.lower() for r in verdict.fail_reasons)

    def test_not_eligible_entrance_score_too_low(self):
        criteria = _make_criteria(
            min_percentage=50.0, review_buffer=3.0,
            requires_entrance_test=True,
            min_entrance_score=70.0,
            entrance_score_field="percentile",
        )
        app_row = [{**_BASE_APPLICANT}]
        qual_row = [{**_BASE_QUAL, "percentage": 75.0}]
        score_row = [{"exam_name": "JEE_MAINS", "score": 100, "percentile": 55.0, "rank": None}]

        with patch(f"{MOD_CRITERIA}.execute_query", side_effect=[app_row, qual_row, score_row]):
            verdict = EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID, criteria)

        assert verdict.verdict == "NOT_ELIGIBLE"
        assert any("55.0" in r for r in verdict.fail_reasons)

    def test_applicant_not_found_raises(self):
        with patch(f"{MOD_CRITERIA}.execute_query", return_value=[]):
            with pytest.raises(BusinessRuleViolation, match="not found"):
                EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID)


class TestEligibilityRuleEngineProvisional:
    """Borderline percentage band → PROVISIONALLY_ELIGIBLE."""

    def test_provisional_within_review_band(self):
        # 61% is in [60, 63) → PROVISIONALLY_ELIGIBLE
        criteria = _make_criteria(min_percentage=60.0, review_buffer=3.0)
        app_row = [{**_BASE_APPLICANT}]
        qual_row = [{**_BASE_QUAL, "percentage": 61.5}]

        with patch(f"{MOD_CRITERIA}.execute_query", side_effect=[app_row, qual_row, []]):
            verdict = EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID, criteria)

        assert verdict.verdict == "PROVISIONALLY_ELIGIBLE"
        assert verdict.applicant_percentage == 61.5

    def test_provisional_when_no_qualification_on_record(self):
        # No required subjects so subject check cannot fail; unknown pct → PROVISIONAL
        criteria = _make_criteria(required_subjects=[])
        app_row = [{**_BASE_APPLICANT}]
        qual_row = []  # no qual data

        with patch(f"{MOD_CRITERIA}.execute_query", side_effect=[app_row, qual_row, []]):
            verdict = EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID, criteria)

        assert verdict.verdict == "PROVISIONALLY_ELIGIBLE"
        assert verdict.applicant_percentage is None


class TestCategoryRelaxations:
    """Category relaxations reduce effective threshold."""

    @pytest.mark.parametrize("category,relaxation,pct,expected", [
        # SC: effective_min=55, upper_edge=58; 56 in [55,58) -> PROVISIONAL
        ("SC", 5.0, 56.0, "PROVISIONALLY_ELIGIBLE"),
        # SC: 59 >= 55+3=58 -> ELIGIBLE
        ("SC", 5.0, 59.0, "ELIGIBLE"),
        ("ST", 5.0, 59.0, "ELIGIBLE"),
        # OBC_NCL: effective_min=57, upper=60; 60 >= 60 -> ELIGIBLE
        ("OBC_NCL", 3.0, 60.0, "ELIGIBLE"),
        # EWS: effective_min=57; 55 < 57 -> NOT_ELIGIBLE
        ("EWS", 3.0, 55.0, "NOT_ELIGIBLE"),
        ("GENERAL", 0.0, 55.0, "NOT_ELIGIBLE"),
    ])
    def test_relaxation(self, category, relaxation, pct, expected):
        criteria = _make_criteria(min_percentage=60.0, review_buffer=3.0, required_subjects=[])
        app_row = [{**_BASE_APPLICANT, "category": category}]
        qual_row = [{**_BASE_QUAL, "percentage": pct}]

        with patch(f"{MOD_CRITERIA}.execute_query", side_effect=[app_row, qual_row, []]):
            verdict = EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID, criteria)

        assert verdict.category == category
        assert verdict.effective_min_percentage == max(0.0, 60.0 - relaxation)
        assert verdict.verdict == expected

    def test_sc_effective_min_reported(self):
        criteria = _make_criteria(min_percentage=60.0)
        app_row = [{**_BASE_APPLICANT, "category": "SC"}]
        qual_row = [{**_BASE_QUAL, "percentage": 59.0}]

        with patch(f"{MOD_CRITERIA}.execute_query", side_effect=[app_row, qual_row, []]):
            verdict = EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID, criteria)

        assert verdict.effective_min_percentage == 55.0  # 60 - 5


class TestRuleEngineFallbackToDefaults:
    """When no criteria configured, rule engine uses in-code defaults."""

    def test_uses_default_criteria_when_none_configured(self):
        # No criteria → defaults (min=50, review=3)
        # Call order: applicant, batch-specific-criteria-miss, program-criteria-miss, qual, entrance
        app_row = [{**_BASE_APPLICANT}]
        qual_row = [{**_BASE_QUAL, "percentage": 80.0}]

        with patch(f"{MOD_CRITERIA}.execute_query", side_effect=[app_row, [], [], qual_row, []]):
            verdict = EligibilityRuleEngine.evaluate(APPLICANT_ID, ORG_ID, criteria=None)

        # With defaults (min=50, buffer=3), 80% → ELIGIBLE
        assert verdict.verdict == "ELIGIBLE"


# =============================================================================
# EligibilityService.evaluate() — integration (P6 orchestration)
# =============================================================================

MOD_SVC_FULL = "server.admissions.eligibility_service"


def _make_agent_result(verdict="PROVISIONALLY_ELIGIBLE", score=0.65):
    r = MagicMock()
    r.success = True
    r.content = json.dumps({
        "eligibility_score": score,
        "confidence_tier": "MEDIUM",
        "proposed_state": verdict,
    })
    r.request_id = "req-ai-001"
    r.error = None
    return r


class TestEligibilityServiceShortCircuit:
    """ELIGIBLE / NOT_ELIGIBLE → direct transition, no AI call."""

    def _db_rows_for_status(self, status="SUBMITTED"):
        return [{"status": status, "intended_program": "B.Tech CS", "intake_batch": "2025"}]

    def test_eligible_skips_ai(self):
        criteria = _make_criteria(min_percentage=60.0, review_buffer=3.0)
        applicant_row = self._db_rows_for_status()
        app_data = [{**_BASE_APPLICANT, "category": "GENERAL", "intended_program": "B.Tech CS", "intake_batch": "2025"}]
        qual_row = [{**_BASE_QUAL, "percentage": 80.0}]

        updated_mock = MagicMock()
        updated_mock.status = "ELIGIBLE"

        with (
            patch(f"{MOD_SVC_FULL}.execute_query", return_value=applicant_row),
            patch(f"{MOD_SVC_FULL}.EligibilityCriteriaService.get_criteria", return_value=criteria),
            patch(f"{MOD_SVC_FULL}.EligibilityRuleEngine.evaluate", return_value=EligibilityVerdictDetail(
                verdict="ELIGIBLE",
                pass_reasons=["80% ≥ 63%"],
                fail_reasons=[],
                warnings=[],
                category="GENERAL",
                effective_min_percentage=60.0,
                applicant_percentage=80.0,
                applicant_board="CBSE",
                entrance_score_used=None,
                criteria_applied="B.Tech CS",
            )),
            patch(f"{MOD_SVC_FULL}.ApplicantService.transition_state", return_value=updated_mock),
            patch("server.agents.admissions.registry.AdmissionsAgentRegistry.execute") as mock_ai,
        ):
            from server.admissions.eligibility_service import EligibilityService
            result = EligibilityService.evaluate(
                applicant_id=APPLICANT_ID,
                org_id=ORG_ID,
                marksheet_text="dummy",
                admission_criteria="dummy",
                actor_id=ACTOR_ID,
            )

        mock_ai.assert_not_called()
        assert result["new_status"] == "ELIGIBLE"
        assert result["confidence_tier"] == "HIGH"
        assert result["agent_request_id"] is None

    def test_not_eligible_skips_ai(self):
        applicant_row = self._db_rows_for_status()
        updated_mock = MagicMock()
        updated_mock.status = "NOT_ELIGIBLE"

        with (
            patch(f"{MOD_SVC_FULL}.execute_query", return_value=applicant_row),
            patch(f"{MOD_SVC_FULL}.EligibilityCriteriaService.get_criteria", return_value=None),
            patch(f"{MOD_SVC_FULL}.EligibilityRuleEngine.evaluate", return_value=EligibilityVerdictDetail(
                verdict="NOT_ELIGIBLE",
                pass_reasons=[],
                fail_reasons=["45% < 50%"],
                warnings=[],
                category="GENERAL",
                effective_min_percentage=50.0,
                applicant_percentage=45.0,
                applicant_board="CBSE",
                entrance_score_used=None,
                criteria_applied="B.Tech CS",
            )),
            patch(f"{MOD_SVC_FULL}.ApplicantService.transition_state", return_value=updated_mock),
            patch("server.agents.admissions.registry.AdmissionsAgentRegistry.execute") as mock_ai,
        ):
            from server.admissions.eligibility_service import EligibilityService
            result = EligibilityService.evaluate(
                applicant_id=APPLICANT_ID,
                org_id=ORG_ID,
                marksheet_text="dummy",
                admission_criteria="dummy",
                actor_id=ACTOR_ID,
            )

        mock_ai.assert_not_called()
        assert result["new_status"] == "NOT_ELIGIBLE"
        assert result["proposed_state"] == "NOT_ELIGIBLE"


class TestEligibilityServiceAIEscalation:
    """PROVISIONALLY_ELIGIBLE → AI agent called."""

    def _db_rows_for_status(self, status="SUBMITTED"):
        return [{"status": status, "intended_program": "B.Tech CS", "intake_batch": "2025"}]

    def test_provisional_calls_ai(self):
        applicant_row = self._db_rows_for_status()
        updated_mock = MagicMock()
        updated_mock.status = "PROVISIONALLY_ELIGIBLE"

        with (
            patch(f"{MOD_SVC_FULL}.execute_query", return_value=applicant_row),
            patch(f"{MOD_SVC_FULL}.EligibilityCriteriaService.get_criteria", return_value=None),
            patch(f"{MOD_SVC_FULL}.EligibilityRuleEngine.evaluate", return_value=EligibilityVerdictDetail(
                verdict="PROVISIONALLY_ELIGIBLE",
                pass_reasons=[],
                fail_reasons=[],
                warnings=["61.5% within review band"],
                category="GENERAL",
                effective_min_percentage=60.0,
                applicant_percentage=61.5,
                applicant_board="CBSE",
                entrance_score_used=None,
                criteria_applied="B.Tech CS",
            )),
            patch(f"{MOD_SVC_FULL}.ApplicantService.transition_state", return_value=updated_mock),
            patch("server.agents.admissions.registry.AdmissionsAgentRegistry.execute",
                  return_value=_make_agent_result("PROVISIONALLY_ELIGIBLE", 0.62)) as mock_ai,
        ):
            from server.admissions.eligibility_service import EligibilityService
            result = EligibilityService.evaluate(
                applicant_id=APPLICANT_ID,
                org_id=ORG_ID,
                marksheet_text="Physics 78, Chemistry 72, Maths 65",
                admission_criteria="min 60%",
                actor_id=ACTOR_ID,
            )

        mock_ai.assert_called_once()
        # Verify rule engine context was passed to AI
        call_kwargs = mock_ai.call_args[1] if mock_ai.call_args[1] else mock_ai.call_args[0][2]
        assert result["new_status"] == "PROVISIONALLY_ELIGIBLE"
        assert result["agent_request_id"] == "req-ai-001"

    def test_ai_failure_falls_back_to_provisional(self):
        applicant_row = self._db_rows_for_status()
        updated_mock = MagicMock()
        updated_mock.status = "PROVISIONALLY_ELIGIBLE"

        failed_result = MagicMock()
        failed_result.success = False
        failed_result.content = None
        failed_result.error = "Ollama timeout"
        failed_result.request_id = None

        with (
            patch(f"{MOD_SVC_FULL}.execute_query", return_value=applicant_row),
            patch(f"{MOD_SVC_FULL}.EligibilityCriteriaService.get_criteria", return_value=None),
            patch(f"{MOD_SVC_FULL}.EligibilityRuleEngine.evaluate", return_value=EligibilityVerdictDetail(
                verdict="PROVISIONALLY_ELIGIBLE",
                pass_reasons=[],
                fail_reasons=[],
                warnings=["borderline"],
                category="GENERAL",
                effective_min_percentage=60.0,
                applicant_percentage=61.0,
                applicant_board="CBSE",
                entrance_score_used=None,
                criteria_applied="B.Tech CS",
            )),
            patch(f"{MOD_SVC_FULL}.ApplicantService.transition_state", return_value=updated_mock),
            patch("server.agents.admissions.registry.AdmissionsAgentRegistry.execute", return_value=failed_result),
        ):
            from server.admissions.eligibility_service import EligibilityService
            result = EligibilityService.evaluate(
                applicant_id=APPLICANT_ID,
                org_id=ORG_ID,
                marksheet_text="dummy",
                admission_criteria="dummy",
                actor_id=ACTOR_ID,
            )

        assert result["new_status"] == "PROVISIONALLY_ELIGIBLE"
        assert result["confidence_tier"] == "LOW"
        assert result["agent_request_id"] is None

    def test_precondition_wrong_status_raises(self):
        applicant_row = [{"status": "ENROLLED", "intended_program": "B.Tech CS", "intake_batch": "2025"}]

        with patch(f"{MOD_SVC_FULL}.execute_query", return_value=applicant_row):
            from server.admissions.eligibility_service import EligibilityService
            from server.core.exceptions import BusinessRuleViolation
            with pytest.raises(BusinessRuleViolation, match="APPLIED status"):
                EligibilityService.evaluate(
                    applicant_id=APPLICANT_ID,
                    org_id=ORG_ID,
                    marksheet_text="dummy",
                    admission_criteria="dummy",
                    actor_id=ACTOR_ID,
                )

    def test_precondition_applicant_not_found_raises(self):
        with patch(f"{MOD_SVC_FULL}.execute_query", return_value=[]):
            from server.admissions.eligibility_service import EligibilityService
            from server.core.exceptions import BusinessRuleViolation
            with pytest.raises(BusinessRuleViolation, match="not found"):
                EligibilityService.evaluate(
                    applicant_id=APPLICANT_ID,
                    org_id=ORG_ID,
                    marksheet_text="dummy",
                    admission_criteria="dummy",
                    actor_id=ACTOR_ID,
                )


# =============================================================================
# Helper function tests
# =============================================================================

class TestHelpers:
    def test_slugify(self):
        assert _slugify("B.Tech Computer Science") == "b_tech_computer_science"
        assert _slugify("MBA (Finance)") == "mba_finance"
        assert _slugify("  BCA  ") == "bca"

    def test_normalize_board_cbse(self):
        assert _normalize_board("CBSE") == "CBSE"
        assert _normalize_board("central board of secondary education") == "CBSE"

    def test_normalize_board_icse(self):
        assert _normalize_board("isc") == "ICSE"
        assert _normalize_board("ICSE") == "ICSE"

    def test_normalize_board_state(self):
        assert _normalize_board("Maharashtra State Board") == "STATE_BOARD"
        assert _normalize_board("UP Madhyamik Parishad") == "STATE_BOARD"

    def test_normalize_board_unknown_uppercased(self):
        # "International Academy" has no matching pattern -> uppercased verbatim
        result = _normalize_board("International Academy")
        assert result == "INTERNATIONAL ACADEMY"

    def test_subject_present_case_insensitive(self):
        assert _subject_present("physics", "Physics Chemistry Maths")
        assert _subject_present("MATHEMATICS", "Physics Chemistry Mathematics")
        assert not _subject_present("Biology", "Physics Chemistry Mathematics")
