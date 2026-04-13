"""Pre-Generated Grade Cards (Examination Workflow)

Grade cards are pre-generated AFTER marks are locked but BEFORE Registrar
approves result publication.  On publication day, the API serves pre-generated
PDFs from MinIO instead of generating on demand.

This is load-critical: result publication hits 2,000 concurrent users in 30 min.

R9 — Template rendered via document_engine.render(template_id, context, tenant_id).
     Template lives in document_templates table — never hardcoded HTML.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from celery import shared_task
from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# MinIO path pattern: grade-cards/{org_id}/{semester_id}/{student_id}.pdf
_MINIO_PREFIX = "grade-cards"


class GradeCardGeneratorService:
    @classmethod
    async def get_grade_card(
        cls,
        org_id: str,
        semester_id: str,
        student_id: str,
    ) -> str | None:
        """Return the MinIO path to the pre-generated grade card PDF.

        Returns None if not yet generated (caller triggers on-demand fallback).
        """
        rows = execute_query(
            """
            SELECT minio_path FROM grade_card_cache
            WHERE org_id = %s AND semester_id = %s AND student_id = %s AND status = 'READY'
            LIMIT 1
        """,
            (org_id, semester_id, student_id),
        )

        return rows[0]["minio_path"] if rows else None

    @classmethod
    async def get_batch_status(
        cls,
        org_id: str,
        semester_id: str,
    ) -> dict:
        """Return progress of the pre-generation batch job."""
        rows = execute_query(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'READY') AS ready,
                COUNT(*) FILTER (WHERE status = 'FAILED') AS failed,
                COUNT(*) FILTER (WHERE status = 'GENERATING') AS in_progress
            FROM grade_card_cache
            WHERE org_id = %s AND semester_id = %s
        """,
            (org_id, semester_id),
        )

        if not rows:
            return {
                "total": 0,
                "ready": 0,
                "failed": 0,
                "in_progress": 0,
                "pct_complete": 0,
            }

        r = rows[0]
        total = int(r["total"] or 0)
        ready = int(r["ready"] or 0)
        return {
            "total": total,
            "ready": ready,
            "failed": int(r["failed"] or 0),
            "in_progress": int(r["in_progress"] or 0),
            "pct_complete": round(ready / total * 100, 1) if total > 0 else 0,
        }


@shared_task(
    name="server.tasks.examinations.pre_generate_grade_cards",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
    acks_late=True,
    time_limit=3600,
)
def pre_generate_grade_cards(
    self, batch_id: str, semester_id: str, org_id: str, actor_id: str
):
    """Celery task: pre-generate grade card PDFs for an entire semester.

    Runs AFTER marks are locked, BEFORE Registrar approves publication.
    """
    logger.info(
        "Starting grade card pre-generation: semester=%s org=%s", semester_id, org_id
    )

    # Get eligible students (marks locked, not yet published)
    students = execute_query(
        """
        SELECT DISTINCT s.id AS student_id, s.name, s.roll_number, s.program
        FROM exam_results er
        JOIN students s ON s.id = er.student_id
        WHERE er.org_id = %s
          AND er.semester_id = %s
          AND er.marks_locked = TRUE
    """,
        (org_id, semester_id),
    )

    total = len(students)
    logger.info("Generating %d grade cards for semester %s", total, semester_id)

    # Get document template for grade cards
    template_rows = execute_query(
        """
        SELECT id, template_body
        FROM document_templates
        WHERE org_id = %s AND template_type = 'GRADE_CARD' AND is_active = TRUE
        LIMIT 1
    """,
        (org_id,),
    )

    template_id = str(template_rows[0]["id"]) if template_rows else None

    # Seed cache rows as GENERATING
    if students:
        ops = []
        for student in students:
            student_id = str(student["student_id"])
            minio_path = f"{_MINIO_PREFIX}/{org_id}/{semester_id}/{student_id}.pdf"
            cache_id = str(uuid.uuid4())
            ops.append(
                (
                    """
                INSERT INTO grade_card_cache
                    (id, org_id, semester_id, student_id, batch_id,
                     minio_path, status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, 'GENERATING', NOW())
                ON CONFLICT (org_id, semester_id, student_id) DO UPDATE
                   SET status = 'GENERATING', batch_id = EXCLUDED.batch_id
            """,
                    (
                        cache_id,
                        org_id,
                        semester_id,
                        student_id,
                        batch_id,
                        minio_path,
                    ),
                )
            )
        execute_transaction(ops)

    # Generate each PDF
    generated = 0
    failed = 0

    for student in students:
        student_id = str(student["student_id"])
        minio_path = f"{_MINIO_PREFIX}/{org_id}/{semester_id}/{student_id}.pdf"

        try:
            _generate_single_card(
                org_id=org_id,
                semester_id=semester_id,
                student_id=student_id,
                student_data=dict(student),
                minio_path=minio_path,
                template_id=template_id,
            )
            execute_transaction(
                [
                    (
                        """
                UPDATE grade_card_cache
                SET status = 'READY', generated_at = NOW()
                WHERE org_id = %s AND semester_id = %s AND student_id = %s
            """,
                        (org_id, semester_id, student_id),
                    )
                ]
            )
            generated += 1

        except Exception as exc:
            logger.error(
                "Grade card generation failed for student %s: %s", student_id, exc
            )
            execute_transaction(
                [
                    (
                        """
                UPDATE grade_card_cache
                SET status = 'FAILED', error_message = %s
                WHERE org_id = %s AND semester_id = %s AND student_id = %s
            """,
                        (str(exc)[:500], org_id, semester_id, student_id),
                    )
                ]
            )
            failed += 1

    logger.info(
        "Grade card pre-generation complete: %d/%d generated, %d failed",
        generated,
        total,
        failed,
    )

    DomainEventBus.publish(
        DomainEvent(
            event_type="examinations.grade_cards_pre_generated",
            org_id=org_id,
            payload={
                "batch_id": batch_id,
                "semester_id": semester_id,
                "total": total,
                "generated": generated,
                "failed": failed,
            },
        )
    )

    AuditLog.log(
        org_id=org_id,
        actor_id=actor_id,
        action=AuditAction.CREATED,
        resource_type="grade_card_batch",
        resource_id=batch_id,
        detail={
            "semester_id": semester_id,
            "total": total,
            "generated": generated,
            "failed": failed,
        },
    )

    return {"batch_id": batch_id, "generated": generated, "failed": failed}


