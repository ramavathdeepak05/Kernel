"""E11-S06 — Export Engine (CSV / XLSX / PDF)

Exports any report data to CSV, Excel, or PDF.
Large exports are processed asynchronously via Celery.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import ExportRequest

logger = logging.getLogger(__name__)


class ExportEngine:
    @classmethod
    def request_export(cls, org_id: str, req: ExportRequest, actor_id: str) -> dict:
        """
        Creates an export job and enqueues it for async processing.
        Returns the job record; client polls GET /exports/{id} for status.
        """
        job_id = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
            INSERT INTO export_jobs
                (id, org_id, report_type, format, filters, status, requested_by)
            VALUES (%s, %s, %s, %s, %s::jsonb, 'QUEUED', %s)
            """,
                    (
                        job_id,
                        org_id,
                        req.report_type,
                        req.format.value,
                        json.dumps(req.filters),
                        actor_id,
                    ),
                )
            ]
        )

        try:
            from server.worker import celery_app

            celery_app.send_task("reporting.run_export", args=[org_id, job_id])
        except Exception as exc:
            logger.warning("ExportEngine: task enqueue failed (non-fatal): %s", exc)

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="export_job",
            entity_id=job_id,
            org_id=org_id,
            module="E11-S06",
            metadata={"report_type": req.report_type, "format": req.format.value},
        )
        return cls.get(org_id, job_id)

    @classmethod
    def get(cls, org_id: str, job_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM export_jobs WHERE id = %s AND org_id = %s",
            (job_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Export job {job_id} not found")
        return dict(rows[0])

    @classmethod
    def list(cls, org_id: str, limit: int = 20) -> list[dict]:
        rows = execute_query(
            "SELECT * FROM export_jobs WHERE org_id = %s ORDER BY created_at DESC LIMIT %s",
            (org_id, limit),
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Called by Celery task
    # ------------------------------------------------------------------

    @classmethod
    def process_job(cls, org_id: str, job_id: str) -> None:
        job_rows = execute_query(
            "SELECT * FROM export_jobs WHERE id = %s AND org_id = %s",
            (job_id, org_id),
        )
        if not job_rows:
            return
        job = dict(job_rows[0])

        execute_transaction(
            [
                (
                    "UPDATE export_jobs SET status = 'RUNNING' WHERE id = %s",
                    (job_id,),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="job",
            entity_id=job_id,
            tenant_id=org_id,
            metadata={"source": "process_job"},
        )

        try:
            data = cls._fetch_data(org_id, job["report_type"], job["filters"] or {})
            fmt = job["format"]
            path = cls._write_file(org_id, job_id, fmt, data)

            execute_transaction(
                [
                    (
                        "UPDATE export_jobs SET status = 'DONE', file_path = %s, completed_at = NOW() WHERE id = %s",
                        (path, job_id),
                    )
                ]
            )
            logger.info("Export job %s complete: %d rows → %s", job_id, len(data), path)
        except Exception as exc:
            execute_transaction(
                [
                    (
                        "UPDATE export_jobs SET status = 'FAILED', error_message = %s WHERE id = %s",
                        (str(exc), job_id),
                    )
                ]
            )
            logger.error("Export job %s failed: %s", job_id, exc, exc_info=True)

    # ------------------------------------------------------------------
    # Data fetching — delegates to module reports
    # ------------------------------------------------------------------

    @classmethod
    def _fetch_data(cls, org_id: str, report_type: str, filters: dict) -> list[dict]:
        academic_year = filters.get("academic_year", "")
        semester = filters.get("semester")

        if report_type == "admissions":
            from .admissions_report import AdmissionsReportService

            funnel = AdmissionsReportService.funnel(org_id, academic_year)
            return funnel.get("by_status", []) if isinstance(funnel, dict) else []

        if report_type == "admissions_program":
            from .admissions_report import AdmissionsReportService

            return AdmissionsReportService.program_wise(org_id, academic_year)

        if report_type == "attendance":
            from .academics_report import AcademicsReportService

            return AcademicsReportService.attendance_summary(
                org_id, academic_year, semester
            )

        if report_type == "low_attendance":
            from .academics_report import AcademicsReportService

            threshold = float(filters.get("threshold", 75))
            return AcademicsReportService.low_attendance_students(
                org_id, academic_year, int(semester or 1), threshold
            )

        if report_type == "grades":
            from server.db_service import execute_query as eq

            student_id = filters.get("student_id", "")
            rows = (
                eq(
                    """
                SELECT gr.student_id, gr.course_id, c.name AS course_name, c.code,
                       gr.marks_obtained, gr.grade_letter, gr.grade_points,
                       gr.is_pass, gr.academic_year, gr.semester
                FROM grade_records gr
                JOIN courses c ON c.id = gr.course_id
                WHERE gr.org_id = %s AND gr.student_id = %s AND gr.academic_year = %s
                """,
                    (org_id, student_id, academic_year)
                    if student_id
                    else (org_id, academic_year),
                )
                if student_id
                else eq(
                    "SELECT * FROM grade_records WHERE org_id = %s AND academic_year = %s ORDER BY student_id",
                    (org_id, academic_year),
                )
            )
            return [dict(r) for r in rows]

        if report_type == "fee_collection":
            from server.db_service import execute_query as eq

            rows = eq(
                """
                SELECT academic_year,
                       COUNT(*) AS total_invoices,
                       SUM(amount_due) AS total_billed,
                       SUM(CASE WHEN status='PAID' THEN amount_due ELSE 0 END) AS collected,
                       SUM(CASE WHEN status='OVERDUE' THEN 1 ELSE 0 END) AS overdue_count
                FROM student_invoices
                WHERE org_id = %s AND academic_year = %s
                GROUP BY academic_year
                """,
                (org_id, academic_year),
            )
            return [dict(r) for r in rows]

        if report_type == "defaulters":
            from server.db_service import execute_query as eq

            rows = eq(
                """
                SELECT si.student_id, u.name, si.invoice_number,
                       si.amount_due, si.due_date, si.status
                FROM student_invoices si
                JOIN students u ON u.id = si.student_id
                WHERE si.org_id = %s AND si.academic_year = %s
                  AND si.status IN ('OVERDUE', 'UNPAID')
                ORDER BY si.due_date
                """,
                (org_id, academic_year),
            )
            return [dict(r) for r in rows]

        if report_type == "staff":
            from server.db_service import execute_query

            rows = execute_query(
                "SELECT name, employee_id, department, designation, employment_type, status FROM staff_profiles WHERE org_id = %s AND status != 'TERMINATED'",
                (org_id,),
            )
            return [dict(r) for r in rows]

        # Generic saved report
        if report_type.startswith("saved:"):
            report_id = report_type.split(":", 1)[1]
            from .custom_reports import CustomReportService

            return CustomReportService.run(org_id, report_id)

        return []

    # ------------------------------------------------------------------
    # File writers
    # ------------------------------------------------------------------

    @classmethod
    def _write_file(cls, org_id: str, job_id: str, fmt: str, data: list[dict]) -> str:
        object_key = f"exports/{org_id}/{job_id}.{fmt.lower()}"

        if fmt == "CSV":
            content = cls._to_csv(data)
            content_type = "text/csv"
        elif fmt == "XLSX":
            content = cls._to_xlsx(data)
            content_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        elif fmt == "PDF":
            content = cls._to_pdf(data)
            content_type = "application/pdf"
        else:
            content = cls._to_csv(data)
            content_type = "text/csv"

        # Upload to MinIO
        try:
            from io import BytesIO

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
                BytesIO(content if isinstance(content, bytes) else content.encode()),
                len(content if isinstance(content, bytes) else content.encode()),
                content_type=content_type,
            )
        except Exception as exc:
            logger.warning("ExportEngine: MinIO upload failed (non-fatal): %s", exc)

        return object_key

    @classmethod
    def _to_csv(cls, data: list[dict]) -> str:
        if not data:
            return ""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(data[0].keys()))
        writer.writeheader()
        for row in data:
            writer.writerow(
                {k: str(v) if v is not None else "" for k, v in row.items()}
            )
        return buf.getvalue()

    @classmethod
    def _to_xlsx(cls, data: list[dict]) -> bytes:
        try:
            import openpyxl

            wb = openpyxl.Workbook()
            ws = wb.active
            if not data:
                buf = io.BytesIO()
                wb.save(buf)
                return buf.getvalue()
            headers = list(data[0].keys())
            ws.append(headers)
            for row in data:
                ws.append([str(row.get(h, "")) for h in headers])
            buf = io.BytesIO()
            wb.save(buf)
            return buf.getvalue()
        except ImportError:
            # Fall back to CSV bytes if openpyxl not installed
            return cls._to_csv(data).encode()

    @classmethod
    def _to_pdf(cls, data: list[dict]) -> bytes:
        try:
            from io import BytesIO

            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import (
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )

            buf = BytesIO()
            doc = SimpleDocTemplate(
                buf,
                pagesize=landscape(A4),
                leftMargin=30,
                rightMargin=30,
                topMargin=30,
                bottomMargin=30,
            )
            styles = getSampleStyleSheet()
            elements = [Paragraph("ALIS Export Report", styles["Title"]), Spacer(1, 12)]

            if data:
                headers = list(data[0].keys())
                table_data = [headers] + [
                    [str(row.get(h, ""))[:40] for h in headers] for row in data[:500]
                ]
                t = Table(table_data)
                t.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 7),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                            (
                                "ROWBACKGROUNDS",
                                (0, 1),
                                (-1, -1),
                                [colors.white, colors.HexColor("#f4f4f4")],
                            ),
                            ("PADDING", (0, 0), (-1, -1), 3),
                        ]
                    )
                )
                elements.append(t)

            doc.build(elements)
            return buf.getvalue()
        except ImportError:
            return cls._to_csv(data).encode()
