"""SS-3 — Placement Drive Management + EC-SS-02/03

Manages the full campus placement drive lifecycle:
- Drive creation, eligibility configuration, student registration
- One-offer policy enforcement (student_placement_status.student_offer_locked)
- EC-SS-02: Offer revocation workflow (employer-side, TPO-verified)
- EC-SS-03: Verbal offer lock (TPO-initiated, auto-expiry)

Domain events emitted:
  placement.drive_opened     → notifies eligible students (via Communication module)
  placement.offer_accepted   → locks student under one-offer policy
  placement.offer_revoked    → unlocks student, re-inserts into active drives
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime

from pydantic import BaseModel
from server.core.audit import AuditAction, AuditLedger
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DriveCreate(BaseModel):
    company_name: str
    jd_title: str
    jd_description: str | None = None
    jd_skills: list[str] = []
    ctc_min_lpa: float | None = None
    ctc_max_lpa: float | None = None
    drive_type: str = "CAMPUS"
    eligibility_min_cgpa: float | None = None
    eligibility_max_backlogs: int = 0
    eligible_programs: list[str] = []
    eligible_batches: list[int] = []
    registration_open_at: datetime | None = None
    registration_close_at: datetime | None = None
    drive_date: date | None = None
    venue: str | None = None
    apply_one_offer_policy: bool = True


class OfferRevocationCreate(BaseModel):
    student_id: str
    drive_id: str | None = None
    company_name: str
    revocation_reason: str
    revocation_date: date
    evidence_url: str | None = None


class VerbalLockCreate(BaseModel):
    student_id: str
    drive_id: str | None = None
    company_name: str
    company_contact_name: str | None = None
    company_contact_email: str | None = None
    formal_offer_due_by: date


# ---------------------------------------------------------------------------
# Drive Service
# ---------------------------------------------------------------------------


class PlacementDriveService:
    @classmethod
    def create(cls, org_id: str, req: DriveCreate, actor_id: str) -> dict:
        did = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
            INSERT INTO placement_drives
                (id, org_id, company_name, jd_title, jd_description, jd_skills,
                 ctc_min_lpa, ctc_max_lpa, drive_type,
                 eligibility_min_cgpa, eligibility_max_backlogs,
                 eligible_programs, eligible_batches,
                 registration_open_at, registration_close_at, drive_date,
                 venue, apply_one_offer_policy, created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
                    (
                        did,
                        org_id,
                        req.company_name,
                        req.jd_title,
                        req.jd_description,
                        req.jd_skills or [],
                        req.ctc_min_lpa,
                        req.ctc_max_lpa,
                        req.drive_type,
                        req.eligibility_min_cgpa,
                        req.eligibility_max_backlogs,
                        req.eligible_programs or [],
                        req.eligible_batches or [],
                        req.registration_open_at,
                        req.registration_close_at,
                        req.drive_date,
                        req.venue,
                        req.apply_one_offer_policy,
                        actor_id,
                    ),
                )
            ]
        )

        AuditLedger.log(
            org_id=org_id,
            actor_id=actor_id,
            actor_type="human",
            action=AuditAction.CREATE,
            resource_type="placement_drive",
            resource_id=did,
            detail={"company": req.company_name, "type": req.drive_type},
        )
        return cls.get(org_id, did)

    @classmethod
    def get(cls, org_id: str, drive_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM placement_drives WHERE id = %s AND org_id = %s",
            (drive_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Placement drive {drive_id} not found")
        return dict(rows[0])

    @classmethod
    def list(
        cls,
        org_id: str,
        status: str | None = None,
        drive_type: str | None = None,
    ) -> list[dict]:
        sql = "SELECT * FROM placement_drives WHERE org_id = %s"
        params: list = [org_id]
        if status:
            sql += " AND status = %s"
            params.append(status)
        if drive_type:
            sql += " AND drive_type = %s"
            params.append(drive_type)
        sql += " ORDER BY drive_date DESC NULLS LAST, created_at DESC"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def open_drive(cls, org_id: str, drive_id: str, actor_id: str) -> dict:
        """Transition drive to OPEN and notify eligible students."""
        drive = cls.get(org_id, drive_id)
        if drive["status"] != "DRAFT":
            raise BusinessRuleViolation(f"Drive is already {drive['status']}")

        execute_transaction(
            [
                (
                    "UPDATE placement_drives SET status = 'OPEN', approved_by = %s, updated_at = NOW() "
                    "WHERE id = %s AND org_id = %s",
                    (actor_id, drive_id, org_id),
                )
            ]
        )

        AuditLedger.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="drive",
            entity_id=drive_id,
            tenant_id=org_id,
            metadata={"source": "open_drive"},
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="placement.drive_opened",
                org_id=org_id,
                payload={"drive_id": drive_id, "company": drive["company_name"]},
            )
        )

        return cls.get(org_id, drive_id)

    @classmethod
    def register_student(
        cls,
        org_id: str,
        drive_id: str,
        student_id: str,
        actor_id: str,
    ) -> dict:
        """Register a student for a drive, enforcing the one-offer policy."""
        drive = cls.get(org_id, drive_id)
        if drive["status"] != "OPEN":
            raise BusinessRuleViolation("Drive is not open for registrations")

        # One-offer policy check
        if drive["apply_one_offer_policy"]:
            lock_rows = execute_query(
                "SELECT student_offer_locked FROM student_placement_status "
                "WHERE org_id = %s AND student_id = %s",
                (org_id, student_id),
            )
            if lock_rows and lock_rows[0]["student_offer_locked"]:
                raise BusinessRuleViolation(
                    "Student already holds an offer — one-offer policy applies. "
                    "Submit an offer revocation request if the employer revoked."
                )

        # Check for duplicate registration
        existing = execute_query(
            "SELECT id FROM placement_registrations WHERE drive_id = %s AND student_id = %s",
            (drive_id, student_id),
        )
        if existing:
            raise BusinessRuleViolation("Student already registered for this drive")

        rid = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
            INSERT INTO placement_registrations
                (id, org_id, drive_id, student_id)
            VALUES (%s, %s, %s, %s)
            """,
                    (rid, org_id, drive_id, student_id),
                )
            ]
        )

        AuditLedger.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="student",
            entity_id=student_id,
            tenant_id=org_id,
            metadata={"source": "register_student"},
        )

        return dict(
            execute_query(
                "SELECT * FROM placement_registrations WHERE id = %s",
                (rid,),
            )[0]
        )

    @classmethod
    def record_offer_accepted(
        cls,
        org_id: str,
        drive_id: str,
        student_id: str,
        ctc_lpa: float,
        offer_letter_url: str | None,
        actor_id: str,
    ) -> dict:
        """Record accepted offer and lock student under one-offer policy."""
        execute_transaction(
            [
                (
                    """UPDATE placement_registrations
                   SET status = 'SELECTED', offer_received = TRUE,
                       offer_accepted = TRUE, ctc_lpa = %s,
                       offer_letter_url = %s, updated_at = NOW()
                   WHERE drive_id = %s AND student_id = %s AND org_id = %s""",
                    (ctc_lpa, offer_letter_url, drive_id, student_id, org_id),
                ),
                # Upsert placement status lock
                (
                    """INSERT INTO student_placement_status
                       (id, org_id, student_id, profile_active,
                        student_offer_locked, locked_by_drive_id, locked_at, lock_type)
                   VALUES (gen_random_uuid(), %s, %s, TRUE, TRUE, %s, NOW(), 'FORMAL_OFFER')
                   ON CONFLICT (org_id, student_id) DO UPDATE
                       SET student_offer_locked = TRUE,
                           locked_by_drive_id = EXCLUDED.locked_by_drive_id,
                           locked_at = EXCLUDED.locked_at,
                           lock_type = 'FORMAL_OFFER',
                           updated_at = NOW()""",
                    (org_id, student_id, drive_id),
                ),
            ]
        )

        AuditLedger.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="offer_accepted",
            entity_id=drive_id,
            tenant_id=org_id,
            metadata={"source": "record_offer_accepted"},
        )

        DomainEventBus.publish(
            DomainEvent(
                event_type="placement.offer_accepted",
                org_id=org_id,
                payload={
                    "student_id": student_id,
                    "drive_id": drive_id,
                    "ctc_lpa": ctc_lpa,
                },
            )
        )

        return dict(
            execute_query(
                "SELECT * FROM placement_registrations WHERE drive_id = %s AND student_id = %s",
                (drive_id, student_id),
            )[0]
        )


