"""Admin Router — Shadow Mode · Data Migration · Outbound Webhooks

All routes require SUPER_ADMIN role.  Mounted at /api/v1/admin.

Sections
────────
1.  Shadow Mode          POST/GET  /admin/shadow-mode/*
2.  Data Migration       POST/GET  /admin/migrations/*
3.  Outbound Webhooks    POST/GET/DELETE /admin/webhooks/*
"""

from __future__ import annotations

import io
import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from server.core.rbac import require_permission
from server.core.shadow_mode import ShadowModeConfig, ShadowModeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ---------------------------------------------------------------------------
# Permission dependency
# ---------------------------------------------------------------------------


async def super_admin(user=Depends(require_permission("SUPER_ADMIN_ACCESS"))):
    return user


# ===========================================================================
# 1.  SHADOW MODE
# ===========================================================================


class EnableShadowModeRequest(BaseModel):
    max_attendance_divergence_pct: float = 2.0
    max_fee_divergence_pct: float = 0.1
    suppress_sms: bool = True
    suppress_email: bool = True
    suppress_whatsapp: bool = True
    consecutive_passing_days_required: int = 5


@router.post("/shadow-mode/enable")
async def enable_shadow_mode(
    body: EnableShadowModeRequest,
    user=Depends(super_admin),
):
    """Activate shadow mode for the calling user's institution."""
    config = ShadowModeConfig(**body.model_dump())
    return ShadowModeService.enable(
        org_id=user["org_id"],
        config=config,
        actor_id=user["user_id"],
    )


@router.post("/shadow-mode/disable")
async def disable_shadow_mode(user=Depends(super_admin)):
    """Deactivate shadow mode."""
    return ShadowModeService.disable(
        org_id=user["org_id"],
        actor_id=user["user_id"],
    )


@router.get("/shadow-mode/status")
async def shadow_mode_status(user=Depends(super_admin)):
    """Return current shadow mode status + go-live gate evaluation."""
    org_id = user["org_id"]
    config = ShadowModeService.get_config(org_id)
    gate = ShadowModeService.check_go_live_gate(org_id)
    return {
        "enabled": config.enabled,
        "config": config.model_dump(),
        "consecutive_days_passing": gate.consecutive_days_passing,
        "can_go_live": gate.can_go_live,
        "latest_attendance_divergence_pct": gate.latest_attendance_divergence_pct,
        "latest_fee_divergence_pct": gate.latest_fee_divergence_pct,
        "reason": gate.reason,
    }


@router.get("/shadow-mode/divergence")
async def shadow_mode_divergence(
    days: int = Query(30, ge=1, le=90),
    user=Depends(super_admin),
):
    """Return divergence log for the last N days."""
    return ShadowModeService.get_divergence_log(org_id=user["org_id"], days=days)


# ===========================================================================
# 2.  DATA MIGRATION PIPELINE
# ===========================================================================

SUPPORTED_ENTITIES = [
    "students",
    "faculty",
    "courses",
    "fee_records",
    "historical_attendance",
    "exam_results",
    "alumni",
]


@router.post("/migrations/{entity_type}/validate")
async def migration_validate(
    entity_type: str = Path(...),
    file: UploadFile = File(...),
    user=Depends(super_admin),
):
    """Parse CSV and return full error report — no DB writes."""
    _check_entity(entity_type)
    from server.migration.migration_pipeline import MigrationPipeline

    content = await file.read()
    return await MigrationPipeline.run(
        entity_type=entity_type,
        csv_bytes=content,
        org_id=user["org_id"],
        mode="validate",
        actor_id=user["user_id"],
    )


@router.post("/migrations/{entity_type}/dry-run")
async def migration_dry_run(
    entity_type: str = Path(...),
    file: UploadFile = File(...),
    user=Depends(super_admin),
):
    """Show what would be inserted/skipped — no DB writes."""
    _check_entity(entity_type)
    from server.migration.migration_pipeline import MigrationPipeline

    content = await file.read()
    return await MigrationPipeline.run(
        entity_type=entity_type,
        csv_bytes=content,
        org_id=user["org_id"],
        mode="dry_run",
        actor_id=user["user_id"],
    )


