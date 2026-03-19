"""E10 — Communication Hub API Router

Endpoints:
  E10-S01  POST   /comms/templates
           GET    /comms/templates
           GET    /comms/templates/{id}
           PATCH  /comms/templates/{id}

  E10-S02/S03  GET   /comms/logs/me
               GET   /comms/logs/failed
               POST  /comms/logs/{id}/retry

  E10-S04  GET   /comms/notifications/me
           POST  /comms/notifications/{id}/read
           POST  /comms/notifications/read-all
           GET   /comms/notifications/me/count

  E10-S05  POST  /comms/announcements
           GET   /comms/announcements
           POST  /comms/announcements/{id}/read
           DELETE /comms/announcements/{id}

  E10-S06  GET   /comms/parent/{student_id}/notifications
           (parent sees their child's in-app feed)

  E10-S07  POST  /comms/bulk
           GET   /comms/bulk
           GET   /comms/bulk/{id}
"""

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from server.core.rbac import Permission, require_permission

from server.communication.notif_templates   import NotifTemplateService
from server.communication.notification_log  import NotificationLogService
from server.communication.in_app            import InAppNotificationService
from server.communication.announcements     import AnnouncementService
from server.communication.bulk              import BulkMessagingService
from server.communication.models            import (
    TemplateCreate, TemplateUpdate,
    AnnouncementCreate, BulkMessageCreate,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/comms", tags=["communication"])


def _org(r: Request) -> str:
    return getattr(r.state, "tenant_id", "default")

def _actor(r: Request) -> str:
    return getattr(r.state, "user_id", "anonymous")
def _jsonify(obj):
    """Recursively convert Decimal/date/datetime/time to JSON-safe types."""
    from decimal import Decimal
    from datetime import datetime, date, time as _time
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonify(i) for i in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, _time):
        return obj.strftime("%H:%M")
    return obj


# ──────────────────────────────────────────────────────────────
# E10-S01 — Notification Templates
# ──────────────────────────────────────────────────────────────

@router.post("/templates", status_code=201)
@require_permission(Permission.NOTIFICATION_MANAGE)
async def create_template(request: Request, body: TemplateCreate) -> JSONResponse:
    result = NotifTemplateService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/templates")
@require_permission(Permission.NOTIFICATION_MANAGE)
async def list_templates(
    request: Request,
    channel: Optional[str] = Query(None),
) -> JSONResponse:
    items = NotifTemplateService.list(_org(request), channel)
    return JSONResponse(content={"templates": items, "total": len(items)})


@router.get("/templates/{template_id}")
@require_permission(Permission.NOTIFICATION_MANAGE)
async def get_template(request: Request, template_id: str) -> JSONResponse:
    return JSONResponse(content=NotifTemplateService.get(_org(request), template_id))


@router.patch("/templates/{template_id}")
@require_permission(Permission.NOTIFICATION_MANAGE)
async def update_template(request: Request, template_id: str, body: TemplateUpdate) -> JSONResponse:
    result = NotifTemplateService.update(_org(request), template_id, body, _actor(request))
    return JSONResponse(content=result)


# ──────────────────────────────────────────────────────────────
# E10-S02/S03 — Delivery Logs
# ──────────────────────────────────────────────────────────────

@router.get("/logs/me")
@require_permission(Permission.NOTIFICATION_READ)
async def my_notification_logs(request: Request) -> JSONResponse:
    items = NotificationLogService.list_for_recipient(_org(request), _actor(request))
    return JSONResponse(content={"logs": items, "total": len(items)})


@router.get("/logs/failed")
@require_permission(Permission.NOTIFICATION_MANAGE)
async def failed_logs(request: Request) -> JSONResponse:
    items = NotificationLogService.list_failed(_org(request))
    return JSONResponse(content={"logs": items, "total": len(items)})


@router.post("/logs/{log_id}/retry")
@require_permission(Permission.NOTIFICATION_MANAGE)
async def retry_notification(request: Request, log_id: str) -> JSONResponse:
    result = NotificationLogService.retry(_org(request), log_id)
    return JSONResponse(content=result)


# ──────────────────────────────────────────────────────────────
# E10-S04 — In-App Notifications
# ──────────────────────────────────────────────────────────────

