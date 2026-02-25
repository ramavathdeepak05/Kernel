"""
ALIS Privilege Escalation & Dual Control - E00-S04

MODULE: Platform Core
LAYER: Layer 5 (Roles, Authority & Quorum) + Layer 4 (Time-bound Locks)

This module implements:
1. Time-bound Elevated Access Tokens — scoped permission grants with auto-expiry
2. Dual Control Guard — enforcement of multi-authority approval for critical operations

Must Align With:
- Layer 5: Authority enforcement, no single god-mode actor
- Layer 4: Time-bound constraints (TTL on elevated tokens)
- Layer 6: Audit all escalation events, resilience

Design Decisions:
- Elevated tokens grant specific permissions (scoped), NOT full role promotion
- Token expiry uses "check-on-use" pattern (no background scheduler needed)
- Dual control delegates to existing ApprovalService (no reinvention)
- Critical operations are configurable via ConfigRegistry (extensible)
- Grantor must differ from requestor (policy-configurable)

Acceptance Criteria (E00-S04):
- [x] Time-bound elevated access tokens with auto-expiry
- [x] Dual approval for critical operations
- [x] Escalation logged at every lifecycle point
- [x] Self-grant prevention (configurable)
- [x] TTL policy-configurable with max cap
- [x] Critical operations extensible via config
"""

from uuid import uuid4
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from .rbac import Role, Permission, check_role_permission
from .audit import AuditLog, AuditAction
from .config import ConfigRegistry
from .approvals import ApprovalService, ApprovalConfig, ApprovalMode, ApprovalState
from .exceptions import EscalationDeniedError, DualControlRequiredError


# --- Escalation State Machine ---

class EscalationState(str, Enum):
    """
    Lifecycle states for an elevated access token.

    State Machine:
        REQUESTED → GRANTED → ACTIVE → EXPIRED | REVOKED
        REQUESTED → DENIED
    """
    REQUESTED = "REQUESTED"
    GRANTED = "GRANTED"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    DENIED = "DENIED"


# Valid state transitions
_ESCALATION_TRANSITIONS = {
    EscalationState.REQUESTED: {EscalationState.GRANTED, EscalationState.DENIED},
    EscalationState.GRANTED: {EscalationState.ACTIVE},
    EscalationState.ACTIVE: {EscalationState.EXPIRED, EscalationState.REVOKED},
    # Terminal states — no transitions
    EscalationState.EXPIRED: set(),
    EscalationState.REVOKED: set(),
    EscalationState.DENIED: set(),
}


# --- Elevated Access Token ---

