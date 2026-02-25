"""
ALIS Immutable Audit Ledger — E00-S02

MODULE: Platform Core (E00 — Institutional Security & Governance)
LAYER: Layer 6 (System Logbook) + Layer 4 (Lock After Commit)
ENTITY: AuditEntry

This module implements a tamper-evident, append-only audit ledger with
cryptographic hash chaining.  Every critical operation in ALIS is recorded
here.  The ledger is persisted to the `audit_ledger` PostgreSQL table whose
immutability is enforced at the database level (triggers block UPDATE /
DELETE / TRUNCATE).

Hash Chain Design
─────────────────
  hash_n = SHA-256( previous_hash ‖ canonical_payload_json )

  • `previous_hash` is NULL for the genesis entry of each tenant.
  • `canonical_payload_json` is a deterministic JSON serialisation
    (sorted keys, no whitespace) of all non-hash fields.
  • The chain is scoped **per tenant** so that tenants can verify their
    own ledger independently without cross-tenant exposure.

Concurrency
───────────
  Inserts acquire an advisory lock keyed on `tenant_id` so that two
  concurrent writers for the same tenant are serialised.  This prevents
  hash-chain forks while keeping cross-tenant writes fully parallel.

Must Align With
───────────────
  • Layer 6 — System logbook (every critical operation logged)
  • Layer 4 — Lock after commit (append-only, no mutation)
  • E00 Hard Constraint: All state mutations must be audit-logged

Acceptance Criteria
───────────────────
  • [x] Actor, role, action, entity, timestamp, hash
  • [x] Hash chain verification endpoint
  • [x] Admin export capability
  • [x] No UPDATE / DELETE on audit table (DB-enforced)
"""

import hashlib
import json
import logging
import csv
import io
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# AUDIT ACTION TYPES
# ============================================================================

class AuditAction(str, Enum):
    """Types of auditable actions."""
    # Entity CRUD
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"  # Soft delete

    # State Changes
    STATE_TRANSITION = "state_transition"
    EVENT_PUBLISHED = "event_published"

    # Access
    LOGIN = "login"
    LOGOUT = "logout"
    ACCESS_DENIED = "access_denied"

    # Overrides
    OVERRIDE_REQUESTED = "override_requested"
    OVERRIDE_APPROVED = "override_approved"
    OVERRIDE_REJECTED = "override_rejected"
    OVERRIDE_EXECUTED = "override_executed"

    # AI Agent
    AGENT_DECISION = "agent_decision"
    AGENT_TOOL_CALL = "agent_tool_call"

    # AI Gateway (E03-S01)
    AI_INVOCATION = "ai_invocation"

    # System
    CONFIG_CHANGE = "config_change"
    LOCK_TRIGGERED = "lock_triggered"
    LOCK_CLEARED = "lock_cleared"

    # Escalation & Dual Control (E00-S04)
    ESCALATION_REQUESTED = "escalation_requested"
    ESCALATION_GRANTED = "escalation_granted"
    ESCALATION_DENIED = "escalation_denied"
    ESCALATION_EXPIRED = "escalation_expired"
    ESCALATION_REVOKED = "escalation_revoked"
    ESCALATION_USED = "escalation_used"
    DUAL_CONTROL_REQUESTED = "dual_control_requested"
    DUAL_CONTROL_COMPLETED = "dual_control_completed"

    # Incident Response & Lockdown (E00-S05)
    LOCKDOWN_ACTIVATED = "lockdown_activated"
    LOCKDOWN_DEACTIVATED = "lockdown_deactivated"
    LOCKDOWN_WRITE_BLOCKED = "lockdown_write_blocked"
    LOCKDOWN_AI_BLOCKED = "lockdown_ai_blocked"

    # Data Classification (E00-S01)
    DATA_CLASSIFIED = "data_classified"
    SENSITIVITY_CHANGED = "sensitivity_changed"
    SENSITIVE_ACCESS = "sensitive_access"


# ============================================================================
# AUDIT ENTRY (immutable value object)
# ============================================================================

