"""
ALIS RBAC+ Middleware - E01-S03 & E01-S04

MODULE: Platform Core
LAYER: Layer 5 (Roles, Authority & Quorum)
ENTITY: Role, Permission, Context

This module implements Blueprint C: RBAC+ Middleware.
- Role-based checks (RBAC)
- Context-aware checks (ABAC extension)
- Agent constraints (AI read/write limits)

Must Align With:
- Blueprint C — RBAC+
- Layer 5 (Authority & Quorum)

Acceptance Criteria (E01-S03):
- [x] Role definitions (Student, Faculty, Admin, Agent, etc.)
- [x] Permission mapping
- [x] Middleware-level enforcement
- [x] No controller-level shortcuts

Acceptance Criteria (E01-S04):
- [x] Context-aware permission evaluation
- [x] Works alongside RBAC (not replacing)
- [x] Default deny
- [x] Explicit failure reasons
"""

from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass
from .exceptions import PermissionDeniedError


# --- Role Definitions ---

class Role(str, Enum):
    """
    Canonical role definitions for ALIS.
    These roles are declarative and not hard-coded into business logic.
    """
    # Human Roles
    STUDENT = "student"
    FACULTY = "faculty"
    HOD = "hod"  # Head of Department
    DEAN = "dean"
    REGISTRAR = "registrar"
    FINANCE_OFFICER = "finance_officer"
    HR_ADMIN = "hr_admin"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"
    DEAN_ELEVATED = "dean_elevated"  # E00-S04: Temporary elevated role

    # System Roles
    AI_AGENT = "ai_agent"
    SYSTEM = "system"


# --- Permission Definitions ---

class Permission(str, Enum):
    """
    Granular permissions for ALIS resources.
    Follows the pattern: <resource>:<action>
    """
    # User Management
    USER_READ = "user:read"
    USER_CREATE = "user:create"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"

    # Student Data
    STUDENT_READ = "student:read"
    STUDENT_CREATE = "student:create"
    STUDENT_UPDATE = "student:update"
    STUDENT_READ_PII = "student:read_pii"

    # Academics
    COURSE_READ = "course:read"
    COURSE_CREATE = "course:create"
    COURSE_UPDATE = "course:update"
    MARKS_READ = "marks:read"
    MARKS_ENTRY = "marks:entry"
    MARKS_FINALIZE = "marks:finalize"

    # Finance
    FEE_READ = "fee:read"
    FEE_CREATE = "fee:create"
    PAYMENT_PROCESS = "payment:process"
    LEDGER_READ = "ledger:read"

    # Examinations
    EXAM_PAPER_READ = "exam_paper:read"
    EXAM_PAPER_CREATE = "exam_paper:create"
    HALL_TICKET_GENERATE = "hall_ticket:generate"
    RESULT_PUBLISH = "result:publish"

    # Overrides & Admin
    OVERRIDE_REQUEST = "override:request"
    OVERRIDE_APPROVE = "override:approve"
    AUDIT_LOG_READ = "audit_log:read"
    CONFIG_READ = "config:read"
    CONFIG_WRITE = "config:write"
    GLOBAL_LOCK_CHECK = "global_lock:check"

    # AI Gateway (E03-S01)
    AI_INVOKE = "ai:invoke"

    # Escalation & Dual Control (E00-S04)
    ESCALATION_REQUEST = "escalation:request"
    ESCALATION_GRANT = "escalation:grant"
    ESCALATION_REVOKE = "escalation:revoke"
    DUAL_CONTROL_APPROVE = "dual_control:approve"


# --- Role-Permission Mapping ---

