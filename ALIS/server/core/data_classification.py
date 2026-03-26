"""
ALIS Data Classification & Sensitivity Model - E00-S01

MODULE: Platform Core (E00 - Security & Governance)
LAYER: Layer 1 (Entity Metadata Extension) + Layer 4 (Field-Level Masking)
ENTITY: SensitivityLevel, RegulatedDataType, FieldClassification

This module defines the mandatory data sensitivity classification framework
for all ALIS entities. Every stored data element must carry a sensitivity
tag that governs encryption, masking, and retention behavior.

Must Align With:
    - Layer 1: Entity metadata extension (sensitivity tags on all models)
    - Layer 4: Field-level masking (invariant — sensitive data never exposed raw)
    - Layer 6: Access log capture (all sensitive access audited)

Data Categories:
    PUBLIC      — Freely shareable (e.g., course catalog, public notices)
    INTERNAL    — Institutional use only (e.g., internal reports, task metadata)
    CONFIDENTIAL — Protected data requiring encryption (e.g., emails, names)
    REGULATED   — Legally protected data (PII, Finance, Biometric, Transcript)

Acceptance Criteria (E00-S01):
    - [x] All models tagged with sensitivity level
    - [x] Encrypted-at-rest for CONFIDENTIAL and REGULATED
    - [x] Masking in logs and AI context
"""
from __future__ import annotations

import re
import logging
from enum import Enum
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# =============================================================================
# SENSITIVITY ENUMS
# =============================================================================

class SensitivityLevel(str, Enum):
    """
    Data sensitivity classification levels.

    Ordered from least to most sensitive.
    Higher levels inherit all protections of lower levels.

        PUBLIC < INTERNAL < CONFIDENTIAL < REGULATED
    """
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    REGULATED = "REGULATED"


# Ordering for comparison
_SENSITIVITY_ORDER: Dict[SensitivityLevel, int] = {
    SensitivityLevel.PUBLIC: 0,
    SensitivityLevel.INTERNAL: 1,
    SensitivityLevel.CONFIDENTIAL: 2,
    SensitivityLevel.REGULATED: 3,
}


def sensitivity_gte(a: SensitivityLevel, b: SensitivityLevel) -> bool:
    """Check if sensitivity level `a` is greater than or equal to `b`."""
    return _SENSITIVITY_ORDER[a] >= _SENSITIVITY_ORDER[b]


class RegulatedDataType(str, Enum):
    """
    Sub-categories for REGULATED data, per compliance requirements.

    NONE is used for non-regulated entities or fields.
    """
    NONE = "NONE"
    PII = "PII"               # Personally Identifiable Information
    FINANCE = "FINANCE"       # Financial records (fees, payments, salary)
    BIOMETRIC = "BIOMETRIC"   # Biometric logs (attendance, facial recognition)
    TRANSCRIPT = "TRANSCRIPT" # Academic transcripts and grade records


class RetentionClass(str, Enum):
    """
    Data retention classification — E00-S07.

    Defines how long a data class must be retained before archival
    or legal deletion is permitted.

        TEMPORARY   — Short-lived operational data (e.g., session tokens)
        STANDARD    — Normal institutional data (e.g., attendance logs)
        LONG_TERM   — Extended retention (e.g., biometric logs)
        PERMANENT   — Never deleted (e.g., transcripts, audit records)
    """
    TEMPORARY = "TEMPORARY"
    STANDARD = "STANDARD"
    LONG_TERM = "LONG_TERM"
    PERMANENT = "PERMANENT"


# Default retention periods in days (None = permanent / no auto-archival)
_DEFAULT_RETENTION_DAYS: Dict[RetentionClass, Optional[int]] = {
    RetentionClass.TEMPORARY: 90,       # 3 months
    RetentionClass.STANDARD: 1825,      # 5 years
    RetentionClass.LONG_TERM: 730,      # 2 years (biometric default)
    RetentionClass.PERMANENT: None,     # Never
}


# =============================================================================
# FIELD-LEVEL CLASSIFICATION
# =============================================================================

@dataclass
class FieldClassification:
    """
    Classification metadata for a single field within an entity.

    Attributes:
        field_name:      Name of the field (e.g., "email", "phone")
        sensitivity:     Sensitivity level of this specific field
        regulated_type:  Regulated sub-category (NONE if not regulated)
        mask_in_logs:    Whether to mask in audit/application logs
        mask_in_ai:      Whether to mask before sending to AI context
        mask_pattern:    Optional custom mask pattern ('partial', 'full', 'hash')
    """
    field_name: str
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    regulated_type: RegulatedDataType = RegulatedDataType.NONE
    mask_in_logs: bool = False
    mask_in_ai: bool = False
    mask_pattern: str = "partial"  # "partial", "full", "hash"


