"""E-A — Student Deduplication Service

Jaro-Winkler composite scoring (name 50%, DOB 30%, phone 20%) >= 0.90 threshold.
Dual-auth merge requires Registrar + Super Admin (R2).
Archives duplicate with merged_into FK.
Different from admissions/deduplication.py (which handles leads).
"""

from __future__ import annotations

import logging
import re
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

# Statuses that must not participate in a merge
_RESTRICTED_STATUSES = {"GRADUATED", "EXPELLED"}


# ---------------------------------------------------------------------------
# Jaro-Winkler implementation (no external deps)
# ---------------------------------------------------------------------------


def _jaro(s1: str, s2: str) -> float:
    """Compute the Jaro similarity between two strings."""
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_distance = max(len1, len2) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0
    transpositions = 0

    for i in range(len1):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, len2)
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
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1

    return (
        matches / len1 + matches / len2 + (matches - transpositions / 2) / matches
    ) / 3.0


def _jaro_winkler(s1: str, s2: str, prefix_weight: float = 0.1) -> float:
    """
    Compute Jaro-Winkler similarity between two strings.

    The prefix bonus (Winkler extension) rewards strings that share a
    common prefix up to 4 characters. prefix_weight defaults to 0.1
    per the standard algorithm.
    """
    jaro_sim = _jaro(s1, s2)

    # Common prefix length (up to 4 characters)
    prefix_len = 0
    for ch1, ch2 in zip(s1[:4], s2[:4]):
        if ch1 == ch2:
            prefix_len += 1
        else:
            break

    return jaro_sim + prefix_len * prefix_weight * (1.0 - jaro_sim)


def _normalize_name(name: str) -> str:
    """Lowercase, strip extra whitespace, remove punctuation."""
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    return re.sub(r"\s+", " ", name)