@router.post("/migrations/{entity_type}/commit")
async def migration_commit(
    entity_type: str = Path(...),
    file: UploadFile = File(...),
    user=Depends(super_admin),
):
    """Commit migration — atomic INSERT with duplicate detection + full audit."""
    _check_entity(entity_type)
    from server.migration.migration_pipeline import MigrationPipeline

    content = await file.read()
    return await MigrationPipeline.run(
        entity_type=entity_type,
        csv_bytes=content,
        org_id=user["org_id"],
        mode="commit",
        actor_id=user["user_id"],
    )


@router.get("/migrations")
async def list_migrations(
    status: str | None = Query(None),
    user=Depends(super_admin),
):
    """List migration jobs for this institution."""
    from server.db_service import execute_query

    sql = """
        SELECT id, entity_type, mode, status, total_rows, processed_rows,
               error_count, started_at, completed_at
        FROM data_migration_jobs
        WHERE org_id = %s
    """
    params = [user["org_id"]]
    if status:
        sql += " AND status = %s"
        params.append(status)
    sql += " ORDER BY started_at DESC LIMIT 100"
    return execute_query(sql, tuple(params))


@router.get("/migrations/{job_id}")
async def get_migration(
    job_id: str = Path(...),
    user=Depends(super_admin),
):
    """Job status + error rows."""
    from server.db_service import execute_query

    rows = execute_query(
        "SELECT * FROM data_migration_jobs WHERE id = %s AND org_id = %s",
        (job_id, user["org_id"]),
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Migration job not found")
    job = dict(rows[0])

    errors = execute_query(
        "SELECT row_number, raw_data, error_message FROM data_migration_errors WHERE job_id = %s ORDER BY row_number",
        (job_id,),
    )
    job["errors"] = errors
    return job


@router.get("/migrations/templates/{entity_type}")
async def download_template(
    entity_type: str = Path(...),
    user=Depends(super_admin),
):
    """Download the CSV template for an entity type."""
    _check_entity(entity_type)
    import os

    template_dir = os.path.join(
        os.path.dirname(__file__), "..", "migration", "templates"
    )
    path = os.path.join(template_dir, f"{entity_type}.csv")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Template not found")
    with open(path, "rb") as f:
        content = f.read()
    return StreamingResponse(
        io.BytesIO(content),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{entity_type}_template.csv"'
        },
    )


def _check_entity(entity_type: str):
    if entity_type not in SUPPORTED_ENTITIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported entity type. Valid: {', '.join(SUPPORTED_ENTITIES)}",
        )


# ===========================================================================
# 3.  OUTBOUND WEBHOOKS
# ===========================================================================


class WebhookSubscriptionRequest(BaseModel):
    event_type: str
    url: str
    secret: str


@router.post("/webhooks/subscriptions")
async def register_webhook(
    body: WebhookSubscriptionRequest,
    user=Depends(super_admin),
):
    """Register an outbound webhook endpoint."""
    from server.core.webhook_dispatcher import WebhookDispatcher

    subscription_id = await WebhookDispatcher.register(
        org_id=user["org_id"],
        event_type=body.event_type,
        url=body.url,
        secret=body.secret,
        actor_id=user["user_id"],
    )
    return {"subscription_id": subscription_id, "status": "active"}


@router.get("/webhooks/subscriptions")
async def list_webhooks(user=Depends(super_admin)):
    """List active webhook subscriptions."""
    from server.db_service import execute_query

    return execute_query(
        """
        SELECT id, event_type, url, active, created_at
        FROM outbound_webhook_subscriptions
        WHERE org_id = %s
        ORDER BY created_at DESC
    """,
        (user["org_id"],),
    )


@router.delete("/webhooks/subscriptions/{subscription_id}")
async def deactivate_webhook(
    subscription_id: str = Path(...),
    user=Depends(super_admin),
):
    """Deactivate a webhook subscription."""
    from server.core.webhook_dispatcher import WebhookDispatcher

    await WebhookDispatcher.deactivate(
        subscription_id=subscription_id,
        org_id=user["org_id"],
        actor_id=user["user_id"],
    )
    return {"status": "deactivated"}