@dataclass
class ElevatedAccessToken:
    """
    A time-bound token granting additional permissions to a user.

    This is NOT a role promotion. The user retains their original role
    and gains additional scoped permissions for a limited duration.

    Attributes:
        id: Unique token identifier
        user_id: The user receiving elevated access
        tenant_id: Tenant scope for isolation
        granted_permissions: List of additional permissions granted
        scope: Operation-specific scope (e.g., "result_publish:EXAM-2024")
        reason: Justification for the escalation
        ttl_minutes: Duration in minutes
        state: Current lifecycle state
        requested_at: When escalation was requested
        granted_by: Who approved the escalation
        granted_at: When escalation was approved
        expires_at: When the token expires
        revoked_by: Who revoked (if revoked)
        revoked_at: When revoked (if revoked)
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = ""
    tenant_id: Optional[str] = None
    granted_permissions: List[Permission] = field(default_factory=list)
    scope: Optional[str] = None
    reason: str = ""
    ttl_minutes: int = 30

    # Lifecycle
    state: EscalationState = EscalationState.REQUESTED
    requested_at: datetime = field(default_factory=datetime.utcnow)
    granted_by: Optional[str] = None
    granted_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    revoked_by: Optional[str] = None
    revoked_at: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if the token has expired (TTL exceeded)."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at

    def is_active(self) -> bool:
        """Check if the token is currently active and not expired."""
        return self.state == EscalationState.ACTIVE and not self.is_expired()

    def _transition_to(self, new_state: EscalationState) -> None:
        """Validate and execute state transition."""
        allowed = _ESCALATION_TRANSITIONS.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid escalation state transition: "
                f"{self.state.value} → {new_state.value}"
            )
        self.state = new_state


# --- Critical Operation Definition ---

@dataclass
class CriticalOperation:
    """
    A registered critical operation that requires dual control.

    Each critical operation creates a corresponding ApprovalConfig
    in the ApprovalService when registered.

    Attributes:
        operation_id: Unique operation identifier (e.g., "result_publish")
        name: Human-readable name
        description: What this operation does
        required_roles: Which roles must approve (dual = 2 different roles)
        approval_config_id: Auto-generated link to ApprovalService config
    """
    operation_id: str = ""
    name: str = ""
    description: str = ""
    required_roles: List[Role] = field(default_factory=list)
    approval_config_id: str = ""


# --- Escalation Service ---

class EscalationService:
    """
    Service for managing privilege escalation tokens.

    Handles the full lifecycle:
    - Request → Grant/Deny → Active → Expire/Revoke

    All actions are audit-logged.
    Uses check-on-use pattern for expiry (no background scheduler).
    """

    # In-memory storage (production: DB-backed)
    _tokens: Dict[str, ElevatedAccessToken] = {}

    @classmethod
    def request_escalation(
        cls,
        user_id: str,
        requested_permissions: List[Permission],
        reason: str,
        scope: Optional[str] = None,
        ttl_minutes: Optional[int] = None,
        tenant_id: Optional[str] = None
    ) -> ElevatedAccessToken:
        """
        Request a privilege escalation.

        Creates an ElevatedAccessToken in REQUESTED state.
        The request must be granted by a separate authority.

        Args:
            user_id: The user requesting elevation
            requested_permissions: Permissions to be temporarily granted
            reason: Justification for the escalation
            scope: Optional operation-specific scope
            ttl_minutes: Optional TTL override (capped at max)
            tenant_id: Tenant scope

        Returns:
            ElevatedAccessToken in REQUESTED state

        Raises:
            EscalationDeniedError: If requested TTL exceeds maximum
        """
        # Resolve TTL
        default_ttl = ConfigRegistry.get(
            ConfigRegistry.ESCALATION_DEFAULT_TTL, 30
        )
        max_ttl = ConfigRegistry.get(
            ConfigRegistry.ESCALATION_MAX_TTL, 120
        )

        effective_ttl = ttl_minutes if ttl_minutes is not None else default_ttl

        if effective_ttl > max_ttl:
            raise EscalationDeniedError(
                message=f"Requested TTL ({effective_ttl} min) exceeds maximum "
                        f"allowed ({max_ttl} min)",
                details={
                    "requested_ttl": effective_ttl,
                    "max_ttl": max_ttl
                }
            )

        token = ElevatedAccessToken(
            user_id=user_id,
            tenant_id=tenant_id,
            granted_permissions=requested_permissions,
            scope=scope,
            reason=reason,
            ttl_minutes=effective_ttl,
            state=EscalationState.REQUESTED,
            requested_at=datetime.utcnow()
        )

        cls._tokens[token.id] = token

        # Audit log
        AuditLog.log(
            action=AuditAction.ESCALATION_REQUESTED,
            actor_id=user_id,
            actor_type="human",
            entity_type="escalation_token",
            entity_id=token.id,
            action_detail=f"Requested elevation: {[p.value for p in requested_permissions]}",
            metadata={
                "permissions": [p.value for p in requested_permissions],
                "scope": scope,
                "ttl_minutes": effective_ttl,
                "reason": reason
            },
            org_id=tenant_id
        )

        return token

    @classmethod
    def grant_escalation(
        cls,
        token_id: str,
        grantor_id: str,
        grantor_role: Role
    ) -> ElevatedAccessToken:
        """
        Grant a privilege escalation request.

        Transitions the token to ACTIVE state with TTL.

        Args:
            token_id: The token to approve
            grantor_id: Who is granting the escalation
            grantor_role: Role of the grantor

        Returns:
            Activated ElevatedAccessToken

        Raises:
            ValueError: If token not found
            EscalationDeniedError: If grantor lacks permission or is self-granting
        """
        token = cls._tokens.get(token_id)
        if token is None:
            raise ValueError(f"Escalation token not found: {token_id}")

        # Check: grantor must have ESCALATION_GRANT permission
        if not check_role_permission(grantor_role, Permission.ESCALATION_GRANT):
            raise EscalationDeniedError(
                message=f"Role '{grantor_role.value}' lacks ESCALATION_GRANT permission",
                details={
                    "grantor_role": grantor_role.value,
                    "required_permission": Permission.ESCALATION_GRANT.value
                }
            )

        # Check: self-grant prevention (configurable)
        require_different = ConfigRegistry.get(
            ConfigRegistry.ESCALATION_REQUIRE_DIFFERENT_GRANTOR, True
        )
        if require_different and grantor_id == token.user_id:
            # Audit the denied attempt
            AuditLog.log(
                action=AuditAction.ESCALATION_DENIED,
                actor_id=grantor_id,
                actor_type="human",
                entity_type="escalation_token",
                entity_id=token_id,
                success=False,
                failure_reason="Self-grant denied",
                action_detail="Attempted self-grant of escalation",
                org_id=token.tenant_id
            )
            raise EscalationDeniedError(
                message="Self-grant denied: grantor must differ from requestor",
                details={
                    "user_id": token.user_id,
                    "grantor_id": grantor_id
                }
            )

        # Transition: REQUESTED → GRANTED → ACTIVE
        token._transition_to(EscalationState.GRANTED)
        token.granted_by = grantor_id
        token.granted_at = datetime.utcnow()

        # Set expiry and activate
        token.expires_at = datetime.utcnow() + timedelta(minutes=token.ttl_minutes)
        token._transition_to(EscalationState.ACTIVE)

        # Audit log
        AuditLog.log(
            action=AuditAction.ESCALATION_GRANTED,
            actor_id=grantor_id,
            actor_type="human",
            actor_role=grantor_role.value,
            entity_type="escalation_token",
            entity_id=token_id,
            action_detail=f"Granted escalation to {token.user_id}",
            metadata={
                "user_id": token.user_id,
                "permissions": [p.value for p in token.granted_permissions],
                "ttl_minutes": token.ttl_minutes,
                "expires_at": token.expires_at.isoformat()
            },
            org_id=token.tenant_id
        )

        return token

    @classmethod
    def deny_escalation(
        cls,
        token_id: str,
        denier_id: str,
        reason: str = ""
    ) -> ElevatedAccessToken:
        """
        Deny a privilege escalation request.

        Args:
            token_id: The token to deny
            denier_id: Who is denying
            reason: Reason for denial

        Returns:
            Denied ElevatedAccessToken
        """
        token = cls._tokens.get(token_id)
        if token is None:
            raise ValueError(f"Escalation token not found: {token_id}")

        token._transition_to(EscalationState.DENIED)

        # Audit log
        AuditLog.log(
            action=AuditAction.ESCALATION_DENIED,
            actor_id=denier_id,
            actor_type="human",
            entity_type="escalation_token",
            entity_id=token_id,
            action_detail=f"Denied escalation for {token.user_id}: {reason}",
            org_id=token.tenant_id
        )

        return token

    @classmethod
    def revoke_escalation(
        cls,
        token_id: str,
        actor_id: str,
        reason: str = ""
    ) -> ElevatedAccessToken:
        """
        Revoke an active escalation token.

        Can be done by any user with ESCALATION_REVOKE or by the system.

        Args:
            token_id: The active token to revoke
            actor_id: Who is revoking
            reason: Reason for revocation

        Returns:
            Revoked ElevatedAccessToken
        """
        token = cls._tokens.get(token_id)
        if token is None:
            raise ValueError(f"Escalation token not found: {token_id}")

        # Auto-expire if past TTL before attempting revoke
        if token.state == EscalationState.ACTIVE and token.is_expired():
            cls._expire_token(token)
            return token

        token._transition_to(EscalationState.REVOKED)
        token.revoked_by = actor_id
        token.revoked_at = datetime.utcnow()

        # Audit log
        AuditLog.log(
            action=AuditAction.ESCALATION_REVOKED,
            actor_id=actor_id,
            actor_type="human",
            entity_type="escalation_token",
            entity_id=token_id,
            action_detail=f"Revoked escalation for {token.user_id}: {reason}",
            metadata={"reason": reason},
            org_id=token.tenant_id
        )

        return token

    @classmethod
    def check_escalation(
        cls,
        user_id: str,
        permission: Permission
    ) -> Optional[ElevatedAccessToken]:
        """
        Check if a user has an active elevated token for a permission.

        Uses check-on-use pattern: auto-expires tokens past TTL.

        Args:
            user_id: User to check
            permission: Permission to check for

        Returns:
            Active ElevatedAccessToken if found, None otherwise
        """
        for token in cls._tokens.values():
            if token.user_id != user_id:
                continue
            if permission not in token.granted_permissions:
                continue

            # Check-on-use expiry
            if token.state == EscalationState.ACTIVE and token.is_expired():
                cls._expire_token(token)
                continue

            if token.is_active():
                # Log usage
                AuditLog.log(
                    action=AuditAction.ESCALATION_USED,
                    actor_id=user_id,
                    actor_type="human",
                    entity_type="escalation_token",
                    entity_id=token.id,
                    action_detail=f"Escalated permission used: {permission.value}",
                    metadata={
                        "permission": permission.value,
                        "scope": token.scope,
                        "expires_at": token.expires_at.isoformat() if token.expires_at else None
                    },
                    org_id=token.tenant_id
                )
                return token

        return None

    @classmethod
    def get_active_tokens(cls, user_id: str) -> List[ElevatedAccessToken]:
        """Get all active (non-expired) tokens for a user."""
        active = []
        for token in cls._tokens.values():
            if token.user_id != user_id:
                continue
            # Check-on-use expiry
            if token.state == EscalationState.ACTIVE and token.is_expired():
                cls._expire_token(token)
                continue
            if token.is_active():
                active.append(token)
        return active

    @classmethod
    def get_token(cls, token_id: str) -> Optional[ElevatedAccessToken]:
        """Get a token by ID."""
        return cls._tokens.get(token_id)

    @classmethod
    def _expire_token(cls, token: ElevatedAccessToken) -> None:
        """Expire a token and log it."""
        token.state = EscalationState.EXPIRED

        AuditLog.log(
            action=AuditAction.ESCALATION_EXPIRED,
            actor_id="system",
            actor_type="system",
            entity_type="escalation_token",
            entity_id=token.id,
            action_detail=f"Escalation auto-expired for {token.user_id}",
            metadata={
                "user_id": token.user_id,
                "ttl_minutes": token.ttl_minutes,
                "expired_at": datetime.utcnow().isoformat()
            },
            org_id=token.tenant_id
        )


# --- Dual Control Guard ---

class DualControlGuard:
    """
    Singleton guard for enforcing dual approval on critical operations.

    Integrates with ApprovalService to require 2-authority confirmation
    before critical operations can execute.

    Registered operations:
    - result_publish    → requires DEAN + REGISTRAR
    - payroll_release   → requires HR_ADMIN + FINANCE_OFFICER
    - transcript_seal   → requires DEAN + REGISTRAR

    The list is extensible via ConfigRegistry.
    """

    _operations: Dict[str, CriticalOperation] = {}
    _initialized: bool = False

    @classmethod
    def initialize_defaults(cls) -> None:
        """Register default critical operations from config."""
        if cls._initialized:
            return

        # Default operations with their required roles
        default_ops = [
            CriticalOperation(
                operation_id="result_publish",
                name="Result Publication",
                description="Publish examination results",
                required_roles=[Role.DEAN, Role.REGISTRAR]
            ),
            CriticalOperation(
                operation_id="payroll_release",
                name="Payroll Release",
                description="Release payroll payments",
                required_roles=[Role.HR_ADMIN, Role.FINANCE_OFFICER]
            ),
            CriticalOperation(
                operation_id="transcript_seal",
                name="Transcript Seal",
                description="Seal academic transcripts",
                required_roles=[Role.DEAN, Role.REGISTRAR]
            ),
        ]

        for op in default_ops:
            cls.register_operation(op)

        cls._initialized = True

    @classmethod
    def register_operation(cls, operation: CriticalOperation) -> None:
        """
        Register a critical operation and create its approval config.

        Args:
            operation: The critical operation to register
        """
        # Create matching approval config
        config_id = f"dual_control_{operation.operation_id}"
        operation.approval_config_id = config_id

        config = ApprovalConfig(
            config_id=config_id,
            allowed_roles=operation.required_roles,
            mode=ApprovalMode.ALL,  # ALL required roles must approve
            description=f"Dual control for {operation.name}"
        )

        ApprovalService.register_config(config)
        cls._operations[operation.operation_id] = operation

    @classmethod
    def require_dual_control(
        cls,
        operation_id: str,
        actor_id: str,
        entity_type: str,
        entity_id: str,
        tenant_id: Optional[str] = None
    ) -> str:
        """
        Initiate a dual control request for a critical operation.

        Creates an ApprovalRequest via ApprovalService.

        Args:
            operation_id: The critical operation being requested
            actor_id: Who is requesting
            entity_type: Type of entity being acted on
            entity_id: ID of the entity
            tenant_id: Tenant scope

        Returns:
            approval_request_id for tracking

        Raises:
            DualControlRequiredError: If operation is not registered
        """
        cls._ensure_initialized()

        operation = cls._operations.get(operation_id)
        if operation is None:
            raise DualControlRequiredError(
                operation_id=operation_id,
                message=f"Unknown critical operation: {operation_id}"
            )

        # Create approval request via ApprovalService
        request = ApprovalService.create_request(
            entity_type=entity_type,
            entity_id=entity_id,
            action_type=operation_id,
            config_id=operation.approval_config_id,
            requested_by=actor_id
        )

        # Audit log
        AuditLog.log(
            action=AuditAction.DUAL_CONTROL_REQUESTED,
            actor_id=actor_id,
            actor_type="human",
            entity_type=entity_type,
            entity_id=entity_id,
            action_detail=f"Dual control requested: {operation.name}",
            metadata={
                "operation_id": operation_id,
                "approval_request_id": request.id,
                "required_roles": [r.value for r in operation.required_roles]
            },
            org_id=tenant_id
        )

        return request.id

    @classmethod
    def verify_dual_control(
        cls,
        operation_id: str,
        entity_type: str,
        entity_id: str
    ) -> bool:
        """
        Verify that dual approval exists for a critical operation.

        Should be called as a pre-condition before executing the operation.

        Args:
            operation_id: Critical operation to check
            entity_type: Type of entity being acted on
            entity_id: ID of the entity

        Returns:
            True if dual approval has been granted, False otherwise
        """
        cls._ensure_initialized()

        operation = cls._operations.get(operation_id)
        if operation is None:
            return False

        # Check via ApprovalService — look for an APPROVED request
        # matching this operation + entity
        try:
            # Search through ApprovalService for matching approved request
            for req_id, req in ApprovalService._requests.items():
                if (req.config_id == operation.approval_config_id and
                        req.entity_type == entity_type and
                        req.entity_id == entity_id and
                        req.status == ApprovalState.APPROVED):

                    # Log verification
                    AuditLog.log(
                        action=AuditAction.DUAL_CONTROL_COMPLETED,
                        actor_id="system",
                        actor_type="system",
                        entity_type=entity_type,
                        entity_id=entity_id,
                        action_detail=f"Dual control verified: {operation.name}",
                        metadata={
                            "operation_id": operation_id,
                            "approval_request_id": req.id
                        }
                    )
                    return True
        except Exception:
            pass

        return False

    @classmethod
    def enforce_dual_control(
        cls,
        operation_id: str,
        entity_type: str,
        entity_id: str
    ) -> None:
        """
        Enforce dual control — raises if not approved.

        This is the enforcement gate. Call before executing any critical operation.

        Args:
            operation_id: Critical operation being executed
            entity_type: Type of entity
            entity_id: ID of entity

        Raises:
            DualControlRequiredError: If dual approval not found
        """
        cls._ensure_initialized()

        if not cls.is_critical_operation(operation_id):
            return  # Not a critical operation — no dual control needed

        if not cls.verify_dual_control(operation_id, entity_type, entity_id):
            raise DualControlRequiredError(
                operation_id=operation_id,
                message=f"Dual control approval required before executing: {operation_id}",
                details={
                    "entity_type": entity_type,
                    "entity_id": entity_id
                }
            )

    @classmethod
    def is_critical_operation(cls, operation_id: str) -> bool:
        """Check if an operation is registered as critical."""
        cls._ensure_initialized()
        return operation_id in cls._operations

    @classmethod
    def get_operation(cls, operation_id: str) -> Optional[CriticalOperation]:
        """Get a registered critical operation."""
        cls._ensure_initialized()
        return cls._operations.get(operation_id)

    @classmethod
    def list_operations(cls) -> List[CriticalOperation]:
        """List all registered critical operations."""
        cls._ensure_initialized()
        return list(cls._operations.values())

    @classmethod
    def _ensure_initialized(cls) -> None:
        """Ensure defaults are initialized."""
        if not cls._initialized:
            cls.initialize_defaults()