@dataclass
class EntityClassification:
    """
    Classification profile for an entity type.

    Captures the default sensitivity for the entity as a whole,
    plus per-field overrides for fields that differ from the default.

    E00-S07 additions:
        retention_class:  Lifecycle classification for archival
        retention_days:   Override for auto-archival period (None = use class default)
    """
    entity_type: str
    default_sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    default_regulated_type: RegulatedDataType = RegulatedDataType.NONE
    field_overrides: Dict[str, FieldClassification] = field(default_factory=dict)
    description: str = ""

    # E00-S07: Data Retention Metadata (Layer 1)
    retention_class: RetentionClass = RetentionClass.STANDARD
    retention_days: Optional[int] = None  # None = use _DEFAULT_RETENTION_DAYS

    @property
    def effective_retention_days(self) -> Optional[int]:
        """Return explicit override or class-level default. None = permanent."""
        if self.retention_days is not None:
            return self.retention_days
        return _DEFAULT_RETENTION_DAYS.get(self.retention_class)

    @property
    def is_permanent(self) -> bool:
        """True if this entity class must never be auto-archived or deleted."""
        return self.effective_retention_days is None


# =============================================================================
# ENTITY CLASSIFICATION REGISTRY
# =============================================================================

class EntityClassificationRegistry:
    """
    Central registry mapping entity types to their classification profiles.

    All entity types in ALIS must be registered here. This is the single
    source of truth for what sensitivity level applies to each entity and
    which fields require masking.

    Usage:
        # Register
        EntityClassificationRegistry.register(EntityClassification(
            entity_type="user",
            default_sensitivity=SensitivityLevel.CONFIDENTIAL,
            ...
        ))

        # Query
        classification = EntityClassificationRegistry.get("user")
    """

    _registry: Dict[str, EntityClassification] = {}

    @classmethod
    def register(cls, classification: EntityClassification) -> None:
        """Register an entity classification profile."""
        cls._registry[classification.entity_type] = classification
        logger.debug(
            "Registered classification for '%s': %s",
            classification.entity_type,
            classification.default_sensitivity.value,
        )

    @classmethod
    def get(cls, entity_type: str) -> Optional[EntityClassification]:
        """Get the classification profile for an entity type."""
        return cls._registry.get(entity_type)

    @classmethod
    def get_or_default(cls, entity_type: str) -> EntityClassification:
        """
        Get classification for an entity type, or return a conservative default.

        Default is INTERNAL sensitivity (fail-safe: don't expose unclassified data).
        """
        return cls._registry.get(entity_type, EntityClassification(
            entity_type=entity_type,
            default_sensitivity=SensitivityLevel.INTERNAL,
            description="Unregistered entity — defaulting to INTERNAL",
        ))

    @classmethod
    def get_field_classification(
        cls,
        entity_type: str,
        field_name: str,
    ) -> FieldClassification:
        """
        Get classification for a specific field within an entity.

        If the field has no explicit override, returns a FieldClassification
        with the entity's default sensitivity.
        """
        ec = cls.get_or_default(entity_type)
        if field_name in ec.field_overrides:
            return ec.field_overrides[field_name]
        return FieldClassification(
            field_name=field_name,
            sensitivity=ec.default_sensitivity,
            regulated_type=ec.default_regulated_type,
        )

    @classmethod
    def list_registered(cls) -> List[str]:
        """List all registered entity types."""
        return list(cls._registry.keys())

    @classmethod
    def _reset(cls) -> None:
        """Reset registry. FOR TESTING ONLY."""
        cls._registry = {}


# =============================================================================
# DATA MASKER
# =============================================================================

