"""
ALIS Core Package

This package contains the foundational platform components:
- models: Core identity entities (User, Organization)
- schema: Pydantic schemas for API I/O
- rbac: Role-Based Access Control (RBAC+)
- state_registry: State machine enforcement (Layer 3)
- locks: Global Locks engine (Layer 4)
- overrides: Override lifecycle management (Layer 6)
- security: Authentication & session control + Tenant Isolation (E00-S03)
- audit: Immutable audit log
- config: System configuration registry
- tenant_crypto: Tenant-specific encryption (E00-S03)
- escalation: Privilege escalation & dual control (E00-S04)
- lockdown: Incident response & lockdown mode (E00-S05)
- data_classification: Data sensitivity model (E00-S01)
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
from .audit import AuditLog, AuditLedger, AuditAction, AuditEntry
from .security import (
    PasswordHasher, TokenGenerator, SessionManager, Session,
    FailedLoginTracker, RateLimiter, InputValidator, SecurityException,
    # E00-S03: Tenant Isolation
    TenantMiddleware, TenantContext,
    set_tenant_context, get_current_tenant_id, clear_tenant_context,
    AuditMiddleware, # E00-S02
)
from .config import ConfigRegistry, ConfigCategory, ConfigEntry
from .exceptions import (
    TenantIsolationError, EscalationDeniedError, DualControlRequiredError,
    LockdownActiveError,  # E00-S05
)
from .tenant_crypto import TenantKeyManager
from .escalation import (
    EscalationService, ElevatedAccessToken, EscalationState,
    DualControlGuard, CriticalOperation
)
from .lockdown import LockdownManager, LockdownEvent, LOCKDOWN_IMMUNE_ROLES  # E00-S05
from .data_classification import (  # E00-S01
    SensitivityLevel, RegulatedDataType, FieldClassification,
    EntityClassificationRegistry, DataMasker, encryption_required,
    initialize_default_classifications,
)

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
    "AuditLog", "AuditLedger", "AuditAction", "AuditEntry",
    # Security
    "PasswordHasher", "TokenGenerator", "SessionManager", "Session",
    "FailedLoginTracker", "RateLimiter", "InputValidator", "SecurityException",
    # Tenant Isolation (E00-S03)
    "TenantMiddleware", "TenantContext", "TenantIsolationError",
    "set_tenant_context", "get_current_tenant_id", "clear_tenant_context",
    "TenantKeyManager", "AuditMiddleware",
    # Config
    "ConfigRegistry", "ConfigCategory", "ConfigEntry",
    # Escalation & Dual Control (E00-S04)
    "EscalationService", "ElevatedAccessToken", "EscalationState",
    "DualControlGuard", "CriticalOperation",
    "EscalationDeniedError", "DualControlRequiredError",
    # Incident Response & Lockdown (E00-S05)
    "LockdownManager", "LockdownEvent", "LockdownActiveError",
    "LOCKDOWN_IMMUNE_ROLES",
    # Data Classification & Sensitivity (E00-S01)
    "SensitivityLevel", "RegulatedDataType", "FieldClassification",
    "EntityClassificationRegistry", "DataMasker", "encryption_required",
    "initialize_default_classifications",
]

