"""E08-S05 — Performance Reviews"""
from __future__ import annotations

import logging
import uuid
from statistics import mean

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction, safe_identifier

from .models import PerformanceReviewCreate, PerformanceReviewUpdate

logger = logging.getLogger(__name__)


class PerformanceReviewService:

    @classmethod
    def create(cls, org_id: str, req: PerformanceReviewCreate, actor_id: str) -> dict:
        import json
        existing = execute_query(
            "SELECT id FROM performance_reviews WHERE org_id = %s AND staff_id = %s AND review_period = %s",
            (org_id, req.staff_id, req.review_period),
        )
        if existing:
            raise BusinessRuleViolation(
                message=f"Review for period {req.review_period} already exists"
            )

        overall = round(mean(req.ratings.values()), 1) if req.ratings else None

        rid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO performance_reviews
                (id, org_id, staff_id, reviewer_id, review_period, review_type,
                 ratings, overall_rating, strengths, improvements, goals_next)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s)
            """,
            (rid, org_id, req.staff_id, actor_id, req.review_period,
             req.review_type.value, json.dumps(req.ratings),
             overall, req.strengths, req.improvements, req.goals_next),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="performance_review", entity_id=rid, org_id=org_id,
                     module="E08-S05",
                     metadata={"staff_id": req.staff_id, "period": req.review_period})

        return cls.get(org_id, rid)

    @classmethod
    def update(cls, org_id: str, review_id: str,
                req: PerformanceReviewUpdate, actor_id: str) -> dict:
        import json
        review = cls.get(org_id, review_id)
        if review["status"] == "FINALIZED":
            raise BusinessRuleViolation(message="Cannot update a finalized review")

        fields = []
        values: list = []

        if req.ratings is not None:
            fields.append("ratings = %s::jsonb")
            values.append(json.dumps(req.ratings))
            overall = round(mean(req.ratings.values()), 1) if req.ratings else None
            fields.append("overall_rating = %s")
            values.append(overall)

        for field in ("strengths", "improvements", "goals_next", "staff_comments"):
            val = getattr(req, field)
            if val is not None:
                fields.append(f"{safe_identifier(field)} = %s")
                values.append(val)

        if req.status:
            if req.status not in ("SUBMITTED", "ACKNOWLEDGED", "FINALIZED"):
                raise BusinessRuleViolation(message="Invalid status transition")
            fields.append("status = %s")
            values.append(req.status)
            if req.status == "SUBMITTED":
                fields.append("submitted_at = NOW()")
            elif req.status == "ACKNOWLEDGED":
                fields.append("acknowledged_at = NOW()")

        if not fields:
            return review

        values.extend([review_id, org_id])
        execute_transaction([(
            f"UPDATE performance_reviews SET {', '.join(fields)} WHERE id = %s AND org_id = %s",
            values,
        )])

        return cls.get(org_id, review_id)

    @classmethod
    def get(cls, org_id: str, review_id: str) -> dict:
        rows = execute_query(
            """
            SELECT pr.*, u.display_name AS staff_name, sp.employee_code, sp.designation,
                   ru.display_name AS reviewer_name
            FROM performance_reviews pr
            JOIN staff_profiles sp ON sp.id = pr.staff_id
            JOIN users u ON u.id = sp.user_id
            JOIN users ru ON ru.id = pr.reviewer_id
            WHERE pr.id = %s AND pr.org_id = %s
            """,
            (review_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Performance review {review_id} not found")
        return dict(rows[0])

    @classmethod
    def list_for_staff(cls, org_id: str, staff_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM performance_reviews WHERE staff_id = %s AND org_id = %s ORDER BY review_period DESC",
            (staff_id, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def list_pending(cls, org_id: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT pr.*, u.display_name AS staff_name, sp.department
            FROM performance_reviews pr
            JOIN staff_profiles sp ON sp.id = pr.staff_id
            JOIN users u ON u.id = sp.user_id
            WHERE pr.org_id = %s AND pr.status IN ('DRAFT', 'SUBMITTED')
            ORDER BY pr.review_period
            """,
            (org_id,),
        )
        return [dict(r) for r in rows]
