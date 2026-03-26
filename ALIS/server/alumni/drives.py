"""E12-S04 — Recruitment Drives"""
from __future__ import annotations

import json
import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import DriveCreate

logger = logging.getLogger(__name__)


class RecruitmentDriveService:

    @classmethod
    def create(cls, org_id: str, req: DriveCreate, actor_id: str) -> dict:
        did = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO recruitment_drives
                (id, org_id, company_name, drive_date, venue, roles_offered,
                 eligibility, description, created_by)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            """,
            (
                did, org_id, req.company_name, req.drive_date, req.venue,
                json.dumps(req.roles_offered), json.dumps(req.eligibility),
                req.description, actor_id,
            ),
        )])

        AuditLog.log(
            action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
            entity_type="recruitment_drive", entity_id=did, org_id=org_id,
            module="E12-S04",
            metadata={"company": req.company_name, "date": req.drive_date},
        )
        return cls.get(org_id, did)

    @classmethod
    def get(cls, org_id: str, drive_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM recruitment_drives WHERE id = %s AND org_id = %s",
            (drive_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Recruitment drive {drive_id} not found")
        return dict(rows[0])

    @classmethod
    def list(cls, org_id: str, status: str | None = None) -> list[dict]:
        sql = "SELECT * FROM recruitment_drives WHERE org_id = %s"
        params: list = [org_id]
        if status:
            sql += " AND status = %s"; params.append(status)
        sql += " ORDER BY drive_date DESC"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def update_status(cls, org_id: str, drive_id: str, status: str, actor_id: str) -> dict:
        if status not in ("SCHEDULED", "ONGOING", "COMPLETED", "CANCELLED"):
            raise BusinessRuleViolation(message=f"Invalid drive status: {status}")
        cls.get(org_id, drive_id)
        execute_transaction([(
            "UPDATE recruitment_drives SET status = %s WHERE id = %s AND org_id = %s",
            (status, drive_id, org_id),
        )])
        return cls.get(org_id, drive_id)

    @classmethod
    def register_student(cls, org_id: str, drive_id: str, student_id: str) -> dict:
        drive = cls.get(org_id, drive_id)
        if drive["status"] not in ("SCHEDULED", "ONGOING"):
            raise BusinessRuleViolation(message="Registrations are closed for this drive")

        # Check eligibility
        eligibility = drive.get("eligibility") or {}
        if eligibility:
            student_rows = execute_query(
                "SELECT program FROM students WHERE id = %s AND org_id = %s",
                (student_id, org_id),
            )
            if student_rows:
                student_program = student_rows[0]["program"]
                allowed_programs = eligibility.get("programs", [])
                if allowed_programs and student_program not in allowed_programs:
                    raise BusinessRuleViolation(
                        message=f"Your program ({student_program}) is not eligible for this drive"
                    )

        existing = execute_query(
            "SELECT id FROM drive_registrations WHERE drive_id = %s AND student_id = %s",
            (drive_id, student_id),
        )
        if existing:
            raise BusinessRuleViolation(message="Already registered for this drive")

        reg_id = str(uuid.uuid4())
        execute_transaction([
            (
                """
                INSERT INTO drive_registrations (id, org_id, drive_id, student_id)
                VALUES (%s, %s, %s, %s)
                """,
                (reg_id, org_id, drive_id, student_id),
            ),
            (
                "UPDATE recruitment_drives SET registered_count = registered_count + 1 WHERE id = %s",
                (drive_id,),
            ),
        ])
        return {"id": reg_id, "drive_id": drive_id, "student_id": student_id, "status": "REGISTERED"}

    @classmethod
    def update_registration_status(
        cls, org_id: str, registration_id: str, status: str, actor_id: str
    ) -> dict:
        if status not in ("REGISTERED", "APPEARED", "SELECTED", "REJECTED"):
            raise BusinessRuleViolation(message=f"Invalid registration status: {status}")

        execute_transaction([(
            "UPDATE drive_registrations SET status = %s WHERE id = %s AND org_id = %s",
            (status, registration_id, org_id),
        )])

        # Update drive selected count
        if status == "SELECTED":
            rows = execute_query(
                "SELECT drive_id FROM drive_registrations WHERE id = %s", (registration_id,)
            )
            if rows:
                execute_transaction([(
                    "UPDATE recruitment_drives SET selected_count = selected_count + 1 WHERE id = %s",
                    (str(rows[0]["drive_id"]),),
                )])

        rows = execute_query(
            "SELECT * FROM drive_registrations WHERE id = %s AND org_id = %s",
            (registration_id, org_id),
        )
        return dict(rows[0]) if rows else {}

    @classmethod
    def list_registrations(cls, org_id: str, drive_id: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT dr.*, s.name AS student_name, s.roll_number, s.program
            FROM drive_registrations dr
            JOIN students s ON s.id = dr.student_id
            WHERE dr.drive_id = %s AND dr.org_id = %s
            ORDER BY dr.registered_at
            """,
            (drive_id, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def student_drives(cls, org_id: str, student_id: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT dr.*, rd.company_name, rd.drive_date, rd.venue, rd.status AS drive_status
            FROM drive_registrations dr
            JOIN recruitment_drives rd ON rd.id = dr.drive_id
            WHERE dr.student_id = %s AND dr.org_id = %s
            ORDER BY rd.drive_date DESC
            """,
            (student_id, org_id),
        )
        return [dict(r) for r in rows]