def _normalize_phone(phone: str) -> str:
    """Keep only digits."""
    return re.sub(r"\D", "", phone or "")


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class StudentDeduplicationService:
    @classmethod
    def find_duplicates(
        cls,
        org_id: str,
        threshold: float = 0.90,
    ) -> list:
        """
        Find likely duplicate student records using Jaro-Winkler composite scoring.

        Composite score:
            name  50%  — Jaro-Winkler on normalised full_name
            DOB   30%  — exact match = 1.0, mismatch = 0.0
            phone 20%  — Jaro-Winkler on digits-only phone

        Returns pairs with composite >= threshold.
        """
        try:
            students = execute_query(
                """
                SELECT id, full_name, date_of_birth, phone
                FROM students
                WHERE org_id = %s
                  AND status != 'ARCHIVED'
                  AND merged_into IS NULL
                """,
                (org_id,),
            )
        except Exception:
            # merged_into column may not exist yet — fall back without the filter
            students = execute_query(
                """
                SELECT id, full_name, date_of_birth, phone
                FROM students
                WHERE org_id = %s
                  AND status != 'ARCHIVED'
                """,
                (org_id,),
            )

        pairs = []
        n = len(students)
        for i in range(n):
            for j in range(i + 1, n):
                a = students[i]
                b = students[j]

                name_a = _normalize_name(a["full_name"] or "")
                name_b = _normalize_name(b["full_name"] or "")
                name_score = _jaro_winkler(name_a, name_b)

                dob_a = str(a["date_of_birth"] or "")
                dob_b = str(b["date_of_birth"] or "")
                dob_score = 1.0 if dob_a and dob_a == dob_b else 0.0

                phone_a = _normalize_phone(a["phone"] or "")
                phone_b = _normalize_phone(b["phone"] or "")
                phone_score = (
                    _jaro_winkler(phone_a, phone_b) if phone_a and phone_b else 0.0
                )

                composite = 0.50 * name_score + 0.30 * dob_score + 0.20 * phone_score

                if composite >= threshold:
                    pairs.append(
                        {
                            "student_a_id": a["id"],
                            "student_b_id": b["id"],
                            "composite_score": round(composite, 4),
                            "name_score": round(name_score, 4),
                            "dob_score": round(dob_score, 4),
                            "phone_score": round(phone_score, 4),
                        }
                    )

        # Sort by highest confidence first
        pairs.sort(key=lambda x: x["composite_score"], reverse=True)
        return pairs

    @classmethod
    def initiate_merge(
        cls,
        primary_id: str,
        duplicate_id: str,
        org_id: str,
        initiator_id: str,
    ) -> dict:
        """
        Raise a dual-auth merge request (Registrar + Super Admin required — R2).
        Validates both students exist and are not in restricted statuses.
        Creates a workflow_tasks record with status PENDING.
        """
        # Fetch both students
        primary_rows = execute_query(
            "SELECT id, full_name, status FROM students WHERE id = %s AND org_id = %s",
            (primary_id, org_id),
        )
        if not primary_rows:
            raise NotFoundError(
                f"Primary student {primary_id} not found", code="STUDENT_NOT_FOUND"
            )

        duplicate_rows = execute_query(
            "SELECT id, full_name, status FROM students WHERE id = %s AND org_id = %s",
            (duplicate_id, org_id),
        )
        if not duplicate_rows:
            raise NotFoundError(
                f"Duplicate student {duplicate_id} not found", code="STUDENT_NOT_FOUND"
            )

        primary = primary_rows[0]
        duplicate = duplicate_rows[0]

        for student, label in [(primary, "primary"), (duplicate, "duplicate")]:
            if str(student["status"]).upper() in _RESTRICTED_STATUSES:
                raise BusinessRuleViolation(
                    f"Cannot merge a student with status {student['status']} ({label})",
                    code="STUDENT_MERGE_RESTRICTED_STATUS",
                )

        import json

        task_id = str(uuid4())
        execute_transaction(
            [
                (
                    """
                INSERT INTO workflow_tasks
                    (id, org_id, task_type, payload, status,
                     requires_roles, created_by, created_at)
                VALUES (%s, %s, 'STUDENT_MERGE', %s, 'PENDING',
                        %s, %s, NOW())
                """,
                    (
                        task_id,
                        org_id,
                        json.dumps(
                            {"primary_id": primary_id, "duplicate_id": duplicate_id}
                        ),
                        json.dumps(["REGISTRAR", "SUPER_ADMIN"]),
                        initiator_id,
                    ),
                )
            ]
        )
        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=initiator_id,
            actor_role="registrar",
            entity_type="student_merge_request",
            entity_id=task_id,
            tenant_id=org_id,
            metadata={
                "source": "initiate_merge",
                "primary_id": primary_id,
                "duplicate_id": duplicate_id,
            },
        )

        logger.info(
            "merge_initiated | org=%s primary=%s duplicate=%s task=%s initiator=%s",
            org_id,
            primary_id,
            duplicate_id,
            task_id,
            initiator_id,
        )

        return {
            "merge_request_id": task_id,
            "primary_id": primary_id,
            "duplicate_id": duplicate_id,
            "status": "PENDING_APPROVAL",
        }

    @classmethod
    def execute_merge(
        cls,
        primary_id: str,
        duplicate_id: str,
        org_id: str,
        approver_id: str,
    ) -> dict:
        """
        Execute an approved student merge.

        - Archives the duplicate (status=ARCHIVED, merged_into=primary_id).
        - Re-parents all FK references across related tables.
        - Fires domain event students.merged.
        """
        # Verify both students exist
        primary_rows = execute_query(
            "SELECT id, status FROM students WHERE id = %s AND org_id = %s",
            (primary_id, org_id),
        )
        if not primary_rows:
            raise NotFoundError(
                f"Primary student {primary_id} not found", code="STUDENT_NOT_FOUND"
            )

        duplicate_rows = execute_query(
            "SELECT id, status FROM students WHERE id = %s AND org_id = %s",
            (duplicate_id, org_id),
        )
        if not duplicate_rows:
            raise NotFoundError(
                f"Duplicate student {duplicate_id} not found", code="STUDENT_NOT_FOUND"
            )

        primary = primary_rows[0]
        duplicate_rows[0]

        # Guard: neither should already be merged/archived in an incompatible way
        if str(primary["status"]).upper() == "ARCHIVED":
            raise BusinessRuleViolation(
                "Primary student is already archived",
                code="STUDENT_MERGE_PRIMARY_ARCHIVED",
            )

        try:
            merged_check = execute_query(
                "SELECT merged_into FROM students WHERE id = %s AND org_id = %s",
                (duplicate_id, org_id),
            )
            if merged_check and merged_check[0].get("merged_into"):
                raise BusinessRuleViolation(
                    "Duplicate student is already merged into another record",
                    code="STUDENT_ALREADY_MERGED",
                )
        except (KeyError, TypeError):
            pass  # merged_into column not present — skip check

        # Build atomic transaction: archive duplicate + re-parent FK references
        ops = [
            # Archive the duplicate
            (
                """
                UPDATE students
                SET merged_into = %s,
                    status = 'ARCHIVED',
                    updated_at = NOW()
                WHERE id = %s AND org_id = %s
                """,
                (primary_id, duplicate_id, org_id),
            ),
            # Re-parent: academic_records
            (
                "UPDATE academic_records SET student_id = %s WHERE student_id = %s",
                (primary_id, duplicate_id),
            ),
            # Re-parent: fee_payments
            (
                "UPDATE fee_payments SET student_id = %s WHERE student_id = %s",
                (primary_id, duplicate_id),
            ),
            # Re-parent: library_fines
            (
                "UPDATE library_fines SET student_id = %s WHERE student_id = %s",
                (primary_id, duplicate_id),
            ),
            # Re-parent: hostel_invoices
            (
                "UPDATE hostel_invoices SET student_id = %s WHERE student_id = %s",
                (primary_id, duplicate_id),
            ),
        ]

        execute_transaction(ops)
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=approver_id,
            actor_role="registrar",
            entity_type="student_merge",
            entity_id=primary_id,
            tenant_id=org_id,
            metadata={"source": "execute_merge", "archived_id": duplicate_id},
        )

        # Fire domain event
        DomainEventBus.publish(
            DomainEvent(
                event_type="students.merged",
                org_id=org_id,
                payload={
                    "primary_id": primary_id,
                    "duplicate_id": duplicate_id,
                    "merged_by": approver_id,
                },
                entity_type="student",
                entity_id=primary_id,
                actor_id=approver_id,
            )
        )

        logger.info(
            "merge_executed | org=%s primary=%s archived=%s approver=%s",
            org_id,
            primary_id,
            duplicate_id,
            approver_id,
        )

        return {
            "primary_id": primary_id,
            "archived_id": duplicate_id,
            "status": "MERGED",
        }