# ---------------------------------------------------------------------------
# EC-SS-02: Offer Revocation Service
# ---------------------------------------------------------------------------


class OfferRevocationService:
    @classmethod
    def submit_revocation(
        cls,
        org_id: str,
        req: OfferRevocationCreate,
        actor_id: str,
    ) -> dict:
        """Student or TPO reports that an employer has revoked an offer.

        TPO must verify using evidence before student is reactivated.
        """
        rid = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
            INSERT INTO placement_offer_revocations
                (id, org_id, student_id, drive_id, company_name,
                 revocation_reason, revocation_date, evidence_url, reported_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
                    (
                        rid,
                        org_id,
                        req.student_id,
                        req.drive_id,
                        req.company_name,
                        req.revocation_reason,
                        req.revocation_date,
                        req.evidence_url,
                        actor_id,
                    ),
                )
            ]
        )

        AuditLedger.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="revocation",
            entity_id=str(req.drive_id) if hasattr(req, "drive_id") else "",
            tenant_id=org_id,
            metadata={"source": "submit_revocation"},
        )

        logger.info(
            "Offer revocation submitted: id=%s student=%s company=%s",
            rid,
            req.student_id,
            req.company_name,
        )
        return cls.get(org_id, rid)

    @classmethod
    def get(cls, org_id: str, revocation_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM placement_offer_revocations WHERE id = %s AND org_id = %s",
            (revocation_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Revocation {revocation_id} not found")
        return dict(rows[0])

    @classmethod
    def list_pending(cls, org_id: str) -> list[dict]:
        rows = execute_query(
            """SELECT r.*, s.name AS student_name, s.roll_number
               FROM placement_offer_revocations r
               JOIN students s ON s.id = r.student_id
               WHERE r.org_id = %s AND r.tpo_verified = FALSE
               ORDER BY r.created_at""",
            (org_id,),
        )
        return [dict(r) for r in rows]

    @classmethod
    def tpo_verify(
        cls,
        org_id: str,
        revocation_id: str,
        approved: bool,
        actor_id: str,
    ) -> dict:
        """TPO verifies (or rejects) the revocation with evidence.

        If approved:
          1. Student placement lock removed.
          2. Student reactivated in all currently OPEN eligible drives.
          3. `placement.offer_revoked` event fired (Regulatory E14 excludes
             REVOKED_BY_EMPLOYER offers from NIRF placed % computation).
        """
        rev = cls.get(org_id, revocation_id)
        if rev["tpo_verified"]:
            raise BusinessRuleViolation("Revocation already verified")

        if approved:
            new_status = "VERIFIED_REACTIVATED"
            execute_transaction(
                [
                    (
                        """UPDATE placement_offer_revocations
                       SET tpo_verified = TRUE, tpo_verified_by = %s, tpo_verified_at = NOW(),
                           student_reactivated = TRUE, student_reactivated_at = NOW(),
                           status = %s
                       WHERE id = %s AND org_id = %s""",
                        (actor_id, new_status, revocation_id, org_id),
                    ),
                    # Unlock the student
                    (
                        """UPDATE student_placement_status
                       SET student_offer_locked = FALSE, unlock_reason = 'OFFER_REVOKED_BY_EMPLOYER',
                           unlocked_at = NOW(), unlocked_by = %s, updated_at = NOW()
                       WHERE org_id = %s AND student_id = %s""",
                        (actor_id, org_id, rev["student_id"]),
                    ),
                ]
            )

            AuditLedger.log(
                action=AuditAction.UPDATE,
                actor_id=actor_id,
                actor_role="system",
                entity_type="tpo_verify",
                entity_id="",
                tenant_id=org_id,
                metadata={"source": "tpo_verify"},
            )

            DomainEventBus.publish(
                DomainEvent(
                    event_type="placement.offer_revoked",
                    org_id=org_id,
                    payload={
                        "student_id": rev["student_id"],
                        "company_name": rev["company_name"],
                        "revocation_id": revocation_id,
                        "excluded_from_nirf": True,  # REVOKED offers not counted
                    },
                )
            )

            logger.info(
                "Offer revocation verified: student=%s company=%s — student unlocked",
                rev["student_id"],
                rev["company_name"],
            )
        else:
            execute_transaction(
                [
                    (
                        """UPDATE placement_offer_revocations
                   SET tpo_verified = TRUE, tpo_verified_by = %s, tpo_verified_at = NOW(),
                       status = 'REJECTED_BY_TPO'
                   WHERE id = %s AND org_id = %s""",
                        (actor_id, revocation_id, org_id),
                    )
                ]
            )

        return cls.get(org_id, revocation_id)


# ---------------------------------------------------------------------------
# EC-SS-03: Verbal Offer Lock Service
# ---------------------------------------------------------------------------


class VerbalLockService:
    @classmethod
    def create_lock(
        cls,
        org_id: str,
        req: VerbalLockCreate,
        actor_id: str,
    ) -> dict:
        """TPO creates a verbal offer lock for a student.

        Has the same drive-blocking effect as a FORMAL_OFFER.
        Auto-expires if formal PDF not received by formal_offer_due_by.
        Only a TPO can initiate — students cannot self-lock.
        """
        lid = str(uuid.uuid4())
        execute_transaction(
            [
                (
                    """
                INSERT INTO placement_offer_locks
                    (id, org_id, student_id, drive_id, company_name,
                     lock_type, initiated_by, company_contact_name,
                     company_contact_email, formal_offer_due_by)
                VALUES (%s, %s, %s, %s, %s, 'VERBAL_LOCK', %s, %s, %s, %s)
                """,
                    (
                        lid,
                        org_id,
                        req.student_id,
                        req.drive_id,
                        req.company_name,
                        actor_id,
                        req.company_contact_name,
                        req.company_contact_email,
                        req.formal_offer_due_by,
                    ),
                ),
                # Lock student in placement status table
                (
                    """INSERT INTO student_placement_status
                       (id, org_id, student_id, profile_active,
                        student_offer_locked, locked_by_drive_id, locked_at, lock_type)
                   VALUES (gen_random_uuid(), %s, %s, TRUE, TRUE, %s, NOW(), 'VERBAL_LOCK')
                   ON CONFLICT (org_id, student_id) DO UPDATE
                       SET student_offer_locked = TRUE,
                           locked_by_drive_id = EXCLUDED.locked_by_drive_id,
                           locked_at = EXCLUDED.locked_at,
                           lock_type = 'VERBAL_LOCK',
                           updated_at = NOW()""",
                    (org_id, req.student_id, req.drive_id),
                ),
            ]
        )

        AuditLedger.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_role="system",
            entity_type="lock",
            entity_id=str(req.drive_id) if hasattr(req, "drive_id") else "",
            tenant_id=org_id,
            metadata={"source": "create_lock"},
        )

        logger.info(
            "Verbal lock created: id=%s student=%s company=%s due_by=%s",
            lid,
            req.student_id,
            req.company_name,
            req.formal_offer_due_by,
        )
        return cls.get(org_id, lid)

    @classmethod
    def get(cls, org_id: str, lock_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM placement_offer_locks WHERE id = %s AND org_id = %s",
            (lock_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Offer lock {lock_id} not found")
        return dict(rows[0])

    @classmethod
    def expire_overdue_locks(cls, org_id: str) -> int:
        """Called by Celery Beat daily to auto-expire verbal locks past deadline.

        Returns count of expired locks.
        """
        expired_rows = execute_query(
            """
            SELECT id, student_id FROM placement_offer_locks
            WHERE org_id = %s
              AND lock_type = 'VERBAL_LOCK'
              AND auto_unlock_if_no_formal = TRUE
              AND formal_offer_received_at IS NULL
              AND formal_offer_due_by < CURRENT_DATE
              AND status = 'ACTIVE'
            """,
            (org_id,),
        )

        if not expired_rows:
            return 0

        lock_ids = [str(r["id"]) for r in expired_rows]
        student_ids = [str(r["student_id"]) for r in expired_rows]
        placeholders = ", ".join(["%s"] * len(lock_ids))

        ops = [
            (
                f"UPDATE placement_offer_locks SET status = 'AUTO_EXPIRED', unlocked_at = NOW() "  # noqa: S608
                f"WHERE id IN ({placeholders}) AND org_id = %s",
                (*lock_ids, org_id),
            ),
        ]
        for sid in student_ids:
            ops.append(
                (
                    """UPDATE student_placement_status
                   SET student_offer_locked = FALSE,
                       unlock_reason = 'VERBAL_LOCK_EXPIRED',
                       unlocked_at = NOW(), updated_at = NOW()
                   WHERE org_id = %s AND student_id = %s
                     AND lock_type = 'VERBAL_LOCK'""",
                    (org_id, sid),
                )
            )

        execute_transaction(ops)

        AuditLedger.log(
            action=AuditAction.UPDATE,
            actor_id="system",
            actor_role="system",
            entity_type="overdue_locks",
            entity_id="",
            tenant_id=org_id,
            metadata={"source": "expire_overdue_locks"},
        )
        logger.info("Auto-expired %d verbal locks for org=%s", len(lock_ids), org_id)
        return len(lock_ids)