def _generate_single_card(
    org_id: str,
    semester_id: str,
    student_id: str,
    student_data: dict,
    minio_path: str,
    template_id: str | None,
) -> None:
    """Generate a single grade card PDF and upload to MinIO.

    R9 — Uses document_engine.render() with template from document_templates.
    """
    # Get student's results for the semester
    results = execute_query(
        """
        SELECT c.course_code, c.title, er.marks_obtained, er.max_marks,
               er.grade, er.grade_points, er.credits
        FROM exam_results er
        JOIN courses c ON c.id = er.course_id
        WHERE er.student_id = %s AND er.semester_id = %s AND er.org_id = %s
    """,
        (student_id, semester_id, org_id),
    )

    # Compute SGPA
    total_gp = sum(
        float(r.get("grade_points", 0)) * float(r.get("credits", 0)) for r in results
    )
    total_credits = sum(float(r.get("credits", 0)) for r in results)
    sgpa = round(total_gp / total_credits, 2) if total_credits > 0 else 0.0

    context = {
        "student": student_data,
        "semester_id": semester_id,
        "results": [dict(r) for r in results],
        "sgpa": sgpa,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # R9 — render via document engine
    try:
        from server.core.document_engine import document_engine

        pdf_bytes = document_engine.render(
            template_id=template_id or "grade_card_default",
            context=context,
            tenant_id=org_id,
        )
    except ImportError:
        # Fallback: simple reportlab render if document_engine not yet wired
        pdf_bytes = _fallback_render(context)

    # Upload to MinIO
    from server.fs_service import FileStorageService

    fs = FileStorageService()
    fs.upload_bytes(
        bucket="alis-documents",
        object_name=minio_path,
        data=pdf_bytes,
        content_type="application/pdf",
    )


def _fallback_render(context: dict) -> bytes:
    """Minimal PDF via reportlab as fallback while document_engine is wired."""
    from io import BytesIO

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    student = context.get("student", {})
    elements = [
        Paragraph(f"Grade Card — {student.get('name', '')}", styles["Title"]),
        Paragraph(f"Roll: {student.get('roll_number', '')}", styles["Normal"]),
        Paragraph(f"SGPA: {context.get('sgpa', 0)}", styles["Normal"]),
    ]
    for r in context.get("results", []):
        elements.append(
            Paragraph(
                f"{r.get('course_code')} — {r.get('title')}: {r.get('grade', 'N/A')}",
                styles["Normal"],
            )
        )
    doc.build(elements)
    return buf.getvalue()
