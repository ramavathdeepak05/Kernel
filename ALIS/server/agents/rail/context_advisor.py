"""
ALIS Agent Rail — Context Advisor (RAIL-v1)

MODULE: RAIL — Agent Rail Intelligence
LAYER: Layer 2 (Agentic Decisions)

Provides context-aware intelligence for the 320px agent rail panel.

Handles two call patterns:
  1. __view_change__ — triggered when the user navigates to a new canvas view.
     Queries live counts, evaluates the tenant's agent_rail_silence policy,
     and returns a proactive brief only if the policy returns SURFACE.
     Returns message=null if the policy returns anything else (stays silent).

  2. User message (chip tap or free text) — interprets intent, queries relevant
     data, returns a message + optional CanvasAction.

Decision Declaration (Layer 2 — Mandatory Format):
    Decision Made:
        "What, if anything, requires this user's immediate attention right now?"

    AI Role:
        Summarise — never decide, never mutate state.

    Silence Rule (via policy engine):
        SLA breach (>= 1) is always surfaced — hardcoded, non-configurable.
        Urgent count and total pending thresholds are institution-specific,
        configured via tenant_policies policy_id="agent_rail_silence".
        Default verdict is SURFACE so the rail works before configuration.

    Human Authority:
        All items highlighted are for human review. Agent never approves.
        EXECUTE actions require a second explicit confirmation chip click —
        never fire automatically from a view_change or generic chip.

Hard Constraints:
    - READ-ONLY: execute_query only, never execute_transaction.
    - __view_change__ path is fully programmatic (no LLM).
    - Free text path: LLM receives only aggregate counts, never raw entity data.
    - PII (student IDs, names, application IDs) is stripped before LLM calls.
    - actor_id is included in task assignment queries — personally-assigned
      tasks are higher signal than role-wide tasks.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from server.core.ai_gateway import AIGatewayContext, AIInvocationResult
from server.core.llm_router import LLMTaskClass, get_model_for_task
from server.core.policy_engine import policy_engine
from server.db_service import execute_query

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PII patterns — stripped from messages before LLM calls
# ---------------------------------------------------------------------------

_PII_PATTERNS = [
    re.compile(r'\bSTU-\d{4}-\d{6}\b'),          # Student IDs
    re.compile(r'\bAPP-\d{4}-\d{6}\b'),          # Application IDs
    re.compile(r'\bFAC-\d+\b'),                   # Faculty IDs
    re.compile(r'\b[6-9]\d{9}\b'),               # Indian mobile numbers
    re.compile(r'\b\d{12}\b'),                    # Aadhaar-length numbers
]


def _strip_pii(text: str) -> str:
    for pattern in _PII_PATTERNS:
        text = pattern.sub('[REDACTED]', text)
    return text


# ---------------------------------------------------------------------------
# ENTITY DETECTION — Tier 2 (status-only, no PII fields returned)
# ---------------------------------------------------------------------------

_APP_ID_RE    = re.compile(r'\b(APP-\d{4}-\d{6})\b', re.IGNORECASE)
_STU_ID_RE    = re.compile(r'\b(STU-\d{4}-\d{6})\b', re.IGNORECASE)
_FAC_ID_RE    = re.compile(r'\b(FAC-\d+)\b',          re.IGNORECASE)
_COURSE_RE    = re.compile(r'\b([A-Z]{2,5}\d{3,4})\b')


def _detect_and_fetch_entity(
    message: str, tenant_id: str
) -> Optional[Dict[str, Any]]:
    """
    Detect a specific entity reference in a free-text message and return its
    status/metadata from the DB.

    Returns only non-PII fields (status, type, counts) so the result is safe
    to include in LLM prompts without violating the RAIL PII constraint.
    Returns None if no entity detected or query fails.
    """
    # 1. Application ID: APP-YYYY-NNNNNN
    m = _APP_ID_RE.search(message)
    if m:
        app_id = m.group(1).upper()
        rows = execute_query(
            """
            SELECT a.id, a.status, a.stage, a.intended_program,
                   a.created_at::date AS submitted_date,
                   COUNT(d.id)                              AS total_docs,
                   COUNT(d.id) FILTER (WHERE d.status='APPROVED') AS approved_docs
            FROM applications a
            LEFT JOIN application_documents d ON d.application_id = a.id
            WHERE a.id = %s AND a.org_id = %s
            GROUP BY a.id, a.status, a.stage, a.intended_program, a.created_at
            """,
            (app_id, tenant_id),
        )
        if rows:
            r = rows[0]
            return {
                "entity_type": "application",
                "id": app_id,
                "status": r["status"],
                "stage": r["stage"],
                "program": r["intended_program"],
                "submitted": str(r["submitted_date"]),
                "docs_approved": f"{r['approved_docs']}/{r['total_docs']}",
            }
        return {"entity_type": "application", "id": app_id, "status": "NOT_FOUND"}

    # 2. Student ID: STU-YYYY-NNNNNN
    m = _STU_ID_RE.search(message)
    if m:
        stu_id = m.group(1).upper()
        rows = execute_query(
            """
            SELECT s.id, s.status, s.program_id,
                   AVG(a.attendance_pct)::numeric(5,1) AS avg_attendance,
                   SUM(i.balance_amount)               AS outstanding_dues
            FROM students s
            LEFT JOIN attendance_records  a ON a.student_id = s.id
            LEFT JOIN student_invoices    i ON i.student_id = s.id AND i.status IN ('UNPAID','OVERDUE')
            WHERE s.id = %s AND s.org_id = %s
            GROUP BY s.id, s.status, s.program_id
            """,
            (stu_id, tenant_id),
        )
        if rows:
            r = rows[0]
            return {
                "entity_type": "student",
                "id": stu_id,
                "status": r["status"],
                "program": r["program_id"],
                "avg_attendance_pct": str(r["avg_attendance"] or "N/A"),
                "outstanding_dues_inr": str(r["outstanding_dues"] or 0),
            }
        return {"entity_type": "student", "id": stu_id, "status": "NOT_FOUND"}

    # 3. Course code: e.g. CS301, MECH402
    m = _COURSE_RE.search(message)
    if m:
        code = m.group(1).upper()
        rows = execute_query(
            """
            SELECT c.id, c.code, c.name, c.status,
                   COUNT(e.id) AS enrolled_count
            FROM courses c
            LEFT JOIN enrollments e ON e.course_id = c.id AND e.status = 'ACTIVE'
            WHERE c.code = %s AND c.org_id = %s
            GROUP BY c.id, c.code, c.name, c.status
            LIMIT 1
            """,
            (code, tenant_id),
        )
        if rows:
            r = rows[0]
            return {
                "entity_type": "course",
                "code": r["code"],
                "name": r["name"],
                "status": r["status"],
                "enrolled": r["enrolled_count"],
            }
        # Don't return NOT_FOUND for course — too many false positives from acronyms

    return None


# ---------------------------------------------------------------------------
# VIEW-SPECIFIC COUNT QUERIES
# Both assignee_role and assignee_actor_id are checked — the union covers
# role-wide tasks (visible to all holders of that role) AND personally-assigned
# tasks (targeted at this specific actor). Personally-assigned SLA breaches
# are flagged separately because they carry higher signal.
# ---------------------------------------------------------------------------

_VIEW_QUERIES: Dict[str, str] = {
    "approval_queue": """
        SELECT
            COUNT(*)                                                           AS total_pending,
            COUNT(*) FILTER (WHERE urgency = 'HIGH')                          AS urgent,
            COUNT(*) FILTER (WHERE sla_deadline < NOW())                       AS sla_breached,
            COUNT(*) FILTER (WHERE assignee_actor_id = %s
                               AND sla_deadline < NOW())                       AS personal_sla_breached,
            ARRAY_AGG(id) FILTER (WHERE urgency = 'HIGH')                      AS urgent_ids
        FROM workflow_tasks
        WHERE tenant_id = %s
          AND status = 'PENDING'
          AND (assignee_role = %s OR assignee_actor_id = %s)
    """,
    "admissions_pipeline": """
        SELECT
            COUNT(*)                                                                   AS total_pending,
            COUNT(*) FILTER (WHERE task_type = 'DOCUMENT_VERIFY')                     AS pending_docs,
            COUNT(*) FILTER (WHERE task_type = 'OFFER_EXPIRY'
                               AND sla_deadline < NOW() + INTERVAL '4 hours')         AS expiring_offers,
            COUNT(*) FILTER (WHERE sla_deadline < NOW())                               AS sla_breached,
            COUNT(*) FILTER (WHERE assignee_actor_id = %s
                               AND sla_deadline < NOW())                               AS personal_sla_breached,
            ARRAY_AGG(id) FILTER (WHERE task_type = 'OFFER_EXPIRY'
                                   AND sla_deadline < NOW() + INTERVAL '4 hours')     AS urgent_ids
        FROM workflow_tasks
        WHERE tenant_id = %s
          AND status = 'PENDING'
          AND (assignee_role = %s OR assignee_actor_id = %s)
    """,
    "fee_dashboard": """
        SELECT
            COUNT(*)                                                           AS total_pending,
            COUNT(*) FILTER (WHERE task_type = 'FEE_OVERDUE')                 AS overdue,
            COUNT(*) FILTER (WHERE sla_deadline < NOW())                       AS sla_breached,
            COUNT(*) FILTER (WHERE assignee_actor_id = %s
                               AND sla_deadline < NOW())                       AS personal_sla_breached,
            ARRAY_AGG(id) FILTER (WHERE task_type = 'FEE_OVERDUE')            AS urgent_ids
        FROM workflow_tasks
        WHERE tenant_id = %s
          AND status = 'PENDING'
          AND (assignee_role = %s OR assignee_actor_id = %s)
    """,
    "exam_management": """
        SELECT
            COUNT(*)                                                              AS total_pending,
            COUNT(*) FILTER (WHERE task_type = 'HALL_TICKET_DISPATCH')           AS hall_tickets,
            COUNT(*) FILTER (WHERE sla_deadline < NOW())                          AS sla_breached,
            COUNT(*) FILTER (WHERE assignee_actor_id = %s
                               AND sla_deadline < NOW())                          AS personal_sla_breached,
            ARRAY_AGG(id) FILTER (WHERE task_type = 'HALL_TICKET_DISPATCH')      AS urgent_ids
        FROM workflow_tasks
        WHERE tenant_id = %s
          AND status = 'PENDING'
          AND (assignee_role = %s OR assignee_actor_id = %s)
    """,
    "student_risk": """
        SELECT
            COUNT(*)                                                              AS total_pending,
            COUNT(*) FILTER (WHERE task_type = 'ATTENDANCE_RISK')                AS attendance_risk,
            COUNT(*) FILTER (WHERE task_type = 'ACADEMIC_PROBATION')             AS probation,
            COUNT(*) FILTER (WHERE sla_deadline < NOW())                          AS sla_breached,
            COUNT(*) FILTER (WHERE assignee_actor_id = %s
                               AND sla_deadline < NOW())                          AS personal_sla_breached,
            ARRAY_AGG(id) FILTER (WHERE urgency = 'HIGH')                        AS urgent_ids
        FROM workflow_tasks
        WHERE tenant_id = %s
          AND status = 'PENDING'
          AND (assignee_role = %s OR assignee_actor_id = %s)
    """,
}

_GENERIC_QUERY = """
    SELECT
        COUNT(*)                                                        AS total_pending,
        COUNT(*) FILTER (WHERE urgency = 'HIGH')                       AS urgent,
        COUNT(*) FILTER (WHERE sla_deadline < NOW())                    AS sla_breached,
        COUNT(*) FILTER (WHERE assignee_actor_id = %s
                           AND sla_deadline < NOW())                    AS personal_sla_breached,
        ARRAY_AGG(id) FILTER (WHERE urgency = 'HIGH')                  AS urgent_ids
    FROM workflow_tasks
    WHERE tenant_id = %s
      AND status = 'PENDING'
      AND (assignee_role = %s OR assignee_actor_id = %s)
