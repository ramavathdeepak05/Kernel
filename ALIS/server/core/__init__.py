"""
ALIS Core Package

This package contains the foundational platform components:
- models: Core identity entities (User, Organization)
- schema: Pydantic schemas for API I/O
- rbac: Role-Based Access Control (RBAC+)
- state_registry: State machine enforcement (Layer 3)
- locks: Global Locks engine (Layer 4)
- overrides: Override lifecycle management (Layer 6)
- security: Authentication & session control
- audit: Immutable audit log
- config: System configuration registry
"""

from .models import User, Organization, ActorType, UserStatus, OrganizationStatus
from .schema import UserCreate, UserRead, UserUpdate, OrganizationCreate, OrganizationRead
from .rbac import Role, Permission, verify_access, check_role_permission, AccessResult
from .state_registry import (
    StudentState, ExamState, OverrideState, StateRegistry,
    validate_student_transition, validate_exam_transition
)
from .locks import LockType, LockStatus, check_global_locks, GlobalLockRegistry
from .overrides import Override, OverrideType, OverrideSeverity, OverrideService
from .audit import AuditLog, AuditAction, AuditEntry
from .security import (
    PasswordHasher, TokenGenerator, SessionManager, Session,
    FailedLoginTracker, RateLimiter, InputValidator, SecurityException
)
from .config import ConfigRegistry, ConfigCategory, ConfigEntry

__all__ = [
    # Models
    "User", "Organization", "ActorType", "UserStatus", "OrganizationStatus",
    # Schema
    "UserCreate", "UserRead", "UserUpdate", "OrganizationCreate", "OrganizationRead",
    # RBAC
    "Role", "Permission", "verify_access", "check_role_permission", "AccessResult",
    # State Registry
    "StudentState", "ExamState", "OverrideState", "StateRegistry",
    "validate_student_transition", "validate_exam_transition",
    # Locks
    "LockType", "LockStatus", "check_global_locks", "GlobalLockRegistry",
    # Overrides
    "Override", "OverrideType", "OverrideSeverity", "OverrideService",
    # Audit
    "AuditLog", "AuditAction", "AuditEntry",
    # Security
    "PasswordHasher", "TokenGenerator", "SessionManager", "Session",
    "FailedLoginTracker", "RateLimiter", "InputValidator", "SecurityException",
    # Config
    "ConfigRegistry", "ConfigCategory", "ConfigEntry",
]
