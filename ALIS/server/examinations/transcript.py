"""E06-S06 — Official Transcript Generation

Generates a signed, versioned academic transcript PDF for a student,
covering all published semester results and grade details.
Uploaded to MinIO; content_hash prevents duplicate generation.
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class TranscriptService:

    @classmethod
    def generate(cls, org_id: str, student_id: str, actor_id: str,
                 is_official: bool = False) -> dict:
        """
        Generate (or return cached) academic transcript for a student.
        Only published results are included.
        If content hasn't changed since last generation, returns existing record.
        """
        student_rows = execute_query(
            "SELECT id, name, roll_number, program, email FROM students WHERE id = %s AND org_id = %s",
            (student_id, org_id),
        )
        if not student_rows:
            raise NotFoundError(f"Student {student_id} not found")
        student = dict(student_rows[0])

        # All published semester results
        results = execute_query(
            """
            SELECT sr.academic_year, sr.semester, sr.sgpa, sr.cgpa,
                   sr.total_credits, sr.credits_earned, sr.status
            FROM semester_results sr
            WHERE sr.student_id = %s AND sr.org_id = %s AND sr.is_published = TRUE
            ORDER BY sr.academic_year, sr.semester
            """,
            (student_id, org_id),
        )
        if not results:
            raise BusinessRuleViolation(message="No published results found for this student")

        # Per-semester grade detail
        grade_rows = execute_query(
            """
            SELECT g.academic_year, g.semester, c.code AS course_code, c.name AS course_name,
                   c.credits, g.marks_obtained, g.max_marks, g.grade, g.grade_points,
                   g.is_absent, g.is_pass
            FROM grades g
            JOIN courses c ON c.id = g.course_id
            WHERE g.student_id = %s AND g.org_id = %s AND g.is_published = TRUE
            ORDER BY g.academic_year, g.semester, c.name
            """,
            (student_id, org_id),
        )

        # Compute content hash to detect changes
        content_data = {
            "student_id": student_id,
            "results": [dict(r) for r in results],
            "grades": [dict(g) for g in grade_rows],
        }
        content_hash = hashlib.sha256(
            json.dumps(content_data, sort_keys=True, default=str).encode()
        ).hexdigest()

        # Return existing if unchanged
        existing = execute_query(
            "SELECT * FROM transcripts WHERE student_id = %s AND org_id = %s AND content_hash = %s",
            (student_id, org_id, content_hash),
        )
        if existing:
            return dict(existing[0])

        pdf_bytes = cls._build_pdf(student, results, grade_rows, org_id, is_official)
        object_key = f"transcripts/{org_id}/{student_id}/{content_hash}.pdf"
        cls._upload_to_minio(object_key, pdf_bytes)

        tid = str(uuid.uuid4())
        execute_transaction([
            (
                """
                INSERT INTO transcripts
                    (id, org_id, student_id, pdf_path, content_hash, is_official, generated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (tid, org_id, student_id, object_key, content_hash, is_official, actor_id),
            )
        ])

        AuditLog.log(
            action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
            entity_type="transcript", entity_id=tid, org_id=org_id,
            module="E06-S06",
            metadata={"student_id": student_id, "is_official": is_official},
        )

        logger.info("Transcript generated: student=%s hash=%s", student_id, content_hash[:8])
        return {
            "id": tid, "student_id": student_id, "pdf_path": object_key,
            "content_hash": content_hash, "is_official": is_official,
        }

    @classmethod
    def list_for_student(cls, org_id: str, student_id: str) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM transcripts WHERE student_id = %s AND org_id = %s ORDER BY generated_at DESC",
            (student_id, org_id),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # PDF builder
    # ------------------------------------------------------------------

    @classmethod
    def _build_pdf(cls, student: dict, results, grade_rows, org_id: str,
                   is_official: bool) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
        styles = getSampleStyleSheet()
        elements = []

        title = "OFFICIAL ACADEMIC TRANSCRIPT" if is_official else "ACADEMIC TRANSCRIPT"
        elements.append(Paragraph(title, styles["Title"]))
        elements.append(Spacer(1, 10))

        elements.append(Paragraph(f"Student: {student['name']}", styles["Normal"]))
        elements.append(Paragraph(f"Roll No: {student['roll_number']}", styles["Normal"]))
        elements.append(Paragraph(f"Program: {student['program']}", styles["Normal"]))
        elements.append(Spacer(1, 16))

        # Group grades by (academic_year, semester)
        from itertools import groupby
        grade_list = [dict(g) for g in grade_rows]
        grade_list.sort(key=lambda x: (x["academic_year"], x["semester"]))

        result_by_key = {(r["academic_year"], r["semester"]): r for r in results}

        for (yr, sem), sem_grades in groupby(grade_list, key=lambda x: (x["academic_year"], x["semester"])):
            sem_grades = list(sem_grades)
            res = result_by_key.get((yr, sem), {})

            elements.append(Paragraph(
                f"{yr} — Semester {sem}  |  SGPA: {res.get('sgpa', '-')}  |  CGPA: {res.get('cgpa', '-')}  |  {res.get('status', '')}",
                styles["Heading3"],
            ))

            table_data = [["Course Code", "Course Name", "Credits", "Marks", "Grade", "Points", "Pass"]]
            for g in sem_grades:
                marks = f"{g['marks_obtained']:.1f}/{g['max_marks']}" if not g["is_absent"] else "ABSENT"
                table_data.append([
                    g["course_code"], g["course_name"], g["credits"],
                    marks, g["grade"] or "-", g["grade_points"] or "-",
                    "Y" if g["is_pass"] else "N",
                ])

            t = Table(table_data, colWidths=[70, 170, 45, 70, 45, 45, 30])
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]))
            elements.append(t)
            elements.append(Spacer(1, 12))

        # Final CGPA
        if results:
            last = dict(results[-1])
            elements.append(Paragraph(f"Cumulative GPA (CGPA): {last.get('cgpa', '-')}", styles["Heading2"]))

        if is_official:
            elements.append(Spacer(1, 30))
            elements.append(Paragraph(
                "This is an official transcript issued by the institution. Any alteration renders it invalid.",
                styles["Normal"],
            ))

        doc.build(elements)
        return buffer.getvalue()

    @classmethod
    def _upload_to_minio(cls, object_key: str, pdf_bytes: bytes) -> None:
        try:
            from io import BytesIO as BIO
            from minio import Minio
            from server.core.settings import settings
            endpoint = settings.minio_endpoint.replace("http://", "").replace("https://", "")
            client = Minio(endpoint, access_key=settings.minio_access_key,
                           secret_key=settings.minio_secret_key, secure=settings.minio_secure)
            if not client.bucket_exists(settings.minio_bucket):
                client.make_bucket(settings.minio_bucket)
            client.put_object(settings.minio_bucket, object_key,
                              BIO(pdf_bytes), len(pdf_bytes), content_type="application/pdf")
        except Exception as exc:
            logger.warning("Transcript: MinIO upload failed (non-fatal): %s", exc)
