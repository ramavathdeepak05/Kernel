"""
ALIS Policy Governance & Registry Service — E00-S09

MODULE: Platform Core (E00 — Institutional Security & Governance)
LAYER: Layer 1 (Policy Entity Schema) + Layer 3 (Activation Legality) +
       Layer 4 (Immutable Version Locking) + Layer 6 (Full Audit Log)
ENTITY: Policy

This module implements a dedicated Policy Service positioned between
the UI and the Rule Engine.  Policies are structured, parameterized,
versioned, time-bound, and approval-controlled.

Lifecycle State Machine
───────────────────────
  DRAFT  →  SUBMITTED  →  APPROVED  →  ACTIVATED  →  SUPERSEDED
                                                      │
                                         (new version activates)

  - DRAFT:       Editable. Author is composing / refining.
  - SUBMITTED:   Locked for review.  Awaiting approval.
  - APPROVED:    Approval granted.  Waiting for effective_from date.
  - ACTIVATED:   Live.  Consumed by rule engine.  IMMUTABLE.
  - SUPERSEDED:  Replaced by a newer activated version.  IMMUTABLE.

Hard Constraints (from Master Developer + Hidden Tensions doc):
──────────────────────────────────────────────────────────────
  • Policies must never be free-text or embedded in AI weights.
  • No retroactive policy mutation once activated.
  • effective_from / effective_to strictly enforced.
  • PolicyActivated event emitted on activation.
  • Full audit trail for every lifecycle transition.
  • Read-only API for rule engine consumption.

Acceptance Criteria (E00-S09):
  - [x] POST /policy/draft
  - [x] POST /policy/submit
  - [x] POST /policy/approve
  - [x] GET  /policy/:policyId?date=
  - [x] Every policy version hash stored
  - [ ] Diff viewer available in admin UI (frontend — separate task)
"""
from __future__ import annotations

import hashlib
import json
import logging
from uuid import uuid4
from datetime import datetime, timezone, date
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from .audit import AuditLog, AuditAction
from .events import EventBus
from .schema import Event
from .rbac import Role, Permission, verify_access, AccessResult

logger = logging.getLogger(__name__)


# ============================================================================
# POLICY LIFECYCLE STATES  (Layer 3 — State Machine)
# ============================================================================

class PolicyStatus(str, Enum):
    """
    Canonical lifecycle states for a Policy entity.

    Allowed Transitions (forward-only, Layer 3 compliant):
        DRAFT      → SUBMITTED
        SUBMITTED  → APPROVED
        APPROVED   → ACTIVATED
        ACTIVATED  → SUPERSEDED  (only by system when new version activates)
    """
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    ACTIVATED = "ACTIVATED"
    SUPERSEDED = "SUPERSEDED"


# Layer 3: Allowed state transitions (forward-only)
POLICY_TRANSITIONS: Dict[PolicyStatus, set] = {
    PolicyStatus.DRAFT: {PolicyStatus.SUBMITTED},
    PolicyStatus.SUBMITTED: {PolicyStatus.APPROVED},
    PolicyStatus.APPROVED: {PolicyStatus.ACTIVATED},
    PolicyStatus.ACTIVATED: {PolicyStatus.SUPERSEDED},
    PolicyStatus.SUPERSEDED: set(),  # Terminal
}


def _validate_transition(current: PolicyStatus, target: PolicyStatus) -> bool:
    """Layer 3: Reject undeclared transitions."""
    return target in POLICY_TRANSITIONS.get(current, set())


# ============================================================================
# POLICY VERSION HASH  (Layer 4 — Immutable Locking)
# ============================================================================

