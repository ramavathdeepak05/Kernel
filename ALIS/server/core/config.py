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

from uuid import uuid4
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from .audit import AuditLog, AuditAction


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


# --- Config Version ---

@dataclass
class ConfigVersion:
    """A versioned configuration entry."""
    version: int
    value: Any
    effective_from: datetime
    effective_until: Optional[datetime] = None
    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    change_reason: Optional[str] = None


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
    versions: List[ConfigVersion] = field(default_factory=list)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

    # Constraints
    value_type: str = "string"  # string, int, float, bool, json
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    allowed_values: Optional[List[Any]] = None

    def get_value(self, as_of: Optional[datetime] = None) -> Any:
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
        reason: Optional[str] = None,
        effective_from: Optional[datetime] = None
    ) -> ConfigVersion:
        """Update the configuration value (creates new version)."""
        # Validate value
        self._validate_value(new_value)

        # Create new version
        new_version = ConfigVersion(
            version=self.current_version + 1,
            value=new_value,
            effective_from=effective_from or datetime.utcnow(),
            created_by=changed_by,
            change_reason=reason
        )

        # Close current version
        if self.versions:
            self.versions[-1].effective_until = new_version.effective_from

        self.versions.append(new_version)
        self.current_version = new_version.version
        self.current_value = new_value
        self.updated_at = datetime.utcnow()

        return new_version

    def _validate_value(self, value: Any) -> None:
        """Validate value against constraints."""
        if self.value_type == "int" and not isinstance(value, int):
            raise ValueError(f"Value must be an integer")
        if self.value_type == "float" and not isinstance(value, (int, float)):
            raise ValueError(f"Value must be a number")
        if self.value_type == "bool" and not isinstance(value, bool):
            raise ValueError(f"Value must be a boolean")

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

    _configs: Dict[str, ConfigEntry] = {}

    # Pre-defined policy keys (from Master Handbook)
    ATTENDANCE_THRESHOLD = "attendance.minimum_percentage"
    EXAM_ELIGIBILITY_ATTENDANCE = "exam.eligibility.attendance_percentage"
    FEE_LATE_PENALTY_PERCENT = "finance.fee.late_penalty_percent"
    SCHOLARSHIP_INCOME_LIMIT = "admission.scholarship.income_limit"
    MARKS_ENTRY_WINDOW_DAYS = "examination.marks_entry_window_days"

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
                max_value=100
            ),
            ConfigEntry(
                key=cls.EXAM_ELIGIBILITY_ATTENDANCE,
                category=ConfigCategory.EXAMINATION,
                description="Minimum attendance for exam eligibility",
                current_value=75,
                value_type="int",
                min_value=0,
                max_value=100
            ),
            ConfigEntry(
                key=cls.FEE_LATE_PENALTY_PERCENT,
                category=ConfigCategory.FINANCE,
                description="Late fee penalty percentage",
                current_value=5,
                value_type="float",
                min_value=0,
                max_value=50
            ),
            ConfigEntry(
                key=cls.SCHOLARSHIP_INCOME_LIMIT,
                category=ConfigCategory.ADMISSION,
                description="Maximum family income for scholarship eligibility",
                current_value=500000,
                value_type="int",
                min_value=0
            ),
            ConfigEntry(
                key=cls.MARKS_ENTRY_WINDOW_DAYS,
                category=ConfigCategory.EXAMINATION,
                description="Days allowed for marks entry after exam",
                current_value=14,
                value_type="int",
                min_value=1,
                max_value=60
            ),
        ]

        for config in defaults:
            if config.key not in cls._configs:
                config.versions.append(ConfigVersion(
                    version=1,
                    value=config.current_value,
                    effective_from=datetime.utcnow(),
                    created_by="system"
                ))
                cls._configs[config.key] = config

    @classmethod
    def get(cls, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        config = cls._configs.get(key)
        if config is None:
            return default
        return config.current_value

    @classmethod
    def get_entry(cls, key: str) -> Optional[ConfigEntry]:
        """Get the full configuration entry."""
        return cls._configs.get(key)

    @classmethod
    def set(
        cls,
        key: str,
        value: Any,
        changed_by: str,
        reason: Optional[str] = None
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
                "version": new_version.version
            }
        )

        return new_version

    @classmethod
    def get_by_category(cls, category: ConfigCategory) -> List[ConfigEntry]:
        """Get all configs in a category."""
        return [c for c in cls._configs.values() if c.category == category]

    @classmethod
    def get_history(cls, key: str) -> List[ConfigVersion]:
        """Get version history for a config."""
        config = cls._configs.get(key)
        if config is None:
            return []
        return config.versions


# Initialize defaults on module load
ConfigRegistry.initialize_defaults()
