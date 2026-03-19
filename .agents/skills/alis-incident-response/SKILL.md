---
name: alis-incident-response
description: |
  ALIS incident response plans and lockdown procedures. Use when implementing or triggering security
  incident response, system lockdown, session revocation, AI disablement, escalation procedures, or
  reviewing incident recovery processes. Covers LockdownManager, LOCKDOWN_IMMUNE_ROLES, lockdown
  activation/deactivation, blocked attempts logging, mass token revocation, AI pause, escalation
  service, dual control approvals, post-incident recovery. Trigger keywords: incident, lockdown,
  security incident, LockdownManager, breach, compromise, block writes, revoke sessions, AI pause,
  escalation, dual control, emergency, system compromise, attack, intrusion, unauthorized access,
  incident response, recovery, deactivate lockdown, security event, ADMIN immune, session revoke.
---

# ALIS Incident Response Plans

You are the ALIS Security Incident Response Expert. ALIS has built-in lockdown and escalation
infrastructure — know how to activate it, what it does, and how to recover.

## Incident Severity Levels

| Level | Description | Response |
|---|---|---|
| P1 — Critical | Active breach, data exfiltration, AI compromise | Immediate full lockdown |
| P2 — High | Unauthorized access pattern, injection attempts | Targeted module lock + escalation |
| P3 — Medium | Anomalous behavior, failed auth spike | Heightened monitoring + dual control |
| P4 — Low | Policy violation, single failed override | Review queue + HITL escalation |

## Full System Lockdown (P1 — Critical)

```python
from server.core.lockdown import LockdownManager

# ACTIVATE — blocks all non-admin writes and AI invocations, revokes non-admin sessions
event = LockdownManager.activate(
    actor_id=admin_actor_id,
    actor_role="super_admin",    # Must be ADMIN, SUPER_ADMIN, or SYSTEM
    reason="Suspected data breach — unauthorized bulk export detected at 03:14 UTC",
    metadata={
        "detected_by": "anomaly_detection_celery",
        "affected_tenant": org_id,
        "indicator": "bulk_export_1500_records",
    },
)
# event.sessions_revoked — number of sessions invalidated
# Automatically logged to immutable AuditLedger (LOCKDOWN_ACTIVATED)
```

### What Lockdown Does

1. **Write Gate (Layer 4)**: All `execute_transaction` calls from non-immune roles raise `LockdownActiveError`
2. **AI Pause (§27)**: All `AIGateway.invoke()` calls are blocked — returns error immediately
3. **Session Revocation**: All non-admin JWT sessions are invalidated (forced re-login on next request)
4. **Audit Trail**: Every blocked attempt is logged to the immutable ledger (`LOCKDOWN_WRITE_BLOCKED` / `LOCKDOWN_AI_BLOCKED`)

### Roles Immune to Lockdown

```python
from server.core.lockdown import LOCKDOWN_IMMUNE_ROLES
# frozenset({Role.ADMIN, Role.SUPER_ADMIN, Role.SYSTEM})
```

ADMIN and SUPER_ADMIN retain full access during lockdown to perform investigation and recovery.
Module managers, faculty, staff, students — ALL lose write access.

## Deactivating Lockdown (Post-Incident Recovery)

```python
# Only deactivate after:
# 1. Root cause identified
# 2. Affected systems patched or isolated
# 3. Dual-control approval from second SUPER_ADMIN

deactivation_event = LockdownManager.deactivate(
    actor_id=super_admin_id,
    actor_role="super_admin",
    reason="Root cause identified: SQL injection via unvalidated report filter. "
           "Patch deployed. Audit complete. Approved by second SUPER_ADMIN.",
    metadata={
        "patch_version": "2026.03.06-hotfix-1",
        "second_approver": second_super_admin_id,
        "incident_duration_minutes": 47,
    },
)
# Logged to AuditLedger (LOCKDOWN_DEACTIVATED)
```

## Checking Lockdown Status (In Middleware / Before Writes)

```python
from server.core.lockdown import LockdownManager
from server.core.rbac import Role

is_locked = LockdownManager.is_locked()
actor_role = Role("admin")

if is_locked and actor_role not in LOCKDOWN_IMMUNE_ROLES:
    # Log the blocked attempt
    LockdownManager.log_blocked_attempt(
        actor_id=actor_id,
        actor_role=actor_role.value,
        operation="execute_transaction",
        resource="students",
    )
    raise LockdownActiveError("System is in lockdown. Contact administrator.")
```

