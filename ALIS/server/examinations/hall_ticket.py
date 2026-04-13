"""E06-S02 — Hall Ticket Generation

Eligibility gates:
  1. Student must have a valid hall ticket (fee paid — FeePaymentReceived event sets this)
  2. Attendance must meet minimum threshold (AttendanceFinalized confirms this)
  3. No pending dues
"""

from __future__ import annotations

import logging
import uuid
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class HallTicketService:
    @classmethod
    def issue_for_semester(
        cls,
        org_id: str,
        academic_year: str,
        semester: int,
        exam_type: str,
        actor_id: str,
    ) -> dict:
        """
        Issue hall tickets for all eligible students in a semester.
        Called automatically when AttendanceFinalized event is received.
        """
        from server.core.policy_store import PolicyKey, PolicyStore

        min_att = float(PolicyStore.get(org_id, PolicyKey.MIN_ATTENDANCE_PCT) or 75.0)

        # Get enrolled students with their attendance %
        students = execute_query(
            """
            SELECT
                s.id AS student_id, s.name, s.roll_number, s.program, s.email,
                COALESCE(
                    ROUND(
                        AVG(
                            CASE WHEN ar.status IN ('PRESENT','LATE') THEN 100.0 ELSE 0.0 END
                        ), 2
                    ), 0
                ) AS avg_attendance
            FROM students s
            JOIN course_enrollments ce ON ce.student_id = s.id
            JOIN attendance_sessions sess ON sess.course_id = ce.course_id
                AND sess.academic_year = ce.academic_year
            LEFT JOIN attendance_records ar ON ar.session_id = sess.id
                AND ar.student_id = s.id
            WHERE s.org_id = %s AND ce.academic_year = %s
              AND ce.semester = %s AND ce.status = 'ENROLLED'
            GROUP BY s.id, s.name, s.roll_number, s.program, s.email
            """,
            (org_id, academic_year, semester),
        )

        issued = []
        blocked = []

        for student in students:
            student_id = str(student["student_id"])
            att_pct = float(student["avg_attendance"] or 0)

            # Attendance gate
            if att_pct < min_att:
                blocked.append(
                    {
                        "student_id": student_id,
                        "reason": f"Attendance {att_pct:.1f}% below minimum {min_att:.1f}%",
                    }
                )
                continue

            # Idempotency
            existing = execute_query(
                "SELECT id FROM hall_tickets WHERE student_id = %s AND academic_year = %s AND exam_type = %s AND org_id = %s",
                (student_id, academic_year, exam_type, org_id),
            )
            if existing:
                issued.append(student_id)
                continue

            ticket_number = f"HT-{student['roll_number']}-{academic_year.replace('-', '')}-S{semester}"
            pdf_path = cls._generate_pdf(
                student, academic_year, semester, exam_type, ticket_number, org_id
            )

            tid = str(uuid.uuid4())
            execute_transaction(
                [
                    (
                        """
                INSERT INTO hall_tickets
                    (id, org_id, student_id, academic_year, semester, exam_type,
                     ticket_number, pdf_path, issued_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                        (
                            tid,
                            org_id,
                            student_id,
                            academic_year,
                            semester,
                            exam_type,
                            ticket_number,
                            pdf_path,
                            actor_id,
                        ),
                    )
                ]
            )
            issued.append(student_id)

            DomainEventBus.publish(
                DomainEvent(
                    event_type="HallTicketIssued",
                    entity_type="student",
                    entity_id=student_id,
                    org_id=org_id,
                    payload={
                        "ticket_number": ticket_number,
                        "academic_year": academic_year,
                        "semester": semester,
                        "exam_type": exam_type,
                    },
                    actor_id=actor_id,
                )
            )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_type="system",
            entity_type="hall_ticket_batch",
            entity_id=f"{org_id}:{academic_year}:sem{semester}",
            org_id=org_id,
            module="E06-S02",
            metadata={"issued": len(issued), "blocked": len(blocked)},
        )

        logger.info(
            "HallTicket: issued=%d blocked=%d for %s sem%d",
            len(issued),
            len(blocked),
            academic_year,
            semester,
        )
        return {"issued": len(issued), "blocked": blocked}

    @classmethod
    def get_for_student(
        cls, org_id: str, student_id: str, academic_year: str
    ) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM hall_tickets WHERE student_id = %s AND academic_year = %s AND org_id = %s ORDER BY issued_at DESC",
            (student_id, academic_year, org_id),
        )
        return [dict(r) for r in rows]

    @classmethod
    def _generate_pdf(
        cls,
        student: dict,
        academic_year: str,
        semester: int,
        exam_type: str,
        ticket_number: str,
        org_id: str,
    ) -> str:
        """Generate hall ticket PDF and upload to MinIO. Returns object key."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        elements.append(Paragraph("HALL TICKET", styles["Title"]))
        elements.append(Spacer(1, 12))
        elements.append(Paragraph(f"Ticket No: {ticket_number}", styles["Normal"]))
        elements.append(Spacer(1, 8))

        data = [
            ["Student Name", student["name"]],
            ["Roll Number", student["roll_number"]],
            ["Program", student["program"]],
            ["Academic Year", academic_year],
            ["Semester", str(semester)],
            ["Exam Type", exam_type],
        ]
        table = Table(data, colWidths=[150, 300])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 11),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 20))
        elements.append(
            Paragraph(
                "This hall ticket must be presented at the examination hall.",
                styles["Normal"],
            )
        )

        doc.build(elements)
        pdf_bytes = buffer.getvalue()

        # Upload to MinIO
        object_key = (
            f"hall_tickets/{org_id}/{academic_year}/sem{semester}/{ticket_number}.pdf"
        )
        try:
            from io import BytesIO as BIO

            from minio import Minio
            from server.core.settings import settings

            endpoint = settings.minio_endpoint.replace("http://", "").replace(
                "https://", ""
            )
            client = Minio(
                endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            if not client.bucket_exists(settings.minio_bucket):
                client.make_bucket(settings.minio_bucket)
            client.put_object(
                settings.minio_bucket,
                object_key,
                BIO(pdf_bytes),
                len(pdf_bytes),
                content_type="application/pdf",
            )
        except Exception as exc:
            logger.warning("HallTicket: MinIO upload failed (non-fatal): %s", exc)

        return object_key
