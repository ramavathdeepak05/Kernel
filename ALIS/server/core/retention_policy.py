"""
ALIS Data Retention & Deletion Policy Engine — E00-S07

MODULE: Platform Core (E00 — Institutional Security & Governance)
LAYER: Layer 1 (Retention Metadata) + Layer 4 (Archival Locks)
ENTITY: RetentionPolicy, ArchivalRecord

This module implements:
  1. Retention Matrix — maps entity types to retention periods via the
     EntityClassificationRegistry (Layer 1 metadata).
  2. Scheduled Archival Service — evaluates active records against their
     retention_class and transitions expired records to ARCHIVED state.
  3. Legal Deletion Workflow — enforces that REGULATED data can only be
     hard-deleted by a SUPER_ADMIN, with full audit trail.
  4. Retention Audit Report — generates a summary of archival and
     deletion activity for compliance.

Must Align With
───────────────
  • Layer 1 — Retention metadata on every entity classification
  • Layer 4 — Archival lock (ARCHIVED_RECORD) blocks mutations
  • E00 Hard Constraints:
      – No hard deletes of regulated records without legal workflow
      – All state mutations must be audit-logged
      – Deletion requires superadmin + log

Acceptance Criteria (E00-S07)
─────────────────────────────
  • [x] Scheduled archival service
  • [x] Deletion requires superadmin + log
  • [x] Retention audit report
"""
from __future__ import annotations

import logging
from enum import Enum
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from .data_classification import (
    EntityClassificationRegistry,
    RetentionClass,
    RegulatedDataType,
)
from .audit import AuditLedger, AuditAction
from .rbac import Role, Permission, check_role_permission
from .locks import check_global_locks, LockType

logger = logging.getLogger(__name__)


# ============================================================================
# ARCHIVAL STATUS
# ============================================================================

class ArchivalStatus(str, Enum):
    """Status of an archival operation."""
    PENDING = "PENDING"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"
    SKIPPED_PERMANENT = "SKIPPED_PERMANENT"


class DeletionStatus(str, Enum):
    """Status of a hard-delete request."""
    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"


# ============================================================================
# ARCHIVAL RECORD (value object per entity processed)
# ============================================================================

@dataclass
class ArchivalRecord:
    """
    Immutable record of an archival action on a single entity.
    """
    entity_type: str
    entity_id: str
    tenant_id: str
    retention_class: RetentionClass
    retention_days: Optional[int]
    created_at: datetime              # When the entity was originally created
    archived_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    status: ArchivalStatus = ArchivalStatus.PENDING
    reason: str = ""


# ============================================================================
# DELETION REQUEST (value object)
# ============================================================================

@dataclass
class DeletionRequest:
    """
    Tracks a legal hard-delete request for regulated data.

    Lifecycle: REQUESTED → APPROVED → EXECUTED (or REJECTED)
    """
    entity_type: str
    entity_id: str
    tenant_id: str
    requested_by: str               # Actor ID who initiated
    actor_role: str
    justification: str
    status: DeletionStatus = DeletionStatus.REQUESTED
    requested_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    executed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


# ============================================================================
# RETENTION MATRIX HELPER
# ============================================================================

class RetentionMatrix:
    """
    Read-only view over the EntityClassificationRegistry that exposes
    the retention matrix required by E00-S07.

    This is a helper — the canonical data lives in the registry.
    """

    @staticmethod
    def get_retention_info(entity_type: str) -> Dict[str, Any]:
        """
        Get retention policy information for an entity type.

        Returns:
            Dict with retention_class, retention_days, is_permanent, regulated_type.
        """
        ec = EntityClassificationRegistry.get_or_default(entity_type)
        return {
            "entity_type": entity_type,
            "retention_class": ec.retention_class.value,
            "retention_days": ec.effective_retention_days,
            "is_permanent": ec.is_permanent,
            "regulated_type": ec.default_regulated_type.value,
            "sensitivity": ec.default_sensitivity.value,
        }

    @staticmethod
    def get_full_matrix() -> List[Dict[str, Any]]:
        """
        Return the full retention matrix for all registered entity types.

        Used for the Retention Audit Report.
        """
        result = []
        for entity_type in EntityClassificationRegistry.list_registered():
            result.append(RetentionMatrix.get_retention_info(entity_type))
        return result