def compute_policy_hash(policy_data: Dict[str, Any]) -> str:
    """
    Compute SHA-256 hash of the policy payload for immutability verification.

    The hash covers: policy_id, version, parameters, effective_from,
    effective_to, and the full structured payload.
    """
    canonical = json.dumps(policy_data, sort_keys=True, separators=(",", ":"),
                           default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ============================================================================
# POLICY SERVICE  (Core Business Logic)
# ============================================================================

class PolicyService:
    """
    Policy Governance & Registry Service.

    All methods are classmethods operating against PostgreSQL via
    db_service (tenant-scoped).  The service enforces:
      - State machine transitions (Layer 3)
      - Immutability of activated policies (Layer 4)
      - Temporal resolution via effective_from / effective_to
      - Audit logging of every transition (Layer 6)
      - PolicyActivated event emission (Event Contract)
    """

    # ------------------------------------------------------------------
    # CREATE DRAFT
    # ------------------------------------------------------------------

    @staticmethod
    def create_draft(
        policy_type: str,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        effective_from: datetime,
        effective_to: Optional[datetime],
        created_by: str,
        actor_role: str,
        tenant_id: str,
        module: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new policy draft.

        Args:
            policy_type:    Category (e.g., 'attendance_threshold',
                            'grading_cutoff', 'fee_waiver_limit').
            name:           Human-readable policy name.
            description:    Purpose description.
            parameters:     Structured JSON parameters
                            (thresholds, ranges, toggles).
            effective_from: When the policy becomes applicable.
            effective_to:   When the policy expires (None = indefinite).
            created_by:     Actor ID of the drafter.
            actor_role:     Role of the drafter.
            tenant_id:      Tenant scope.
            module:         Optional owning module (e.g., 'm1', 'm4').

        Returns:
            Dict with the created policy record.
        """
        from server.db_service import execute_query, execute_transaction

        policy_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # Determine version number: latest version of this policy_type + 1
        existing = execute_query(
            "SELECT COALESCE(MAX(version), 0) AS max_ver "
            "FROM policy_registry WHERE policy_type = %s AND tenant_id = %s",
            (policy_type, tenant_id),
            tenant_id=tenant_id,
        )
        version = (existing[0]["max_ver"] if existing else 0) + 1

        # Compute content hash
        hash_payload = {
            "policy_type": policy_type,
            "version": version,
            "parameters": parameters,
            "effective_from": str(effective_from),
            "effective_to": str(effective_to) if effective_to else None,
        }
        content_hash = compute_policy_hash(hash_payload)

        insert_sql = """
            INSERT INTO policy_registry (
                id, tenant_id, policy_type, name, description,
                parameters, version, status,
                effective_from, effective_to,
                content_hash, created_by, created_at, updated_at,
                module
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s
            )
        """
        execute_transaction(
            [(insert_sql, (
                policy_id, tenant_id, policy_type, name, description,
                json.dumps(parameters), version, PolicyStatus.DRAFT.value,
                effective_from, effective_to,
                content_hash, created_by, now, now,
                module,
            ))],
            tenant_id=tenant_id,
        )

        # Layer 6: Audit
        AuditLog.log(
            action=AuditAction.POLICY_DRAFTED,
            actor_id=created_by,
            actor_role=actor_role,
            entity_type="policy",
            entity_id=policy_id,
            tenant_id=tenant_id,
            metadata={
                "policy_type": policy_type,
                "version": version,
                "content_hash": content_hash,
                "module": module,
            },
        )

        logger.info(
            "Policy draft created [id=%s type=%s version=%d tenant=%s]",
            policy_id, policy_type, version, tenant_id,
        )

        return {
            "id": policy_id,
            "policy_type": policy_type,
            "name": name,
            "version": version,
            "status": PolicyStatus.DRAFT.value,
            "content_hash": content_hash,
        }

    # ------------------------------------------------------------------
    # SUBMIT FOR APPROVAL
    # ------------------------------------------------------------------

    @staticmethod
    def submit_for_approval(
        policy_id: str,
        submitted_by: str,
        actor_role: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """
        Transition a DRAFT policy to SUBMITTED.

        The policy is locked from further edits after this point.
        """
        from server.db_service import execute_query, execute_transaction

        rows = execute_query(
            "SELECT id, status, policy_type, version FROM policy_registry "
            "WHERE id = %s AND tenant_id = %s",
            (policy_id, tenant_id),
            tenant_id=tenant_id,
        )
        if not rows:
            raise ValueError(f"Policy {policy_id} not found.")

        current_status = PolicyStatus(rows[0]["status"])
        if not _validate_transition(current_status, PolicyStatus.SUBMITTED):
            raise ValueError(
                f"Illegal transition: {current_status.value} → SUBMITTED. "
                f"Only DRAFT policies can be submitted."
            )

        now = datetime.now(timezone.utc)
        execute_transaction(
            [(
                "UPDATE policy_registry "
                "SET status = %s, submitted_by = %s, submitted_at = %s, updated_at = %s "
                "WHERE id = %s AND tenant_id = %s",
                (PolicyStatus.SUBMITTED.value, submitted_by, now, now,
                 policy_id, tenant_id),
            )],
            tenant_id=tenant_id,
        )

        AuditLog.log(
            action=AuditAction.POLICY_SUBMITTED,
            actor_id=submitted_by,
            actor_role=actor_role,
            entity_type="policy",
            entity_id=policy_id,
            tenant_id=tenant_id,
            metadata={
                "policy_type": rows[0]["policy_type"],
                "version": rows[0]["version"],
            },
        )

        logger.info("Policy %s submitted for approval.", policy_id)
        return {"id": policy_id, "status": PolicyStatus.SUBMITTED.value}

    # ------------------------------------------------------------------
    # APPROVE POLICY
    # ------------------------------------------------------------------

    @staticmethod
    def approve_policy(
        policy_id: str,
        approved_by: str,
        actor_role: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """
        Transition a SUBMITTED policy to APPROVED.

        Only authorized roles (ADMIN, SUPER_ADMIN) may approve.
        """
        from server.db_service import execute_query, execute_transaction

        # RBAC check
        access = verify_access(
            Role(actor_role),
            Permission.POLICY_APPROVE,
            context={"tenant_id": tenant_id},
        )
        if not access.allowed:
            raise PermissionError(
                f"Role '{actor_role}' is not authorized to approve policies. "
                f"Reason: {access.reason}"
            )

        rows = execute_query(
            "SELECT id, status, policy_type, version, effective_from "
            "FROM policy_registry WHERE id = %s AND tenant_id = %s",
            (policy_id, tenant_id),
            tenant_id=tenant_id,
        )
        if not rows:
            raise ValueError(f"Policy {policy_id} not found.")

        current_status = PolicyStatus(rows[0]["status"])
        if not _validate_transition(current_status, PolicyStatus.APPROVED):
            raise ValueError(
                f"Illegal transition: {current_status.value} → APPROVED. "
                f"Only SUBMITTED policies can be approved."
            )

        now = datetime.now(timezone.utc)
        effective_from = rows[0]["effective_from"]

        # If effective_from is now or in the past, auto-activate
        should_activate = (
            effective_from is not None
            and effective_from <= now
        )

        new_status = (
            PolicyStatus.ACTIVATED if should_activate
            else PolicyStatus.APPROVED
        )

        execute_transaction(
            [(
                "UPDATE policy_registry "
                "SET status = %s, approved_by = %s, approved_at = %s, "
                "    activated_at = %s, updated_at = %s "
                "WHERE id = %s AND tenant_id = %s",
                (new_status.value, approved_by, now,
                 now if should_activate else None, now,
                 policy_id, tenant_id),
            )],
            tenant_id=tenant_id,
        )

        AuditLog.log(
            action=AuditAction.POLICY_APPROVED,
            actor_id=approved_by,
            actor_role=actor_role,
            entity_type="policy",
            entity_id=policy_id,
            tenant_id=tenant_id,
            metadata={
                "policy_type": rows[0]["policy_type"],
                "version": rows[0]["version"],
                "auto_activated": should_activate,
            },
        )

        if should_activate:
            _on_policy_activated(
                policy_id=policy_id,
                policy_type=rows[0]["policy_type"],
                version=rows[0]["version"],
                actor_id=approved_by,
                actor_role=actor_role,
                tenant_id=tenant_id,
            )

        logger.info(
            "Policy %s approved (auto_activated=%s).", policy_id, should_activate
        )
        return {"id": policy_id, "status": new_status.value}

    # ------------------------------------------------------------------
    # GET POLICY (temporal resolution)
    # ------------------------------------------------------------------

    @staticmethod
    def get_policy(
        policy_id: str,
        tenant_id: str,
        as_of_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a policy by ID.

        If `as_of_date` is provided, returns the version of this
        policy_type that was active on that date.  If omitted, returns
        the current record for the given policy_id.

        This is the READ-ONLY API consumed by the rule engine.
        """
        from server.db_service import execute_query

        if as_of_date:
            # Temporal query: find the ACTIVATED version for this policy's
            # type that covers the requested date.
            # First, get the policy_type from the given ID.
            type_row = execute_query(
                "SELECT policy_type FROM policy_registry "
                "WHERE id = %s AND tenant_id = %s",
                (policy_id, tenant_id),
                tenant_id=tenant_id,
            )
            if not type_row:
                return None

            policy_type = type_row[0]["policy_type"]

            rows = execute_query(
                "SELECT * FROM policy_registry "
                "WHERE policy_type = %s AND tenant_id = %s "
                "  AND status IN (%s, %s) "
                "  AND effective_from <= %s "
                "  AND (effective_to IS NULL OR effective_to >= %s) "
                "ORDER BY version DESC LIMIT 1",
                (policy_type, tenant_id,
                 PolicyStatus.ACTIVATED.value, PolicyStatus.SUPERSEDED.value,
                 as_of_date, as_of_date),
                tenant_id=tenant_id,
            )
        else:
            rows = execute_query(
                "SELECT * FROM policy_registry "
                "WHERE id = %s AND tenant_id = %s",
                (policy_id, tenant_id),
                tenant_id=tenant_id,
            )

        if not rows:
            return None

        row = dict(rows[0])
        # Deserialize parameters from JSON string
        if isinstance(row.get("parameters"), str):
            row["parameters"] = json.loads(row["parameters"])
        return row

    # ------------------------------------------------------------------
    # GET ACTIVE POLICY BY TYPE (Rule Engine convenience)
    # ------------------------------------------------------------------

    @staticmethod
    def get_active_policy_by_type(
        policy_type: str,
        tenant_id: str,
        as_of_date: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve the currently active policy for a given type.

        Used by the Rule Engine for policy resolution at execution time.
        Binds to version active at `as_of_date` (defaults to now).
        """
        from server.db_service import execute_query

        ref_date = as_of_date or datetime.now(timezone.utc)

        rows = execute_query(
            "SELECT * FROM policy_registry "
            "WHERE policy_type = %s AND tenant_id = %s "
            "  AND status = %s "
            "  AND effective_from <= %s "
            "  AND (effective_to IS NULL OR effective_to >= %s) "
            "ORDER BY version DESC LIMIT 1",
            (policy_type, tenant_id,
             PolicyStatus.ACTIVATED.value,
             ref_date, ref_date),
            tenant_id=tenant_id,
        )

        if not rows:
            return None

        row = dict(rows[0])
        if isinstance(row.get("parameters"), str):
            row["parameters"] = json.loads(row["parameters"])
        return row

    # ------------------------------------------------------------------
    # LIST POLICIES
    # ------------------------------------------------------------------

    @staticmethod
    def list_policies(
        tenant_id: str,
        policy_type: Optional[str] = None,
        status: Optional[PolicyStatus] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List policies with optional filters."""
        from server.db_service import execute_query

        conditions = ["tenant_id = %s"]
        params: list = [tenant_id]

        if policy_type:
            conditions.append("policy_type = %s")
            params.append(policy_type)
        if status:
            conditions.append("status = %s")
            params.append(status.value)

        where = " AND ".join(conditions)
        params.extend([limit, offset])

        rows = execute_query(
            f"SELECT * FROM policy_registry "
            f"WHERE {where} ORDER BY created_at DESC "
            f"LIMIT %s OFFSET %s",
            tuple(params),
            tenant_id=tenant_id,
        )

        results = []
        for row in rows:
            r = dict(row)
            if isinstance(r.get("parameters"), str):
                r["parameters"] = json.loads(r["parameters"])
            results.append(r)
        return results

    # ------------------------------------------------------------------
    # GET VERSION HISTORY (for diff viewer)
    # ------------------------------------------------------------------

    @staticmethod
    def get_version_history(
        policy_type: str,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Return all versions of a given policy_type, ordered by version
        ascending.  Used by the admin UI diff viewer.
        """
        from server.db_service import execute_query

        rows = execute_query(
            "SELECT id, version, status, parameters, content_hash, "
            "       effective_from, effective_to, created_by, created_at, "
            "       approved_by, approved_at "
            "FROM policy_registry "
            "WHERE policy_type = %s AND tenant_id = %s "
            "ORDER BY version ASC",
            (policy_type, tenant_id),
            tenant_id=tenant_id,
        )

        results = []
        for row in rows:
            r = dict(row)
            if isinstance(r.get("parameters"), str):
                r["parameters"] = json.loads(r["parameters"])
            results.append(r)
        return results


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _on_policy_activated(
    policy_id: str,
    policy_type: str,
    version: int,
    actor_id: str,
    actor_role: str,
    tenant_id: str,
) -> None:
    """
    Handle post-activation side effects:
      1. Supersede any previously activated version of the same type.
      2. Emit PolicyActivated event to the Event Bus.
      3. Log activation to audit ledger.
    """
    from server.db_service import execute_transaction

    # 1. Supersede previous active versions
    execute_transaction(
        [(
            "UPDATE policy_registry "
            "SET status = %s, updated_at = %s "
            "WHERE policy_type = %s AND tenant_id = %s "
            "  AND status = %s AND id != %s",
            (PolicyStatus.SUPERSEDED.value,
             datetime.now(timezone.utc),
             policy_type, tenant_id,
             PolicyStatus.ACTIVATED.value, policy_id),
        )],
        tenant_id=tenant_id,
    )

    # 2. Emit event
    event = Event(
        id=str(uuid4()),
        type="e00.policy.activated",
        source="policy_service",
        payload={
            "policy_id": policy_id,
            "policy_type": policy_type,
            "version": version,
            "tenant_id": tenant_id,
        },
    )
    EventBus.publish(event, actor_id=actor_id)

    # 3. Audit
    AuditLog.log(
        action=AuditAction.POLICY_ACTIVATED,
        actor_id=actor_id,
        actor_role=actor_role,
        entity_type="policy",
        entity_id=policy_id,
        tenant_id=tenant_id,
        metadata={
            "policy_type": policy_type,
            "version": version,
            "event_id": event.id,
        },
    )

    logger.info(
        "Policy activated [id=%s type=%s version=%d tenant=%s]",
        policy_id, policy_type, version, tenant_id,
    )