class DataMasker:
    """
    Utility class for field-level data masking.

    Provides context-appropriate masking for:
    - Audit logs (mask_for_log)
    - AI prompts (mask_for_ai_context) — most aggressive
    - API responses (mask_value)

    Layer 4 invariant: Sensitive data must NEVER appear in raw form
    in logs or AI context.
    """

    # --- Core Masking Functions ---

    @staticmethod
    def mask_email(email: str) -> str:
        """Mask an email address, preserving structure for debugging."""
        if not email or "@" not in email:
            return "***"
        local, domain = email.rsplit("@", 1)
        if len(local) <= 2:
            masked_local = "*" * len(local)
        else:
            masked_local = local[0] + "*" * (len(local) - 2) + local[-1]
        domain_parts = domain.split(".")
        masked_domain = "*" * len(domain_parts[0]) + "." + ".".join(domain_parts[1:])
        return f"{masked_local}@{masked_domain}"

    @staticmethod
    def mask_phone(phone: str) -> str:
        """Mask a phone number, keeping last 4 digits."""
        digits = re.sub(r'\D', '', phone)
        if len(digits) <= 4:
            return "***"
        return "*" * (len(digits) - 4) + digits[-4:]

    @staticmethod
    def mask_name(name: str) -> str:
        """Mask a person's name, keeping first initial."""
        if not name:
            return "***"
        parts = name.split()
        masked = []
        for part in parts:
            if len(part) <= 1:
                masked.append("*")
            else:
                masked.append(part[0] + "*" * (len(part) - 1))
        return " ".join(masked)

    @staticmethod
    def mask_generic(value: str, keep_chars: int = 2) -> str:
        """Generic partial masking — keep first N characters."""
        if not value:
            return "***"
        s = str(value)
        if len(s) <= keep_chars:
            return "*" * len(s)
        return s[:keep_chars] + "*" * (len(s) - keep_chars)

    @staticmethod
    def mask_full(value: str) -> str:
        """Full masking — replace entire value."""
        return "[REDACTED]"

    # --- Field-Aware Masking ---

    @classmethod
    def mask_value(
        cls,
        field_name: str,
        value: Any,
        sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL,
    ) -> Any:
        """
        Mask a single field value based on its name and sensitivity.

        Args:
            field_name:   Name of the field (used to infer masking strategy)
            value:        The value to mask
            sensitivity:  Sensitivity level of the field

        Returns:
            Masked value, or original if PUBLIC
        """
        if value is None:
            return None

        # PUBLIC data is never masked
        if sensitivity == SensitivityLevel.PUBLIC:
            return value

        str_value = str(value)

        # Apply type-specific masking based on field name
        field_lower = field_name.lower()

        if "email" in field_lower:
            return cls.mask_email(str_value)
        elif "phone" in field_lower or "mobile" in field_lower:
            return cls.mask_phone(str_value)
        elif any(n in field_lower for n in ["name", "display_name", "full_name"]):
            return cls.mask_name(str_value)
        elif any(s in field_lower for s in [
            "password", "secret", "token", "key", "biometric"
        ]):
            return cls.mask_full(str_value)
        elif sensitivity == SensitivityLevel.REGULATED:
            return cls.mask_generic(str_value, keep_chars=2)
        elif sensitivity == SensitivityLevel.CONFIDENTIAL:
            return cls.mask_generic(str_value, keep_chars=3)
        else:
            # INTERNAL — light masking
            return cls.mask_generic(str_value, keep_chars=4)

    @classmethod
    def mask_dict(
        cls,
        data: Dict[str, Any],
        entity_type: str,
    ) -> Dict[str, Any]:
        """
        Mask all classified fields in a dictionary.

        Uses the EntityClassificationRegistry to determine which fields
        need masking and at what level.

        Args:
            data:         Dictionary of field_name → value
            entity_type:  Entity type for registry lookup

        Returns:
            New dictionary with sensitive fields masked
        """
        ec = EntityClassificationRegistry.get_or_default(entity_type)
        result = {}

        for key, value in data.items():
            fc = ec.field_overrides.get(key)
            if fc and (fc.mask_in_logs or fc.mask_in_ai):
                result[key] = cls.mask_value(key, value, fc.sensitivity)
            elif sensitivity_gte(ec.default_sensitivity, SensitivityLevel.CONFIDENTIAL):
                # Entity-level is CONFIDENTIAL+ → mask all string values
                if isinstance(value, str):
                    result[key] = cls.mask_value(key, value, ec.default_sensitivity)
                else:
                    result[key] = value
            else:
                result[key] = value

        return result

    @classmethod
    def mask_for_ai_context(
        cls,
        data: Dict[str, Any],
        entity_type: str,
    ) -> Dict[str, Any]:
        """
        Aggressively mask data before sending to AI context.

        ALL fields marked mask_in_ai are fully redacted.
        ALL CONFIDENTIAL+ string fields are masked.
        IDs and non-sensitive metadata are preserved.

        Args:
            data:         Dictionary of field_name → value
            entity_type:  Entity type for registry lookup

        Returns:
            New dictionary safe for AI consumption
        """
        ec = EntityClassificationRegistry.get_or_default(entity_type)
        result = {}

        # Fields that are safe to pass through to AI regardless
        safe_fields: Set[str] = {"id", "status", "entity_type", "org_id", "created_at",
                                  "updated_at", "actor_type", "sensitivity_level"}

        for key, value in data.items():
            if key in safe_fields:
                result[key] = value
                continue

            fc = ec.field_overrides.get(key)

            if fc and fc.mask_in_ai:
                result[key] = cls.mask_full(str(value)) if value is not None else None
            elif fc and sensitivity_gte(fc.sensitivity, SensitivityLevel.CONFIDENTIAL):
                result[key] = cls.mask_value(key, value, fc.sensitivity)
            elif sensitivity_gte(ec.default_sensitivity, SensitivityLevel.CONFIDENTIAL):
                if isinstance(value, str):
                    result[key] = cls.mask_value(key, value, ec.default_sensitivity)
                else:
                    result[key] = value
            else:
                result[key] = value

        return result

    @classmethod
    def mask_for_log(
        cls,
        data: Dict[str, Any],
        entity_type: str,
    ) -> Dict[str, Any]:
        """
        Mask data for audit/application log output.

        Fields with mask_in_logs=True are masked.
        REGULATED fields are always masked in logs.

        Args:
            data:         Dictionary of field_name → value
            entity_type:  Entity type for registry lookup

        Returns:
            New dictionary safe for logging
        """
        ec = EntityClassificationRegistry.get_or_default(entity_type)
        result = {}

        for key, value in data.items():
            fc = ec.field_overrides.get(key)

            if fc and fc.mask_in_logs:
                result[key] = cls.mask_value(key, value, fc.sensitivity)
            elif fc and fc.sensitivity == SensitivityLevel.REGULATED:
                result[key] = cls.mask_value(key, value, SensitivityLevel.REGULATED)
            else:
                result[key] = value

        return result