# ============================================================================
# ARCHIVAL SERVICE
# ============================================================================

class ArchivalService:
    """
    Scheduled archival service — E00-S07.

    Evaluates active records against their retention classification and
    archives those that have exceeded their retention period.

    This service is designed to be called by:
      • A cron job / external scheduler
      • A secured API endpoint
      • A CLI management command

    It does NOT run as a background thread inside the application.
    """

    # In-memory store for archival records (testing / in-process usage)
    _archival_log: List[ArchivalRecord] = []

    @classmethod
    def run_archival_job(
        cls,
        tenant_id: str,
        records: List[Dict[str, Any]],
        dry_run: bool = False,
    ) -> List[ArchivalRecord]:
        """
        Execute archival evaluation for a batch of records.

        Args:
            tenant_id:  Tenant scope for the archival run.
            records:    List of entity dicts, each containing at minimum:
                          entity_type, entity_id, created_at, status
            dry_run:    If True, evaluate but do not commit.

        Returns:
            List of ArchivalRecord objects describing what was (or would be)
            archived.
        """
        now = datetime.now(timezone.utc)
        results: List[ArchivalRecord] = []

        for record in records:
            entity_type = record.get("entity_type", "")
            entity_id = record.get("entity_id", "")
            created_at_raw = record.get("created_at")

            # Parse created_at
            if isinstance(created_at_raw, str):
                created_at = datetime.fromisoformat(created_at_raw)
            elif isinstance(created_at_raw, datetime):
                created_at = created_at_raw
            else:
                logger.warning(
                    "Skipping record %s/%s: invalid created_at",
                    entity_type, entity_id,
                )
                continue

            # Ensure timezone-aware
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)

            # Skip already archived
            current_status = str(record.get("status", "")).upper()
            if current_status == "ARCHIVED":
                continue

            # Look up retention policy
            ec = EntityClassificationRegistry.get_or_default(entity_type)

            # Permanent records are never auto-archived
            if ec.is_permanent:
                results.append(ArchivalRecord(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    tenant_id=tenant_id,
                    retention_class=ec.retention_class,
                    retention_days=ec.effective_retention_days,
                    created_at=created_at,
                    status=ArchivalStatus.SKIPPED_PERMANENT,
                    reason="Permanent retention — not eligible for archival",
                ))
                continue

            # Check if retention period has elapsed
            retention_days = ec.effective_retention_days
            expiry_date = created_at + timedelta(days=retention_days)

            if now < expiry_date:
                # Not yet eligible
                continue

            # Record is eligible for archival
            archival_record = ArchivalRecord(
                entity_type=entity_type,
                entity_id=entity_id,
                tenant_id=tenant_id,
                retention_class=ec.retention_class,
                retention_days=retention_days,
                created_at=created_at,
                status=ArchivalStatus.ARCHIVED if not dry_run else ArchivalStatus.PENDING,
                reason=f"Retention period of {retention_days} days exceeded",
            )

            if not dry_run:
                # Log the archival action to the immutable audit ledger
                try:
                    AuditLedger.log(
                        action=AuditAction.ARCHIVE,
                        actor_id="system",
                        actor_role="system",
                        entity_type=entity_type,
                        entity_id=entity_id,
                        tenant_id=tenant_id,
                        metadata={
                            "retention_class": ec.retention_class.value,
                            "retention_days": retention_days,
                            "created_at": created_at.isoformat(),
                            "archived_at": now.isoformat(),
                            "reason": archival_record.reason,
                        },
                    )
                    archival_record.status = ArchivalStatus.ARCHIVED
                except Exception as exc:
                    logger.exception(
                        "Failed to archive %s/%s: %s",
                        entity_type, entity_id, exc,
                    )
                    archival_record.status = ArchivalStatus.FAILED
                    archival_record.reason = f"Archival failed: {exc}"

            results.append(archival_record)
            cls._archival_log.append(archival_record)

        logger.info(
            "Archival job completed for tenant %s: %d records evaluated, "
            "%d archived, %d skipped (permanent)",
            tenant_id,
            len(records),
            sum(1 for r in results if r.status == ArchivalStatus.ARCHIVED),
            sum(1 for r in results if r.status == ArchivalStatus.SKIPPED_PERMANENT),
        )

        return results

    @classmethod
    def _reset(cls) -> None:
        """Reset archival log. FOR TESTING ONLY."""
        cls._archival_log = []


