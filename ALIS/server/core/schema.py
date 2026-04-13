"""
ALIS Core Schema - Pydantic Models for API I/O

This module contains Pydantic models for request/response validation.
Separate from core models to maintain clean separation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .models import ActorType, OrganizationStatus, TaskPriority, TaskStatus, UserStatus

# --- Task Schemas (E02-S08) ---


class TaskCreate(BaseModel):
    """Schema for creating a new task."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM

    # Assignment (One is required)
    assignee_id: str | None = None
    assignee_role: str | None = None

    due_date: datetime | None = None

    # Context
    entity_type: str | None = None
    entity_id: str | None = None


class TaskUpdate(BaseModel):
    """Schema for updating a task."""

    title: str | None = None
    description: str | None = None
    priority: TaskPriority | None = None
    due_date: datetime | None = None
    status: TaskStatus | None = None


class TaskRead(BaseModel):
    """Schema for reading a task."""

    id: str
    title: str
    description: str | None
    priority: TaskPriority
    status: TaskStatus
    assignee_id: str | None
    assignee_role: str | None
    due_date: datetime | None
    completed_at: datetime | None
    entity_type: str | None
    entity_id: str | None
    created_at: datetime
    updated_at: datetime | None


# --- User Schemas ---


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    username: str = Field(..., min_length=3, max_length=64)
    email: str | None = None
    display_name: str | None = None
    actor_type: ActorType = ActorType.HUMAN
    org_id: str | None = None


class UserRead(BaseModel):
    """Schema for reading user data."""

    id: str
    username: str
    email: str | None
    display_name: str | None
    actor_type: ActorType
    status: UserStatus
    org_id: str | None
    created_at: datetime
    updated_at: datetime | None


class UserUpdate(BaseModel):
    """Schema for updating user data (partial)."""

    email: str | None = None
    display_name: str | None = None
    status: UserStatus | None = None


# --- Organization Schemas ---


class OrganizationCreate(BaseModel):
    """Schema for creating a new organization."""

    name: str = Field(..., min_length=2, max_length=256)
    code: str = Field(..., min_length=2, max_length=32)
    parent_id: str | None = None


class OrganizationRead(BaseModel):
    """Schema for reading organization data."""

    id: str
    name: str
    code: str
    parent_id: str | None
    status: OrganizationStatus
    created_at: datetime
    updated_at: datetime | None


from typing import Any  # noqa: E402

# --- Timeline Event Schema (Phase B — Entity Debugger) ---


class TimelineEvent(BaseModel):
    """A single formatted entry in an entity's decision/activity timeline.

    Returned by GET /api/v1/audit/timeline/{entity_type}/{entity_id}.
    Designed for direct UI consumption — labels, colors, and icons are
    pre-computed so the frontend renders without business logic.
    """

    id: int
    timestamp: str  # ISO 8601 UTC
    action: str  # raw AuditAction value
    label: str  # "Policy Evaluated (v3, Rule r1)"
    actor_id: str
    actor_role: str | None = None
    color: str  # "green" | "blue" | "amber" | "red" | "muted"
    icon: str  # "check" | "ai" | "lock" | "alert" | "clock" | "zap"
    metadata: dict[str, Any] = {}
    formatted_detail: str | None = None  # metadata["formatted"] if present


# --- Event Schema (E02-S09) ---


class Event(BaseModel):
    """
    Standard Logic Event Envelope (Shared Service).

    All system events must conform to this schema.
    """

    id: str = Field(..., description="Unique Event ID (UUID4)")
    type: str = Field(
        ..., description="Event Type (e.g., 'm1.admissions.student_enrolled')"
    )
    version: str = Field(default="1.0.0", description="Schema Version")
    source: str = Field(..., description="Source System/Module ID")
    payload: dict[str, Any] = Field(default_factory=dict, description="Event Data")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="UTC Timestamp"
    )
    correlation_id: str | None = Field(
        None, description="Trace ID for cross-event tracking"
    )