@router.get("/webhooks/deliveries")
async def list_deliveries(
    status: str | None = Query(None),
    event_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(super_admin),
):
    """Delivery log with optional filters."""
    from server.db_service import execute_query

    sql = """
        SELECT d.id, d.subscription_id, s.event_type, s.url,
               d.status, d.attempt_count, d.next_retry_at, d.last_error, d.created_at
        FROM outbound_webhook_deliveries d
        JOIN outbound_webhook_subscriptions s ON s.id = d.subscription_id
        WHERE s.org_id = %s
    """
    params: list = [user["org_id"]]
    if status:
        sql += " AND d.status = %s"
        params.append(status)
    if event_type:
        sql += " AND s.event_type = %s"
        params.append(event_type)
    sql += " ORDER BY d.created_at DESC LIMIT %s"
    params.append(limit)
    return execute_query(sql, tuple(params))


@router.post("/webhooks/deliveries/{delivery_id}/replay")
async def replay_delivery(
    delivery_id: str = Path(...),
    user=Depends(super_admin),
):
    """Manually replay a failed or dead delivery."""
    from server.core.webhook_dispatcher import WebhookDispatcher

    await WebhookDispatcher.replay(delivery_id=delivery_id, org_id=user["org_id"])
    return {"status": "queued"}


# ---------------------------------------------------------------------------
# PAA — Policy Authoring Agent Routes (P22)
# ---------------------------------------------------------------------------


@router.post("/policies/draft-with-ai")
async def draft_policy_with_ai(
    request: Request,
    body: dict,
    user=Depends(super_admin),
) -> JSONResponse:
    """Use LLM to generate a policy DSL draft (always DRAFT status — human must approve)."""
    from server.core.policy_authoring_agent import PolicyAuthoringAgent

    result = PolicyAuthoringAgent.draft_policy(
        org_id=user["org_id"],
        policy_key=body["policy_key"],
        plain_english_description=body["description"],
        actor_id=user["user_id"],
    )
    return JSONResponse(content=result, status_code=201)


@router.get("/policies/drafts")
async def list_policy_drafts(
    user=Depends(super_admin),
) -> JSONResponse:
    """List all pending AI-generated policy drafts."""
    from server.core.policy_authoring_agent import PolicyAuthoringAgent

    result = PolicyAuthoringAgent.list_drafts(user["org_id"])
    return JSONResponse(content={"drafts": result, "total": len(result)})


@router.post("/policies/drafts/{draft_id}/approve")
async def approve_policy_draft(
    draft_id: str,
    body: dict,
    user=Depends(super_admin),
) -> JSONResponse:
    """Approve a policy draft (activates it by setting status=APPROVED)."""
    from server.core.policy_authoring_agent import PolicyAuthoringAgent

    result = PolicyAuthoringAgent.approve_draft(
        draft_id, user["org_id"], user["user_id"], body.get("justification", "")
    )
    return JSONResponse(content=result)


@router.post("/policies/drafts/{draft_id}/reject")
async def reject_policy_draft(
    draft_id: str,
    body: dict,
    user=Depends(super_admin),
) -> JSONResponse:
    """Reject a policy draft."""
    from server.core.policy_authoring_agent import PolicyAuthoringAgent

    result = PolicyAuthoringAgent.reject_draft(
        draft_id, user["org_id"], user["user_id"], body.get("reason", "")
    )
    return JSONResponse(content=result)


# ---------------------------------------------------------------------------
# Multi-campus Routes (P22)
# ---------------------------------------------------------------------------


@router.post("/campuses/provision")
async def provision_campus(
    request: Request,
    body: dict,
    user=Depends(super_admin),
) -> JSONResponse:
    """Provision a new campus under a GROUP organization."""
    from server.core.campus_service import CampusService

    result = CampusService.provision_campus(
        group_org_id=body["group_org_id"],
        campus_code=body["campus_code"],
        campus_name=body["campus_name"],
        city=body.get("city", ""),
        state=body.get("state", ""),
        address=body.get("address"),
        pincode=body.get("pincode"),
        phone=body.get("phone"),
        principal_user_id=body.get("principal_user_id"),
        actor_id=user["user_id"],
    )
    return JSONResponse(content=result, status_code=201)


