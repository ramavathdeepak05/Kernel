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
    DiffTrackingError,  # E00-S08
    PolicyResolutionError,  # E00-S10
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
    RetentionClass,  # E00-S07
)
from .retention_policy import (  # E00-S07
    ArchivalService, RetentionService, RetentionMatrix,
    RetentionAuditReport, ArchivalStatus, DeletionStatus,
)
from .diff_tracker import (  # E00-S08
    compute_and_log_field_diffs, get_decrypted_field_diffs,
    TRACKED_ENTITIES, is_tracked_entity,
)
from .ai_gateway import (  # E03-S01
    AIGateway, AIGatewayContext, AIInvocationResult, InstrumentedLLM,
    AIResponseSchema, AIOutputValidator, PromptInjectionDetector,
    ConfidenceTier, StateImpact,
)
from .model_registry import (  # E03-S02
    ModelRegistry, ModelCapability, ModelStatus,
    LLMModelRead, LLMModelRegister, ResolvedModel,
)
from .tool_registry import (  # E03-S05
    BaseTool, ToolOutputSchema, ToolRegistry, ToolInvoker,
)
from .policy_service import PolicyService, PolicyStatus  # E00-S09
from .policy_resolver import (  # E00-S10
    PolicyResolverCache, RequirePolicy, resolve_policy_for_rule,
    build_policy_context, get_resolver_cache,
)
from .guardrails import (  # E03-S08
    AIGuardrails, GuardrailResult, GuardrailViolation,
    ToxicityFilter, HallucinationDetector,
    PolicyContradictionDetector, UnsafeSuggestionBlocker,
)
from .hitl import (  # E03-S09
    HITLEnforcer, HITLResult, HITLDisposition,
)
from .ai_observability import (  # E03-S10
    AIObservabilityService, InvocationMetrics, ModelMetrics,
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
    # Data Retention & Deletion (E00-S07)
    "RetentionClass", "ArchivalService", "RetentionService",
    "RetentionMatrix", "RetentionAuditReport",
    "ArchivalStatus", "DeletionStatus",
    # Field-Level Change Tracking (E00-S08)
    "compute_and_log_field_diffs", "get_decrypted_field_diffs",
    "TRACKED_ENTITIES", "is_tracked_entity", "DiffTrackingError",
    # AI Gateway (E03-S01)
    "AIGateway", "AIGatewayContext", "AIInvocationResult", "InstrumentedLLM",
    "AIResponseSchema", "AIOutputValidator", "PromptInjectionDetector",
    "ConfidenceTier", "StateImpact",
    # Model Registry (E03-S02)
    "ModelRegistry", "ModelCapability", "ModelStatus",
    "LLMModelRead", "LLMModelRegister", "ResolvedModel",
    # Tool Invocation Framework (E03-S05)
    "BaseTool", "ToolOutputSchema", "ToolRegistry", "ToolInvoker",
    # Policy Governance (E00-S09)
    "PolicyService", "PolicyStatus",
    # Policy Resolver Middleware (E00-S10)
    "PolicyResolverCache", "RequirePolicy", "resolve_policy_for_rule",
    "build_policy_context", "get_resolver_cache", "PolicyResolutionError",
    # AI Guardrails (E03-S08)
    "AIGuardrails", "GuardrailResult", "GuardrailViolation",
    "ToxicityFilter", "HallucinationDetector",
    "PolicyContradictionDetector", "UnsafeSuggestionBlocker",
    # HITL Enforcement (E03-S09)
    "HITLEnforcer", "HITLResult", "HITLDisposition",
    # AI Observability (E03-S10)
    "AIObservabilityService", "InvocationMetrics", "ModelMetrics",
]

