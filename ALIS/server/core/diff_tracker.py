"""
ALIS Field-Level Change Tracking — E00-S08

MODULE: Platform Core (E00 — Institutional Security & Governance)
LAYER: Layer 6 (Field-level audit) + Layer 4 (No silent mutation)
ENTITY: FieldDiffEntry

This module implements per-field diff tracking for critical entities
(marks, payroll, fee, transcript).  Previous values are stored encrypted
using the tenant's symmetric key (TenantKeyManager / Fernet).

The diffs are persisted **inside** the existing immutable `audit_ledger`
via the `metadata` JSONB column, inheriting:
  • Hash-chain tamper detection (E00-S02)
  • Append-only immutability (DB triggers block UPDATE/DELETE)
  • Tenant-scoped Row-Level Security

Design Decisions
────────────────
  1. No separate DB table — diffs live in `audit_ledger.metadata` to
     avoid schema sprawl and reuse all existing tamper-detection infra.
  2. Only *changed* fields are recorded (no full-entity snapshots).
  3. Encryption is at the application layer using TenantKeyManager so
     that tenant keys remain cryptographically isolated.
  4. If no tenant key exists, previous values are stored as plaintext
     (encryption is optional per E00-S03).

Must Align With
───────────────
  • Layer 6: Field-level audit
  • Layer 4: No silent mutation
  • E00-S02: Immutable audit ledger
  • E00-S03: Tenant cryptographic isolation

Acceptance Criteria (E00-S08)
─────────────────────────────
  • [x] Diff log per entity
  • [x] Viewable in admin console (via get_decrypted_field_diffs)
  • [x] Tamper detection enabled (hash-chain from AuditLedger)
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from .audit import AuditAction, AuditLedger, AuditEntry
from .tenant_crypto import TenantKeyManager
from .exceptions import DiffTrackingError

logger = logging.getLogger(__name__)


# ============================================================================
# CRITICAL ENTITY REGISTRY
# ============================================================================
# Only entities listed here will have field-level change tracking.
# Maps entity_type -> set of tracked field names.
# If the set is empty, ALL fields are tracked.

TRACKED_ENTITIES: Dict[str, Set[str]] = {
    "marks": {
        "score", "grade", "internal_marks", "external_marks",
        "total_marks", "result_status", "moderation_applied",
    },
    "payroll": {
        "basic_salary", "gross_salary", "net_salary", "deductions",
        "allowances", "lop_days", "payable_days",
    },
    "fee": {
        "fee_amount", "discount", "waiver_pct", "penalty",
        "due_date", "payment_status", "balance",
    },
    "transcript": {
        "sgpa", "cgpa", "credits_earned", "credits_required",
        "result_status", "honours", "remarks",
    },
}


def is_tracked_entity(entity_type: str) -> bool:
    """Check if an entity type is registered for field-level tracking."""
    return entity_type.lower() in TRACKED_ENTITIES


def get_tracked_fields(entity_type: str) -> Set[str]:
    """
    Return the set of tracked fields for an entity type.
    Returns an empty set if the entity is not tracked.
    """
    return TRACKED_ENTITIES.get(entity_type.lower(), set())


# ============================================================================
# FIELD DIFF COMPUTATION
# ============================================================================

def _compute_field_diffs(
    old_data: Dict[str, Any],
    new_data: Dict[str, Any],
    tracked_fields: Optional[Set[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Compare old_data vs new_data and return a dict of changed fields.

    If tracked_fields is provided, only those fields are compared.
    Otherwise, all fields present in either dict are compared.

    Returns:
        {
            "field_name": {
                "old": <old_value>,
                "new": <new_value>,
            },
            ...
        }

    Only fields whose values actually differ are included.
    """
    if tracked_fields:
        fields_to_check = tracked_fields
    else:
        fields_to_check = set(old_data.keys()) | set(new_data.keys())

    diffs: Dict[str, Dict[str, Any]] = {}
    for field in fields_to_check:
        old_val = old_data.get(field)
        new_val = new_data.get(field)
        if old_val != new_val:
            diffs[field] = {"old": old_val, "new": new_val}

    return diffs


# ============================================================================
# ENCRYPTION OF PREVIOUS VALUES
# ============================================================================

def _encrypt_old_value(tenant_id: str, value: Any) -> str:
    """
    Encrypt a previous field value using the tenant's symmetric key.

    The value is JSON-serialised first, then encrypted.  The ciphertext
    is returned as a base64-encoded string for safe JSONB storage.

    If no tenant key is configured, returns the JSON string as-is
    (encryption is optional per E00-S03).
    """
    plaintext = json.dumps(value, default=str).encode("utf-8")
    ciphertext = TenantKeyManager.encrypt_data(tenant_id, plaintext)

    # If encrypt_data returned the same bytes (no key), store raw
    if ciphertext == plaintext:
        return json.dumps(value, default=str)

    return base64.b64encode(ciphertext).decode("ascii")


def _decrypt_old_value(tenant_id: str, encrypted_str: str) -> Any:
    """
    Decrypt a previously encrypted old field value.

    Attempts base64 decode + Fernet decrypt.  If that fails (e.g. the
    value was stored as plaintext because no key was configured), falls
    back to JSON-parsing the raw string.
    """
    try:
        ciphertext = base64.b64decode(encrypted_str)
        plaintext = TenantKeyManager.decrypt_data(tenant_id, ciphertext)
        return json.loads(plaintext.decode("utf-8"))
    except Exception:
        # Fallback: value was stored as plain JSON string
        try:
            return json.loads(encrypted_str)
        except (json.JSONDecodeError, TypeError):
            return encrypted_str