@router.get("/notifications/me")
@require_permission(Permission.NOTIFICATION_READ)
async def my_notifications(
    request: Request,
    unread_only: bool = Query(False),
    limit: int = Query(50, le=200),
) -> JSONResponse:
    items = InAppNotificationService.list_for_user(
        _org(request), _actor(request), unread_only, limit
    )
    return JSONResponse(content={"notifications": items, "total": len(items)})


@router.get("/notifications/me/count")
@require_permission(Permission.NOTIFICATION_READ)
async def unread_count(request: Request) -> JSONResponse:
    count = InAppNotificationService.unread_count(_org(request), _actor(request))
    return JSONResponse(content={"unread": count})


@router.post("/notifications/{notification_id}/read")
@require_permission(Permission.NOTIFICATION_READ)
async def mark_read(request: Request, notification_id: str) -> JSONResponse:
    result = InAppNotificationService.mark_read(
        _org(request), _actor(request), notification_id
    )
    return JSONResponse(content=result)


@router.post("/notifications/read-all")
@require_permission(Permission.NOTIFICATION_READ)
async def mark_all_read(request: Request) -> JSONResponse:
    result = InAppNotificationService.mark_all_read(_org(request), _actor(request))
    return JSONResponse(content=result)


# ──────────────────────────────────────────────────────────────
# E10-S05 — Announcements
# ──────────────────────────────────────────────────────────────

@router.post("/announcements", status_code=201)
@require_permission(Permission.ANNOUNCEMENT_CREATE)
async def create_announcement(request: Request, body: AnnouncementCreate) -> JSONResponse:
    result = AnnouncementService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/announcements")
@require_permission(Permission.NOTIFICATION_READ)
async def list_announcements(
    request: Request,
    audience: Optional[str] = Query(None),
    active_only: bool = Query(True),
) -> JSONResponse:
    items = AnnouncementService.list(_org(request), audience, active_only)
    return JSONResponse(content={"announcements": items, "total": len(items)})


@router.post("/announcements/{announcement_id}/read")
@require_permission(Permission.NOTIFICATION_READ)
async def mark_announcement_read(request: Request, announcement_id: str) -> JSONResponse:
    result = AnnouncementService.mark_read(_org(request), announcement_id, _actor(request))
    return JSONResponse(content=result)


@router.delete("/announcements/{announcement_id}")
@require_permission(Permission.ANNOUNCEMENT_CREATE)
async def deactivate_announcement(request: Request, announcement_id: str) -> JSONResponse:
    result = AnnouncementService.deactivate(_org(request), announcement_id, _actor(request))
    return JSONResponse(content=result)


# ──────────────────────────────────────────────────────────────
# E10-S06 — Parent/Guardian Portal (read-only view of child's feed)
# ──────────────────────────────────────────────────────────────

@router.get("/parent/{student_id}/notifications")
@require_permission(Permission.NOTIFICATION_READ)
async def parent_view(
    request: Request,
    student_id: str,
    limit: int = Query(30, le=100),
) -> JSONResponse:
    """
    Returns the in-app notification feed for a student.
    The caller must be a parent/guardian linked to this student.
    RBAC: PARENT role is granted NOTIFICATION_READ scoped to their children.
    """
    items = InAppNotificationService.list_for_user(
        _org(request), student_id, unread_only=False, limit=limit
    )
    return JSONResponse(content={"notifications": items, "total": len(items)})


# ──────────────────────────────────────────────────────────────
# E10-S07 — Bulk Messaging
# ──────────────────────────────────────────────────────────────

@router.post("/bulk", status_code=201)
@require_permission(Permission.BULK_MESSAGE)
async def create_bulk_job(request: Request, body: BulkMessageCreate) -> JSONResponse:
    result = BulkMessagingService.create_job(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/bulk")
@require_permission(Permission.BULK_MESSAGE)
async def list_bulk_jobs(request: Request) -> JSONResponse:
    items = BulkMessagingService.list(_org(request))
    return JSONResponse(content={"jobs": items, "total": len(items)})


@router.get("/bulk/{job_id}")
@require_permission(Permission.BULK_MESSAGE)
async def get_bulk_job(request: Request, job_id: str) -> JSONResponse:
    return JSONResponse(content=BulkMessagingService.get(_org(request), job_id))
