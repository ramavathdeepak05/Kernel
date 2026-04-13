"""
ALIS System Configuration Registry - E01-S10

MODULE: Platform Core
LAYER: Cross-cutting (Policy Management)
ENTITY: ConfigEntry

This module implements a configuration registry for policy parameters.
Follows the Policy vs Logic vs Invariant separation.

Must Align With:
- Policy vs Logic vs Invariant separation (Master Handbook)

Policy (CONFIGURABLE VIA UI):
- Thresholds (scores, percentages)
- Ranges (scholarship %, attendance cutoffs)
- Effective dates and applicability

Acceptance Criteria:
- [x] Versioned configs
- [x] Change history
- [x] Read-only to non-admins
- [x] No runtime mutation of invariants
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from .audit import AuditAction, AuditLog

# --- Config Categories ---


class ConfigCategory(str, Enum):
    """Categories of configuration."""

    ATTENDANCE = "attendance"
    FINANCE = "finance"
    EXAMINATION = "examination"
    ADMISSION = "admission"
    ACADEMIC = "academic"
    HR = "hr"
    SYSTEM = "system"
    NOTIFICATION = "notification"  # E02-S03
    SECURITY = "security"  # E00-S04


# --- Config Version ---


@dataclass
class ConfigVersion:
    """A versioned configuration entry."""

    version: int
    value: Any
    effective_from: datetime
    effective_until: datetime | None = None
    created_by: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    change_reason: str | None = None


# --- Config Entry ---


@dataclass
class ConfigEntry:
    """
    Configuration entry with version history.
    """

    id: str = field(default_factory=lambda: str(uuid4()))
    key: str = ""
    category: ConfigCategory = ConfigCategory.SYSTEM
    description: str = ""

    # Current value
    current_version: int = 1
    current_value: Any = None

    # Version history
    versions: list[ConfigVersion] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    # Constraints
    value_type: str = "string"  # string, int, float, bool, json
    min_value: float | None = None
    max_value: float | None = None
    allowed_values: list[Any] | None = None

    def get_value(self, as_of: datetime | None = None) -> Any:
        """Get the effective value at a point in time."""
        if as_of is None:
            return self.current_value

        for version in sorted(self.versions, key=lambda v: v.version, reverse=True):
            if version.effective_from <= as_of:
                if version.effective_until is None or version.effective_until > as_of:
                    return version.value

        return self.current_value

    def update(
        self,
        new_value: Any,
        changed_by: str,
        reason: str | None = None,
        effective_from: datetime | None = None,
    ) -> ConfigVersion:
        """Update the configuration value (creates new version)."""
        # Validate value
        self._validate_value(new_value)

        # Create new version
        new_version = ConfigVersion(
            version=self.current_version + 1,
            value=new_value,
            effective_from=effective_from or datetime.now(timezone.utc),
            created_by=changed_by,
            change_reason=reason,
        )

        # Close current version
        if self.versions:
            self.versions[-1].effective_until = new_version.effective_from

        self.versions.append(new_version)
        self.current_version = new_version.version
        self.current_value = new_value
        self.updated_at = datetime.now(timezone.utc)

        return new_version

    def _validate_value(self, value: Any) -> None:
        """Validate value against constraints."""
        if self.value_type == "int" and not isinstance(value, int):
            raise ValueError("Value must be an integer")
        if self.value_type == "float" and not isinstance(value, (int, float)):
            raise ValueError("Value must be a number")
        if self.value_type == "bool" and not isinstance(value, bool):
            raise ValueError("Value must be a boolean")

        if self.min_value is not None and value < self.min_value:
            raise ValueError(f"Value must be >= {self.min_value}")
        if self.max_value is not None and value > self.max_value:
            raise ValueError(f"Value must be <= {self.max_value}")
        if self.allowed_values is not None and value not in self.allowed_values:
            raise ValueError(f"Value must be one of {self.allowed_values}")


# --- Config Registry ---


class ConfigRegistry:
    """
    Central configuration registry.

    Manages all policy parameters with versioning and audit trails.
    """

    _configs: dict[str, ConfigEntry] = {}

    # Pre-defined policy keys (from Master Handbook)
    ATTENDANCE_THRESHOLD = "attendance.minimum_percentage"
    EXAM_ELIGIBILITY_ATTENDANCE = "exam.eligibility.attendance_percentage"
    FEE_LATE_PENALTY_PERCENT = "finance.fee.late_penalty_percent"
    SCHOLARSHIP_INCOME_LIMIT = "admission.scholarship.income_limit"
    MARKS_ENTRY_WINDOW_DAYS = "examination.marks_entry_window_days"

    # E02-S03: Notification Config Keys
    NOTIFICATION_EMAIL_ENABLED = "notification.email.enabled"
    NOTIFICATION_SMS_ENABLED = "notification.sms.enabled"
    NOTIFICATION_WHATSAPP_ENABLED = "notification.whatsapp.enabled"
    NOTIFICATION_EMAIL_SMTP_HOST = "notification.email.smtp_host"
    NOTIFICATION_EMAIL_SMTP_PORT = "notification.email.smtp_port"
    NOTIFICATION_MAX_RETRIES = "notification.max_retries"

    # E03-S01: AI Gateway Config Keys
    LLM_BASE_URL = "ai.llm.base_url"
    LLM_MODEL_NAME = "ai.llm.model_name"
    LLM_EMBED_MODEL = "ai.llm.embed_model"

    # E00-S04: Escalation & Dual Control Config Keys
    ESCALATION_DEFAULT_TTL = "escalation.default_ttl_minutes"
    ESCALATION_MAX_TTL = "escalation.max_ttl_minutes"
    ESCALATION_REQUIRE_DIFFERENT_GRANTOR = "escalation.require_different_grantor"
    ESCALATION_CRITICAL_OPERATIONS = "escalation.critical_operations"

    @classmethod
    def initialize_defaults(cls) -> None:
        """Initialize default configuration values."""
        defaults = [
            ConfigEntry(
                key=cls.ATTENDANCE_THRESHOLD,
                category=ConfigCategory.ATTENDANCE,
                description="Minimum attendance percentage required",
                current_value=75,
                value_type="int",
                min_value=0,
                max_value=100,
            ),
            ConfigEntry(
                key=cls.EXAM_ELIGIBILITY_ATTENDANCE,
                category=ConfigCategory.EXAMINATION,
                description="Minimum attendance for exam eligibility",
                current_value=75,
                value_type="int",
                min_value=0,
                max_value=100,
            ),
            ConfigEntry(
                key=cls.FEE_LATE_PENALTY_PERCENT,
                category=ConfigCategory.FINANCE,
                description="Late fee penalty percentage",
                current_value=5,
                value_type="float",
                min_value=0,
                max_value=50,
            ),
            ConfigEntry(
                key=cls.SCHOLARSHIP_INCOME_LIMIT,
                category=ConfigCategory.ADMISSION,
                description="Maximum family income for scholarship eligibility",
                current_value=500000,
                value_type="int",
                min_value=0,
            ),
            ConfigEntry(
                key=cls.MARKS_ENTRY_WINDOW_DAYS,
                category=ConfigCategory.EXAMINATION,
                description="Days allowed for marks entry after exam",
                current_value=14,
                value_type="int",
                min_value=1,
                max_value=60,
            ),
            # E02-S03: Notification Defaults
            ConfigEntry(
                key=cls.NOTIFICATION_EMAIL_ENABLED,
                category=ConfigCategory.NOTIFICATION,
                description="Enable email notifications",
                current_value=True,
                value_type="bool",
            ),
            ConfigEntry(
                key=cls.NOTIFICATION_SMS_ENABLED,
                category=ConfigCategory.NOTIFICATION,
                description="Enable SMS notifications",
                current_value=False,
                value_type="bool",
            ),
            ConfigEntry(
                key=cls.NOTIFICATION_WHATSAPP_ENABLED,
                category=ConfigCategory.NOTIFICATION,
                description="Enable WhatsApp notifications",
                current_value=False,
                value_type="bool",
            ),
            ConfigEntry(
                key=cls.NOTIFICATION_EMAIL_SMTP_HOST,
                category=ConfigCategory.NOTIFICATION,
                description="SMTP host for email",
                current_value="localhost",
                value_type="string",
            ),
            ConfigEntry(
                key=cls.NOTIFICATION_EMAIL_SMTP_PORT,
                category=ConfigCategory.NOTIFICATION,
                description="SMTP port for email",
                current_value=25,
                value_type="int",
                min_value=1,
                max_value=65535,
            ),
            ConfigEntry(
                key=cls.NOTIFICATION_MAX_RETRIES,
                category=ConfigCategory.NOTIFICATION,
                description="Maximum retries for failed notifications",
                current_value=3,
                value_type="int",
                min_value=0,
                max_value=10,
            ),
            # E03-S01: AI Gateway Defaults
            ConfigEntry(
                key=cls.LLM_BASE_URL,
                category=ConfigCategory.SYSTEM,
                description="Base URL for local LLM (Ollama)",
                current_value="http://localhost:11434",
                value_type="string",
            ),
            ConfigEntry(
                key=cls.LLM_MODEL_NAME,
                category=ConfigCategory.SYSTEM,
                description="Default LLM model name",
                current_value="qwen2.5:1.5b-instruct-q8_0",
                value_type="string",
            ),
            ConfigEntry(
                key=cls.LLM_EMBED_MODEL,
                category=ConfigCategory.SYSTEM,
                description="Embedding model name (for PGVector/RAG)",
                current_value="nomic-embed-text",
                value_type="string",
            ),
            # E00-S04: Escalation & Dual Control Defaults
            ConfigEntry(
                key=cls.ESCALATION_DEFAULT_TTL,
                category=ConfigCategory.SECURITY,
                description="Default TTL for elevated access tokens (minutes)",
                current_value=30,
                value_type="int",
                min_value=5,
                max_value=480,
            ),
            ConfigEntry(
                key=cls.ESCALATION_MAX_TTL,
                category=ConfigCategory.SECURITY,
                description="Maximum allowed TTL for elevated access tokens (minutes)",
                current_value=120,
                value_type="int",
                min_value=5,
                max_value=480,
            ),
            ConfigEntry(
                key=cls.ESCALATION_REQUIRE_DIFFERENT_GRANTOR,
                category=ConfigCategory.SECURITY,
                description="Require grantor to differ from requestor",
                current_value=True,
                value_type="bool",
            ),
            ConfigEntry(
                key=cls.ESCALATION_CRITICAL_OPERATIONS,
                category=ConfigCategory.SECURITY,
                description="List of operation IDs requiring dual control",
                current_value=["result_publish", "payroll_release", "transcript_seal"],
                value_type="json",
            ),
        ]

        for config in defaults:
            if config.key not in cls._configs:
                config.versions.append(
                    ConfigVersion(
                        version=1,
                        value=config.current_value,
                        effective_from=datetime.now(timezone.utc),
                        created_by="system",
                    )
                )
                cls._configs[config.key] = config

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        config = cls._configs.get(key)
        if config is None:
            return default
        return config.current_value

    @classmethod
    def get_entry(cls, key: str) -> ConfigEntry | None:
        """Get the full configuration entry."""
        return cls._configs.get(key)

    @classmethod
    def set(
        cls, key: str, value: Any, changed_by: str, reason: str | None = None
    ) -> ConfigVersion:
        """
        Update a configuration value.

        Requires admin role - enforced at API layer.
        Creates an audit log entry.
        """
        config = cls._configs.get(key)
        if config is None:
            raise ValueError(f"Configuration key '{key}' not found")

        old_value = config.current_value
        new_version = config.update(value, changed_by, reason)

        # Audit log
        AuditLog.log(
            action=AuditAction.CONFIG_CHANGE,
            actor_id=changed_by,
            actor_type="human",
            entity_type="config",
            entity_id=key,
            action_detail=f"Changed from {old_value} to {value}",
            metadata={
                "old_value": old_value,
                "new_value": value,
                "reason": reason,
                "version": new_version.version,
            },
        )

        return new_version

    @classmethod
    def get_by_category(cls, category: ConfigCategory) -> list[ConfigEntry]:
        """Get all configs in a category."""
        return [c for c in cls._configs.values() if c.category == category]

    @classmethod
    def get_history(cls, key: str) -> list[ConfigVersion]:
        """Get version history for a config."""
        config = cls._configs.get(key)
        if config is None:
            return []
        return config.versions


# Initialize defaults on module load
ConfigRegistry.initialize_defaults()
