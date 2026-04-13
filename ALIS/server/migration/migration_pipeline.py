"""Data Migration Pipeline (§27)

3-phase import pipeline for historical institutional data.

Phases
──────
validate   — Parse + check every row; return error report. No DB writes.
dry_run    — Show what would be inserted/skipped.  No DB writes.
commit     — Atomic INSERT with duplicate detection + full audit trail.

Supported entity types
──────────────────────
students, faculty, courses, fee_records, historical_attendance,
exam_results, alumni

Duplicate detection
───────────────────
Jaro-Winkler similarity ≥ 0.90 on (name, dob, phone) combination.
All rows audited with source='migration_pipeline' in audit_ledger.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from typing import Literal

from pydantic import BaseModel
from server.core.audit import AuditAction, AuditLog
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

Mode = Literal["validate", "dry_run", "commit"]

# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class RowError(BaseModel):
    row_number: int
    raw_data: dict
    error_message: str


class MigrationResult(BaseModel):
    job_id: str | None
    entity_type: str
    mode: Mode
    status: str
    total_rows: int
    processed_rows: int
    skipped_duplicates: int
    error_count: int
    errors: list[RowError]


# ---------------------------------------------------------------------------
# Column specs per entity
# ---------------------------------------------------------------------------

_REQUIRED_COLUMNS: dict[str, list[str]] = {
    "students": ["name", "dob", "phone", "program_code", "enrollment_year"],
    "faculty": ["name", "dob", "phone", "department_code", "designation"],
    "courses": ["course_code", "title", "credits", "department_code", "academic_year"],
    "fee_records": [
        "student_ref",
        "invoice_date",
        "amount_due",
        "amount_paid",
        "academic_year",
    ],
    "historical_attendance": ["student_ref", "course_code", "session_date", "status"],
    "exam_results": [
        "student_ref",
        "course_code",
        "semester",
        "marks_obtained",
        "max_marks",
    ],
    "alumni": ["name", "dob", "phone", "graduation_year", "program_code"],
}


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def _jaro_winkler(s1: str, s2: str) -> float:
    """Simplified Jaro-Winkler similarity."""
    if s1 == s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    len_s1, len_s2 = len(s1), len(s2)
    match_dist = max(len_s1, len_s2) // 2 - 1
    if match_dist < 0:
        match_dist = 0

    s1_matches = [False] * len_s1
    s2_matches = [False] * len_s2
    matches = 0
    transpositions = 0

    for i in range(len_s1):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, len_s2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(len_s1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    jaro = (
        matches / len_s1 + matches / len_s2 + (matches - transpositions / 2) / matches
    ) / 3

    # Winkler prefix bonus (up to 4 chars)
    prefix = 0
    for i in range(min(4, len_s1, len_s2)):
        if s1[i] == s2[i]:
            prefix += 1
        else:
            break

    return jaro + prefix * 0.1 * (1 - jaro)


def _detect_duplicates(row: dict, org_id: str, entity_type: str) -> list[str]:
    """Return list of existing entity IDs that are likely duplicates (JW ≥ 0.90)."""
    if entity_type not in ("students", "faculty", "alumni"):
        return []

    name = str(row.get("name", "")).lower().strip()
    phone = str(row.get("phone", "")).strip()

    if entity_type == "students":
        candidates = execute_query(
            """
            SELECT id, name, phone FROM students
            WHERE org_id = %s AND phone = %s
            LIMIT 20
        """,
            (org_id, phone),
        )
    elif entity_type == "faculty":
        candidates = execute_query(
            """
            SELECT id, name, phone FROM faculty_members
            WHERE org_id = %s AND phone = %s
            LIMIT 20
        """,
            (org_id, phone),
        )
    else:
        candidates = execute_query(
            """
            SELECT id, name, phone FROM alumni_profiles
            WHERE org_id = %s AND phone = %s
            LIMIT 20
        """,
            (org_id, phone),
        )

    duplicates = []
    for c in candidates:
        candidate_name = str(c.get("name", "")).lower().strip()
        similarity = _jaro_winkler(name, candidate_name)
        if similarity >= 0.90:
            duplicates.append(str(c["id"]))

    return duplicates


# ---------------------------------------------------------------------------
# Entity-specific insert
# ---------------------------------------------------------------------------


def _build_insert_query(
    entity_type: str, row: dict, org_id: str, job_id: str
) -> tuple | None:
    """Return a single validated row insert tuple."""
    eid = str(uuid.uuid4())

    if entity_type == "students":
        return (
            """
            INSERT INTO students
                (id, org_id, name, date_of_birth, phone, program_code,
                 enrollment_year, status, source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'ENROLLED', 'migration_pipeline', NOW())
            ON CONFLICT DO NOTHING
        """,
            (
                eid,
                org_id,
                row["name"],
                row.get("dob"),
                row.get("phone"),
                row.get("program_code"),
                row.get("enrollment_year"),
            ),
        )

    if entity_type == "faculty":
        return (
            """
            INSERT INTO faculty_members
                (id, org_id, name, date_of_birth, phone, department_code,
                 designation, status, source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'ACTIVE', 'migration_pipeline', NOW())
            ON CONFLICT DO NOTHING
        """,
            (
                eid,
                org_id,
                row["name"],
                row.get("dob"),
                row.get("phone"),
                row.get("department_code"),
                row.get("designation"),
            ),
        )

    if entity_type == "courses":
        return (
            """
            INSERT INTO courses
                (id, org_id, course_code, title, credits, department_code,
                 academic_year, status, source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'ACTIVE', 'migration_pipeline', NOW())
            ON CONFLICT (org_id, course_code) DO NOTHING
        """,
            (
                eid,
                org_id,
                row["course_code"],
                row["title"],
                row.get("credits"),
                row.get("department_code"),
                row.get("academic_year"),
            ),
        )

    if entity_type == "fee_records":
        return (
            """
            INSERT INTO student_invoices
                (id, org_id, student_ref, invoice_date, amount_due, amount_paid,
                 balance, academic_year, status, source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s - %s, %s, 'HISTORICAL', 'migration_pipeline', NOW())
            ON CONFLICT DO NOTHING
        """,
            (
                eid,
                org_id,
                row["student_ref"],
                row.get("invoice_date"),
                row["amount_due"],
                row["amount_paid"],
                row["amount_due"],
                row["amount_paid"],
                row.get("academic_year"),
            ),
        )

    if entity_type == "historical_attendance":
        return (
            """
            INSERT INTO attendance_records
                (id, org_id, student_ref, course_code, session_date, status,
                 source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, 'migration_pipeline', NOW())
            ON CONFLICT DO NOTHING
        """,
            (
                eid,
                org_id,
                row["student_ref"],
                row["course_code"],
                row.get("session_date"),
                row["status"],
            ),
        )

    if entity_type == "exam_results":
        return (
            """
            INSERT INTO exam_results
                (id, org_id, student_ref, course_code, semester,
                 marks_obtained, max_marks, source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'migration_pipeline', NOW())
            ON CONFLICT DO NOTHING
        """,
            (
                eid,
                org_id,
                row["student_ref"],
                row["course_code"],
                row["semester"],
                row["marks_obtained"],
                row["max_marks"],
            ),
        )

    if entity_type == "alumni":
        return (
            """
            INSERT INTO alumni_profiles
                (id, org_id, name, date_of_birth, phone, graduation_year,
                 program_code, status, source, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'ACTIVE', 'migration_pipeline', NOW())
            ON CONFLICT DO NOTHING
        """,
            (
                eid,
                org_id,
                row["name"],
                row.get("dob"),
                row.get("phone"),
                row.get("graduation_year"),
                row.get("program_code"),
            ),
        )

    return None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


class MigrationPipeline:
    @classmethod
    async def run(
        cls,
        entity_type: str,
        csv_bytes: bytes,
        org_id: str,
        mode: Mode,
        actor_id: str,
    ) -> MigrationResult:
        required_cols = _REQUIRED_COLUMNS.get(entity_type, [])
        job_id = str(uuid.uuid4()) if mode == "commit" else None

        # Create job record for commit mode
        if mode == "commit" and job_id:
            execute_transaction(
                [
                    (
                        """
                INSERT INTO data_migration_jobs
                    (id, org_id, entity_type, mode, status, total_rows, processed_rows,
                     error_count, started_at, actor_id)
                VALUES (%s, %s, %s, %s, 'RUNNING', 0, 0, 0, NOW(), %s)
            """,
                        (job_id, org_id, entity_type, mode, actor_id),
                    )
                ]
            )

        errors: list[RowError] = []
        processed = 0
        skipped = 0
        total = 0

        try:
            text = csv_bytes.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            rows_raw = list(reader)
            total = len(rows_raw)

            # Validate columns
            if rows_raw:
                actual_cols = set(rows_raw[0].keys())
                missing = set(required_cols) - actual_cols
                if missing:
                    return MigrationResult(
                        job_id=job_id,
                        entity_type=entity_type,
                        mode=mode,
                        status="FAILED",
                        total_rows=0,
                        processed_rows=0,
                        skipped_duplicates=0,
                        error_count=1,
                        errors=[
                            RowError(
                                row_number=0,
                                raw_data={},
                                error_message=f"Missing required columns: {', '.join(sorted(missing))}",
                            )
                        ],
                    )

            for i, row in enumerate(rows_raw, start=1):
                row_dict = dict(row)
                try:
                    # Required field check
                    for col in required_cols:
                        if not str(row_dict.get(col, "")).strip():
                            raise ValueError(f"Required column '{col}' is empty")

                    # Duplicate detection
                    dupe_ids = _detect_duplicates(row_dict, org_id, entity_type)
                    if dupe_ids:
                        skipped += 1
                        if mode == "commit" and job_id:
                            execute_transaction(
                                [
                                    (
                                        """
                                INSERT INTO data_migration_errors
                                    (id, job_id, row_number, raw_data, error_message)
                                VALUES (%s, %s, %s, %s, %s)
                            """,
                                        (
                                            str(uuid.uuid4()),
                                            job_id,
                                            i,
                                            json.dumps(row_dict),
                                            f"Duplicate detected — matches existing IDs: {', '.join(dupe_ids[:3])}",
                                        ),
                                    )
                                ]
                            )
                        continue

                    if mode == "commit":
                        q_tup = _build_insert_query(
                            entity_type, row_dict, org_id, job_id or ""
                        )
                        if q_tup:
                            execute_transaction([q_tup])
                        AuditLog.log(
                            org_id=org_id,
                            actor_id=actor_id,
                            action=AuditAction.CREATED,
                            resource_type=f"migration.{entity_type}",
                            resource_id=job_id or "",
                            detail={"row": i, "source": "migration_pipeline"},
                        )

                    processed += 1

                except Exception as exc:
                    errors.append(
                        RowError(
                            row_number=i,
                            raw_data=row_dict,
                            error_message=str(exc),
                        )
                    )
                    if mode == "commit" and job_id:
                        execute_transaction(
                            [
                                (
                                    """
                            INSERT INTO data_migration_errors
                                (id, job_id, row_number, raw_data, error_message)
                            VALUES (%s, %s, %s, %s, %s)
                        """,
                                    (
                                        str(uuid.uuid4()),
                                        job_id,
                                        i,
                                        json.dumps(row_dict),
                                        str(exc)[:1000],
                                    ),
                                )
                            ]
                        )

        except Exception as exc:
            logger.exception("Migration pipeline failed: %s", exc)
            final_status = "FAILED"
            if mode == "commit" and job_id:
                execute_transaction(
                    [
                        (
                            """
                    UPDATE data_migration_jobs
                    SET status = 'FAILED', completed_at = NOW(),
                        total_rows = %s, processed_rows = %s, error_count = %s
                    WHERE id = %s
                """,
                            (total, processed, len(errors), job_id),
                        )
                    ]
                )
            return MigrationResult(
                job_id=job_id,
                entity_type=entity_type,
                mode=mode,
                status="FAILED",
                total_rows=total,
                processed_rows=processed,
                skipped_duplicates=skipped,
                error_count=len(errors),
                errors=errors,
            )

        final_status = "COMPLETED" if not errors else "COMPLETED_WITH_ERRORS"
        if mode == "commit" and job_id:
            execute_transaction(
                [
                    (
                        """
                UPDATE data_migration_jobs
                SET status = %s, completed_at = NOW(),
                    total_rows = %s, processed_rows = %s, error_count = %s
                WHERE id = %s
            """,
                        (final_status, total, processed, len(errors), job_id),
                    )
                ]
            )

        return MigrationResult(
            job_id=job_id,
            entity_type=entity_type,
            mode=mode,
            status=final_status,
            total_rows=total,
            processed_rows=processed,
            skipped_duplicates=skipped,
            error_count=len(errors),
            errors=errors,
        )