# ============================================================================
# PRIMARY API: COMPUTE AND LOG FIELD DIFFS
# ============================================================================

def compute_and_log_field_diffs(
    tenant_id: str,
    actor_id: str,
    actor_role: str,
    entity_type: str,
    entity_id: str,
    old_data: Dict[str, Any],
    new_data: Dict[str, Any],
    module: Optional[str] = None,
    wizard: Optional[str] = None,
) -> Optional[AuditEntry]:
    """
    Compute per-field diffs between old_data and new_data, encrypt the
    previous values, and log the result to the immutable audit ledger.

    This is the **primary entry point** for E00-S08.

    Args:
        tenant_id:   Tenant context (mandatory).
        actor_id:    The actor performing the mutation.
        actor_role:  Role of the actor (e.g. 'faculty', 'admin').
        entity_type: One of the TRACKED_ENTITIES keys.
        entity_id:   Unique identifier of the entity instance.
        old_data:    Dict of field values BEFORE mutation.
        new_data:    Dict of field values AFTER mutation.
        module:      Optional module name for audit context.
        wizard:      Optional wizard name for audit context.

    Returns:
        AuditEntry if diffs were found and logged, None if no changes.

    Raises:
        DiffTrackingError: If the entity type is not in TRACKED_ENTITIES.
    """
    entity_lower = entity_type.lower()

    if not is_tracked_entity(entity_lower):
        raise DiffTrackingError(
            message=f"Entity type '{entity_type}' is not registered for "
                    f"field-level change tracking.",
            details={
                "entity_type": entity_type,
                "registered_types": list(TRACKED_ENTITIES.keys()),
            }
        )

    tracked_fields = get_tracked_fields(entity_lower)

    # Compute diffs
    diffs = _compute_field_diffs(old_data, new_data, tracked_fields)

    if not diffs:
        logger.debug(
            "No field changes detected for %s:%s — skipping diff log.",
            entity_type, entity_id,
        )
        return None

    # Encrypt previous values
    encrypted_diffs: Dict[str, Dict[str, Any]] = {}
    for field_name, change in diffs.items():
        encrypted_diffs[field_name] = {
            "old_encrypted": _encrypt_old_value(tenant_id, change["old"]),
            "new": change["new"],
        }

    # Build metadata payload
    metadata: Dict[str, Any] = {
        "diff_type": "field_level",
        "field_diffs": encrypted_diffs,
        "fields_changed": list(encrypted_diffs.keys()),
        "change_count": len(encrypted_diffs),
    }
    if module:
        metadata["module"] = module
    if wizard:
        metadata["wizard"] = wizard

    # Log to immutable audit ledger (inherits hash-chain tamper detection)
    entry = AuditLedger.log(
        action=AuditAction.FIELD_CHANGE,
        actor_id=actor_id,
        actor_role=actor_role,
        entity_type=entity_type,
        entity_id=entity_id,
        tenant_id=tenant_id,
        metadata=metadata,
    )

    logger.info(
        "E00-S08: Field-level diff logged for %s:%s — %d field(s) changed "
        "[actor=%s, tenant=%s]",
        entity_type, entity_id, len(encrypted_diffs),
        actor_id, tenant_id,
    )

    return entry


# ============================================================================
# ADMIN CONSOLE: RETRIEVE DECRYPTED FIELD DIFFS
# ============================================================================

def get_decrypted_field_diffs(
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """
    Retrieve field-level diff history for an entity, with previous
    values decrypted on-the-fly for the admin console.

    Only entries with `metadata.diff_type == "field_level"` are returned.
    Each entry includes the decrypted old values alongside the new values.

    Args:
        tenant_id:   Tenant context.
        entity_type: Entity type (e.g. 'marks').
        entity_id:   Entity instance ID.
        limit:       Max entries to return.

    Returns:
        List of dicts, each containing:
            - audit_id
            - actor_id
            - actor_role
            - timestamp
            - hash (for tamper verification)
            - field_diffs: { field_name: { old: <decrypted>, new: <value> } }
    """
    raw_history = AuditLedger.get_entity_history(
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )

    results: List[Dict[str, Any]] = []

    for row in raw_history:
        meta = row.get("metadata")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                continue

        if not isinstance(meta, dict):
            continue

        if meta.get("diff_type") != "field_level":
            continue

        encrypted_diffs = meta.get("field_diffs", {})

        # Decrypt each field's old value
        decrypted_diffs: Dict[str, Dict[str, Any]] = {}
        for field_name, change in encrypted_diffs.items():
            decrypted_diffs[field_name] = {
                "old": _decrypt_old_value(
                    tenant_id, change.get("old_encrypted", "")
                ),
                "new": change.get("new"),
            }

        results.append({
            "audit_id": row.get("id"),
            "actor_id": row.get("actor_id"),
            "actor_role": row.get("actor_role"),
            "timestamp": row.get("timestamp"),
            "hash": row.get("hash"),
            "fields_changed": meta.get("fields_changed", []),
            "change_count": meta.get("change_count", 0),
            "field_diffs": decrypted_diffs,
        })

    return results