# =============================================================================
# ENCRYPTION HELPERS
# =============================================================================

def encryption_required(sensitivity: SensitivityLevel) -> bool:
    """
    Determine if a sensitivity level requires encryption-at-rest.

    CONFIDENTIAL and REGULATED data MUST be encrypted.

    Args:
        sensitivity: The sensitivity level to check

    Returns:
        True if encryption is required
    """
    return sensitivity in (SensitivityLevel.CONFIDENTIAL, SensitivityLevel.REGULATED)


# =============================================================================
# DEFAULT REGISTRATIONS
# =============================================================================

def initialize_default_classifications() -> None:
    """
    Register default classifications for all known ALIS entities.

    Called during application startup. Modules may register additional
    entity types as they initialize.
    """

    # --- User (E01-S01) ---
    EntityClassificationRegistry.register(EntityClassification(
        entity_type="user",
        default_sensitivity=SensitivityLevel.CONFIDENTIAL,
        default_regulated_type=RegulatedDataType.PII,
        description="User identity — contains PII (name, email)",
        retention_class=RetentionClass.STANDARD,   # E00-S07: PII — 5 years
        field_overrides={
            "id": FieldClassification(
                field_name="id",
                sensitivity=SensitivityLevel.INTERNAL,
            ),
            "username": FieldClassification(
                field_name="username",
                sensitivity=SensitivityLevel.CONFIDENTIAL,
                regulated_type=RegulatedDataType.PII,
                mask_in_logs=True,
                mask_in_ai=True,
            ),
            "email": FieldClassification(
                field_name="email",
                sensitivity=SensitivityLevel.REGULATED,
                regulated_type=RegulatedDataType.PII,
                mask_in_logs=True,
                mask_in_ai=True,
            ),
            "display_name": FieldClassification(
                field_name="display_name",
                sensitivity=SensitivityLevel.CONFIDENTIAL,
                regulated_type=RegulatedDataType.PII,
                mask_in_logs=True,
                mask_in_ai=True,
            ),
            "status": FieldClassification(
                field_name="status",
                sensitivity=SensitivityLevel.INTERNAL,
            ),
            "org_id": FieldClassification(
                field_name="org_id",
                sensitivity=SensitivityLevel.INTERNAL,
            ),
            "actor_type": FieldClassification(
                field_name="actor_type",
                sensitivity=SensitivityLevel.PUBLIC,
            ),
        },
    ))

    # --- Organization (E01-S05) ---
    EntityClassificationRegistry.register(EntityClassification(
        entity_type="organization",
        default_sensitivity=SensitivityLevel.INTERNAL,
        description="Institutional entity — generally non-sensitive",
        field_overrides={
            "name": FieldClassification(
                field_name="name",
                sensitivity=SensitivityLevel.PUBLIC,
            ),
            "code": FieldClassification(
                field_name="code",
                sensitivity=SensitivityLevel.PUBLIC,
            ),
        },
    ))

    # --- NotificationLog (E02-S03) ---
    EntityClassificationRegistry.register(EntityClassification(
        entity_type="notification_log",
        default_sensitivity=SensitivityLevel.CONFIDENTIAL,
        default_regulated_type=RegulatedDataType.PII,
        description="Notification records — contains recipient PII",
        retention_class=RetentionClass.STANDARD,   # E00-S07: 5 years
        field_overrides={
            "recipient_address": FieldClassification(
                field_name="recipient_address",
                sensitivity=SensitivityLevel.REGULATED,
                regulated_type=RegulatedDataType.PII,
                mask_in_logs=True,
                mask_in_ai=True,
                mask_pattern="partial",
            ),
            "recipient_id": FieldClassification(
                field_name="recipient_id",
                sensitivity=SensitivityLevel.CONFIDENTIAL,
                mask_in_logs=True,
                mask_in_ai=True,
            ),
        },
    ))

    # --- Task (E02-S08) ---
    EntityClassificationRegistry.register(EntityClassification(
        entity_type="task",
        default_sensitivity=SensitivityLevel.INTERNAL,
        description="System tasks — internal operational data",
        retention_class=RetentionClass.TEMPORARY,  # E00-S07: 90 days
    ))

    # --- FileMetadata (E02-S05) ---
    EntityClassificationRegistry.register(EntityClassification(
        entity_type="file_metadata",
        default_sensitivity=SensitivityLevel.CONFIDENTIAL,
        description="Files may contain sensitive data — default to CONFIDENTIAL",
        field_overrides={
            "filename": FieldClassification(
                field_name="filename",
                sensitivity=SensitivityLevel.INTERNAL,
            ),
            "content_hash": FieldClassification(
                field_name="content_hash",
                sensitivity=SensitivityLevel.INTERNAL,
            ),
        },
    ))

    # --- GeneratedDocument (Documents) ---
    EntityClassificationRegistry.register(EntityClassification(
        entity_type="generated_document",
        default_sensitivity=SensitivityLevel.REGULATED,
        default_regulated_type=RegulatedDataType.TRANSCRIPT,
        description="Official documents (transcripts, certificates) — REGULATED",
        retention_class=RetentionClass.PERMANENT,  # E00-S07: Transcripts are permanent
        field_overrides={
            "document_id": FieldClassification(
                field_name="document_id",
                sensitivity=SensitivityLevel.INTERNAL,
            ),
            "file_hash": FieldClassification(
                field_name="file_hash",
                sensitivity=SensitivityLevel.INTERNAL,
            ),
        },
    ))

    # --- AuditEntry ---
    EntityClassificationRegistry.register(EntityClassification(
        entity_type="audit_entry",
        default_sensitivity=SensitivityLevel.INTERNAL,
        description="Audit logs — metadata is INTERNAL, contents may be masked",
        retention_class=RetentionClass.PERMANENT,  # E00-S07: Audit records are permanent
        field_overrides={
            "metadata": FieldClassification(
                field_name="metadata",
                sensitivity=SensitivityLevel.CONFIDENTIAL,
                mask_in_logs=False,  # Already in the log
                mask_in_ai=True,
            ),
        },
    ))

    # --- E00-S07: Biometric Attendance Logs ---
    EntityClassificationRegistry.register(EntityClassification(
        entity_type="biometric_log",
        default_sensitivity=SensitivityLevel.REGULATED,
        default_regulated_type=RegulatedDataType.BIOMETRIC,
        description="Biometric attendance logs — REGULATED, 2-year retention",
        retention_class=RetentionClass.LONG_TERM,  # E00-S07: Biometric = 2 years
    ))

    # --- E00-S07: Attendance Records ---
    EntityClassificationRegistry.register(EntityClassification(
        entity_type="attendance_record",
        default_sensitivity=SensitivityLevel.INTERNAL,
        description="Daily attendance records — 5-year retention",
        retention_class=RetentionClass.STANDARD,   # E00-S07: Attendance = 5 years
    ))

    # --- E00-S07: Financial Records ---
    EntityClassificationRegistry.register(EntityClassification(
        entity_type="financial_record",
        default_sensitivity=SensitivityLevel.REGULATED,
        default_regulated_type=RegulatedDataType.FINANCE,
        description="Fee payments, ledger entries — REGULATED, permanent",
        retention_class=RetentionClass.PERMANENT,  # E00-S07: Financial = permanent
    ))

    logger.info(
        "Initialized default data classifications for %d entity types.",
        len(EntityClassificationRegistry.list_registered()),
    )
