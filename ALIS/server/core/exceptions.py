"""
ALIS Shared Exceptions - E02-S10

MODULE: Shared Services
LAYER: All Layers (Foundational)

This module defines the canonical exception hierarchy for ALIS.
All modules MUST raise these exceptions instead of generic Python errors
or raw HTTP exceptions.

Hierarchy matches the ALIS Layered Architecture:
- ALISError (Base)
  - Layer 1: ModuleAuthorityError
  - Layer 2: DecisionError, BusinessRuleViolation
  - Layer 3: IllegalStateTransitionError
  - Layer 4: GlobalLockViolationError
  - Layer 5: AuthorityError (PermissionDenied, QuotaExceeded, EscalationDenied, DualControlRequired)
  - Layer 6: ResilienceError (ProvisionalWarning)
"""

from typing import Any, Dict, Optional, List


class ALISError(Exception):
    """
    Base class for all ALIS functional errors.
    
    Attributes:
        message: User-safe error message.
        code: Machine-readable error code (e.g., ERR_AUTH_DENIED).
        details: Optional dictionary of debug/context info.
        http_status: Suggested HTTP status code for API responses.
    """
    def __init__(
        self, 
        message: str, 
        code: str = "ERR_GENERIC",
        details: Optional[Dict[str, Any]] = None,
        http_status: int = 400
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.http_status = http_status


# --- Layer 1: Module Authority ---

class ModuleAuthorityError(ALISError):
    """
    Raised when a module attempts to decide an outcome locally
    that belongs to another module (Layer 1 violation).
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="ERR_LAYER1_AUTHORITY",
            details=details,
            http_status=500  # This is a code/architecture bug, not user error
        )


# --- Layer 2: Decisions & Logic ---

class DecisionError(ALISError):
    """Base class for errors during Wizard execution."""
    pass


class BusinessRuleViolation(DecisionError):
    """
    Raised when input data violates a domain business rule.
    Example: "Applicant cannot be under 18 years old."
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="ERR_LAYER2_RULE",
            details=details,
            http_status=422
        )


# --- Layer 3: State Machines ---

class IllegalStateTransitionError(ALISError):
    """
    Raised when a state transition is not allowed by the central registry.
    Example: ENROLLED -> APPLIED
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="ERR_LAYER3_STATE",
            details=details,
            http_status=409  # Conflict
        )


# --- Layer 4: Global Locks ---

class GlobalLockViolationError(ALISError):
    """
    Raised when a Global Lock prevents an action.
    Example: "Cannot generate Hall Ticket: Dues Pending"
    """
    def __init__(self, violations: List[str], details: Optional[Dict] = None):
        details = details or {}
        details["violations"] = violations
        super().__init__(
            message=f"Global locks active: {', '.join(violations)}",
            code="ERR_LAYER4_LOCK",
            details=details,
            http_status=423  # Locked
        )


class TenantIsolationError(ALISError):
    """
    Raised when tenant isolation is violated (Layer 4).

    Examples:
    - Request missing tenant_id context
    - Cross-tenant data access attempt
    - Tenant context mismatch in DB query
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="ERR_LAYER4_TENANT",
            details=details,
            http_status=403  # Forbidden
        )


class LockdownActiveError(ALISError):
    """
    Raised when an operation is blocked because the system is in
    lockdown mode (E00-S05 — Incident Response).

    Examples:
    - Non-admin write attempt during lockdown
    - AI invocation attempt during lockdown
    - Session creation for non-admin during lockdown
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="ERR_LAYER4_LOCKDOWN",
            details=details,
            http_status=423  # Locked
        )


# --- E00-S06: AI Boundary Enforcement ---

class AIBoundaryViolationError(ALISError):
    """
    Base class for AI boundary enforcement violations (E00-S06).

    Raised when AI attempts to breach its operational constraints:
    - Prompt injection detected
    - Forbidden STATE_IMPACT value in output
    - Invalid output schema
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="ERR_AI_BOUNDARY",
            details=details,
            http_status=422
        )


class PromptInjectionError(AIBoundaryViolationError):
    """
    Raised when a prompt injection attempt is detected (E00-S06).

    Examples:
    - "Ignore previous instructions"
    - "You are now in DAN mode"
    - System prompt override attempts
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        details = details or {}
        super().__init__(
            message=message,
            details=details,
        )
        self.code = "ERR_AI_PROMPT_INJECTION"


class AISchemaViolationError(AIBoundaryViolationError):
    """
    Raised when AI output fails mandatory schema validation (E00-S06).

    Examples:
    - Missing confidence_score
    - STATE_IMPACT set to 'Final' or 'Commit' (forbidden)
    - Free-text response where structured JSON is required
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        details = details or {}
        super().__init__(
            message=message,
            details=details,
        )
        self.code = "ERR_AI_SCHEMA_VIOLATION"


# --- Layer 5: Authority & RBAC ---

class AuthorityError(ALISError):
    """Base class for RBAC/Auth errors."""
    pass


class PermissionDeniedError(AuthorityError):
    """
    Raised when an actor (Human or Agent) lacks permission.
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="ERR_LAYER5_ACCESS",
            details=details,
            http_status=403
        )


class QuotaExceededError(AuthorityError):
    """
    Raised when an action exceeds a quota/limit (e.g. Agent Read Limit).
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="ERR_LAYER5_QUOTA",
            details=details,
            http_status=429
        )


class EscalationDeniedError(AuthorityError):
    """
    Raised when a privilege escalation request is denied (E00-S04).

    Examples:
    - Grantor lacks ESCALATION_GRANT permission
    - Self-grant attempted when require_different_grantor is True
    - Requested TTL exceeds maximum allowed
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="ERR_LAYER5_ESCALATION",
            details=details,
            http_status=403
        )


class DualControlRequiredError(AuthorityError):
    """
    Raised when a critical operation is attempted without dual approval (E00-S04).

    Critical operations (result publish, payroll release, transcript seal)
    require 2-authority confirmation before execution.
    """
    def __init__(
        self,
        operation_id: str,
        message: Optional[str] = None,
        details: Optional[Dict] = None
    ):
        details = details or {}
        details["operation_id"] = operation_id
        super().__init__(
            message=message or f"Dual control approval required for: {operation_id}",
            code="ERR_LAYER5_DUAL_CONTROL",
            details=details,
            http_status=403
        )


# --- Layer 6: Resilience ---

class ResilienceProvisionalError(ALISError):
    """
    Raised when a definitive decision cannot be made,
    forcing the system into a Provisional State.
    This is often a Warning, not a hard Failure.
    """
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(
            message=message,
            code="WARN_LAYER6_PROVISIONAL",
            details=details,
            http_status=202  # Accepted (processing continues provisionally)
        )
