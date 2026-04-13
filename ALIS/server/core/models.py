"""
ALIS Core Models - E01-S01: Core Identity Model

MODULE: Platform Core
LAYER: Layer 5 (Roles, Authority & Quorum)
ENTITY: User, Organization
DECISION: N/A (Data Model Only)

This module defines the canonical identity entities for ALIS.
All actors (human, AI agent, system) are represented here.

Constraints (from Master Handbook):
- Immutable IDs (UUID)
- Soft-delete only (no hard deletes)
- No domain-specific fields
- Status lifecycle: ACTIVE, SUSPENDED, ARCHIVED
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from .data_classification import RegulatedDataType, SensitivityLevel

# --- Enums ---


class ActorType(str, Enum):
    """Type of actor in the system."""

    HUMAN = "human"
    AI_AGENT = "ai_agent"
    SYSTEM = "system"


class UserStatus(str, Enum):
    """Lifecycle states for a User entity (Layer 3 compliant)."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"  # Soft-delete state


class OrganizationStatus(str, Enum):
    """Lifecycle states for an Organization entity."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"


# --- E02-S03: Notification Enums ---


class NotificationStatus(str, Enum):
    """Delivery status for notifications."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class NotificationChannel(str, Enum):
    """Supported notification channels."""

    EMAIL = "EMAIL"
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"


# --- Base Models ---


class BaseEntity(BaseModel):
    """
    Base entity with common fields for all ALIS models.
    Enforces immutable ID and audit timestamps.

    E00-S01: All entities carry sensitivity metadata.
    """

    id: str = Field(default_factory=lambda: str(uuid4()), frozen=True)
    version: int = Field(
        default=1,
        description="Entity version for optimistic locking (Runtime Contract v1.0)",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    # E00-S01: Data Classification (Layer 1 metadata extension)
    sensitivity_level: SensitivityLevel = Field(
        default=SensitivityLevel.INTERNAL,
        description="Data sensitivity classification (E00-S01)",
    )
    regulated_data_type: RegulatedDataType = Field(
        default=RegulatedDataType.NONE,
        description="Regulated data sub-category (E00-S01)",
    )

    class Config:
        frozen = False  # Allow updates to non-frozen fields


# --- E01-S01: Core Identity Model ---


class User(BaseEntity):
    """
    Canonical User entity.
    Represents all actors in ALIS: human users, AI agents, and system actors.

    Must Align With:
    - Layer 5 (Roles, Authority & Quorum)

    Acceptance Criteria:
    - [x] Canonical User entity with immutable ID
    - [x] Supports human + AI agent identities (actor_type)
    - [x] Status lifecycle: ACTIVE, SUSPENDED, ARCHIVED
    - [x] No domain-specific fields
    - [x] Soft-delete only (status -> ARCHIVED)
    - [x] E00-S01: Sensitivity = CONFIDENTIAL, Regulated = PII
    """

    # E00-S01: User data is CONFIDENTIAL (PII)
    sensitivity_level: SensitivityLevel = SensitivityLevel.CONFIDENTIAL
    regulated_data_type: RegulatedDataType = RegulatedDataType.PII

    # Identity
    username: str = Field(..., min_length=3, max_length=64)
    email: str | None = None
    display_name: str | None = None

    # Actor Classification
    actor_type: ActorType = ActorType.HUMAN

    # Status (Layer 3: State Machine)
    status: UserStatus = UserStatus.ACTIVE

    # Organization Scoping (for E01-S05)
    org_id: str | None = None

    # Soft-delete marker
    is_deleted: bool = False
    deleted_at: datetime | None = None

    def archive(self) -> None:
        """Soft-delete the user by transitioning to ARCHIVED state."""
        if self.status == UserStatus.ARCHIVED:
            raise ValueError("User is already archived.")
        self.status = UserStatus.ARCHIVED
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


# --- E01-S05: Organization & Tenant Isolation ---


class Organization(BaseEntity):
    """
    Organization/Tenant entity for institutional data isolation.

    Must Align With:
    - Layer 1 (Module Authority)
    - Layer 4 (Global Locks)

    Acceptance Criteria:
    - [x] Organization entity
    - [x] Support for department/unit hierarchy (parent_id)
    - [x] Mandatory org_id scoping (enforced at service layer)
    """

    name: str = Field(..., min_length=2, max_length=256)
    code: str = Field(..., min_length=2, max_length=32)  # Short code, e.g., "WOXSEN"

    # Hierarchy
    parent_id: str | None = None  # For department/unit hierarchy

    # Status
    status: OrganizationStatus = OrganizationStatus.ACTIVE

    # Soft-delete
    is_deleted: bool = False
    deleted_at: datetime | None = None

    def archive(self) -> None:
        """Soft-delete the organization."""
        if self.status == OrganizationStatus.ARCHIVED:
            raise ValueError("Organization is already archived.")
        self.status = OrganizationStatus.ARCHIVED
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)


# --- E02-S03: Notification Log ---


class NotificationLog(BaseEntity):
    """
    Audit log for notification delivery attempts.

    MODULE: Shared Services (E02-S03)
    LAYER: Layer 6 (Resilience)

    Tracks all notification send attempts with status, retries, and errors.

    E00-S01: Contains recipient PII (addresses) — CONFIDENTIAL.
    """

    # E00-S01: Notification logs contain PII
    sensitivity_level: SensitivityLevel = SensitivityLevel.CONFIDENTIAL
    regulated_data_type: RegulatedDataType = RegulatedDataType.PII

    # Target
    recipient_id: str = Field(..., description="User ID of recipient")
    recipient_address: str = Field(..., description="Email/Phone number")

    # Content
    template_id: str = Field(..., description="Template used")
    channel: NotificationChannel = NotificationChannel.EMAIL

    # Delivery Status
    status: NotificationStatus = NotificationStatus.PENDING
    error_message: str | None = None
    retry_count: int = 0
    max_retries: int = 3

    # Timestamps
    sent_at: datetime | None = None
    last_retry_at: datetime | None = None

    # Context (for debugging)
    context_snapshot: dict | None = None

    # Organization scoping
    org_id: str | None = None


# --- E02-S08: Task & Reminder Engine ---


class TaskStatus(str, Enum):
    """Lifecycle states for a Task entity."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class TaskPriority(str, Enum):
    """Priority levels for tasks."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Task(BaseEntity):
    """
    System-driven Task entity (E02-S08).

    Represents a unit of work assigned to a User OR a Role.

    constraints:
    - Must have either assignee_id OR assignee_role (but not both empty)
    - If assignee_role is set, it follows the "Shared Worklist" pattern
    """

    # content
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM

    # Assignment (User OR Role)
    assignee_id: str | None = None
    assignee_role: str | None = None  # Stores Role.value

    # Scheduling
    due_date: datetime | None = None
    completed_at: datetime | None = None
    reminder_sent: bool = False

    # Context / Source Linking
    entity_type: str | None = None  # e.g., "approval_request", "document"
    entity_id: str | None = None

    # Status
    status: TaskStatus = TaskStatus.PENDING

    # Organization
    org_id: str | None = None

    def complete(self, user_id: str) -> None:
        """Mark task as completed by a specific user."""
        if self.status in [TaskStatus.COMPLETED, TaskStatus.CANCELLED]:
            raise ValueError(f"Task is already {self.status}")

        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        # If it was a role-based task, we might want to capture who actually did it
        # effectively "claiming" it. For now, we just mark it done.
