"""
P6 — Eligibility Criteria Registry + Rule Engine (Stage 4)

MODULE: M1 — Admissions & Marketing
LAYER: Layer 1 (Policy Config) + Layer 2 (Rule Evaluation)

Provides configurable, deterministic eligibility evaluation per program:

    EligibilityCriteriaService
        - Define per-program criteria (min %, required subjects, boards, entrance)
        - Category relaxations (SC/ST/OBC/EWS/PWD get % reduction on threshold)
        - Recognized board whitelist (or "*" for all boards)

    EligibilityRuleEngine
        - Deterministic evaluation — no AI required for clear PASS/FAIL
        - Returns ELIGIBLE / NOT_ELIGIBLE / PROVISIONALLY_ELIGIBLE / NEEDS_AI_REVIEW
        - Only borderline cases escalate to AI agent

Storage: `institution_policies` table via PolicyStore
    Key pattern: admissions.eligibility.criteria.{program_name_slug}
    Value:       EligibilityCriteria dict (JSONB)

Rule Logic:
    1. Load criteria for the applicant's intended_program (fall back to defaults)
    2. Fetch CLASS_12 academic qualification + entrance_exam_scores
    3. Apply category relaxation → effective_min_percentage
    4. Score bands:
       >= effective_min + review_buffer  → ELIGIBLE (confident)
       >= effective_min                  → PROVISIONALLY_ELIGIBLE (borderline → AI review)
       < effective_min                  → NOT_ELIGIBLE (hard fail)
    5. Required subjects check (substring match on stream_or_subject)
    6. Board validation (whitelist or "*" = any)
    7. Entrance score check (if requires_entrance_test)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import BusinessRuleViolation
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# Category relaxation applied to minimum percentage threshold
_DEFAULT_CATEGORY_RELAXATIONS: Dict[str, float] = {
    "SC":      5.0,   # min reduced by 5%
    "ST":      5.0,
    "OBC_NCL": 3.0,
    "EWS":     3.0,
    "PWD":     5.0,
}

# Known board aliases for normalization
_BOARD_ALIASES: Dict[str, str] = {
    "cbse":               "CBSE",
    "central board":      "CBSE",
    "icse":               "ICSE",
    "isc":                "ICSE",
    "council for the indian school": "ICSE",
    "state board":        "STATE_BOARD",
    "state":              "STATE_BOARD",
    "igcse":              "IGCSE",
    "cambridge":          "IGCSE",
    "ib":                 "IB",
    "international baccalaureate": "IB",
    "nios":               "NIOS",
    "open school":        "NIOS",
}


# =============================================================================
# Models
# =============================================================================

class EligibilityCriteria(BaseModel):
    """Per-program eligibility criteria definition."""
    program_name: str
    intake_batch: Optional[str] = Field(
        default=None,
        description="NULL = applies to all batches for this program"
    )

    # Academic threshold
    min_percentage: float = Field(
        default=50.0, ge=0, le=100,
        description="Minimum qualifying percentage in Class 12 (or highest qualification)"
    )
    review_buffer: float = Field(
        default=3.0, ge=0, le=20,
        description="Applicants within [min - buffer, min) are PROVISIONALLY_ELIGIBLE"
    )

    # Subject requirements
    required_subjects: List[str] = Field(
        default_factory=list,
        description="Required subject keywords — e.g. ['Physics', 'Chemistry', 'Mathematics']"
    )

    # Board whitelist
    accepted_boards: List[str] = Field(
        default_factory=lambda: ["*"],
        description='Board names OR ["*"] for any board'
    )

    # Entrance test
    requires_entrance_test: bool = False
    min_entrance_score: Optional[float] = Field(
        default=None, ge=0,
        description="Minimum raw score / percentile required on entrance exam"
    )
    entrance_score_field: str = Field(
        default="percentile",
        description="Which field to check: 'percentile' | 'score' | 'rank'"
    )
    accepted_exams: List[str] = Field(
        default_factory=list,
        description="Accepted exam names (e.g. ['JEE_MAINS', 'STATE_CET']); empty = any"
    )

    # Category relaxations (overrides defaults)
    category_relaxations: Dict[str, float] = Field(
        default_factory=lambda: dict(_DEFAULT_CATEGORY_RELAXATIONS)
    )

    # Metadata
    approved_by: Optional[str] = None
    effective_from: Optional[str] = None  # ISO date


class EligibilityVerdictDetail(BaseModel):
    """Full breakdown of the rule engine verdict."""
    verdict: str  # ELIGIBLE | NOT_ELIGIBLE | PROVISIONALLY_ELIGIBLE | NEEDS_AI_REVIEW
    pass_reasons: List[str]
    fail_reasons: List[str]
    warnings: List[str]

    # Data used in evaluation
    category: str
    effective_min_percentage: float
    applicant_percentage: Optional[float]
    applicant_board: Optional[str]
    entrance_score_used: Optional[float]
    criteria_applied: Optional[str]  # program name of criteria used


# =============================================================================
# ELIGIBILITY CRITERIA SERVICE
# =============================================================================

class EligibilityCriteriaService:
    """
    Stores and retrieves eligibility criteria per program.

    Persists to institution_policies as:
        key  = admissions.eligibility.criteria.{slug(program_name)}
        value = EligibilityCriteria dict

    Batch-specific criteria override program-level (key includes batch suffix).
    """

    _KEY_PREFIX = "admissions.eligibility.criteria."

    @classmethod
    def _key(cls, program_name: str, intake_batch: Optional[str] = None) -> str:
        slug = _slugify(program_name)
        if intake_batch:
            return f"{cls._KEY_PREFIX}{slug}.{_slugify(intake_batch)}"
        return f"{cls._KEY_PREFIX}{slug}"

    @classmethod
    def set_criteria(
        cls,
        criteria: EligibilityCriteria,
        org_id: str,
        actor_id: str,
    ) -> EligibilityCriteria:
        """
        Create or replace eligibility criteria for a program (and optional batch).

        Upserts into institution_policies.
        """
        key = cls._key(criteria.program_name, criteria.intake_batch)
        value = criteria.model_dump()
        now = datetime.now(timezone.utc)

        execute_transaction([
            (
                """
                INSERT INTO institution_policies
                    (id, org_id, key, value, description, category, is_active, created_at, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                ON CONFLICT (org_id, key)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = NOW()
                """,
                (
                    str(uuid4()), org_id, key,
                    json.dumps(value),
                    f"Eligibility criteria for {criteria.program_name}",
                    "eligibility",
                    True,
                    now, now,
                ),
            )
        ])

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="eligibility_criteria",
            entity_id=key,
            org_id=org_id,
            module="M1",
            wizard="Eligibility Criteria",
            success=True,
            metadata={
                "program_name": criteria.program_name,
                "min_percentage": criteria.min_percentage,
                "required_subjects": criteria.required_subjects,
                "requires_entrance_test": criteria.requires_entrance_test,
            },
        )

        logger.info(
            "Eligibility criteria set: %s [org=%s min_pct=%.1f]",
            criteria.program_name, org_id, criteria.min_percentage,
        )
        return criteria

    @classmethod
    def get_criteria(
        cls,
        org_id: str,
        program_name: str,
        intake_batch: Optional[str] = None,
    ) -> Optional[EligibilityCriteria]:
        """
        Fetch eligibility criteria for a program.

        Lookup priority:
          1. Batch-specific criteria (program + batch)
          2. Program-level criteria (program only)
          3. None (caller falls back to defaults)
        """
        # Try batch-specific first
        if intake_batch:
            row = cls._fetch_row(org_id, cls._key(program_name, intake_batch))
            if row:
                return EligibilityCriteria(**row)

        # Fall back to program-level
        row = cls._fetch_row(org_id, cls._key(program_name))
        if row:
            return EligibilityCriteria(**row)

        return None

    @classmethod
    def list_criteria(cls, org_id: str) -> List[EligibilityCriteria]:
        rows = execute_query(
            "SELECT value FROM institution_policies "
            "WHERE org_id = %s AND category = 'eligibility' AND is_active = TRUE "
            "ORDER BY key ASC",
            (org_id,),
        )
        results = []
        for r in rows:
            try:
                val = r["value"] if isinstance(r["value"], dict) else json.loads(r["value"])
                results.append(EligibilityCriteria(**val))
            except Exception:
                pass
        return results

    @classmethod
    def delete_criteria(
        cls, org_id: str, program_name: str, actor_id: str,
        intake_batch: Optional[str] = None,
    ) -> None:
        key = cls._key(program_name, intake_batch)
        execute_transaction([
            (
                "UPDATE institution_policies SET is_active = FALSE, updated_at = NOW() "
                "WHERE org_id = %s AND key = %s",
                (org_id, key),
            )
        ])
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="eligibility_criteria",
            entity_id=key,
            org_id=org_id,
            module="M1",
            wizard="Eligibility Criteria",
            success=True,
            metadata={"action": "deactivated", "program_name": program_name},
        )

    @classmethod
    def _fetch_row(cls, org_id: str, key: str) -> Optional[Dict[str, Any]]:
        rows = execute_query(
            "SELECT value FROM institution_policies "
            "WHERE org_id = %s AND key = %s AND is_active = TRUE",
            (org_id, key),
        )
        if not rows:
            return None
        val = rows[0]["value"]
        return val if isinstance(val, dict) else json.loads(val)


# =============================================================================
# ELIGIBILITY RULE ENGINE
# =============================================================================

class EligibilityRuleEngine:
    """
    Deterministic rule-based eligibility evaluation.

    Does NOT call the AI gateway. Produces a verdict that the
    EligibilityService orchestrator uses to decide whether to:
    - Auto-transition (clear PASS or clear FAIL), OR
    - Escalate to AI agent for borderline cases
    """

    @classmethod
    def evaluate(
        cls,
        applicant_id: str,
        org_id: str,
        criteria: Optional[EligibilityCriteria] = None,
    ) -> EligibilityVerdictDetail:
        """
        Evaluate an applicant against eligibility criteria.

        Args:
            applicant_id:  Applicant to check
            org_id:        Tenant scope
            criteria:      Pre-loaded criteria (if None, uses defaults)

        Returns:
            EligibilityVerdictDetail with verdict + full reasoning
        """
        # --- Load applicant ---
        app_rows = execute_query(
            "SELECT intended_program, category, intake_batch FROM applicants "
            "WHERE id = %s AND org_id = %s",
            (applicant_id, org_id),
        )
        if not app_rows:
            raise BusinessRuleViolation(message=f"Applicant '{applicant_id}' not found.")

        applicant = app_rows[0]
        category = applicant.get("category") or "GENERAL"
        program = applicant.get("intended_program", "")
        batch = applicant.get("intake_batch")

        # --- Load criteria (or defaults) ---
        if criteria is None:
            criteria = EligibilityCriteriaService.get_criteria(org_id, program, batch)
        if criteria is None:
            criteria = EligibilityCriteria(program_name=program)  # all-defaults

        # --- Apply category relaxation ---
        relaxation = criteria.category_relaxations.get(category, 0.0)
        effective_min = max(0.0, criteria.min_percentage - relaxation)

        pass_reasons: List[str] = []
        fail_reasons: List[str] = []
        warnings: List[str] = []

        # ----------------------------------------------------------------
        # Check 1: Academic percentage
        # ----------------------------------------------------------------
        qual_rows = execute_query(
            "SELECT percentage, cgpa, grade_scale, stream_or_subject, board_or_university "
            "FROM academic_qualifications "
            "WHERE applicant_id = %s AND org_id = %s "
            "AND level IN ('CLASS_12', 'DIPLOMA') "
            "ORDER BY year_of_passing DESC LIMIT 1",
            (applicant_id, org_id),
        )

        applicant_pct: Optional[float] = None
        applicant_board: Optional[str] = None
        stream_text: str = ""

        if qual_rows:
            qual = qual_rows[0]
            # Derive percentage: direct field, or CGPA×10 if only CGPA available
            if qual.get("percentage") is not None:
                applicant_pct = float(qual["percentage"])
            elif qual.get("cgpa") is not None and qual.get("grade_scale"):
                applicant_pct = float(qual["cgpa"]) / float(qual["grade_scale"]) * 100
            applicant_board = qual.get("board_or_university") or ""
            stream_text = qual.get("stream_or_subject") or ""
        else:
            warnings.append("No Class 12 / Diploma qualification on record.")

        # Percentage band check
        pct_verdict = "UNKNOWN"
        if applicant_pct is not None:
            if applicant_pct >= effective_min + criteria.review_buffer:
                pass_reasons.append(
                    f"Academic percentage {applicant_pct:.1f}% ≥ "
                    f"effective threshold {effective_min + criteria.review_buffer:.1f}%."
                )
                pct_verdict = "PASS"
            elif applicant_pct >= effective_min:
                warnings.append(
                    f"Academic percentage {applicant_pct:.1f}% is within review band "
                    f"[{effective_min:.1f}%, {effective_min + criteria.review_buffer:.1f}%). "
                    f"Flagged for AI review."
                )
                pct_verdict = "BORDERLINE"
            else:
                fail_reasons.append(
                    f"Academic percentage {applicant_pct:.1f}% < "
                    f"effective minimum {effective_min:.1f}% "
                    f"(base {criteria.min_percentage:.1f}%, "
                    f"category relaxation {relaxation:.1f}% for {category})."
                )
                pct_verdict = "FAIL"
        else:
            pct_verdict = "UNKNOWN"
            warnings.append("Cannot check academic threshold — percentage not on record.")

        # ----------------------------------------------------------------
        # Check 2: Required subjects
        # ----------------------------------------------------------------
        if criteria.required_subjects:
            missing_subjects = []
            for subj in criteria.required_subjects:
                if not _subject_present(subj, stream_text):
                    missing_subjects.append(subj)
            if missing_subjects:
                fail_reasons.append(
                    f"Missing required subjects: {', '.join(missing_subjects)}. "
                    f"Stream recorded: '{stream_text}'."
                )
            else:
                pass_reasons.append(
                    f"All required subjects present: {', '.join(criteria.required_subjects)}."
                )

        # ----------------------------------------------------------------
        # Check 3: Board validation
        # ----------------------------------------------------------------
        if criteria.accepted_boards and criteria.accepted_boards != ["*"]:
            if applicant_board:
                normalized = _normalize_board(applicant_board)
                accepted_normalized = {_normalize_board(b) for b in criteria.accepted_boards}
                if normalized not in accepted_normalized and "STATE_BOARD" not in accepted_normalized:
                    fail_reasons.append(
                        f"Board '{applicant_board}' is not in accepted boards: "
                        f"{criteria.accepted_boards}."
                    )
                else:
                    pass_reasons.append(f"Board '{applicant_board}' is accepted.")
            else:
                warnings.append("Board/University not on record — cannot validate.")

        # ----------------------------------------------------------------
        # Check 4: Entrance exam score
        # ----------------------------------------------------------------
        entrance_score_used: Optional[float] = None
        if criteria.requires_entrance_test:
            score_rows = execute_query(
                "SELECT exam_name, score, percentile, rank "
                "FROM entrance_exam_scores "
                "WHERE applicant_id = %s AND org_id = %s "
                "ORDER BY created_at DESC",
                (applicant_id, org_id),
            )
            if not score_rows:
                fail_reasons.append(
                    "Entrance exam score is required but none found on record."
                )
            else:
                # Filter by accepted exams if specified
                valid_scores = score_rows
                if criteria.accepted_exams:
                    valid_scores = [
                        r for r in score_rows
                        if r["exam_name"] in criteria.accepted_exams
                    ]
                    if not valid_scores:
                        fail_reasons.append(
                            f"No valid entrance exam score found. "
                            f"Accepted exams: {criteria.accepted_exams}. "
                            f"Found: {[r['exam_name'] for r in score_rows]}."
                        )
                        valid_scores = []

                if valid_scores:
                    # Use best score among valid entries
                    field = criteria.entrance_score_field
                    best = max(
                        (float(r[field]) for r in valid_scores if r.get(field) is not None),
                        default=None,
                    )
                    entrance_score_used = best

                    if criteria.min_entrance_score is not None and best is not None:
                        if best >= criteria.min_entrance_score:
                            pass_reasons.append(
                                f"Entrance {field} {best:.2f} ≥ "
                                f"required {criteria.min_entrance_score:.2f}."
                            )
                        else:
                            fail_reasons.append(
                                f"Entrance {field} {best:.2f} < "
                                f"required {criteria.min_entrance_score:.2f}."
                            )
                    else:
                        pass_reasons.append(
                            f"Entrance exam score on record ({field}={best})."
                        )

        # ----------------------------------------------------------------
        # Final verdict
        # ----------------------------------------------------------------
        has_hard_fail = bool(fail_reasons)
        is_borderline = pct_verdict == "BORDERLINE" and not has_hard_fail

        if has_hard_fail:
            verdict = "NOT_ELIGIBLE"
        elif is_borderline or pct_verdict == "UNKNOWN":
            verdict = "PROVISIONALLY_ELIGIBLE"
        else:
            verdict = "ELIGIBLE"

        # Escalate to AI if there are warnings alongside a pass (edge cases)
        if verdict == "ELIGIBLE" and len(warnings) >= 2:
            verdict = "PROVISIONALLY_ELIGIBLE"
            warnings.append("Multiple warnings — flagged for additional AI review.")

        logger.info(
            "P6 Rule Engine: applicant=%s verdict=%s [pct=%.1f eff_min=%.1f cat=%s fails=%d]",
            applicant_id,
            verdict,
            applicant_pct or 0,
            effective_min,
            category,
            len(fail_reasons),
        )

        return EligibilityVerdictDetail(
            verdict=verdict,
            pass_reasons=pass_reasons,
            fail_reasons=fail_reasons,
            warnings=warnings,
            category=category,
            effective_min_percentage=effective_min,
            applicant_percentage=applicant_pct,
            applicant_board=applicant_board,
            entrance_score_used=entrance_score_used,
            criteria_applied=criteria.program_name,
        )


# =============================================================================
# Helpers
# =============================================================================

def _slugify(text: str) -> str:
    """Convert program name to a safe policy key segment."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _subject_present(subject: str, stream_text: str) -> bool:
    """Check if a subject keyword appears in the stream/subject text (case-insensitive)."""
    return subject.lower() in stream_text.lower()


def _normalize_board(board: str) -> str:
    """Normalize a board name to its canonical alias."""
    lower = board.lower()
    for pattern, canonical in _BOARD_ALIASES.items():
        if pattern in lower:
            return canonical
    # State board detection: contains state name patterns
    if any(w in lower for w in ["board", "madhyamik", "parishad", "vidyalaya"]):
        return "STATE_BOARD"
    return board.upper().strip()