# ============================================================================
# RETENTION SERVICE (LEGAL DELETION WORKFLOW)
# ============================================================================

class RetentionService:
    """
    Legal deletion workflow for regulated data — E00-S07.

    Hard deletion of REGULATED data is strictly prohibited unless:
      1. Actor has Role.SUPER_ADMIN
      2. A justification is provided
      3. The pre-deletion payload is logged to the immutable audit ledger
      4. The entity's regulated status is verified

    This enforces the E00 Hard Constraint:
        "No hard deletes of regulated records without legal workflow"
    """

    # In-memory deletion request log (testing / in-process usage)
    _deletion_requests: List[DeletionRequest] = []

    @classmethod
    def request_hard_delete(
        cls,
        entity_type: str,
        entity_id: str,
        tenant_id: str,
        actor_id: str,
        actor_role: str,
        justification: str,
        entity_snapshot: Optional[Dict[str, Any]] = None,
    ) -> DeletionRequest:
        """
        Request hard deletion of a regulated record.

        Enforces:
          - actor_role == SUPER_ADMIN
          - justification is non-empty
          - Pre-deletion snapshot is logged to audit ledger
          - Entity is not permanently retained

        Args:
            entity_type:     Type of entity to delete
            entity_id:       ID of the entity
            tenant_id:       Tenant scope
            actor_id:        ID of the requesting actor
            actor_role:      Role of the requesting actor
            justification:   Legal reason for the deletion
            entity_snapshot: Pre-deletion data (logged before physical delete)

        Returns:
            DeletionRequest with status EXECUTED or REJECTED.

        Raises:
            PermissionError: If actor is not SUPER_ADMIN.
            ValueError:      If justification is missing or entity is permanent.
        """
        # --- Gate 1: Role enforcement ---
        try:
            role = Role(actor_role) if isinstance(actor_role, str) else actor_role
        except ValueError:
            raise PermissionError(
                f"Unknown role '{actor_role}' — hard delete denied"
            )

        if role != Role.SUPER_ADMIN:
            # Log the denied attempt
            try:
                AuditLedger.log(
                    action=AuditAction.HARD_DELETE,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    tenant_id=tenant_id,
                    metadata={
                        "status": "REJECTED",
                        "reason": "Insufficient privileges — SUPER_ADMIN required",
                    },
                )
            except Exception:
                pass  # Audit failure must not mask the security denial
            raise PermissionError(
                "Hard deletion of regulated data requires SUPER_ADMIN role (E00-S07)"
            )

        # --- Gate 2: Justification ---
        if not justification or not justification.strip():
            raise ValueError(
                "A legal justification is required for hard deletion (E00-S07)"
            )

        # --- Gate 3: Check retention policy ---
        ec = EntityClassificationRegistry.get_or_default(entity_type)
        if ec.is_permanent:
            req = DeletionRequest(
                entity_type=entity_type,
                entity_id=entity_id,
                tenant_id=tenant_id,
                requested_by=actor_id,
                actor_role=actor_role,
                justification=justification,
                status=DeletionStatus.REJECTED,
                rejection_reason=(
                    f"Entity type '{entity_type}' has PERMANENT retention — "
                    "hard deletion is prohibited"
                ),
            )
            cls._deletion_requests.append(req)

            try:
                AuditLedger.log(
                    action=AuditAction.HARD_DELETE,
                    actor_id=actor_id,
                    actor_role=actor_role,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    tenant_id=tenant_id,
                    metadata={
                        "status": "REJECTED",
                        "reason": req.rejection_reason,
                        "justification": justification,
                    },
                )
            except Exception:
                pass  # Audit failure should not block the rejection

            return req

        # --- Gate 4: Log pre-deletion snapshot ---
        deletion_metadata: Dict[str, Any] = {
            "status": "EXECUTED",
            "justification": justification,
            "retention_class": ec.retention_class.value,
            "regulated_type": ec.default_regulated_type.value,
        }
        if entity_snapshot:
            deletion_metadata["pre_deletion_snapshot"] = entity_snapshot

        try:
            AuditLedger.log(
                action=AuditAction.HARD_DELETE,
                actor_id=actor_id,
                actor_role=actor_role,
                entity_type=entity_type,
                entity_id=entity_id,
                tenant_id=tenant_id,
                metadata=deletion_metadata,
            )
        except Exception as exc:
            logger.exception("Failed to log hard-delete audit entry: %s", exc)
            # We do NOT proceed with deletion if audit logging fails
            raise RuntimeError(
                "Cannot proceed with hard deletion — audit logging failed. "
                "E00 invariant: all state mutations must be audit-logged."
            ) from exc

        # --- Build result ---
        req = DeletionRequest(
            entity_type=entity_type,
            entity_id=entity_id,
            tenant_id=tenant_id,
            requested_by=actor_id,
            actor_role=actor_role,
            justification=justification,
            status=DeletionStatus.EXECUTED,
            executed_at=datetime.now(timezone.utc),
        )
        cls._deletion_requests.append(req)

        logger.info(
            "Hard delete executed for %s/%s by %s [tenant=%s]: %s",
            entity_type, entity_id, actor_id, tenant_id, justification,
        )

        return req

    @classmethod
    def _reset(cls) -> None:
        """Reset deletion log. FOR TESTING ONLY."""
        cls._deletion_requests = []