@router.get("/campuses/{group_org_id}/summary")
async def get_group_summary(
    group_org_id: str,
    user=Depends(super_admin),
) -> JSONResponse:
    """Get group-level aggregate summary across all campuses."""
    from server.core.campus_service import CampusService

    result = CampusService.get_group_summary(group_org_id, user["user_id"])
    return JSONResponse(content=result)


@router.get("/campuses/{group_org_id}")
async def list_campuses(
    group_org_id: str,
    user=Depends(super_admin),
) -> JSONResponse:
    """List all campuses under a GROUP organization."""
    from server.core.campus_service import CampusService

    result = CampusService.list_campuses(group_org_id)
    return JSONResponse(content={"campuses": result, "total": len(result)})


# ===========================================================================
# 4.  DEAD-LETTER QUEUE — Failed Task Log
# ===========================================================================


@router.get("/failed-tasks")
async def list_failed_tasks(
    task_name: str | None = Query(None),
    retried: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user=Depends(super_admin),
):
    """List Celery tasks that exhausted all retries and landed in the DLQ."""
    from server.db_service import execute_query

    sql = "SELECT id, task_id, task_name, args, kwargs, error, failed_at, tenant_id, retried, retried_at FROM failed_task_log WHERE TRUE"
    params: list = []
    if task_name:
        sql += " AND task_name ILIKE %s"
        params.append(f"%{task_name}%")
    if retried is not None:
        sql += " AND retried = %s"
        params.append(retried)
    sql += " ORDER BY failed_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    rows = execute_query(sql, tuple(params))
    count_row = execute_query(
        "SELECT COUNT(*) AS n FROM failed_task_log WHERE TRUE"  # noqa: S608
        + (
            (" AND task_name ILIKE %s" if task_name else "")
            + (" AND retried = %s" if retried is not None else "")
        ),
        tuple(params[:-2]) if params[:-2] else (),
    )
    total = count_row[0]["n"] if count_row else 0
    return {"tasks": rows, "total": total, "limit": limit, "offset": offset}


@router.post("/failed-tasks/{task_log_id}/retry")
async def retry_failed_task(
    task_log_id: int = Path(...),
    user=Depends(super_admin),
):
    """Re-enqueue a failed task by its dead-letter log ID."""
    from server.db_service import execute_query, execute_transaction

    rows = execute_query("SELECT * FROM failed_task_log WHERE id = %s", (task_log_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Task not found in dead-letter log")
    row = rows[0]
    if row["retried"]:
        raise HTTPException(status_code=409, detail="Task already retried")
    # Re-enqueue via Celery send_task
    from server.worker import celery_app

    celery_app.send_task(
        row["task_name"],
        args=row["args"] or [],
        kwargs=row["kwargs"] or {},
    )
    execute_transaction(
        [
            (
                "UPDATE failed_task_log SET retried = TRUE, retried_at = NOW() WHERE id = %s",
                (task_log_id,),
            )
        ]
    )
    from server.core.audit import AuditAction, AuditLog

    AuditLog.log(
        action=AuditAction.UPDATE,
        actor_id=user["user_id"],
        actor_role="super_admin",
        entity_type="failed_task_log",
        entity_id=str(task_log_id),
        tenant_id=user.get("org_id", ""),
        metadata={"source": "retry_failed_task", "task_name": row["task_name"]},
    )
    return {"status": "requeued", "task_name": row["task_name"]}


@router.post("/organizations/{org_id}/promote-to-group")
async def promote_org_to_group(
    org_id: str,
    user=Depends(super_admin),
) -> JSONResponse:
    """Promote a STANDALONE organization to GROUP entity type."""
    from server.core.campus_service import CampusService

    result = CampusService.promote_to_group(org_id, user["user_id"])
    return JSONResponse(content=result)
