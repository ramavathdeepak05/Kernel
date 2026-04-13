"""
Admissions automation tasks — E04-S13+

Celery tasks that drive the autonomous M1 pipeline.
Triggered by domain events or the public intake endpoint.
"""

from __future__ import annotations

import logging

from server.worker import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="admissions.advance_pipeline", bind=True, max_retries=3, default_retry_delay=30
)
def advance_pipeline(
    self, org_id: str, applicant_id: str, actor_id: str = "system"
) -> dict:
    """
    Advance an applicant one step through the automation pipeline.
    Safe to call multiple times — each step is idempotent.
    Re-queued automatically after review decisions and payment confirmations.
    """
    from server.admissions.automation_pipeline import AdmissionsPipeline

    try:
        result = AdmissionsPipeline.advance(
            applicant_id=applicant_id,
            org_id=org_id,
            actor_id=actor_id,
        )
        logger.info(
            "admissions.advance_pipeline: applicant=%s status=%s next=%s",
            applicant_id,
            result.status,
            result.next_step,
        )
        return {
            "applicant_id": applicant_id,
            "status": result.status,
            "next_step": result.next_step,
            "message": result.message,
        }
    except Exception as exc:
        logger.error("admissions.advance_pipeline failed: %s", exc)
        raise self.retry(exc=exc)


@celery_app.task(
    name="admissions.process_intake", bind=True, max_retries=3, default_retry_delay=15
)
def process_intake(self, org_id: str, payload: dict) -> dict:
    """
    End-to-end intake processing for a public form submission.
    Steps:
      1. Create applicant record
      2. Run deduplication
      3. Queue advance_pipeline
    """
    from server.admissions.deduplication import LeadDeduplicationService
    from server.admissions.models import ApplicantCreate, SourceChannel
    from server.admissions.service import ApplicantService

    try:
        # 1. Create applicant
        applicant = ApplicantService.create(
            request=ApplicantCreate(
                name=payload["name"],
                email=payload["email"],
                phone=payload.get("phone", ""),
                intended_program=payload.get("intended_program", "General"),
                source_channel=SourceChannel.WEBSITE,
                metadata=payload.get("metadata", {}),
            ),
            org_id=org_id,
            actor_id="intake_api",
        )

        # 2. Deduplication check
        try:
            LeadDeduplicationService.find_and_merge_duplicates(
                applicant_id=applicant.id,
                org_id=org_id,
                actor_id="intake_api",
            )
        except Exception as dedup_exc:
            # Non-fatal — log and continue
            logger.warning(
                "process_intake: dedup check failed (non-fatal): %s", dedup_exc
            )

        # 3. Trigger automation pipeline
        advance_pipeline.delay(org_id=org_id, applicant_id=applicant.id)

        logger.info(
            "process_intake: created applicant %s for org %s", applicant.id, org_id
        )
        return {"applicant_id": applicant.id, "status": "queued"}

    except Exception as exc:
        logger.error("process_intake failed: %s", exc)
        raise self.retry(exc=exc)


@celery_app.task(name="admissions.check_fee_overdue")
def check_fee_overdue() -> dict:
    """
    Daily beat task: flag applicants whose offer letter validity has expired
    without fee payment.
    """
    from datetime import date, timedelta

    from server.admissions.policy_store import PolicyKey, PolicyStore
    from server.core.domain_events import DomainEvent, DomainEventBus
    from server.db_service import execute_query

    # Get all orgs with active offer letters
    try:
        rows = execute_query(
            """
            SELECT ol.org_id, ol.applicant_id, ol.issued_at
            FROM offer_letters ol
            JOIN applicants a ON a.id = ol.applicant_id
            WHERE ol.is_valid = TRUE
              AND a.status NOT IN ('ADMITTED','ENROLLED','ANNULLED')
            """,
            (),
        )
        flagged = 0
        for row in rows:
            validity_days = int(
                PolicyStore.get(row["org_id"], PolicyKey.OFFER_VALIDITY_DAYS) or 30
            )
            expiry = row["issued_at"].date() + timedelta(days=validity_days)
            if date.today() > expiry:
                DomainEventBus.publish(
                    DomainEvent(
                        event_type="OfferLetterExpired",
                        entity_type="applicant",
                        entity_id=str(row["applicant_id"]),
                        org_id=row["org_id"],
                        payload={
                            "issued_at": str(row["issued_at"]),
                            "expired_on": str(expiry),
                        },
                        actor_id="system",
                    )
                )
                flagged += 1

        logger.info("check_fee_overdue: flagged %d expired offer letters", flagged)
        return {"status": "ok", "flagged": flagged}
    except Exception as exc:
        logger.error("check_fee_overdue failed: %s", exc)
        return {"status": "error", "error": str(exc)}


@celery_app.task(name="tasks.expire_utr_access_lifts")
def expire_utr_access_lifts() -> dict:
    """
    EC-ADM-05 — Expire 48-hour access lifts for UTR payment disputes.

    Scheduled every 30 minutes. Marks disputes whose access_lifted_until
    has passed as access_expired = TRUE, restoring normal access restrictions.
    """
    from server.core.audit import AuditAction, AuditLog
    from server.core.domain_events import DomainEvent, DomainEventBus
    from server.db_service import execute_query, execute_transaction

    try:
        rows = execute_query(
            """
            SELECT id, org_id, payment_id
            FROM   payment_utr_disputes
            WHERE  access_lifted_until IS NOT NULL
              AND  access_lifted_until <= NOW()
              AND  access_expired = FALSE
            """,
            (),
        )
        expired = 0
        for row in rows:
            execute_transaction(
                [
                    (
                        """
                UPDATE payment_utr_disputes
                   SET access_expired = TRUE
                 WHERE id = %s
                """,
                        (row["id"],),
                    )
                ]
            )
            AuditLog.log(
                action=AuditAction.UPDATE,
                actor_id="system",
                actor_role="system",
                entity_type="utr_dispute",
                entity_id="",
                tenant_id="",
                metadata={"source": "expire_utr_access_lifts"},
            )
            DomainEventBus.publish(
                DomainEvent(
                    event_type="DisputeAccessLiftExpired",
                    entity_type="payment_utr_dispute",
                    entity_id=str(row["id"]),
                    org_id=str(row["org_id"]),
                    payload={"payment_id": str(row["payment_id"])},
                    actor_id="system",
                )
            )
            expired += 1

        logger.info("expire_utr_access_lifts: expired %d access lifts", expired)
        return {"status": "ok", "expired": expired}
    except Exception as exc:
        logger.error("expire_utr_access_lifts failed: %s", exc)
        return {"status": "error", "error": str(exc)}