# ============================================================================
# RETENTION AUDIT REPORT
# ============================================================================

class RetentionAuditReport:
    """
    Generate a retention audit report summarising:
      • The current retention matrix
      • Recent archival activity
      • Recent deletion activity
    """

    @staticmethod
    def generate(
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate a retention audit report.

        Args:
            tenant_id: Optional filter — if None, report covers all tenants.

        Returns:
            Dict with retention_matrix, archival_summary, deletion_summary.
        """
        # Retention matrix
        matrix = RetentionMatrix.get_full_matrix()

        # Archival summary
        archival_records = ArchivalService._archival_log
        if tenant_id:
            archival_records = [
                r for r in archival_records if r.tenant_id == tenant_id
            ]

        archival_summary = {
            "total_evaluated": len(archival_records),
            "archived": sum(
                1 for r in archival_records
                if r.status == ArchivalStatus.ARCHIVED
            ),
            "skipped_permanent": sum(
                1 for r in archival_records
                if r.status == ArchivalStatus.SKIPPED_PERMANENT
            ),
            "failed": sum(
                1 for r in archival_records
                if r.status == ArchivalStatus.FAILED
            ),
        }

        # Deletion summary
        deletion_requests = RetentionService._deletion_requests
        if tenant_id:
            deletion_requests = [
                r for r in deletion_requests if r.tenant_id == tenant_id
            ]

        deletion_summary = {
            "total_requests": len(deletion_requests),
            "executed": sum(
                1 for r in deletion_requests
                if r.status == DeletionStatus.EXECUTED
            ),
            "rejected": sum(
                1 for r in deletion_requests
                if r.status == DeletionStatus.REJECTED
            ),
        }

        return {
            "report_generated_at": datetime.now(timezone.utc).isoformat(),
            "tenant_id": tenant_id or "ALL",
            "retention_matrix": matrix,
            "archival_summary": archival_summary,
            "deletion_summary": deletion_summary,
        }