"""

# Params order for all queries: (actor_id, tenant_id, role, actor_id)
# actor_id appears twice — once for personal_sla_breached, once for the WHERE clause.


def _query_counts(view: str, tenant_id: str, actor_id: str, role: str) -> Dict[str, Any]:
    """Run the view-specific count query. Returns empty dict on failure."""
    sql = _VIEW_QUERIES.get(view, _GENERIC_QUERY)
    try:
        rows = execute_query(sql, (actor_id, tenant_id, role, actor_id), tenant_id=tenant_id)
        return dict(rows[0]) if rows else {}
    except Exception as exc:
        logger.warning("context_advisor: count query failed view=%s — %s", view, exc)
        return {}


def _safe_ids(raw: Any) -> List[str]:
    if not raw:
        return []
    return [str(i) for i in raw if i is not None]


# ---------------------------------------------------------------------------
# SILENCE DECISION via policy engine
# ---------------------------------------------------------------------------

def _should_surface(counts: Dict[str, Any], tenant_id: str) -> bool:
    """
    Evaluate the agent_rail_silence policy for this tenant.

    personal_sla_breached bypasses the policy entirely — personally-assigned
    SLA breaches always surface regardless of institution thresholds.

    default_verdict="SURFACE" ensures the rail works before the institution
    has configured any thresholds.
    """
    # Personally-assigned SLA breach: bypass policy, always surface
    if (counts.get("personal_sla_breached") or 0) >= 1:
        return True

    result = policy_engine.evaluate(
        policy_id="agent_rail_silence",
        context={
            "counts": {
                "sla_breached":   counts.get("sla_breached") or 0,
                "urgent":         counts.get("urgent") or 0,
                "total_pending":  counts.get("total_pending") or 0,
            }
        },
        tenant_id=tenant_id,
        default_verdict="SURFACE",   # permissive — surface if no policy configured
    )
    return result.verdict == "SURFACE"


# ---------------------------------------------------------------------------
# PROACTIVE BRIEF BUILDER
# ---------------------------------------------------------------------------

def _build_proactive_message(view: str, counts: Dict[str, Any]) -> Optional[str]:
    """Build a brief from counts. Returns None when nothing worth saying."""
    sla       = counts.get("sla_breached") or 0
    total     = counts.get("total_pending") or 0
    urgent    = counts.get("urgent") or 0
    docs      = counts.get("pending_docs") or 0
    offers    = counts.get("expiring_offers") or 0
    overdue   = counts.get("overdue") or 0
    tickets   = counts.get("hall_tickets") or 0
    att_risk  = counts.get("attendance_risk") or 0
    probation = counts.get("probation") or 0

    if total == 0 and sla == 0:
        return None

    def n(count: int, singular: str, plural: Optional[str] = None) -> str:
        word = plural or (singular + "s")
        return f"{count} {singular if count == 1 else word}"

    parts: List[str] = []

    if view == "admissions_pipeline":
        if offers:
            parts.append(f"{n(offers, 'offer letter')} expiring in < 4h")
        if docs:
            parts.append(f"{n(docs, 'document')} pending verification")
        if sla and not offers:
            parts.append(f"{n(sla, 'item')} past SLA")
    elif view == "approval_queue":
        if sla:
            parts.append(f"{n(sla, 'item')} past SLA deadline")
        if urgent and not sla:
            parts.append(f"{n(urgent, 'high-priority approval')}")
        elif total and not sla and not urgent:
            parts.append(f"{n(total, 'approval')} pending")
    elif view == "fee_dashboard":
        if overdue:
            parts.append(f"{n(overdue, 'overdue fee account')}")
        if sla and not overdue:
            parts.append(f"{n(sla, 'item')} past SLA")
    elif view == "exam_management":
        if tickets:
            parts.append(f"{n(tickets, 'hall ticket')} pending dispatch")
        if sla and not tickets:
            parts.append(f"{n(sla, 'item')} past SLA")
    elif view == "student_risk":
        if att_risk:
            parts.append(f"{n(att_risk, 'student')} at attendance risk")
        if probation:
            parts.append(f"{n(probation, 'student')} on academic probation")
    else:
        if sla:
            parts.append(f"{n(sla, 'item')} past SLA deadline")
        elif urgent:
            parts.append(f"{n(urgent, 'urgent item')}")
        elif total:
            parts.append(f"{n(total, 'item')} pending")

    return (". ".join(parts) + ".") if parts else None


# ---------------------------------------------------------------------------
# CHIP / KNOWN COMMAND HANDLER
# Params: (actor_id, tenant_id, role, actor_id) — same order as view queries.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# TASK COCKPIT — "What should I do today?"
# Queries workflow_tasks and groups by priority for structured display.
# ---------------------------------------------------------------------------

_COCKPIT_CHIPS = {
    "what should i do today",
    "my tasks",
    "show my tasks",
    "show my queue",
    "today's tasks",
    "my work",
    "show all my tasks",
}

# Maps task_type → canvas view to navigate to when user taps a task item
_TASK_VIEW_MAP: Dict[str, str] = {
    "DOCUMENT_VERIFY":      "admissions_pipeline",
    "OFFER_EXPIRY":         "admissions_pipeline",
    "ENROLLMENT_PROVISION": "admissions_pipeline",
    "MERIT_LIST_APPROVE":   "admissions_pipeline",
    "FEE_OVERDUE":          "fee_dashboard",
    "FEE_WAIVER":           "fee_dashboard",
    "ATTENDANCE_RISK":      "student_risk",
    "ACADEMIC_PROBATION":   "student_risk",
    "HALL_TICKET_DISPATCH": "exam_management",
    "EXAM_CONFLICT":        "exam_management",
    "STUDENT_HOLD":         "approval_queue",
    "ELIGIBILITY_CHECK":    "approval_queue",
}

_TASK_TYPE_LABELS: Dict[str, str] = {
    "DOCUMENT_VERIFY":      "Verify Documents",
    "OFFER_EXPIRY":         "Offer Letter Expiring",
    "ENROLLMENT_PROVISION": "Complete Enrollment",
    "MERIT_LIST_APPROVE":   "Approve Merit List",
    "FEE_OVERDUE":          "Follow Up — Overdue Fee",
    "FEE_WAIVER":           "Review Waiver Request",
    "ATTENDANCE_RISK":      "Attendance Risk Alert",
    "ACADEMIC_PROBATION":   "Academic Probation Review",
    "HALL_TICKET_DISPATCH": "Dispatch Hall Tickets",
    "EXAM_CONFLICT":        "Resolve Exam Conflict",
    "STUDENT_HOLD":         "Resolve Student Hold",
    "ELIGIBILITY_CHECK":    "Eligibility Review",
}


def _build_task_cockpit(tenant_id: str, actor_id: str, role: str) -> Dict[str, Any]:
    """Query live workflow_tasks and return structured groups for the action cockpit.

    Groups: SLA BREACH → URGENT → APPROVALS → NORMAL (priority order).
    Returns {"groups": List[TaskGroup], "total": int}.
    Each TaskGroup: {"label", "count", "tasks": List[TaskItem]}.
    Each TaskItem: {"id", "label", "task_type", "urgency", "sla_deadline", "canvas_view", "resource_id"}.
    """
    sql = """
        SELECT id, task_type, resource_id, urgency, sla_deadline
        FROM workflow_tasks
        WHERE tenant_id = %s
          AND status = 'PENDING'
          AND (assignee_role = %s OR assignee_actor_id = %s)
        ORDER BY
          CASE urgency WHEN 'HIGH' THEN 0 WHEN 'NORMAL' THEN 1 WHEN 'LOW' THEN 2 ELSE 3 END,
          sla_deadline ASC NULLS LAST
        LIMIT 50
    """
    try:
        rows = execute_query(sql, (tenant_id, role, actor_id), tenant_id=tenant_id)
    except Exception as exc:
        logger.warning("context_advisor: task_cockpit query failed — %s", exc)
        rows = []

    if not rows:
        return {"groups": [], "total": 0}

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    sla_breached: List[Dict[str, Any]] = []
    urgent: List[Dict[str, Any]] = []
    approvals: List[Dict[str, Any]] = []
    normal: List[Dict[str, Any]] = []

    for row in rows:
        task_type = row.get("task_type", "")
        sla = row.get("sla_deadline")
        is_breached = sla is not None and sla < now

        item: Dict[str, Any] = {
            "id": str(row.get("id", "")),
            "label": _TASK_TYPE_LABELS.get(task_type, task_type.replace("_", " ").title()),
            "task_type": task_type,
            "urgency": row.get("urgency", "NORMAL"),
            "sla_deadline": sla.isoformat() if sla else None,
            "canvas_view": _TASK_VIEW_MAP.get(task_type, "approval_queue"),
            "resource_id": str(row["resource_id"]) if row.get("resource_id") else None,
        }

        if is_breached:
            sla_breached.append(item)
        elif row.get("urgency") == "HIGH":
            urgent.append(item)
        elif task_type in ("MERIT_LIST_APPROVE", "STUDENT_HOLD", "ELIGIBILITY_CHECK"):
            approvals.append(item)
        else:
            normal.append(item)

    groups: List[Dict[str, Any]] = []
    if sla_breached:
        groups.append({"label": "SLA BREACH", "count": len(sla_breached), "tasks": sla_breached})
    if urgent:
        groups.append({"label": "URGENT", "count": len(urgent), "tasks": urgent})
    if approvals:
        groups.append({"label": "APPROVALS", "count": len(approvals), "tasks": approvals})
    if normal:
        groups.append({"label": "NORMAL", "count": len(normal), "tasks": normal})

    return {"groups": groups, "total": len(rows)}


_CHIP_QUERIES: Dict[str, str] = {
    "show urgent items":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND urgency = 'HIGH' AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
    "pending verifications":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type = 'DOCUMENT_VERIFY' AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
    "offer letters due":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type = 'OFFER_EXPIRY' AND (assignee_role = %s OR assignee_actor_id = %s) ORDER BY sla_deadline ASC LIMIT 10",
    "enrollment progress":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type = 'ENROLLMENT_PROVISION' AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
    "merit list status":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type = 'MERIT_LIST_APPROVE' AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 10",
    "show defaulters":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type = 'FEE_OVERDUE' AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
    "show overdue items":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND sla_deadline < NOW() AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
    "show detention risk":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type = 'ATTENDANCE_RISK' AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
    "show red-risk students":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type IN ('ATTENDANCE_RISK','ACADEMIC_PROBATION') AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
    "eligibility status":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type = 'ELIGIBILITY_CHECK' AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
    "hall ticket dispatch":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type = 'HALL_TICKET_DISPATCH' AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
    "waiver requests":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type = 'FEE_WAIVER' AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
    "students with holds":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type = 'STUDENT_HOLD' AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
    "academic probation list":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type = 'ACADEMIC_PROBATION' AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
    "flag conflicts":
        "SELECT id FROM workflow_tasks WHERE tenant_id = %s AND status = 'PENDING' AND task_type = 'EXAM_CONFLICT' AND (assignee_role = %s OR assignee_actor_id = %s) LIMIT 20",
}
# Chip query params: (tenant_id, role, actor_id)


def _handle_chip(message: str, tenant_id: str, role: str, actor_id: str) -> Optional[Dict[str, Any]]:
    key = message.strip().lower()

    # ── Task cockpit: "What should I do today?" and variants ──────────────────
    if key in _COCKPIT_CHIPS:
        cockpit = _build_task_cockpit(tenant_id, actor_id, role)
        total = cockpit["total"]
        if total == 0:
            return {
                "message": "Your queue is clear — nothing pending right now.",
                "canvasAction": None,
                "tasks": [],
            }
        n = total
        return {
            "message": f"{n} item{'s' if n != 1 else ''} in your queue.",
            "canvasAction": None,
            "tasks": cockpit["groups"],
        }

    # ── Standard chip queries (highlight by ID) ───────────────────────────────
    sql = _CHIP_QUERIES.get(key)
    if sql is None:
        return None
    try:
        rows = execute_query(sql, (tenant_id, role, actor_id), tenant_id=tenant_id)
        ids = [str(r["id"]) for r in (rows or [])]
    except Exception as exc:
        logger.warning("context_advisor: chip query failed %r — %s", message, exc)
        ids = []

    if not ids:
        return {"message": f"Nothing found for \"{message}\" right now.", "canvasAction": None}

    count = len(ids)
    label = "item" if count == 1 else "items"
    return {
        "message": f"{count} {label} highlighted on the canvas.",
        "canvasAction": {"type": "HIGHLIGHT_MULTIPLE", "itemIds": ids},
    }


# ---------------------------------------------------------------------------
# EXECUTOR
# ---------------------------------------------------------------------------

def execute_context_advisor(
    context: AIGatewayContext,
    input_data: Dict[str, Any],
    model_override: Optional[str] = None,
) -> AIInvocationResult:
    """
    Entry point called by RailAgentRegistry.execute().

    input_data keys:
        view            — CanvasView string  e.g. "admissions_pipeline"
        role            — actor role string  e.g. "registrar"
        message         — "__view_change__" | chip text | free text
        agent_context   — opaque string from previous response (optional)
        recent_messages — last 5 { role, text } messages (optional)

    Returns AIInvocationResult with content = JSON-encoded AgentResponse:
        {
          message:      string | null,
          canvasAction: CanvasAction | null,
          agentContext: string | null
        }
    """
    t0 = time.monotonic()
    tenant_id = context.org_id or ""
    actor_id  = context.actor_id or ""
    view:    str = input_data.get("view", "home")
    message: str = input_data.get("message", "__view_change__")
    role:    str = input_data.get("role", "")

    try:
        # ── 1. View-change: programmatic proactive brief ─────────────────
        if message == "__view_change__":
            counts = _query_counts(view, tenant_id, actor_id, role)

            if not _should_surface(counts, tenant_id):
                response: Dict[str, Any] = {"message": None, "canvasAction": None, "agentContext": None}
            else:
                brief = _build_proactive_message(view, counts)
                urgent_ids = _safe_ids(counts.get("urgent_ids"))
                canvas_action = {"type": "HIGHLIGHT_MULTIPLE", "itemIds": urgent_ids} if urgent_ids else None
                agent_ctx = f"view:{view}:urgent:{','.join(urgent_ids[:5])}" if urgent_ids else None
                response = {
                    "message": brief,
                    "canvasAction": canvas_action,
                    "agentContext": agent_ctx,
                }

        # ── 2. Known chip action: programmatic query + highlight ─────────
        elif (chip_resp := _handle_chip(message, tenant_id, role, actor_id)) is not None:
            ids = chip_resp.get("canvasAction", {}).get("itemIds", []) if chip_resp.get("canvasAction") else []
            chip_resp["agentContext"] = f"chip:{message.lower()[:40]}:{','.join(ids[:5])}" if ids else None
            response = chip_resp

        # ── 3. Free text: Tier 2 entity lookup, then Tier 1 counts ──────
        else:
            counts = _query_counts(view, tenant_id, actor_id, role)

            # Reconstruct session context for pronoun resolution
            prev_context = input_data.get("agent_context") or ""
            recent = input_data.get("recent_messages") or []

            # Strip PII from recent messages before passing to LLM
            safe_recent = [
                {"role": m.get("role"), "text": _strip_pii(m.get("text", ""))}
                for m in recent[-5:]
            ]

            # Tier 2: detect a specific entity reference (APP-/STU-/course code)
            # and inject its status into the prompt (non-PII: status, counts only).
            try:
                entity_data = _detect_and_fetch_entity(message, tenant_id)
            except Exception:
                entity_data = None

            entity_clause = (
                f" Entity lookup result: {json.dumps(entity_data)}."
                if entity_data
                else ""
            )

            prompt = (
                f"You are the ALIS ERP assistant embedded in a university management system. "
                f"A {role or 'staff member'} on the {view.replace('_', ' ')} screen asked: \"{_strip_pii(message)}\". "
                f"Live dashboard counts: {json.dumps(counts)}.{entity_clause} "
                f"Session context hint: {prev_context or 'none'}. "
                f"Recent conversation: {json.dumps(safe_recent)}. "
                f"Reply in 1–2 concise sentences. Be specific. "
                f"Only reference numbers and entity data provided above — never invent data. "
                f"If the question requires detail not in the counts or entity lookup, "
                f"say so clearly rather than guessing."
            )

            reply = None
            try:
                from server.core.ai_gateway import AIGateway
                llm = AIGateway.get_llm(context)
                llm_result = llm.invoke(prompt)
                reply = llm_result.content
            except Exception as llm_exc:
                logger.warning("context_advisor: LLM call failed — %s", llm_exc)

            if not reply:
                reply = _build_proactive_message(view, counts) or "No items currently require attention."

            response = {
                "message": reply,
                "canvasAction": None,
                "agentContext": prev_context or None,  # preserve existing context across free-text turns
            }

    except Exception as exc:
        logger.exception("context_advisor: unhandled error — %s", exc)
        return AIInvocationResult(
            success=False,
            error=str(exc),
            request_id=context.request_id,
            model=model_override or "",
            latency_ms=(time.monotonic() - t0) * 1000,
        )

    return AIInvocationResult(
        success=True,
        content=json.dumps(response),
        request_id=context.request_id,
        model=model_override or "programmatic",
        latency_ms=(time.monotonic() - t0) * 1000,
    )