## Scoped Role Revocation (P2 — Targeted Access Removal)

When an account is compromised but full lockdown isn't warranted, revoke only the
role grants scoped to the affected resource rather than locking down the whole system.

```python
from server.db_service import execute_transaction, execute_query

# Find all role grants for a compromised user account
grants = execute_query(
    """
    SELECT id, role_id, scope_type, scope_ref
    FROM role_assignments
    WHERE org_id = %s AND user_id = %s AND (expires_at IS NULL OR expires_at > NOW())
    """,
    (org_id, compromised_user_id),
    tenant_id=org_id,
)

# Revoke all grants for that user (full account revocation)
execute_transaction(
    [("DELETE FROM role_assignments WHERE org_id = %s AND user_id = %s",
      (org_id, compromised_user_id))],
    tenant_id=org_id,
)

# — OR — revoke only a specific scope (e.g., FINANCE module access)
execute_transaction(
    [("DELETE FROM role_assignments WHERE org_id = %s AND user_id = %s AND scope_type = %s",
      (org_id, compromised_user_id, "DEPARTMENT"))],
    tenant_id=org_id,
)
```

Always log the revocation:

```python
AuditLedger.log(
    action=AuditAction.UPDATE,
    actor_id=admin_actor_id,
    actor_role="super_admin",
    entity_type="role_assignments",
    entity_id=compromised_user_id,
    tenant_id=org_id,
    metadata={
        "reason": "Account compromised — role grants revoked",
        "revoked_grants": [g["id"] for g in grants],
        "scope_types": list({g["scope_type"] for g in grants}),
    },
)
```

## Module-Level Escalation (P2–P3)

For incidents affecting a specific module without full system compromise:

```python
from server.core.escalation import EscalationService

# Escalate to module manager + ADMIN for review
escalation = EscalationService.request_escalation(
    actor_id=actor_id,
    actor_role=actor_role,
    reason="Repeated OVERRIDE_APPROVE attempts by unrecognized IP block",
    affected_module="M3",           # Examinations
    escalation_level="ADMIN",
    metadata={
        "ip_block": "192.168.1.0/24",
        "attempts": 47,
        "time_window": "5 minutes",
    },
)
# Escalation routed to ADMIN review queue
# Logged to AuditLedger (ESCALATION_REQUESTED)
```

## Dual Control Approval (High-Risk Operations)

For operations requiring two independent approvals (P2 prevention):

```python
from server.core.approvals import ApprovalService

# Trigger dual-control for sensitive config change
approval_req = ApprovalService.create_dual_control_request(
    entity_type="ConfigChange",
    entity_id=config_change_id,
    operation="MODEL_UPGRADE",
    required_approvers=2,
    approver_roles=["super_admin", "admin"],
    org_id=org_id,
    initiator_id=actor_id,
    metadata={"change_description": "Upgrade LLM model to v2"},
)
# Second SUPER_ADMIN must independently approve before change takes effect
# Logged: DUAL_CONTROL_REQUESTED → DUAL_CONTROL_COMPLETED
```

## AI Compromise Response (§27 — AI Disablement Safeguard)

If AI is suspected of producing adversarial or injected outputs:

```python
# 1. Activate lockdown (blocks all AI invocations immediately)
LockdownManager.activate(actor_id=..., reason="Suspected prompt injection attack")

# 2. Query recent AI invocations for injection markers
suspicious = AuditLedger.query(
    tenant_id=org_id,
    action=AuditAction.AI_PROMPT_INJECTION,
    limit=100,
)

# 3. Review and quarantine affected entity decisions
# Any decision made by AI in the window must be escalated to human review
# Use HITL retroactively for all AGENT_DECISION entries in the time window

# 4. After investigation, rotate Ollama model config in ConfigRegistry
# Do NOT reuse same prompt versions — increment prompt_version

# 5. Deactivate lockdown with dual-control approval
```

## Incident Audit Query Patterns

