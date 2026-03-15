"""E09-S04 — Student Counselling

Handles academic, personal, career, and crisis counselling sessions.
Notes are treated as sensitive — stored in DB but flagged is_confidential.
Referrals to external professionals tracked separately.
"""

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import CounsellingReferralCreate, CounsellingSessionCreate

logger = logging.getLogger(__name__)


class CounsellingService:

    # ── Sessions ─────────────────────────────────────────────

    @classmethod
    def create_session(cls, org_id: str, req: CounsellingSessionCreate,
                        actor_id: str) -> dict:
        sid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO counselling_sessions
                (id, org_id, student_id, counsellor_id, session_date,
                 session_type, duration_mins, notes, follow_up_date, is_confidential)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (sid, org_id, req.student_id, actor_id, req.session_date,
             req.session_type.value, req.duration_mins, req.notes,
             req.follow_up_date, req.is_confidential),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="counselling_session", entity_id=sid, org_id=org_id,
                     module="E09-S04",
                     metadata={"student_id": req.student_id,
                               "type": req.session_type.value,
                               "confidential": req.is_confidential})

        return cls.get_session(org_id, sid, include_notes=True)

    @classmethod
    def update_session(cls, org_id: str, session_id: str,
                        updates: dict, actor_id: str) -> dict:
        allowed = {"notes", "follow_up_date", "duration_mins"}
        fields = []
        values: list = []
        for k, v in updates.items():
            if k in allowed and v is not None:
                fields.append(f"{k} = %s")
                values.append(v)
        if not fields:
            return cls.get_session(org_id, session_id, include_notes=True)
        values.extend([session_id, org_id])
        execute_transaction([(
            f"UPDATE counselling_sessions SET {', '.join(fields)} WHERE id = %s AND org_id = %s",
            values,
        )])
        return cls.get_session(org_id, session_id, include_notes=True)

    @classmethod
    def get_session(cls, org_id: str, session_id: str,
                     include_notes: bool = False) -> dict:
        note_col = "cs.notes," if include_notes else ""
        rows = execute_query(
            f"""
            SELECT cs.id, cs.org_id, cs.student_id, cs.counsellor_id,
                   cs.session_date, cs.session_type, cs.duration_mins,
                   {note_col}
                   cs.follow_up_date, cs.is_confidential, cs.created_at,
                   s.name AS student_name, s.roll_number,
                   u.display_name AS counsellor_name
            FROM counselling_sessions cs
            JOIN students s ON s.id = cs.student_id
            JOIN users u ON u.id = cs.counsellor_id
            WHERE cs.id = %s AND cs.org_id = %s
            """,
            (session_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Session {session_id} not found")
        return dict(rows[0])

    @classmethod
    def list_for_student(cls, org_id: str, student_id: str,
                          include_notes: bool = False) -> list[dict]:
        note_col = "cs.notes," if include_notes else ""
        rows = execute_query(
            f"""
            SELECT cs.id, cs.session_date, cs.session_type, cs.duration_mins,
                   {note_col} cs.follow_up_date, cs.is_confidential,
                   u.display_name AS counsellor_name
            FROM counselling_sessions cs
            JOIN users u ON u.id = cs.counsellor_id
            WHERE cs.student_id = %s AND cs.org_id = %s
            ORDER BY cs.session_date DESC
            """,
            (student_id, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def list_for_counsellor(cls, org_id: str, counsellor_id: str,
                              date_from: str | None = None,
                              date_to: str | None = None) -> list[dict]:
        sql = """
            SELECT cs.id, cs.session_date, cs.session_type, cs.duration_mins,
                   cs.follow_up_date, cs.is_confidential,
                   s.name AS student_name, s.roll_number
            FROM counselling_sessions cs
            JOIN students s ON s.id = cs.student_id
            WHERE cs.counsellor_id = %s AND cs.org_id = %s
        """
        params: list = [counsellor_id, org_id]
        if date_from:
            sql += " AND cs.session_date >= %s"
            params.append(date_from)
        if date_to:
            sql += " AND cs.session_date <= %s"
            params.append(date_to)
        sql += " ORDER BY cs.session_date DESC"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def upcoming_follow_ups(cls, org_id: str, counsellor_id: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT cs.*, s.name AS student_name, s.email
            FROM counselling_sessions cs
            JOIN students s ON s.id = cs.student_id
            WHERE cs.counsellor_id = %s AND cs.org_id = %s
              AND cs.follow_up_date >= CURRENT_DATE
            ORDER BY cs.follow_up_date
            LIMIT 20
            """,
            (counsellor_id, org_id),
        )
        return [dict(r) for r in rows]

    # ── Referrals ────────────────────────────────────────────

    @classmethod
    def create_referral(cls, org_id: str, req: CounsellingReferralCreate,
                         actor_id: str) -> dict:
        rid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO counselling_referrals
                (id, org_id, student_id, referred_by, referred_to,
                 reason, urgency, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (rid, org_id, req.student_id, actor_id, req.referred_to,
             req.reason, req.urgency.value, req.notes),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="counselling_referral", entity_id=rid, org_id=org_id,
                     module="E09-S04",
                     metadata={"student_id": req.student_id,
                               "urgency": req.urgency.value})

        rows = execute_query("SELECT * FROM counselling_referrals WHERE id = %s", (rid,))
        return dict(rows[0]) if rows else {}

    @classmethod
    def update_referral_status(cls, org_id: str, referral_id: str,
                                status: str, actor_id: str) -> dict:
        execute_transaction([(
            "UPDATE counselling_referrals SET status = %s WHERE id = %s AND org_id = %s",
            (status, referral_id, org_id),
        )])
        rows = execute_query("SELECT * FROM counselling_referrals WHERE id = %s", (referral_id,))
        return dict(rows[0]) if rows else {}

    @classmethod
    def list_referrals(cls, org_id: str, status: str | None = None) -> list[dict]:
        sql = """
            SELECT cr.*, s.name AS student_name, u.display_name AS referred_by_name
            FROM counselling_referrals cr
            JOIN students s ON s.id = cr.student_id
            JOIN users u ON u.id = cr.referred_by
            WHERE cr.org_id = %s
        """
        params: list = [org_id]
        if status:
            sql += " AND cr.status = %s"
            params.append(status)
        sql += " ORDER BY cr.referral_date DESC"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def summary(cls, org_id: str) -> dict:
        rows = execute_query(
            """
            SELECT
                COUNT(*) AS total_sessions,
                COUNT(DISTINCT student_id) AS unique_students,
                COUNT(*) FILTER (WHERE session_type = 'CRISIS') AS crisis_sessions,
                COUNT(*) FILTER (WHERE follow_up_date >= CURRENT_DATE) AS pending_followups
            FROM counselling_sessions
            WHERE org_id = %s
            """,
            (org_id,),
        )
        stats = dict(rows[0]) if rows else {}
        ref_rows = execute_query(
            "SELECT COUNT(*) AS pending FROM counselling_referrals WHERE org_id = %s AND status = 'PENDING'",
            (org_id,),
        )
        stats["pending_referrals"] = int(ref_rows[0]["pending"] or 0) if ref_rows else 0
        return stats
