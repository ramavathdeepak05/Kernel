"""
E16 — Guardian / Parent Portal (Go-Live Blocker)

OTP-only authentication for parents/guardians.
Read-only access scoped to one student_id.
Auto-provisioned on student.enrolled with parent_phone.

Visible data:
- Attendance percentage
- Fee dues summary
- Exam schedule
- Results (published only)
- Risk traffic light (Green/Amber/Red — NO clinical details)

Hard-coded restrictions (never exposed):
- Counseling session notes
- Grievance details
- Placement details
- Underlying risk factors

Session:
- OTP-based (30-minute session, no password)
- Multi-student support (one parent may have multiple children)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from server.core.security import GuardianOTPManager
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class GuardianPortalService:
    @classmethod
    def provision_guardian(
        cls,
        org_id: str,
        student_id: str,
        guardian_phone: str,
        guardian_name: str = "",
        relationship: str = "PARENT",
    ) -> dict[str, Any]:
        """Auto-provision guardian account on student enrollment."""
        guardian_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # Check if guardian already exists for this phone
        existing = execute_query(
            "SELECT id FROM guardian_accounts WHERE phone = %s AND org_id = %s",
            (guardian_phone, org_id),
            tenant_id=org_id,
        )
        if existing:
            guardian_id = str(existing[0]["id"])
            # Link student to existing guardian
            execute_transaction(
                [
                    (
                        "INSERT INTO guardian_student_links (id, org_id, guardian_id, student_id, relationship, created_at) "
                        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (org_id, guardian_id, student_id) DO NOTHING",
                        (
                            str(uuid4()),
                            org_id,
                            guardian_id,
                            student_id,
                            relationship,
                            now,
                        ),
                    )
                ],
                tenant_id=org_id,
            )
            return {"guardian_id": guardian_id, "status": "LINKED"}

        execute_transaction(
            [
                (
                    "INSERT INTO guardian_accounts (id, org_id, phone, name, status, created_at) "
                    "VALUES (%s, %s, %s, %s, 'ACTIVE', %s)",
                    (guardian_id, org_id, guardian_phone, guardian_name, now),
                ),
                (
                    "INSERT INTO guardian_student_links (id, org_id, guardian_id, student_id, relationship, created_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (str(uuid4()), org_id, guardian_id, student_id, relationship, now),
                ),
            ],
            tenant_id=org_id,
        )

        return {"guardian_id": guardian_id, "status": "PROVISIONED"}

    @classmethod
    def send_otp(cls, org_id: str, phone: str) -> dict[str, Any]:
        """Send OTP to guardian phone for login."""
        guardian = execute_query(
            "SELECT id FROM guardian_accounts WHERE phone = %s AND org_id = %s AND status = 'ACTIVE'",
            (phone, org_id),
            tenant_id=org_id,
        )
        if not guardian:
            # Don't reveal whether phone exists
            return {"message": "If this phone is registered, an OTP has been sent."}

        guardian_id = str(guardian[0]["id"])

        # Get first linked student for context
        links = execute_query(
            "SELECT student_id FROM guardian_student_links WHERE guardian_id = %s AND org_id = %s LIMIT 1",
            (guardian_id, org_id),
            tenant_id=org_id,
        )
        student_id = str(links[0]["student_id"]) if links else ""

        GuardianOTPManager.generate(phone, student_id, org_id)

        # In production: send via SMS/WhatsApp
        logger.info(
            "Guardian OTP generated for phone=%s (guardian_id=%s)",
            phone[-4:],
            guardian_id,
        )

        return {"message": "OTP sent to registered phone number."}

    @classmethod
    def verify_otp(cls, org_id: str, phone: str, otp: str) -> dict[str, Any] | None:
        """Verify OTP and return guardian session."""
        result = GuardianOTPManager.verify_and_consume(phone, otp)
        if not result:
            return None

        guardian = execute_query(
            "SELECT id, name FROM guardian_accounts WHERE phone = %s AND org_id = %s AND status = 'ACTIVE'",
            (phone, org_id),
            tenant_id=org_id,
        )
        if not guardian:
            return None

        guardian_id = str(guardian[0]["id"])

        # Get all linked students
        students = execute_query(
            "SELECT gs.student_id, u.display_name AS student_name, gs.relationship "
            "FROM guardian_student_links gs "
            "JOIN users u ON u.id = gs.student_id "
            "WHERE gs.guardian_id = %s AND gs.org_id = %s",
            (guardian_id, org_id),
            tenant_id=org_id,
        )

        return {
            "guardian_id": guardian_id,
            "guardian_name": guardian[0].get("name", ""),
            "students": [dict(s) for s in students],
            "tenant_id": org_id,
            "expires_in_minutes": 30,
        }

    @classmethod
    def get_student_dashboard(cls, org_id: str, student_id: str) -> dict[str, Any]:
        """
        Read-only dashboard for guardian.
        Returns ONLY permitted data — no counseling, grievances, placement, or risk factors.
        """
        dashboard: dict[str, Any] = {}

        # 1. Attendance percentage
        att = execute_query(
            """
            SELECT
                COUNT(*) FILTER (WHERE status IN ('PRESENT','EXCUSED_LATE_JOINER','EXCUSED_DISRUPTION')) AS present,
                COUNT(*) AS total
            FROM attendance_records WHERE student_id = %s AND org_id = %s
            """,
            (student_id, org_id),
            tenant_id=org_id,
        )
        if att and att[0]["total"] > 0:
            dashboard["attendance_percentage"] = round(
                att[0]["present"] / att[0]["total"] * 100, 1
            )
        else:
            dashboard["attendance_percentage"] = None

        # 2. Fee dues summary
        dues = execute_query(
            "SELECT total_due, last_payment_date FROM student_dues_status WHERE student_id = %s AND org_id = %s",
            (student_id, org_id),
            tenant_id=org_id,
        )
        if dues:
            dashboard["total_dues"] = float(dues[0].get("total_due", 0))
            dashboard["last_payment"] = (
                str(dues[0].get("last_payment_date", ""))
                if dues[0].get("last_payment_date")
                else None
            )
        else:
            dashboard["total_dues"] = 0
            dashboard["last_payment"] = None

        # 3. Upcoming exam schedule
        exams = execute_query(
            """
            SELECT es.course_code, es.exam_date, es.start_time, es.venue
            FROM exam_schedules es
            JOIN student_exam_registrations ser ON ser.exam_schedule_id = es.id
            WHERE ser.student_id = %s AND es.org_id = %s AND es.exam_date >= CURRENT_DATE
            ORDER BY es.exam_date LIMIT 10
            """,
            (student_id, org_id),
            tenant_id=org_id,
        )
        dashboard["upcoming_exams"] = [dict(e) for e in exams] if exams else []

        # 4. Latest results (published only)
        results = execute_query(
            """
            SELECT g.course_code, g.grade, g.grade_points, g.semester, g.academic_year
            FROM grades g
            WHERE g.student_id = %s AND g.org_id = %s AND g.is_published = TRUE
            ORDER BY g.academic_year DESC, g.semester DESC LIMIT 20
            """,
            (student_id, org_id),
            tenant_id=org_id,
        )
        dashboard["results"] = [dict(r) for r in results] if results else []

        # 5. Risk traffic light (Green/Amber/Red ONLY — no factors, no clinical data)
        risk = execute_query(
            "SELECT risk_score FROM student_risk_profiles WHERE student_id = %s AND org_id = %s",
            (student_id, org_id),
            tenant_id=org_id,
        )
        if risk:
            score = float(risk[0].get("risk_score", 0))
            if score >= 70:
                dashboard["risk_level"] = "RED"
            elif score >= 40:
                dashboard["risk_level"] = "AMBER"
            else:
                dashboard["risk_level"] = "GREEN"
        else:
            dashboard["risk_level"] = "GREEN"

        # Hard-coded: NEVER include these
        # - counseling notes
        # - grievance details
        # - placement details
        # - risk factor breakdown

        return dashboard
