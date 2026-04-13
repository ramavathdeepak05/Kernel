"""
E04-S05 — Counsellor Allocation Wizard

MODULE: M1 — Admissions & Marketing
LAYER: Layer 2 (Embedding agent) + Layer 4 (Capacity lock)
ENTITY: CounsellorAssignment

Assigns the best-fit counsellor to an applicant using vector similarity
between applicant profile embedding and counsellor specialization embeddings.

Algorithm:
    1. Embed applicant profile (name, program, source_channel) via Ollama
    2. Search counsellor embedding index in PGVector
    3. Select top match with lowest current load
    4. Block if counsellor capacity is exceeded (Layer 4)
    5. Allow manual override with justification

Acceptance Criteria (E04-S05):
    - [x] API: POST /counsellors/assign
    - [x] Manual reassignment with reason
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, GlobalLockViolationError
from server.db_service import execute_query, execute_transaction

from .models import (
    AllocationMethod,
    CounsellorAssignmentRead,
    CounsellorAssignRequest,
)

logger = logging.getLogger(__name__)

# Maximum active assignments a counsellor may hold
_MAX_COUNSELLOR_LOAD = 50


class CounsellorAllocationService:
    """
    Allocates counsellors to applicants using vector similarity + load balancing.
    """

    @classmethod
    def assign(
        cls,
        request: CounsellorAssignRequest,
        org_id: str,
        actor_id: str,
        actor_role: Any = None,
    ) -> CounsellorAssignmentRead:
        """
        Assign a counsellor to an applicant.

        If preferred_counsellor_id is set → manual assignment (with justification).
        Otherwise → vector search + load-balanced auto-assignment.

        Args:
            request:    Assignment request
            org_id:     Tenant scope
            actor_id:   Actor performing the assignment
            actor_role: Role of the actor

        Returns:
            CounsellorAssignmentRead

        Raises:
            BusinessRuleViolation: If applicant not found or already assigned.
            GlobalLockViolationError: If counsellor is at capacity.
        """
        # Verify applicant exists
        applicant_rows = execute_query(
            "SELECT * FROM applicants WHERE id = %s AND org_id = %s",
            (request.applicant_id, org_id),
        )
        if not applicant_rows:
            raise BusinessRuleViolation(
                message=f"Applicant '{request.applicant_id}' not found."
            )
        applicant = applicant_rows[0]

        # Check if already assigned
        existing = execute_query(
            "SELECT id, counsellor_id FROM counsellor_assignments "
            "WHERE applicant_id = %s AND org_id = %s LIMIT 1",
            (request.applicant_id, org_id),
        )
        if existing:
            raise BusinessRuleViolation(
                message=(
                    f"Applicant '{request.applicant_id}' already has a counsellor "
                    f"assigned (counsellor_id={existing[0]['counsellor_id']}). "
                    f"Use reassign endpoint for changes."
                ),
                details={"existing_assignment_id": existing[0]["id"]},
            )

        # --- Determine assignment path ---
        if request.preferred_counsellor_id:
            counsellor_id, method, score = cls._manual_assignment(
                preferred_id=request.preferred_counsellor_id,
                org_id=org_id,
                actor_role=actor_role,
                justification=request.justification,
            )
        else:
            counsellor_id, method, score = cls._auto_assign(applicant, org_id)

        # --- Layer 4: Capacity lock ---
        load = cls._get_counsellor_load(counsellor_id, org_id)
        if load >= _MAX_COUNSELLOR_LOAD:
            raise GlobalLockViolationError(
                violations=[
                    f"Counsellor '{counsellor_id}' is at maximum capacity "
                    f"({load}/{_MAX_COUNSELLOR_LOAD} assignments)"
                ]
            )

        # --- Persist assignment ---
        assignment_id = str(uuid4())
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                INSERT INTO counsellor_assignments
                    (id, org_id, applicant_id, counsellor_id, method,
                     similarity_score, assigned_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        assignment_id,
                        org_id,
                        request.applicant_id,
                        counsellor_id,
                        method,
                        score,
                        actor_id,
                        now,
                    ),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            entity_type="counsellor_assignment",
            entity_id=assignment_id,
            org_id=org_id,
            module="M1",
            wizard="Counsellor Allocation",
            success=True,
            metadata={
                "applicant_id": request.applicant_id,
                "counsellor_id": counsellor_id,
                "method": method,
                "similarity_score": score,
                "justification": request.justification,
            },
        )

        logger.info(
            "E04-S05: Counsellor assigned [applicant=%s, counsellor=%s, method=%s]",
            request.applicant_id,
            counsellor_id,
            method,
        )

        return CounsellorAssignmentRead(
            id=assignment_id,
            org_id=org_id,
            applicant_id=request.applicant_id,
            counsellor_id=counsellor_id,
            method=method,
            similarity_score=score,
            assigned_by=actor_id,
            created_at=now,
        )

    # -------------------------------------------------------------------------
    # Private: Auto-assignment via vector search
    # -------------------------------------------------------------------------

    @classmethod
    def _auto_assign(
        cls, applicant: dict, org_id: str
    ) -> tuple[str, str, float | None]:
        """
        Auto-assign counsellor via vector similarity search.

        Falls back to load-balanced assignment if no vector matches found.
        """
        from server.core.ai_gateway import AIGatewayContext
        from server.core.rbac import Role
        from server.core.tool_registry import ToolInvoker
        from server.tools.rag_retriever import RAGRetrieverTool

        profile_text = (
            f"Applicant: {applicant.get('name', '')}. "
            f"Program: {applicant.get('intended_program', '')}. "
            f"Source: {applicant.get('source_channel', '')}."
        )

        # Try vector search for counsellor match
        try:
            AIGatewayContext(
                actor_id="counsellor_allocator",
                actor_role=Role.SYSTEM,
                org_id=org_id,
                module="M1",
            )
            RAGRetrieverTool()
            output = ToolInvoker.invoke(
                tool_name="tool.rag.retriever",
                input_data={
                    "query": profile_text,
                    "index_name": "counsellors",
                    "top_k": 5,
                    "score_threshold": 0.5,
                },
                agent_id="counsellor_allocator",
                allowed_tools=("tool.rag.retriever",),
                tenant_id=org_id,
                module="M1",
                wizard="Counsellor Allocation",
            )
            chunks = output.data.get("chunks", [])
            if chunks:
                # Pick highest-score counsellor with lowest load
                best = cls._pick_lowest_load(
                    [
                        c.get("metadata", {}).get("counsellor_id")
                        for c in chunks
                        if c.get("metadata", {}).get("counsellor_id")
                    ],
                    org_id,
                )
                if best:
                    return (
                        best,
                        AllocationMethod.VECTOR_SEARCH.value,
                        chunks[0].get("score"),
                    )
        except Exception as e:
            logger.warning("E04-S05: Vector search failed, falling back: %s", e)

        # Fallback: load-balanced assignment
        counsellor_id = cls._load_balanced_fallback(org_id)
        if not counsellor_id:
            raise BusinessRuleViolation(
                message="No available counsellors found for this tenant."
            )
        return counsellor_id, AllocationMethod.LOAD_BALANCED.value, None

    @classmethod
    def _manual_assignment(
        cls,
        preferred_id: str,
        org_id: str,
        actor_role: Any,
        justification: str | None,
    ) -> tuple[str, str, None]:
        """Validate and accept a manually chosen counsellor."""
        from server.core.rbac import Role

        try:
            role = Role(actor_role)
        except (ValueError, TypeError):
            role = Role.STUDENT

        if role not in (Role.ADMIN, Role.SUPER_ADMIN, Role.SYSTEM, Role.FACULTY):
            raise BusinessRuleViolation(
                message="Manual counsellor assignment requires ADMIN or FACULTY role."
            )
        if not justification:
            raise BusinessRuleViolation(
                message="Justification is required for manual counsellor assignment."
            )
        # Verify counsellor exists in tenant
        rows = execute_query(
            "SELECT id FROM users WHERE id = %s AND org_id = %s LIMIT 1",
            (preferred_id, org_id),
        )
        if not rows:
            raise BusinessRuleViolation(
                message=f"Counsellor '{preferred_id}' not found in this tenant."
            )
        return preferred_id, AllocationMethod.MANUAL.value, None

    @classmethod
    def _get_counsellor_load(cls, counsellor_id: str, org_id: str) -> int:
        rows = execute_query(
            "SELECT COUNT(*) AS cnt FROM counsellor_assignments "
            "WHERE counsellor_id = %s AND org_id = %s",
            (counsellor_id, org_id),
        )
        return int(rows[0]["cnt"]) if rows else 0

    @classmethod
    def _pick_lowest_load(
        cls, counsellor_ids: list[str | None], org_id: str
    ) -> str | None:
        """From a list of candidate IDs, return the one with fewest assignments."""
        valid = [c for c in counsellor_ids if c]
        if not valid:
            return None
        loads = {c: cls._get_counsellor_load(c, org_id) for c in valid}
        return min(loads, key=loads.__getitem__)

    @classmethod
    def _load_balanced_fallback(cls, org_id: str) -> str | None:
        """Pick the counsellor with the fewest assignments in this tenant."""
        rows = execute_query(
            """
            SELECT u.id
            FROM users u
            LEFT JOIN counsellor_assignments ca
                ON ca.counsellor_id = u.id AND ca.org_id = u.org_id
            WHERE u.org_id = %s
              AND u.status = 'ACTIVE'
            GROUP BY u.id
            ORDER BY COUNT(ca.id) ASC
            LIMIT 1
            """,
            (org_id,),
        )
        return rows[0]["id"] if rows else None