@dataclass(frozen=True)
class AuditEntry:
    """
    Immutable audit log entry.

    Uses frozen=True to ensure immutability after creation.
    Fields mirror the `audit_ledger` DB table.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    tenant_id: str = ""
    actor_id: str = ""
    actor_role: str = ""
    action: str = ""
    entity_type: str = ""
    entity_id: str = ""
    metadata: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    previous_hash: Optional[str] = None
    hash: str = ""


# ============================================================================
# HASH COMPUTATION
# ============================================================================

def _canonical_payload(entry_data: Dict[str, Any]) -> str:
    """
    Produce a deterministic JSON string for hashing.

    Keys are sorted, no extra whitespace, datetimes are ISO-formatted.
    This ensures the same logical entry always produces the same hash
    regardless of dict insertion order.
    """
    def _default(obj: Any) -> str:
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Non-serialisable type: {type(obj)}")

    return json.dumps(entry_data, sort_keys=True, separators=(",", ":"),
                      default=_default)


def compute_entry_hash(
    previous_hash: Optional[str],
    tenant_id: str,
    actor_id: str,
    actor_role: str,
    action: str,
    entity_type: str,
    entity_id: str,
    timestamp: datetime,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Compute SHA-256 hash for a new ledger entry.

    hash = SHA256( previous_hash + canonical_json(payload) )
    """
    payload = {
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "actor_role": actor_role,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "timestamp": timestamp,
        "metadata": metadata,
    }
    canonical = _canonical_payload(payload)
    preimage = (previous_hash or "") + canonical
    return hashlib.sha256(preimage.encode("utf-8")).hexdigest()


# ============================================================================
# ADVISORY LOCK HELPER
# ============================================================================