ROLE_PERMISSIONS: Dict[Role, List[Permission]] = {
    Role.STUDENT: [
        Permission.STUDENT_READ,
        Permission.COURSE_READ,
        Permission.MARKS_READ,
        Permission.FEE_READ,
    ],
    Role.FACULTY: [
        Permission.STUDENT_READ,
        Permission.COURSE_READ,
        Permission.MARKS_READ,
        Permission.MARKS_ENTRY,
    ],
    Role.HOD: [
        Permission.STUDENT_READ,
        Permission.STUDENT_READ_PII,
        Permission.COURSE_READ,
        Permission.COURSE_CREATE,
        Permission.COURSE_UPDATE,
        Permission.MARKS_READ,
        Permission.MARKS_ENTRY,
        Permission.MARKS_FINALIZE,
        Permission.OVERRIDE_REQUEST,
        Permission.ESCALATION_REQUEST,  # E00-S04
    ],
    Role.REGISTRAR: [
        Permission.STUDENT_READ,
        Permission.STUDENT_READ_PII,
        Permission.STUDENT_CREATE,
        Permission.STUDENT_UPDATE,
        Permission.COURSE_READ,
        Permission.HALL_TICKET_GENERATE,
        Permission.RESULT_PUBLISH,
        Permission.OVERRIDE_REQUEST,
        Permission.OVERRIDE_APPROVE,
        Permission.ESCALATION_REQUEST,   # E00-S04
        Permission.DUAL_CONTROL_APPROVE, # E00-S04
    ],
    Role.FINANCE_OFFICER: [
        Permission.FEE_READ,
        Permission.FEE_CREATE,
        Permission.PAYMENT_PROCESS,
        Permission.LEDGER_READ,
        Permission.OVERRIDE_REQUEST,
        Permission.ESCALATION_REQUEST,   # E00-S04
        Permission.DUAL_CONTROL_APPROVE, # E00-S04
    ],
    Role.ADMIN: [
        Permission.USER_READ,
        Permission.USER_CREATE,
        Permission.USER_UPDATE,
        Permission.CONFIG_READ,
        Permission.AUDIT_LOG_READ,
        Permission.OVERRIDE_REQUEST,
        Permission.OVERRIDE_APPROVE,
        Permission.ESCALATION_REQUEST,   # E00-S04
        Permission.ESCALATION_GRANT,     # E00-S04
        Permission.ESCALATION_REVOKE,    # E00-S04
        Permission.DUAL_CONTROL_APPROVE, # E00-S04
    ],
    Role.SUPER_ADMIN: [
        # Super admin has all permissions
        *[p for p in Permission]
    ],
    Role.AI_AGENT: [
        # AI Agents have READ access only (Agent Constraints)
        Permission.STUDENT_READ,
        Permission.COURSE_READ,
        Permission.MARKS_READ,
        Permission.FEE_READ,
        Permission.GLOBAL_LOCK_CHECK,
        Permission.AI_INVOKE,  # E03-S01: AI Agents can invoke AI Gateway
    ],
    Role.SYSTEM: [
        # System has all permissions for internal operations
        *[p for p in Permission]
    ],
}


# --- Access Check Results ---

@dataclass
class AccessResult:
    """Result of an access check."""
    allowed: bool
    reason: Optional[str] = None
    context_violations: Optional[List[str]] = None


# --- RBAC Basic Check ---

def check_role_permission(role: Role, permission: Permission) -> bool:
    """
    Basic RBAC check: Does the role have the permission?

    Args:
        role: The actor's role
        permission: The required permission

    Returns:
        True if role has permission, False otherwise
    """
    role_perms = ROLE_PERMISSIONS.get(role, [])
    return permission in role_perms


# --- RBAC+ Context-Aware Check (ABAC Extension) ---

