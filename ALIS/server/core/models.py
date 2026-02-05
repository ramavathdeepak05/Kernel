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

from enum import Enum
from uuid import uuid4
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


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


# --- Base Models ---

class BaseEntity(BaseModel):
    """
    Base entity with common fields for all ALIS models.
    Enforces immutable ID and audit timestamps.
    """
    id: str = Field(default_factory=lambda: str(uuid4()), frozen=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

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
    """
    # Identity
    username: str = Field(..., min_length=3, max_length=64)
    email: Optional[str] = None
    display_name: Optional[str] = None

    # Actor Classification
    actor_type: ActorType = ActorType.HUMAN

    # Status (Layer 3: State Machine)
    status: UserStatus = UserStatus.ACTIVE

    # Organization Scoping (for E01-S05)
    org_id: Optional[str] = None

    # Soft-delete marker
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None

    def archive(self) -> None:
        """Soft-delete the user by transitioning to ARCHIVED state."""
        if self.status == UserStatus.ARCHIVED:
            raise ValueError("User is already archived.")
        self.status = UserStatus.ARCHIVED
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()


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
    parent_id: Optional[str] = None  # For department/unit hierarchy

    # Status
    status: OrganizationStatus = OrganizationStatus.ACTIVE

    # Soft-delete
    is_deleted: bool = False
    deleted_at: Optional[datetime] = None

    def archive(self) -> None:
        """Soft-delete the organization."""
        if self.status == OrganizationStatus.ARCHIVED:
            raise ValueError("Organization is already archived.")
        self.status = OrganizationStatus.ARCHIVED
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
