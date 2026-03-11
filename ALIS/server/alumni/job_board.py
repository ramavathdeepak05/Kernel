"""E12-S03 — Job Board"""

import json
import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import JobApplicationCreate, JobPostingCreate

logger = logging.getLogger(__name__)


class JobBoardService:

    # ------------------------------------------------------------------
    # Postings
    # ------------------------------------------------------------------

    @classmethod
    def create_posting(cls, org_id: str, req: JobPostingCreate, actor_id: str) -> dict:
        jid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO job_postings
                (id, org_id, title, company_name, description, location,
                 job_type, experience_min, experience_max, salary_range,
                 skills_required, apply_url, apply_email,
                 posted_by, source, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
            """,
            (
                jid, org_id, req.title, req.company_name, req.description,
                req.location, req.job_type.value, req.experience_min, req.experience_max,
                req.salary_range, json.dumps(req.skills_required),
                req.apply_url, req.apply_email, actor_id, req.source, req.expires_at,
            ),
        )])

        AuditLog.log(
            action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
            entity_type="job_posting", entity_id=jid, org_id=org_id,
            module="E12-S03",
            metadata={"title": req.title, "company": req.company_name},
        )
        return cls.get_posting(org_id, jid)

    @classmethod
    def get_posting(cls, org_id: str, job_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM job_postings WHERE id = %s AND org_id = %s",
            (job_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Job posting {job_id} not found")
        return dict(rows[0])

    @classmethod
    def list_postings(
        cls,
        org_id: str,
        job_type: str | None = None,
        active_only: bool = True,
        search: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        sql = "SELECT * FROM job_postings WHERE org_id = %s"
        params: list = [org_id]
        if active_only:
            sql += " AND status = 'ACTIVE' AND (expires_at IS NULL OR expires_at > NOW())"
        if job_type:
            sql += " AND job_type = %s"; params.append(job_type)
        if search:
            sql += " AND (title ILIKE %s OR company_name ILIKE %s OR description ILIKE %s)"
            params += [f"%{search}%", f"%{search}%", f"%{search}%"]
        sql += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def close_posting(cls, org_id: str, job_id: str, actor_id: str) -> dict:
        cls.get_posting(org_id, job_id)
        execute_transaction([(
            "UPDATE job_postings SET status = 'CLOSED' WHERE id = %s AND org_id = %s",
            (job_id, org_id),
        )])
        return cls.get_posting(org_id, job_id)

    # ------------------------------------------------------------------
    # Applications
    # ------------------------------------------------------------------

    @classmethod
    def apply(cls, org_id: str, req: JobApplicationCreate, actor_id: str) -> dict:
        job = cls.get_posting(org_id, req.job_id)
        if job["status"] != "ACTIVE":
            raise BusinessRuleViolation(message="This job posting is no longer accepting applications")

        existing = execute_query(
            "SELECT id FROM job_applications WHERE job_id = %s AND applicant_id = %s",
            (req.job_id, actor_id),
        )
        if existing:
            raise BusinessRuleViolation(message="You have already applied for this position")

        app_id = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO job_applications
                (id, org_id, job_id, applicant_id, applicant_type, resume_path, cover_note)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (app_id, org_id, req.job_id, actor_id, req.applicant_type,
             req.resume_path, req.cover_note),
        )])
        return {"id": app_id, "job_id": req.job_id, "status": "APPLIED"}

    @classmethod
    def list_applications(cls, org_id: str, job_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM job_applications WHERE job_id = %s AND org_id = %s ORDER BY applied_at",
            (job_id, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def update_application_status(
        cls, org_id: str, application_id: str, status: str, actor_id: str
    ) -> dict:
        if status not in ("APPLIED", "SHORTLISTED", "REJECTED", "HIRED"):
            raise BusinessRuleViolation(message=f"Invalid application status: {status}")
        execute_transaction([(
            "UPDATE job_applications SET status = %s WHERE id = %s AND org_id = %s",
            (status, application_id, org_id),
        )])
        rows = execute_query(
            "SELECT * FROM job_applications WHERE id = %s AND org_id = %s",
            (application_id, org_id),
        )
        return dict(rows[0]) if rows else {}

    @classmethod
    def my_applications(cls, org_id: str, applicant_id: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT ja.*, jp.title, jp.company_name, jp.job_type
            FROM job_applications ja
            JOIN job_postings jp ON jp.id = ja.job_id
            WHERE ja.applicant_id = %s AND ja.org_id = %s
            ORDER BY ja.applied_at DESC
            """,
            (applicant_id, org_id),
        )
        return [dict(r) for r in rows]
