"""E17 — Credit Transfer Service

AI-generated equivalency mapping (draft via llm_router, Academic Committee review).
policy_engine governs max transferable credits.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.core.llm_router import LLMTaskClass, get_model_for_task
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class CreditTransferStatus(str, Enum):
    PENDING = "PENDING"
    AI_DRAFTED = "AI_DRAFTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


# =============================================================================
# CREDIT TRANSFER SERVICE
# =============================================================================


class CreditTransferService:
    """
    Manages credit transfer requests from external institutions.

    Workflow:
        1. submit_request()        — Student submits source course details.
        2. generate_ai_draft()     — LLM proposes an equivalency mapping.
        3. review_and_decide()     — Academic Committee approves/rejects/partial.

    Rules:
        - R1: Max transferable credit percentage is policy-governed.
        - R12: policy_version_id recorded on every committee decision.
        - R7: Eligibility threshold comes from policy_engine, never hardcoded.
    """

    # -------------------------------------------------------------------------
    # Submit
    # -------------------------------------------------------------------------

    @classmethod
    def submit_request(
        cls,
        org_id: str,
        student_id: str,
        source_institution: str,
        source_course_code: str,
        source_course_name: str,
        source_credits: int,
        readmission_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Submit a credit transfer request for an external course.

        Args:
            org_id:              Tenant ID.
            student_id:          UUID of the student requesting the transfer.
            source_institution:  Name of the institution where the course was taken.
            source_course_code:  Original course code (e.g. "CS101").
            source_course_name:  Full course name (e.g. "Introduction to Computing").
            source_credits:      Number of credits assigned by source institution.
            readmission_id:      Optional — link to a readmission application.

        Returns:
            Credit transfer request dict.
        """
        request_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                INSERT INTO credit_transfer_requests (
                    id, org_id, student_id, readmission_id,
                    source_institution, source_course_code, source_course_name,
                    source_credits, status, equivalency_method,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s
                )
                """,
                    (
                        request_id,
                        org_id,
                        student_id,
                        readmission_id,
                        source_institution,
                        source_course_code,
                        source_course_name,
                        source_credits,
                        CreditTransferStatus.PENDING.value,
                        "AI_DRAFT",
                        now,
                        now,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=student_id,
            entity_type="credit_transfer_request",
            entity_id=request_id,
            org_id=org_id,
            module="M1",
            wizard="Credit Transfer",
            success=True,
            metadata={
                "source_institution": source_institution,
                "source_course_code": source_course_code,
                "source_credits": source_credits,
                "readmission_id": readmission_id,
            },
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="admissions.credit_transfer_submitted",
                org_id=org_id,
                entity_type="credit_transfer_request",
                entity_id=request_id,
                actor_id=student_id,
                payload={
                    "request_id": request_id,
                    "org_id": org_id,
                    "student_id": student_id,
                    "source_institution": source_institution,
                    "source_course_code": source_course_code,
                    "source_course_name": source_course_name,
                    "source_credits": source_credits,
                    "readmission_id": readmission_id,
                },
            )
        )

        logger.info(
            "E17: Credit transfer request submitted [id=%s, student=%s, course=%s, credits=%d]",
            request_id,
            student_id,
            source_course_code,
            source_credits,
        )
        return cls._get_request(request_id, org_id)

    # -------------------------------------------------------------------------
    # Generate AI Draft
    # -------------------------------------------------------------------------

    @classmethod
    def generate_ai_draft(
        cls,
        request_id: str,
        org_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """
        Call the LLM to produce an equivalency mapping draft.

        Uses LLMTaskClass.REASONING (curriculum analysis requires multi-step
        reasoning). Falls back gracefully if Ollama is unavailable — the
        request is left in a reviewable state with a safe default draft.

        Args:
            request_id: UUID of the credit transfer request.
            org_id:     Tenant ID.
            actor_id:   Actor triggering the AI draft (e.g. admissions staff).

        Returns:
            Updated credit transfer request dict with ai_draft_json populated.
        """
        import httpx

        req = cls._require(request_id, org_id)

        source_institution = req["source_institution"]
        source_course_code = req["source_course_code"]
        source_course_name = req["source_course_name"]
        source_credits = req["source_credits"]

        model = get_model_for_task(LLMTaskClass.REASONING)

        prompt = (
            f"You are an academic curriculum expert.\n"
            f"A student is transferring from {source_institution}.\n"
            f"Source course: {source_course_code} — {source_course_name} ({source_credits} credits)\n\n"
            f"Suggest the most appropriate equivalent course from a standard "
            f"engineering/management curriculum.\n"
            f'Return JSON: {{"target_course_suggestion": "...", "target_credits": N, '
            f'"equivalency_rationale": "...", "confidence": 0.0-1.0}}'
        )

        ai_draft_raw: str
        try:
            from server.core.settings import settings as _settings

            resp = httpx.post(
                f"{_settings.ollama_base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=30,
            )
            resp.raise_for_status()
            ai_draft_raw = resp.json().get("response", "{}")
        except Exception as exc:
            logger.warning(
                "E17: LLM call failed for credit transfer draft [id=%s]: %s — using fallback",
                request_id,
                exc,
            )
            ai_draft_raw = (
                '{"target_course_suggestion": "Pending manual review", '
                '"target_credits": 0, "confidence": 0}'
            )

        # Parse JSON defensively — store raw string if parsing fails
        try:
            ai_draft_parsed = json.loads(ai_draft_raw)
        except (json.JSONDecodeError, ValueError):
            # Attempt to extract JSON substring if the model returned extra prose
            import re

            json_match = re.search(r"\{.*\}", ai_draft_raw, re.DOTALL)
            if json_match:
                try:
                    ai_draft_parsed = json.loads(json_match.group())
                except (json.JSONDecodeError, ValueError):
                    ai_draft_parsed = {
                        "target_course_suggestion": "Pending manual review",
                        "target_credits": 0,
                        "confidence": 0,
                        "raw_response": ai_draft_raw[:500],
                    }
            else:
                ai_draft_parsed = {
                    "target_course_suggestion": "Pending manual review",
                    "target_credits": 0,
                    "confidence": 0,
                    "raw_response": ai_draft_raw[:500],
                }

        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                UPDATE credit_transfer_requests
                SET status = %s,
                    ai_draft_json = %s,
                    equivalency_method = 'AI_DRAFT',
                    ai_drafted_at = %s,
                    ai_drafted_by = %s,
                    updated_at = %s
                WHERE id = %s AND org_id = %s
                """,
                    (
                        CreditTransferStatus.AI_DRAFTED.value,
                        json.dumps(ai_draft_parsed),
                        now,
                        actor_id,
                        now,
                        request_id,
                        org_id,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            entity_type="credit_transfer_request",
            entity_id=request_id,
            org_id=org_id,
            module="M1",
            wizard="Credit Transfer",
            success=True,
            metadata={
                "action": "ai_draft_generated",
                "model": model,
                "confidence": ai_draft_parsed.get("confidence"),
                "target_course_suggestion": ai_draft_parsed.get(
                    "target_course_suggestion"
                ),
            },
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="admissions.credit_transfer_ai_drafted",
                org_id=org_id,
                entity_type="credit_transfer_request",
                entity_id=request_id,
                actor_id=actor_id,
                payload={
                    "request_id": request_id,
                    "org_id": org_id,
                    "student_id": req["student_id"],
                    "source_course_code": source_course_code,
                    "ai_draft": ai_draft_parsed,
                    "model": model,
                },
            )
        )

        logger.info(
            "E17: AI draft generated [id=%s, model=%s, confidence=%s]",
            request_id,
            model,
            ai_draft_parsed.get("confidence"),
        )
        return cls._get_request(request_id, org_id)

    # -------------------------------------------------------------------------
    # Review and Decide
    # -------------------------------------------------------------------------

    @classmethod
    def review_and_decide(
        cls,
        request_id: str,
        org_id: str,
        decision: str,
        decided_by: str,
        notes: str | None = None,
        target_course_id: str | None = None,
        credits_awarded: int | None = None,
    ) -> dict[str, Any]:
        """
        Academic Committee decision on a credit transfer request.

        Validates that total approved credits for the student do not exceed
        the policy-governed maximum percentage of program credits.

        Args:
            request_id:       UUID of the credit transfer request.
            org_id:           Tenant ID.
            decision:         'APPROVED', 'REJECTED', or 'PARTIAL'.
            decided_by:       Actor ID of the committee member deciding.
            notes:            Optional committee notes.
            target_course_id: Optional UUID of the matched internal course.
            credits_awarded:  Number of credits to award (required for APPROVED/PARTIAL).

        Returns:
            Updated request dict.

        Raises:
            BusinessRuleViolation: For invalid decisions or credit cap exceeded.
        """
        _valid_decisions = {"APPROVED", "REJECTED", "PARTIAL"}
        if decision not in _valid_decisions:
            raise BusinessRuleViolation(
                message=f"Invalid decision '{decision}'. Must be one of: {', '.join(sorted(_valid_decisions))}.",
                details={"valid_decisions": sorted(_valid_decisions)},
            )

        req = cls._require(request_id, org_id)

        # R1 / R7 — policy-governed credit cap validation
        # Only validate if a target course is being linked (not for bare REJECTED decisions)
        if target_course_id is not None and decision in ("APPROVED", "PARTIAL"):
            max_credit_pct = policy_engine.get_value(
                "admissions.credit_transfer_max_pct", org_id, default=50
            )

            # Sum up previously approved credits for this student
            approved_rows = execute_query(
                """
                SELECT COALESCE(SUM(credits_awarded), 0) AS total_approved
                FROM credit_transfer_requests
                WHERE org_id = %s
                  AND student_id = %s
                  AND status IN ('APPROVED', 'PARTIAL')
                  AND id != %s
                """,
                (org_id, req["student_id"], request_id),
            )
            previously_approved = (
                int(approved_rows[0]["total_approved"]) if approved_rows else 0
            )
            this_award = credits_awarded or 0
            total_after = previously_approved + this_award

            # Fetch program total credits to compute percentage cap
            program_rows = execute_query(
                "SELECT total_credits FROM programs WHERE id = %s AND org_id = %s",
                (req.get("program_id") or "", org_id),
            )
            if program_rows and program_rows[0].get("total_credits"):
                program_total = int(program_rows[0]["total_credits"])
                cap_credits = (max_credit_pct / 100.0) * program_total
                if total_after > cap_credits:
                    raise BusinessRuleViolation(
                        message=(
                            f"Approving {this_award} credits would bring total transferred credits "
                            f"to {total_after}, exceeding the {max_credit_pct}% policy cap "
                            f"({cap_credits:.0f} credits for this program)."
                        ),
                        details={
                            "previously_approved_credits": previously_approved,
                            "this_award": this_award,
                            "total_after": total_after,
                            "cap_credits": cap_credits,
                            "max_credit_pct": max_credit_pct,
                        },
                    )

        # Map decision to a terminal status
        final_status = (
            CreditTransferStatus.APPROVED.value
            if decision in ("APPROVED", "PARTIAL")
            else CreditTransferStatus.REJECTED.value
        )

        # Fetch the currently active policy version for R12 compliance
        policy_version_rows = execute_query(
            """
            SELECT id FROM tenant_policies
            WHERE org_id = %s AND status = 'APPROVED'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (org_id,),
        )
        policy_version_id = (
            policy_version_rows[0]["id"] if policy_version_rows else None
        )

        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                UPDATE credit_transfer_requests
                SET status = %s,
                    committee_decision = %s,
                    committee_notes = %s,
                    decided_by = %s,
                    decided_at = %s,
                    target_course_id = %s,
                    credits_awarded = %s,
                    policy_version_id = %s,
                    updated_at = %s
                WHERE id = %s AND org_id = %s
                """,
                    (
                        final_status,
                        decision,
                        notes,
                        decided_by,
                        now,
                        target_course_id,
                        credits_awarded,
                        policy_version_id,
                        now,
                        request_id,
                        org_id,
                    ),
                )
            ]
        )

        # If approved, write to the equivalency records table
        if decision in ("APPROVED", "PARTIAL") and target_course_id:
            equiv_id = str(uuid4())
            execute_transaction(
                [
                    (
                        """
                    INSERT INTO credit_equivalency_records (
                        id, org_id, request_id, student_id,
                        source_institution, source_course_code, source_course_name, source_credits,
                        target_course_id, credits_awarded, committee_decision,
                        decided_by, decided_at, policy_version_id,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s
                    )
                    """,
                        (
                            equiv_id,
                            org_id,
                            request_id,
                            req["student_id"],
                            req["source_institution"],
                            req["source_course_code"],
                            req["source_course_name"],
                            req["source_credits"],
                            target_course_id,
                            credits_awarded,
                            decision,
                            decided_by,
                            now,
                            policy_version_id,
                            now,
                            now,
                        ),
                    )
                ]
            )
            logger.info(
                "E17: Credit equivalency record created [equiv_id=%s, request_id=%s, awarded=%s]",
                equiv_id,
                request_id,
                credits_awarded,
            )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=decided_by,
            entity_type="credit_transfer_request",
            entity_id=request_id,
            org_id=org_id,
            module="M1",
            wizard="Credit Transfer",
            success=True,
            metadata={
                "action": "committee_decision",
                "decision": decision,
                "credits_awarded": credits_awarded,
                "target_course_id": target_course_id,
                "policy_version_id": policy_version_id,
            },
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="admissions.credit_transfer_decided",
                org_id=org_id,
                entity_type="credit_transfer_request",
                entity_id=request_id,
                actor_id=decided_by,
                payload={
                    "request_id": request_id,
                    "org_id": org_id,
                    "student_id": req["student_id"],
                    "decision": decision,
                    "credits_awarded": credits_awarded,
                    "target_course_id": target_course_id,
                    "policy_version_id": policy_version_id,
                },
            )
        )

        logger.info(
            "E17: Credit transfer decision recorded [id=%s, decision=%s, credits=%s, by=%s]",
            request_id,
            decision,
            credits_awarded,
            decided_by,
        )
        return cls._get_request(request_id, org_id)

    # -------------------------------------------------------------------------
    # Read helpers
    # -------------------------------------------------------------------------

    @classmethod
    def list_requests(
        cls,
        org_id: str,
        student_id: str | None = None,
        readmission_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        List credit transfer requests for a tenant with optional filters.

        Args:
            org_id:         Tenant ID.
            student_id:     Optional — filter by student UUID.
            readmission_id: Optional — filter by linked readmission application.
            status:         Optional CreditTransferStatus value.

        Returns:
            List of request dicts ordered by created_at descending.
        """
        conditions = ["org_id = %s"]
        params: list = [org_id]

        if student_id:
            conditions.append("student_id = %s")
            params.append(student_id)

        if readmission_id:
            conditions.append("readmission_id = %s")
            params.append(readmission_id)

        if status:
            conditions.append("status = %s")
            params.append(status)

        rows = execute_query(
            f"SELECT * FROM credit_transfer_requests WHERE {' AND '.join(conditions)} "  # noqa: S608
            "ORDER BY created_at DESC",
            tuple(params),
        )
        return [dict(r) for r in rows] if rows else []

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _get_request(cls, request_id: str, org_id: str) -> dict[str, Any]:
        """Fetch a credit transfer request by ID."""
        rows = execute_query(
            "SELECT * FROM credit_transfer_requests WHERE id = %s AND org_id = %s",
            (request_id, org_id),
        )
        if not rows:
            raise NotFoundError(
                message=f"Credit transfer request '{request_id}' not found.",
                details={"request_id": request_id, "org_id": org_id},
            )
        return dict(rows[0])

    @classmethod
    def _require(cls, request_id: str, org_id: str) -> dict[str, Any]:
        """Fetch or raise NotFoundError — alias used internally."""
        return cls._get_request(request_id, org_id)
