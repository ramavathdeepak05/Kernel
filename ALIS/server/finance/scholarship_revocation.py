"""EC-FIN-03 — Retroactive Scholarship Revocation

Rules (strictly enforced):
R2 — Approval chain: triggers workflow_engine.trigger('scholarship_revocation', ...)
     Dual-auth DAG stored in workflow_definitions — never hardcoded approvers.
R6 — NEVER mutate closed ledger entries.
     INSERT SCHOLARSHIP_REVERSAL instead of UPDATE.
R12 — Store policy_version_id on every revocation record.
R1 — Dispute window from policy_engine ('finance.scholarship_dispute_window_days').
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.core.policy_engine import policy_engine
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class ScholarshipRevocationRequest(BaseModel):
    scholarship_assignment_id: str
    reason: str
    effective_from: str   # ISO date — when revocation takes effect


class ScholarshipRevocationService:

    @classmethod
    async def initiate_revocation(
        cls,
        org_id: str,
        request: ScholarshipRevocationRequest,
        actor_id: str,
    ) -> dict:
        """Initiate scholarship revocation — dispatches dual-auth workflow.

        Does NOT modify any ledger entry. Returns the workflow task ID.
        """
        # Verify assignment exists
        rows = execute_query("""
            SELECT sa.id, sa.scholarship_id, sa.student_id, sa.academic_year,
                   sa.discount_amount, sa.status
            FROM scholarship_assignments sa
            WHERE sa.id = %s AND sa.org_id = %s
        """, (request.scholarship_assignment_id, org_id))

        if not rows:
            raise NotFoundError(
                f"Scholarship assignment {request.scholarship_assignment_id} not found"
            )

        assignment = rows[0]
        if assignment["status"] == "REVOKED":
            raise BusinessRuleViolation("Scholarship is already revoked")

        # R12 — get policy version at decision time
        policy_version = policy_engine.get_version(
            "finance.scholarship_dispute_window_days", org_id
        )
        dispute_days = int(policy_engine.get_value(
            "finance.scholarship_dispute_window_days", org_id, 30
        ))
        # R3 — absolute deadline
        dispute_deadline = datetime.now(timezone.utc) + timedelta(days=dispute_days)

        revocation_id = str(uuid.uuid4())
        workflow_task_id = str(uuid.uuid4())

        # R6 — INSERT reversal record, never UPDATE existing ledger
        import json
        execute_transaction([
            ("""
            INSERT INTO scholarship_revocations
                (id, org_id, assignment_id, reason, effective_from,
                 dispute_deadline, policy_version_id, status, initiated_by, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDING_APPROVAL', %s, NOW())
            """, (
                revocation_id, org_id,
                request.scholarship_assignment_id,
                request.reason,
                request.effective_from,
                dispute_deadline,
                policy_version,
                actor_id,
            )),
            # R2 — dispatch workflow (dual-auth DAG in workflow_definitions)
            ("""
            INSERT INTO workflow_tasks
                (id, org_id, workflow_type, resource_id, status, created_by,
                 payload, sla_deadline, created_at)
            VALUES (%s, %s, 'scholarship_revocation', %s, 'PENDING_APPROVAL',
                    %s, %s, %s, NOW())
            """, (
                workflow_task_id, org_id, revocation_id, actor_id,
                json.dumps({
                    "revocation_id": revocation_id,
                    "assignment_id": request.scholarship_assignment_id,
                    "student_id": str(assignment["student_id"]),
                    "discount_amount": str(assignment.get("discount_amount", 0)),
                    "reason": request.reason,
                    "effective_from": request.effective_from,
                    "policy_version_id": policy_version,
                }),
                dispute_deadline,
            )),
        ])

        AuditLog.log(
            org_id=org_id,
            actor_id=actor_id,
            action=AuditAction.CREATED,
            resource_type="scholarship_revocation",
            resource_id=revocation_id,
            detail={
                "assignment_id": request.scholarship_assignment_id,
                "reason": request.reason,
                "policy_version_id": policy_version,
            },
        )

        DomainEventBus.publish(DomainEvent(
            event_type="finance.scholarship_revocation_initiated",
            org_id=org_id,
            payload={
                "revocation_id": revocation_id,
                "workflow_task_id": workflow_task_id,
                "student_id": str(assignment["student_id"]),
                "effective_from": request.effective_from,
                "dispute_deadline": dispute_deadline.isoformat(),
            },
        ))

        return {
            "revocation_id": revocation_id,
            "workflow_task_id": workflow_task_id,
            "status": "PENDING_APPROVAL",
            "dispute_deadline": dispute_deadline.isoformat(),
            "message": "Dual-auth workflow dispatched. Revocation pending approval.",
        }

    @classmethod
    async def execute_revocation(
        cls,
        org_id: str,
        revocation_id: str,
        approver_id: str,
    ) -> dict:
        """Called by workflow engine after dual-auth approval.

        Inserts SCHOLARSHIP_REVERSAL ledger entries — never modifies existing rows (R6).
        """
        rows = execute_query("""
            SELECT r.*, sa.student_id, sa.discount_amount, sa.academic_year
            FROM scholarship_revocations r
            JOIN scholarship_assignments sa ON sa.id = r.assignment_id
            WHERE r.id = %s AND r.org_id = %s
        """, (revocation_id, org_id))

        if not rows:
            raise NotFoundError(f"Revocation {revocation_id} not found")

        rev = rows[0]
        if rev["status"] != "PENDING_APPROVAL":
            raise BusinessRuleViolation(f"Revocation already in status: {rev['status']}")

        reversal_id = str(uuid.uuid4())
        discount_amount = float(rev.get("discount_amount") or 0)

        execute_transaction([
            # R6 — INSERT reversal, never UPDATE original
            ("""
            INSERT INTO scholarship_ledger_entries
                (id, org_id, assignment_id, entry_type, amount,
                 effective_date, policy_version_id, created_by, created_at)
            VALUES (%s, %s, %s, 'SCHOLARSHIP_REVERSAL', %s, %s, %s, %s, NOW())
            """, (
                reversal_id, org_id, str(rev["assignment_id"]),
                discount_amount,
                rev["effective_from"],
                rev["policy_version_id"],
                approver_id,
            )),
            # Mark assignment as REVOKED
            ("""
            UPDATE scholarship_assignments
            SET status = 'REVOKED', revoked_at = NOW(), revoked_by = %s
            WHERE id = %s AND org_id = %s
            """, (approver_id, str(rev["assignment_id"]), org_id)),
            # Mark revocation as EXECUTED
            ("""
            UPDATE scholarship_revocations
            SET status = 'EXECUTED', executed_at = NOW(), executed_by = %s
            WHERE id = %s AND org_id = %s
            """, (approver_id, revocation_id, org_id)),
        ])

        AuditLog.log(
            org_id=org_id,
            actor_id=approver_id,
            action=AuditAction.UPDATED,
            resource_type="scholarship_revocation",
            resource_id=revocation_id,
            detail={
                "executed": True,
                "reversal_id": reversal_id,
                "amount_reversed": discount_amount,
            },
        )

        DomainEventBus.publish(DomainEvent(
            event_type="finance.scholarship_revoked",
            org_id=org_id,
            payload={
                "revocation_id": revocation_id,
                "student_id": str(rev["student_id"]),
                "amount_reversed": discount_amount,
                "academic_year": str(rev.get("academic_year", "")),
                "template_key": "SCHOLARSHIP_REVOCATION_NOTICE",
            },
        ))

        return {
            "revocation_id": revocation_id,
            "reversal_id": reversal_id,
            "status": "EXECUTED",
            "amount_reversed": discount_amount,
        }