```python
from server.core.audit import AuditLedger, AuditAction

# Find all lockdown events
lockdowns = AuditLedger.query(
    tenant_id=org_id,
    action=AuditAction.LOCKDOWN_ACTIVATED,
    limit=50,
)

# Find all blocked write attempts during lockdown
blocked = AuditLedger.query(
    tenant_id=org_id,
    action=AuditAction.LOCKDOWN_WRITE_BLOCKED,
    start_time=incident_start,
    end_time=incident_end,
    limit=1000,
)

# Find all override requests (potential privilege abuse)
overrides = AuditLedger.query(
    tenant_id=org_id,
    action=AuditAction.OVERRIDE_REQUESTED,
    limit=200,
)

# Find access denials (unauthorized access attempts)
denials = AuditLedger.query(
    tenant_id=org_id,
    action=AuditAction.ACCESS_DENIED,
    limit=500,
)
```

## Incident Response Runbook

### P1 — Active Breach
1. **T+0**: `LockdownManager.activate()` — SUPER_ADMIN or on-call ADMIN
2. **T+5**: Notify DEAN + Registrar via out-of-band channel (not ALIS — may be compromised)
3. **T+10**: Export audit log for the breach window (`AuditLedger.export_ledger`)
4. **T+15**: Identify affected entity types and scope (org_id, time window)
5. **T+30**: Patch the vulnerability (SQL, injection, auth bypass)
6. **T+60**: Second SUPER_ADMIN reviews patch — dual control deactivation
7. **T+90**: `LockdownManager.deactivate()` — log root cause + remediation
8. **T+120**: Notify affected students/staff if PII was exposed (legal requirement)
9. **T+7d**: Post-incident report filed to `audit_ledger` + regulatory notification if required

### P2 — Unauthorized Access Pattern
1. Block affected user sessions via token revocation
2. Escalate to ADMIN via `EscalationService.request_escalation()`
3. Enable heightened monitoring for affected module
4. Dual-control required for any override operations during investigation

### P3 — Policy Violation / Anomaly
1. Route to HITL review queue for human examination
2. Flag actor for temporary permission reduction via escalation
3. Review and close within 24 hours SLA

## Notification Channels During Incidents

```python
from server.core.notifications.service import NotificationService

# Internal alert to admin team (during lockdown, notifications still work for ADMIN+)
await NotificationService.send_alert(
    recipients=[admin_id, super_admin_id],
    subject="[P1 INCIDENT] System lockdown activated",
    body=f"Reason: {reason}. Locked at {timestamp}. Contact IT immediately.",
    channel="email",
    priority="CRITICAL",
)
```

## Stuck-Event Awareness During Incidents

FINANCE and EXAMINATION domain events use a 30-second Beat task (`retry-stuck-critical-events`)
that resets PROCESSING events older than 2 minutes back to PENDING. During an incident:

- If a Celery worker was compromised, PROCESSING events from that worker may be in a dirty state.
  The Beat task will automatically re-queue them after 2 minutes — **do not manually reset these**
  unless the Beat task is also disabled.
- To check for stuck events during an incident:

```python
from server.db_service import execute_system_query

stuck = execute_system_query(
    """
    SELECT id, event_type, org_id, processing_started_at
    FROM domain_events
    WHERE status = 'PROCESSING'
      AND processing_started_at < NOW() - INTERVAL '2 minutes'
    ORDER BY processing_started_at ASC
    """,
    (),
)
# Investigate each stuck event before the Beat task auto-requeues it
```

## Post-Incident Recovery Checklist

- [ ] Root cause documented in `AuditLedger` (CONFIG_CHANGE action, metadata=incident_report)
- [ ] Patch deployed and tested before deactivation
- [ ] Second SUPER_ADMIN dual-control approval obtained for deactivation
- [ ] Affected user sessions regenerated (force re-login)
- [ ] Tenant encryption key rotated if key material may have been exposed
- [ ] Affected AI invocations reviewed — retroactive HITL applied if needed
- [ ] Prompt/model versions incremented if AI was compromised
- [ ] Regulatory notification sent within 72 hours if REGULATED PII was exposed (GDPR)
- [ ] Post-incident report filed and stored in `generated_documents` (PERMANENT retention)
- [ ] Lockdown deactivation logged with full justification