def _tenant_lock_key(tenant_id: str) -> int:
    """
    Derive a stable int64 advisory-lock key from a tenant_id string.
    We use a CRC-style approach via hash to keep it deterministic.
    """
    # Use first 8 bytes of SHA-256 interpreted as signed int64
    digest = hashlib.sha256(tenant_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


# ============================================================================
# AUDIT LEDGER SERVICE
# ============================================================================

class AuditLedger:
    """
    Append-only, hash-chained audit ledger backed by PostgreSQL.

    All writes go through `log()` which:
      1. Acquires a per-tenant advisory lock (serialises concurrent inserts).
      2. Fetches the latest hash for the tenant.
      3. Computes the new hash.
      4. Inserts the new row.

    The DB triggers prevent any UPDATE / DELETE / TRUNCATE on the table.
    """

    # ------------------------------------------------------------------
    # Primary logging method
    # ------------------------------------------------------------------

    @staticmethod
    def log(
        action: AuditAction,
        actor_id: str,
        actor_role: Optional[str] = None,
        entity_type: str = "",
        entity_id: str = "",
        tenant_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        # --- Backward-compatible kwargs from old AuditLog API ---
        actor_type: Optional[str] = None,
        action_detail: Optional[str] = None,
        success: bool = True,
        failure_reason: Optional[str] = None,
        org_id: Optional[str] = None,
        module: Optional[str] = None,
        wizard: Optional[str] = None,
        previous_state: Optional[str] = None,
        new_state: Optional[str] = None,
        **extra_kwargs: Any,
    ) -> AuditEntry:
        """
        Append a new entry to the immutable audit ledger.

        This method is backward-compatible with the old ``AuditLog.log()``
        API.  Legacy keyword arguments (``actor_type``, ``action_detail``,
        ``success``, ``failure_reason``, ``org_id``, ``module``, ``wizard``,
        ``previous_state``, ``new_state``) are folded into the ``metadata``
        JSONB column so that no information is lost.

        ``tenant_id`` is resolved in this priority:
          1. Explicit parameter.
          2. Request-scoped ContextVar (set by TenantMiddleware).
          3. Falls back to ``"SYSTEM"`` for system-level operations.

        ``actor_role`` falls back to ``actor_type`` if not provided
        (old callers used ``actor_type`` instead of ``actor_role``).
        """
        from server.db_service import get_db_connection
        try:
            from psycopg2.extras import RealDictCursor
        except ImportError:
            # Graceful degradation if psycopg2 is unavailable
            logger.warning("psycopg2 unavailable — audit entry NOT persisted.")
            return AuditEntry()

        # --- Resolve actor_role (backward compat) ---
        resolved_role = actor_role or actor_type or "unknown"

        # --- Resolve tenant_id ---
        resolved_tenant = tenant_id or org_id
        if not resolved_tenant:
            try:
                from server.core.security import get_current_tenant_id
                resolved_tenant = get_current_tenant_id()
            except Exception:
                resolved_tenant = "SYSTEM"

        # --- Merge legacy fields into metadata ---
        merged_meta: Dict[str, Any] = dict(metadata or {})
        if actor_type:
            merged_meta["actor_type"] = actor_type
        if action_detail:
            merged_meta["action_detail"] = action_detail
        if not success:
            merged_meta["success"] = False
        if failure_reason:
            merged_meta["failure_reason"] = failure_reason
        if org_id:
            merged_meta["org_id"] = org_id
        if module:
            merged_meta["module"] = module
        if wizard:
            merged_meta["wizard"] = wizard
        if previous_state:
            merged_meta["previous_state"] = previous_state
        if new_state:
            merged_meta["new_state"] = new_state
        if extra_kwargs:
            merged_meta.update(extra_kwargs)

        now = datetime.now(timezone.utc)
        lock_key = _tenant_lock_key(resolved_tenant)
        action_str = action.value if isinstance(action, AuditAction) else str(action)

        with get_db_connection() as conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. Acquire per-tenant advisory lock (released at
                    #    transaction end).  This serialises hash-chain
                    #    writes for a single tenant while leaving other
                    #    tenants fully concurrent.
                    cur.execute(
                        "SELECT pg_advisory_xact_lock(%s)", (lock_key,)
                    )

                    # 2. Fetch previous hash (latest entry for this tenant)
                    cur.execute(
                        "SELECT hash FROM audit_ledger "
                        "WHERE tenant_id = %s "
                        "ORDER BY id DESC LIMIT 1",
                        (resolved_tenant,),
                    )
                    row = cur.fetchone()
                    previous_hash = row["hash"] if row else None

                    # 3. Compute new hash
                    entry_hash = compute_entry_hash(
                        previous_hash=previous_hash,
                        tenant_id=resolved_tenant,
                        actor_id=actor_id,
                        actor_role=resolved_role,
                        action=action_str,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        timestamp=now,
                        metadata=merged_meta or None,
                    )

                    # 4. Insert
                    cur.execute(
                        """
                        INSERT INTO audit_ledger
                            (tenant_id, actor_id, actor_role, action,
                             entity_type, entity_id, metadata,
                             timestamp, previous_hash, hash)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            resolved_tenant,
                            actor_id,
                            resolved_role,
                            action_str,
                            entity_type,
                            entity_id,
                            json.dumps(merged_meta) if merged_meta else None,
                            now,
                            previous_hash,
                            entry_hash,
                        ),
                    )
                    inserted_id = cur.fetchone()["id"]

                conn.commit()

                entry = AuditEntry(
                    id=str(inserted_id),
                    tenant_id=resolved_tenant,
                    actor_id=actor_id,
                    actor_role=resolved_role,
                    action=action_str,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    metadata=merged_meta or None,
                    timestamp=now,
                    previous_hash=previous_hash,
                    hash=entry_hash,
                )
                logger.info(
                    "Audit ledger entry %s recorded "
                    "[tenant=%s actor=%s action=%s entity=%s:%s]",
                    inserted_id, resolved_tenant, actor_id, action,
                    entity_type, entity_id,
                )
                return entry

            except Exception:
                conn.rollback()
                logger.exception("Failed to write to audit ledger")
                raise


    # ------------------------------------------------------------------
    # Convenience helpers (delegate to log())
    # ------------------------------------------------------------------

    @classmethod
    def log_state_transition(
        cls,
        actor_id: str,
        actor_role: str,
        entity_type: str,
        entity_id: str,
        tenant_id: str,
        previous_state: str,
        new_state: str,
        **kwargs: Any,
    ) -> AuditEntry:
        """Convenience: log a state transition with states in metadata."""
        meta = kwargs.pop("metadata", {}) or {}
        meta.update({
            "previous_state": previous_state,
            "new_state": new_state,
        })
        return cls.log(
            action=AuditAction.STATE_TRANSITION,
            actor_id=actor_id,
            actor_role=actor_role,
            entity_type=entity_type,
            entity_id=entity_id,
            tenant_id=tenant_id,
            metadata=meta,
        )

    @classmethod
    def log_agent_decision(
        cls,
        agent_id: str,
        entity_type: str,
        entity_id: str,
        tenant_id: str,
        decision: str,
        confidence: float,
        **kwargs: Any,
    ) -> AuditEntry:
        """Log an AI agent decision."""
        meta = kwargs.pop("metadata", {}) or {}
        meta.update({
            "decision": decision,
            "confidence": confidence,
        })
        return cls.log(
            action=AuditAction.AGENT_DECISION,
            actor_id=agent_id,
            actor_role="ai_agent",
            entity_type=entity_type,
            entity_id=entity_id,
            tenant_id=tenant_id,
            metadata=meta,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @staticmethod
    def query(
        tenant_id: str,
        actor_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Query audit ledger entries for a tenant.

        All filters are ANDed together.  Results are ordered by id DESC
        (newest first).
        """
        from server.db_service import execute_query

        conditions = ["tenant_id = %s"]
        params: list = [tenant_id]

        if actor_id:
            conditions.append("actor_id = %s")
            params.append(actor_id)
        if entity_type:
            conditions.append("entity_type = %s")
            params.append(entity_type)
        if entity_id:
            conditions.append("entity_id = %s")
            params.append(entity_id)
        if action:
            conditions.append("action = %s")
            params.append(action.value if isinstance(action, AuditAction) else str(action))
        if start_time:
            conditions.append("timestamp >= %s")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= %s")
            params.append(end_time)

        where_clause = " AND ".join(conditions)
        params.extend([limit, offset])

        sql = (
            f"SELECT * FROM audit_ledger "
            f"WHERE {where_clause} "
            f"ORDER BY id DESC "
            f"LIMIT %s OFFSET %s"
        )
        return execute_query(sql, tuple(params), tenant_id=tenant_id)

    @classmethod
    def get_entity_history(
        cls,
        tenant_id: str,
        entity_type: str,
        entity_id: str,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Get full audit history for a specific entity."""
        return cls.query(
            tenant_id=tenant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )

    # ------------------------------------------------------------------
    # Hash Chain Verification  (E00-S02 Acceptance Criterion)
    # ------------------------------------------------------------------

    @staticmethod
    def verify_chain_integrity(tenant_id: str) -> Dict[str, Any]:
        """
        Walk the entire hash chain for a tenant and verify every link.

        Returns a dict:
            {
                "valid": bool,
                "total_entries": int,
                "first_invalid_id": Optional[int],
                "message": str,
            }

        This uses execute_system_query (bypasses RLS) so that the
        verification service can read without requiring a tenant session
        variable — useful for background integrity checks.
        """
        from server.db_service import execute_system_query

        rows = execute_system_query(
            "SELECT id, tenant_id, actor_id, actor_role, action, "
            "       entity_type, entity_id, metadata, timestamp, "
            "       previous_hash, hash "
            "FROM audit_ledger "
            "WHERE tenant_id = %s "
            "ORDER BY id ASC",
            (tenant_id,),
        )

        if not rows:
            return {
                "valid": True,
                "total_entries": 0,
                "first_invalid_id": None,
                "message": "Ledger is empty for this tenant.",
            }

        expected_previous_hash: Optional[str] = None

        for row in rows:
            # Verify previous_hash linkage
            if row["previous_hash"] != expected_previous_hash:
                return {
                    "valid": False,
                    "total_entries": len(rows),
                    "first_invalid_id": row["id"],
                    "message": (
                        f"Chain break at entry {row['id']}: "
                        f"expected previous_hash={expected_previous_hash!r}, "
                        f"got {row['previous_hash']!r}."
                    ),
                }

            # Recompute hash and compare
            ts = row["timestamp"]
            meta = row["metadata"]
            if isinstance(meta, str):
                meta = json.loads(meta)

            recomputed = compute_entry_hash(
                previous_hash=row["previous_hash"],
                tenant_id=row["tenant_id"],
                actor_id=row["actor_id"],
                actor_role=row["actor_role"],
                action=row["action"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                timestamp=ts,
                metadata=meta,
            )

            if recomputed != row["hash"]:
                return {
                    "valid": False,
                    "total_entries": len(rows),
                    "first_invalid_id": row["id"],
                    "message": (
                        f"Hash mismatch at entry {row['id']}: "
                        f"expected={recomputed!r}, stored={row['hash']!r}."
                    ),
                }

            expected_previous_hash = row["hash"]

        return {
            "valid": True,
            "total_entries": len(rows),
            "first_invalid_id": None,
            "message": f"All {len(rows)} entries verified successfully.",
        }

    # ------------------------------------------------------------------
    # Admin Export  (E00-S02 Acceptance Criterion)
    # ------------------------------------------------------------------

    @staticmethod
    def export_ledger(
        tenant_id: str,
        fmt: str = "json",
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> str:
        """
        Export the audit ledger for a tenant as a string.

        Args:
            tenant_id:   Tenant to export.
            fmt:         "json" or "csv".
            start_time:  Optional lower-bound filter.
            end_time:    Optional upper-bound filter.

        Returns:
            A string containing the full export.
        """
        from server.db_service import execute_system_query

        conditions = ["tenant_id = %s"]
        params: list = [tenant_id]

        if start_time:
            conditions.append("timestamp >= %s")
            params.append(start_time)
        if end_time:
            conditions.append("timestamp <= %s")
            params.append(end_time)

        where_clause = " AND ".join(conditions)

        rows = execute_system_query(
            f"SELECT id, tenant_id, actor_id, actor_role, action, "
            f"       entity_type, entity_id, metadata, timestamp, "
            f"       previous_hash, hash "
            f"FROM audit_ledger "
            f"WHERE {where_clause} "
            f"ORDER BY id ASC",
            tuple(params),
        )

        if fmt == "csv":
            return _rows_to_csv(rows)

        # Default: JSON
        return _rows_to_json(rows)


# ============================================================================
# EXPORT HELPERS
# ============================================================================

_EXPORT_COLUMNS = [
    "id", "tenant_id", "actor_id", "actor_role", "action",
    "entity_type", "entity_id", "metadata", "timestamp",
    "previous_hash", "hash",
]


def _rows_to_json(rows: List[Dict[str, Any]]) -> str:
    """Serialise rows to a JSON string."""
    def _default(obj: Any) -> str:
        if isinstance(obj, datetime):
            return obj.isoformat()
        return str(obj)
    return json.dumps(rows, indent=2, default=_default)


def _rows_to_csv(rows: List[Dict[str, Any]]) -> str:
    """Serialise rows to a CSV string."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_EXPORT_COLUMNS)
    writer.writeheader()
    for row in rows:
        # Flatten metadata to JSON string for CSV cell
        r = dict(row)
        if isinstance(r.get("metadata"), dict):
            r["metadata"] = json.dumps(r["metadata"])
        if isinstance(r.get("timestamp"), datetime):
            r["timestamp"] = r["timestamp"].isoformat()
        writer.writerow(r)
    return output.getvalue()


# ============================================================================
# BACKWARD-COMPATIBILITY ALIAS
# ============================================================================
# Other modules may import `AuditLog` from the old API.  This alias
# ensures they continue to work while pointing at the new ledger.
AuditLog = AuditLedger
