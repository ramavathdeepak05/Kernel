"""E12-S05 — Alumni Network (connections + mentorship)"""

from __future__ import annotations

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import MentorshipRequestCreate

logger = logging.getLogger(__name__)


class AlumniNetworkService:
    # ------------------------------------------------------------------
    # Connections
    # ------------------------------------------------------------------

    @classmethod
    def send_connection_request(
        cls, org_id: str, requester_id: str, target_id: str
    ) -> dict:
        if requester_id == target_id:
            raise BusinessRuleViolation(message="Cannot connect with yourself")

        existing = execute_query(
            "SELECT id, status FROM alumni_connections WHERE requester_id = %s AND target_id = %s",
            (requester_id, target_id),
        )
        if existing:
            raise BusinessRuleViolation(
                message=f"Connection request already exists with status: {existing[0]['status']}"
            )

        cid = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
            INSERT INTO alumni_connections (id, org_id, requester_id, target_id)
            VALUES (%s, %s, %s, %s)
            """,
                    (cid, org_id, requester_id, target_id),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id="system",
            actor_role="system",
            entity_type="connection_request",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "send_connection_request"},
        )
        return {"id": cid, "status": "PENDING"}

    @classmethod
    def respond_connection(
        cls, org_id: str, connection_id: str, accept: bool, actor_id: str
    ) -> dict:
        rows = execute_query(
            "SELECT * FROM alumni_connections WHERE id = %s AND org_id = %s",
            (connection_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Connection request {connection_id} not found")
        conn = dict(rows[0])

        if str(conn["target_id"]) != actor_id:
            raise BusinessRuleViolation(
                message="Only the request recipient can respond"
            )

        if conn["status"] != "PENDING":
            raise BusinessRuleViolation(message=f"Request is already {conn['status']}")

        new_status = "ACCEPTED" if accept else "REJECTED"
        execute_transaction(
            [
                (
                    "UPDATE alumni_connections SET status = %s WHERE id = %s",
                    (new_status, connection_id),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="connection",
            entity_id=connection_id,
            tenant_id=org_id,
            metadata={"source": "respond_connection"},
        )
        return {"id": connection_id, "status": new_status}

    @classmethod
    def my_connections(cls, org_id: str, alumni_id: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT ac.*,
                   r.name AS requester_name, r.current_employer AS requester_employer,
                   t.name AS target_name,    t.current_employer AS target_employer
            FROM alumni_connections ac
            JOIN alumni_profiles r ON r.id = ac.requester_id
            JOIN alumni_profiles t ON t.id = ac.target_id
            WHERE ac.org_id = %s
              AND (ac.requester_id = %s OR ac.target_id = %s)
              AND ac.status = 'ACCEPTED'
            ORDER BY ac.created_at DESC
            """,
            (org_id, alumni_id, alumni_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def pending_requests(cls, org_id: str, alumni_id: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT ac.*, r.name AS requester_name, r.program, r.graduation_year
            FROM alumni_connections ac
            JOIN alumni_profiles r ON r.id = ac.requester_id
            WHERE ac.org_id = %s AND ac.target_id = %s AND ac.status = 'PENDING'
            ORDER BY ac.created_at DESC
            """,
            (org_id, alumni_id),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Mentorship
    # ------------------------------------------------------------------

    @classmethod
    def request_mentorship(
        cls, org_id: str, req: MentorshipRequestCreate, mentee_id: str
    ) -> dict:
        # Verify mentor exists and is available
        mentor_rows = execute_query(
            "SELECT id, name, is_mentor FROM alumni_profiles WHERE id = %s AND org_id = %s",
            (req.mentor_id, org_id),
        )
        if not mentor_rows:
            raise NotFoundError(f"Alumni {req.mentor_id} not found")
        if not mentor_rows[0]["is_mentor"]:
            raise BusinessRuleViolation(
                message="This alumni is not available for mentorship"
            )

        mid = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
            INSERT INTO mentorship_requests
                (id, org_id, mentor_id, mentee_id, topic, message)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
                    (mid, org_id, req.mentor_id, mentee_id, req.topic, req.message),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="mentorship",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "request_mentorship"},
        )
        return {"id": mid, "mentor_id": req.mentor_id, "status": "PENDING"}

    @classmethod
    def respond_mentorship(
        cls,
        org_id: str,
        request_id: str,
        accept: bool,
        session_date: str | None,
        actor_alumni_id: str,
    ) -> dict:
        rows = execute_query(
            "SELECT * FROM mentorship_requests WHERE id = %s AND org_id = %s",
            (request_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Mentorship request {request_id} not found")
        req = dict(rows[0])

        if str(req["mentor_id"]) != actor_alumni_id:
            raise BusinessRuleViolation(
                message="Only the mentor can respond to mentorship requests"
            )

        if req["status"] != "PENDING":
            raise BusinessRuleViolation(message=f"Request is already {req['status']}")

        new_status = "ACCEPTED" if accept else "DECLINED"
        execute_transaction(
            [
                (
                    "UPDATE mentorship_requests SET status = %s, session_date = %s WHERE id = %s",
                    (new_status, session_date, request_id),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="mentorship",
            entity_id=request_id,
            tenant_id=org_id,
            metadata={"source": "respond_mentorship"},
        )
        return {"id": request_id, "status": new_status, "session_date": session_date}

    @classmethod
    def my_mentorship_requests(cls, org_id: str, alumni_id: str) -> list[dict]:
        """Requests where this alumni is the mentor."""
        rows = execute_query(
            """
            SELECT mr.*, ap.name AS mentee_name
            FROM mentorship_requests mr
            LEFT JOIN students s ON s.id::text = mr.mentee_id
            LEFT JOIN alumni_profiles ap ON ap.id::text = mr.mentee_id
            WHERE mr.org_id = %s AND mr.mentor_id = %s
            ORDER BY mr.created_at DESC
            """,
            (org_id, alumni_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def list_mentors(cls, org_id: str, program: str | None = None) -> list[dict]:
        sql = """
            SELECT id, name, program, graduation_year, current_employer,
                   current_designation, current_location, bio
            FROM alumni_profiles
            WHERE org_id = %s AND is_mentor = TRUE AND status = 'ACTIVE' AND is_verified = TRUE
        """
        params: list = [org_id]
        if program:
            sql += " AND program = %s"
            params.append(program)
        sql += " ORDER BY graduation_year DESC, name"
        return [dict(r) for r in execute_query(sql, params)]