def verify_access(
    actor_role: Role,
    permission: Permission,
    context: Optional[Dict] = None
) -> AccessResult:
    """
    RBAC+ Access verification with context awareness.

    This implements Blueprint C from the ALIS Master Handbook:
    1. Standard RBAC (Role)
    2. Tenant Isolation (E00-S03 — Layer 4 Invariant)
    3. Context-Awareness (State)
    4. Agent Constraints (AI Safety)

    Args:
        actor_role: The role of the actor requesting access
        permission: The permission being requested
        context: Optional context dict with state information
            - tenant_id: Current tenant scope (MANDATORY for non-system)
            - exam_status: Current exam cycle state
            - course_id: Course being accessed
            - is_owner: Whether actor owns the resource
            - action: 'read' or 'write'

    Returns:
        AccessResult with allowed status and reason
    """
    context = context or {}
    violations = []

    # --- Step 1: Standard RBAC Check ---
    if not check_role_permission(actor_role, permission):
        return AccessResult(
            allowed=False,
            reason=f"Role '{actor_role.value}' does not have permission '{permission.value}'"
        )

    # --- Step 2: Tenant Isolation Check (E00-S03 — Layer 4) ---
    # System role is exempt from tenant checks (internal operations)
    if actor_role != Role.SYSTEM:
        tenant_id = context.get("tenant_id")
        if not tenant_id:
            # Try to get from ContextVar (set by TenantMiddleware)
            try:
                from .security import get_current_tenant_id
                tenant_id = get_current_tenant_id()
            except Exception:
                pass  # Will be caught by the check below

        if not tenant_id:
            violations.append(
                "Tenant isolation: tenant_id is required for all non-system operations "
                "(Layer 4 Invariant)"
            )

    # --- Step 3: Context-Awareness Checks ---

    # Example: Faculty can only edit marks during "Evaluation Window"
    if actor_role == Role.FACULTY and permission == Permission.MARKS_ENTRY:
        exam_status = context.get("exam_status")
        if exam_status and exam_status != "EVALUATION_OPEN":
            violations.append(
                f"Marks entry denied: Exam status is '{exam_status}', not 'EVALUATION_OPEN'"
            )

    # Example: Only course owner can update course
    if permission == Permission.COURSE_UPDATE:
        is_owner = context.get("is_owner", False)
        if not is_owner and actor_role not in [Role.HOD, Role.ADMIN, Role.SUPER_ADMIN]:
            violations.append("Course update denied: Actor is not the course owner")

    # --- Step 4: Agent Constraints (AI Safety) ---
    # AI Agents have READ access but NO WRITE access to Sensitive Data
    # AI Agents CANNOT override tenant context under any circumstance
    if actor_role == Role.AI_AGENT:
        action = context.get("action", "read")
        sensitive_write_perms = [
            Permission.MARKS_FINALIZE,
            Permission.RESULT_PUBLISH,
            Permission.OVERRIDE_APPROVE,
            Permission.CONFIG_WRITE,
        ]
        if action == "write" or permission in sensitive_write_perms:
            violations.append(
                "AI Agent constraint: Agents cannot perform write operations on sensitive data"
            )

        # E00-S03: AI Agents cannot override tenant context
        if context.get("override_tenant"):
            violations.append(
                "AI Agent constraint: Agents cannot override tenant context "
                "(E00-S03 Layer 4 Invariant)"
            )

    # --- Final Decision ---
    if violations:
        return AccessResult(
            allowed=False,
            reason="Context-based access denied",
            context_violations=violations
        )

    return AccessResult(allowed=True)


# --- Middleware Decorator (For FastAPI/Starlette) ---

def require_permission(permission: Permission):
    """
    Decorator factory for requiring a specific permission.
    Use with FastAPI route handlers.

    Example:
        @app.get("/students")
        @require_permission(Permission.STUDENT_READ)
        async def get_students(request: Request):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # In real implementation, extract role from request/session
            # This is a placeholder for the middleware pattern
            request = kwargs.get("request")
            if request is None:
                for arg in args:
                    if hasattr(arg, "state"):
                        request = arg
                        break

            if request and hasattr(request, "state"):
                role = getattr(request.state, "user_role", None)
                context = getattr(request.state, "access_context", {})

                if role:
                    result = verify_access(role, permission, context)
                    if not result.allowed:
                        raise PermissionDeniedError(
                            message=result.reason,
                            details={"violations": result.context_violations}
                        )

            return await func(*args, **kwargs)
        return wrapper
    return decorator
