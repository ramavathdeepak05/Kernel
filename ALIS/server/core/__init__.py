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
- diff_tracker: Field-level change tracking (E00-S08)
- data_classification: Data sensitivity model (E00-S01)
- model_registry: LLM Model Registry for hot-swap (E03-S02)
- policy_service: Policy Governance & Registry (E00-S09)
- policy_resolver: Policy Resolver Middleware (E00-S10)
"""

from __future__ import annotations

from .ai_gateway import (  # E03-S01
    AIGateway,
    AIGatewayContext,
    AIInvocationResult,
    AIOutputValidator,
    AIResponseSchema,
    ConfidenceTier,
    InstrumentedLLM,
    PromptInjectionDetector,
    StateImpact,
)
from .ai_observability import (  # E03-S10
    AIObservabilityService,
    InvocationMetrics,
    ModelMetrics,
)
from .audit import AuditAction, AuditEntry, AuditLedger, AuditLog
from .config import ConfigCategory, ConfigEntry, ConfigRegistry
from .data_classification import (  # E00-S01
    DataMasker,
    EntityClassificationRegistry,
    FieldClassification,
    RegulatedDataType,
    RetentionClass,  # E00-S07
    SensitivityLevel,
    encryption_required,
    initialize_default_classifications,
)
from .diff_tracker import (  # E00-S08
    TRACKED_ENTITIES,
    compute_and_log_field_diffs,
    get_decrypted_field_diffs,
    is_tracked_entity,
)
from .escalation import (
    CriticalOperation,
    DualControlGuard,
    ElevatedAccessToken,
    EscalationService,
    EscalationState,
)
from .exceptions import (
    DiffTrackingError,  # E00-S08
    DualControlRequiredError,
    EscalationDeniedError,
    LockdownActiveError,  # E00-S05
    PolicyResolutionError,  # E00-S10
    TenantIsolationError,
)
from .guardrails import (  # E03-S08
    AIGuardrails,
    GuardrailResult,
    GuardrailViolation,
    HallucinationDetector,
    PolicyContradictionDetector,
    ToxicityFilter,
    UnsafeSuggestionBlocker,
)
from .hitl import (  # E03-S09
    HITLDisposition,
    HITLEnforcer,
    HITLResult,
)
from .lockdown import LOCKDOWN_IMMUNE_ROLES, LockdownEvent, LockdownManager  # E00-S05
from .locks import GlobalLockRegistry, LockStatus, LockType, check_global_locks
from .model_registry import (  # E03-S02
    LLMModelRead,
    LLMModelRegister,
    ModelCapability,
    ModelRegistry,
    ModelStatus,
    ResolvedModel,
)
from .models import ActorType, Organization, OrganizationStatus, User, UserStatus
from .overrides import Override, OverrideService, OverrideSeverity, OverrideType
from .policy_resolver import (  # E00-S10
    PolicyResolverCache,
    RequirePolicy,
    build_policy_context,
    get_resolver_cache,
    resolve_policy_for_rule,
)
from .policy_service import PolicyService, PolicyStatus  # E00-S09
from .rbac import AccessResult, Permission, Role, check_role_permission, verify_access
from .retention_policy import (  # E00-S07
    ArchivalService,
    ArchivalStatus,
    DeletionStatus,
    RetentionAuditReport,
    RetentionMatrix,
    RetentionService,
)
from .schema import (
    OrganizationCreate,
    OrganizationRead,
    UserCreate,
    UserRead,
    UserUpdate,
)
from .security import (
    AuditMiddleware,  # E00-S02
    FailedLoginTracker,
    InputValidator,
    PasswordHasher,
    RateLimiter,
    SecurityException,
    Session,
    SessionManager,
    TenantContext,
    # E00-S03: Tenant Isolation
    TenantMiddleware,
    TokenGenerator,
    clear_tenant_context,
    get_current_tenant_id,
    set_tenant_context,
)
from .state_registry import (
    ExamState,
    OverrideState,
    StateRegistry,
    StudentState,
    validate_exam_transition,
    validate_student_transition,
)
from .tenant_crypto import TenantKeyManager
from .tool_registry import (  # E03-S05
    BaseTool,
    ToolInvoker,
    ToolOutputSchema,
    ToolRegistry,
)

__all__ = [
    # Models
    "User",
    "Organization",
    "ActorType",
    "UserStatus",
    "OrganizationStatus",
    # Schema
    "UserCreate",
    "UserRead",
    "UserUpdate",
    "OrganizationCreate",
    "OrganizationRead",
    # RBAC
    "Role",
    "Permission",
    "verify_access",
    "check_role_permission",
    "AccessResult",
    # State Registry
    "StudentState",
    "ExamState",
    "OverrideState",
    "StateRegistry",
    "validate_student_transition",
    "validate_exam_transition",
    # Locks
    "LockType",
    "LockStatus",
    "check_global_locks",
    "GlobalLockRegistry",
    # Overrides
    "Override",
    "OverrideType",
    "OverrideSeverity",
    "OverrideService",
    # Audit
    "AuditLog",
    "AuditLedger",
    "AuditAction",
    "AuditEntry",
    # Security
    "PasswordHasher",
    "TokenGenerator",
    "SessionManager",
    "Session",
    "FailedLoginTracker",
    "RateLimiter",
    "InputValidator",
    "SecurityException",
    # Tenant Isolation (E00-S03)
    "TenantMiddleware",
    "TenantContext",
    "TenantIsolationError",
    "set_tenant_context",
    "get_current_tenant_id",
    "clear_tenant_context",
    "TenantKeyManager",
    "AuditMiddleware",
    # Config
    "ConfigRegistry",
    "ConfigCategory",
    "ConfigEntry",
    # Escalation & Dual Control (E00-S04)
    "EscalationService",
    "ElevatedAccessToken",
    "EscalationState",
    "DualControlGuard",
    "CriticalOperation",
    "EscalationDeniedError",
    "DualControlRequiredError",
    # Incident Response & Lockdown (E00-S05)
    "LockdownManager",
    "LockdownEvent",
    "LockdownActiveError",
    "LOCKDOWN_IMMUNE_ROLES",
    # Data Classification & Sensitivity (E00-S01)
    "SensitivityLevel",
    "RegulatedDataType",
    "FieldClassification",
    "EntityClassificationRegistry",
    "DataMasker",
    "encryption_required",
    "initialize_default_classifications",
    # Data Retention & Deletion (E00-S07)
    "RetentionClass",
    "ArchivalService",
    "RetentionService",
    "RetentionMatrix",
    "RetentionAuditReport",
    "ArchivalStatus",
    "DeletionStatus",
    # Field-Level Change Tracking (E00-S08)
    "compute_and_log_field_diffs",
    "get_decrypted_field_diffs",
    "TRACKED_ENTITIES",
    "is_tracked_entity",
    "DiffTrackingError",
    # AI Gateway (E03-S01)
    "AIGateway",
    "AIGatewayContext",
    "AIInvocationResult",
    "InstrumentedLLM",
    "AIResponseSchema",
    "AIOutputValidator",
    "PromptInjectionDetector",
    "ConfidenceTier",
    "StateImpact",
    # Model Registry (E03-S02)
    "ModelRegistry",
    "ModelCapability",
    "ModelStatus",
    "LLMModelRead",
    "LLMModelRegister",
    "ResolvedModel",
    # Tool Invocation Framework (E03-S05)
    "BaseTool",
    "ToolOutputSchema",
    "ToolRegistry",
    "ToolInvoker",
    # Policy Governance (E00-S09)
    "PolicyService",
    "PolicyStatus",
    # Policy Resolver Middleware (E00-S10)
    "PolicyResolverCache",
    "RequirePolicy",
    "resolve_policy_for_rule",
    "build_policy_context",
    "get_resolver_cache",
    "PolicyResolutionError",
    # AI Guardrails (E03-S08)
    "AIGuardrails",
    "GuardrailResult",
    "GuardrailViolation",
    "ToxicityFilter",
    "HallucinationDetector",
    "PolicyContradictionDetector",
    "UnsafeSuggestionBlocker",
    # HITL Enforcement (E03-S09)
    "HITLEnforcer",
    "HITLResult",
    "HITLDisposition",
    # AI Observability (E03-S10)
    "AIObservabilityService",
    "InvocationMetrics",
    "ModelMetrics",
]
