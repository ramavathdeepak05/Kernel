"""E12-S01 — Alumni Profile Management"""

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import AlumniProfileCreate, AlumniProfileUpdate

logger = logging.getLogger(__name__)


class AlumniProfileService:

    @classmethod
    def create(cls, org_id: str, req: AlumniProfileCreate, actor_id: str) -> dict:
        existing = execute_query(
            "SELECT id FROM alumni_profiles WHERE org_id = %s AND email = %s",
            (org_id, req.email),
        )
        if existing:
            raise BusinessRuleViolation(message=f"Alumni profile with email {req.email} already exists")

        aid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO alumni_profiles
                (id, org_id, name, email, phone, program, graduation_year,
                 roll_number, cgpa, current_employer, current_designation,
                 current_location, linkedin_url, bio, is_mentor)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                aid, org_id, req.name, req.email, req.phone, req.program,
                req.graduation_year, req.roll_number, req.cgpa,
                req.current_employer, req.current_designation, req.current_location,
                req.linkedin_url, req.bio, req.is_mentor,
            ),
        )])

        AuditLog.log(
            action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
            entity_type="alumni_profile", entity_id=aid, org_id=org_id,
            module="E12-S01",
            metadata={"name": req.name, "program": req.program, "year": req.graduation_year},
        )
        return cls.get(org_id, aid)

    @classmethod
    def create_from_student(cls, org_id: str, student_id: str, actor_id: str = "system") -> dict:
        """
        Auto-creates an alumni profile when StudentGraduated event fires.
        Pulls data from the students table.
        """
        rows = execute_query(
            "SELECT * FROM students WHERE id = %s AND org_id = %s",
            (student_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Student {student_id} not found")
        student = dict(rows[0])

        # Get CGPA from latest semester result
        cgpa_rows = execute_query(
            "SELECT cgpa FROM semester_results WHERE student_id = %s AND org_id = %s AND is_published = TRUE ORDER BY academic_year DESC, semester DESC LIMIT 1",
            (student_id, org_id),
        )
        cgpa = float(cgpa_rows[0]["cgpa"]) if cgpa_rows else None

        # Derive graduation year from latest academic year
        from datetime import date
        grad_year = date.today().year

        existing = execute_query(
            "SELECT id FROM alumni_profiles WHERE org_id = %s AND email = %s",
            (org_id, student.get("email", "")),
        )
        if existing:
            return cls.get(org_id, str(existing[0]["id"]))

        aid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO alumni_profiles
                (id, org_id, student_id, name, email, phone, program, graduation_year,
                 roll_number, cgpa, is_verified)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE)
            """,
            (
                aid, org_id, student_id,
                student.get("name", ""), student.get("email", ""),
                student.get("phone"), student.get("program", ""),
                grad_year, student.get("roll_number"), cgpa,
            ),
        )])

        logger.info("Alumni profile auto-created for student %s", student_id)
        return cls.get(org_id, aid)

    @classmethod
    def get(cls, org_id: str, alumni_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM alumni_profiles WHERE id = %s AND org_id = %s",
            (alumni_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Alumni profile {alumni_id} not found")
        return dict(rows[0])

    @classmethod
    def list(
        cls,
        org_id: str,
        program: str | None = None,
        graduation_year: int | None = None,
        is_mentor: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        sql = "SELECT * FROM alumni_profiles WHERE org_id = %s AND status = 'ACTIVE'"
        params: list = [org_id]
        if program:
            sql += " AND program = %s"; params.append(program)
        if graduation_year:
            sql += " AND graduation_year = %s"; params.append(graduation_year)
        if is_mentor is not None:
            sql += " AND is_mentor = %s"; params.append(is_mentor)
        sql += " ORDER BY graduation_year DESC, name LIMIT %s OFFSET %s"
        params += [limit, offset]
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def update(cls, org_id: str, alumni_id: str, req: AlumniProfileUpdate, actor_id: str) -> dict:
        cls.get(org_id, alumni_id)
        fields, params = [], []
        if req.current_employer is not None:
            fields.append("current_employer = %s"); params.append(req.current_employer)
        if req.current_designation is not None:
            fields.append("current_designation = %s"); params.append(req.current_designation)
        if req.current_location is not None:
            fields.append("current_location = %s"); params.append(req.current_location)
        if req.linkedin_url is not None:
            fields.append("linkedin_url = %s"); params.append(req.linkedin_url)
        if req.bio is not None:
            fields.append("bio = %s"); params.append(req.bio)
        if req.is_mentor is not None:
            fields.append("is_mentor = %s"); params.append(req.is_mentor)
        if req.phone is not None:
            fields.append("phone = %s"); params.append(req.phone)
        if not fields:
            return cls.get(org_id, alumni_id)
        fields.append("updated_at = NOW()")
        params += [alumni_id, org_id]
        execute_transaction([(
            f"UPDATE alumni_profiles SET {', '.join(fields)} WHERE id = %s AND org_id = %s",
            params,
        )])
        return cls.get(org_id, alumni_id)

    @classmethod
    def verify(cls, org_id: str, alumni_id: str, actor_id: str) -> dict:
        cls.get(org_id, alumni_id)
        execute_transaction([(
            "UPDATE alumni_profiles SET is_verified = TRUE, updated_at = NOW() WHERE id = %s AND org_id = %s",
            (alumni_id, org_id),
        )])
        return cls.get(org_id, alumni_id)

    @classmethod
    def statistics(cls, org_id: str) -> dict:
        rows = execute_query(
            """
            SELECT
                COUNT(*)                                    AS total_alumni,
                COUNT(*) FILTER (WHERE is_verified = TRUE) AS verified,
                COUNT(*) FILTER (WHERE is_mentor = TRUE)   AS mentors,
                COUNT(*) FILTER (WHERE current_employer IS NOT NULL) AS employed,
                COUNT(DISTINCT program)                     AS programs,
                MIN(graduation_year)                        AS earliest_batch,
                MAX(graduation_year)                        AS latest_batch
            FROM alumni_profiles
            WHERE org_id = %s AND status = 'ACTIVE'
            """,
            (org_id,),
        )
        return dict(rows[0]) if rows else {}
