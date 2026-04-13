"""E15 — PhD / Doctoral API Router

Routes:
  POST   /phd/register                         — register new PhD scholar
  GET    /phd/scholars                          — list scholars (filtered)
  GET    /phd/scholars/{phd_id}                 — get single scholar
  POST   /phd/milestones/{phd_id}/complete      — complete a milestone
  POST   /phd/thesis/submit                     — submit thesis
  POST   /phd/degree/award                      — award PhD degree
  POST   /phd/dc-meetings                       — schedule DC meeting
  POST   /phd/dc-meetings/{meeting_id}/outcome  — record DC meeting outcome
  POST   /phd/plagiarism/submit                 — submit plagiarism check
  POST   /phd/plagiarism/{report_id}/result     — record plagiarism result
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from server.core.exceptions import (
    ALISError,
    BusinessRuleViolation,
    NotFoundError,
)
from server.core.rbac import Permission, require_permission
from server.phd.phd_service import PhDService
from server.phd.plagiarism_service import PlagiarismService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/phd", tags=["PhD"])


def _org(r: Request) -> str:
    return getattr(r.state, "tenant_id", "default")


def _actor(r: Request) -> str:
    return getattr(r.state, "user_id", "anonymous")


# ──────────────────────────────────────────────────────────────
# Scholar Registration
# ──────────────────────────────────────────────────────────────


@router.post("/register", status_code=201)
@require_permission(Permission.PHD_MANAGE)
async def register_scholar(request: Request, body: dict) -> JSONResponse:
    try:
        result = PhDService.register_scholar(
            org_id=_org(request),
            student_id=body["student_id"],
            supervisor_id=body["supervisor_id"],
            program_id=body["program_id"],
            research_area=body["research_area"],
            co_supervisor_id=body.get("co_supervisor_id"),
            actor_id=_actor(request),
        )
        return JSONResponse(status_code=201, content=result)
    except BusinessRuleViolation as exc:
        return JSONResponse(status_code=422, content={"detail": exc.message})
    except ALISError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"detail": exc.message}
        )
    except Exception as exc:
        logger.exception("register_scholar failed")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


# ──────────────────────────────────────────────────────────────
# Scholar Listing & Retrieval
# ──────────────────────────────────────────────────────────────


@router.get("/scholars")
@require_permission(Permission.PHD_READ)
async def list_scholars(
    request: Request,
    status: str | None = Query(None),
    supervisor_id: str | None = Query(None),
    program_id: str | None = Query(None),
) -> JSONResponse:
    try:
        scholars = PhDService.list_scholars(
            org_id=_org(request),
            status=status,
            supervisor_id=supervisor_id,
            program_id=program_id,
        )
        return JSONResponse(content={"scholars": scholars, "total": len(scholars)})
    except ALISError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"detail": exc.message}
        )
    except Exception as exc:
        logger.exception("list_scholars failed")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@router.get("/scholars/{phd_id}")
@require_permission(Permission.PHD_READ)
async def get_scholar(request: Request, phd_id: str) -> JSONResponse:
    try:
        result = PhDService.get_scholar(phd_id=phd_id, org_id=_org(request))
        return JSONResponse(content=result)
    except NotFoundError as exc:
        return JSONResponse(status_code=404, content={"detail": exc.message})
    except ALISError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"detail": exc.message}
        )
    except Exception as exc:
        logger.exception("get_scholar failed")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


# ──────────────────────────────────────────────────────────────
# Milestones
# ──────────────────────────────────────────────────────────────


@router.post("/milestones/{phd_id}/complete")
@require_permission(Permission.PHD_MANAGE)
async def complete_milestone(request: Request, phd_id: str, body: dict) -> JSONResponse:
    try:
        result = PhDService.complete_milestone(
            phd_id=phd_id,
            milestone_type=body["milestone_type"],
            org_id=_org(request),
            actor_id=_actor(request),
            notes=body.get("notes"),
        )
        return JSONResponse(content=result)
    except NotFoundError as exc:
        return JSONResponse(status_code=404, content={"detail": exc.message})
    except BusinessRuleViolation as exc:
        return JSONResponse(status_code=422, content={"detail": exc.message})
    except ALISError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"detail": exc.message}
        )
    except Exception as exc:
        logger.exception("complete_milestone failed")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


# ──────────────────────────────────────────────────────────────
# Thesis Submission
# ──────────────────────────────────────────────────────────────


@router.post("/thesis/submit", status_code=201)
@require_permission(Permission.PHD_MANAGE)
async def submit_thesis(request: Request, body: dict) -> JSONResponse:
    try:
        result = PhDService.submit_thesis(
            phd_id=body["phd_id"],
            org_id=_org(request),
            thesis_document_url=body["thesis_document_url"],
            examiner_1_id=body["examiner_1_id"],
            examiner_2_id=body["examiner_2_id"],
            external_examiner_id=body.get("external_examiner_id"),
            actor_id=_actor(request),
        )
        return JSONResponse(status_code=201, content=result)
    except NotFoundError as exc:
        return JSONResponse(status_code=404, content={"detail": exc.message})
    except BusinessRuleViolation as exc:
        return JSONResponse(status_code=422, content={"detail": exc.message})
    except ALISError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"detail": exc.message}
        )
    except Exception as exc:
        logger.exception("submit_thesis failed")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


# ──────────────────────────────────────────────────────────────
# Degree Award
# ──────────────────────────────────────────────────────────────


@router.post("/degree/award")
@require_permission(Permission.PHD_MANAGE)
async def award_degree(request: Request, body: dict) -> JSONResponse:
    try:
        result = PhDService.award_degree(
            phd_id=body["phd_id"],
            org_id=_org(request),
            actor_id=_actor(request),
        )
        return JSONResponse(content=result)
    except NotFoundError as exc:
        return JSONResponse(status_code=404, content={"detail": exc.message})
    except BusinessRuleViolation as exc:
        return JSONResponse(status_code=422, content={"detail": exc.message})
    except ALISError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"detail": exc.message}
        )
    except Exception as exc:
        logger.exception("award_degree failed")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


# ──────────────────────────────────────────────────────────────
# DC Meetings
# ──────────────────────────────────────────────────────────────


@router.post("/dc-meetings", status_code=201)
@require_permission(Permission.PHD_MANAGE)
async def schedule_dc_meeting(request: Request, body: dict) -> JSONResponse:
    try:
        result = PhDService.schedule_dc_meeting(
            phd_id=body["phd_id"],
            org_id=_org(request),
            scheduled_at_iso=body["scheduled_at"],
            committee_members=body["committee_members"],
            agenda=body["agenda"],
            actor_id=_actor(request),
        )
        return JSONResponse(status_code=201, content=result)
    except NotFoundError as exc:
        return JSONResponse(status_code=404, content={"detail": exc.message})
    except ALISError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"detail": exc.message}
        )
    except Exception as exc:
        logger.exception("schedule_dc_meeting failed")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@router.post("/dc-meetings/{meeting_id}/outcome")
@require_permission(Permission.PHD_MANAGE)
async def record_dc_outcome(
    request: Request, meeting_id: str, body: dict
) -> JSONResponse:
    try:
        result = PhDService.record_dc_outcome(
            meeting_id=meeting_id,
            org_id=_org(request),
            outcome=body["outcome"],
            minutes=body["minutes"],
            actor_id=_actor(request),
        )
        return JSONResponse(content=result)
    except NotFoundError as exc:
        return JSONResponse(status_code=404, content={"detail": exc.message})
    except ALISError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"detail": exc.message}
        )
    except Exception as exc:
        logger.exception("record_dc_outcome failed")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


# ──────────────────────────────────────────────────────────────
# Plagiarism
# ──────────────────────────────────────────────────────────────


@router.post("/plagiarism/submit", status_code=201)
@require_permission(Permission.PHD_MANAGE)
async def submit_plagiarism_check(request: Request, body: dict) -> JSONResponse:
    try:
        result = PlagiarismService.submit_check(
            phd_id=body["phd_id"],
            org_id=_org(request),
            document_url=body["document_url"],
            actor_id=_actor(request),
        )
        return JSONResponse(status_code=201, content=result)
    except NotFoundError as exc:
        return JSONResponse(status_code=404, content={"detail": exc.message})
    except ALISError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"detail": exc.message}
        )
    except Exception as exc:
        logger.exception("submit_plagiarism_check failed")
        return JSONResponse(status_code=500, content={"detail": str(exc)})


@router.post("/plagiarism/{report_id}/result")
@require_permission(Permission.PHD_MANAGE)
async def record_plagiarism_result(
    request: Request, report_id: str, body: dict
) -> JSONResponse:
    try:
        result = PlagiarismService.record_result(
            report_id=report_id,
            org_id=_org(request),
            similarity_pct=float(body["similarity_pct"]),
            actor_id=_actor(request),
        )
        return JSONResponse(content=result)
    except NotFoundError as exc:
        return JSONResponse(status_code=404, content={"detail": exc.message})
    except ALISError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"detail": exc.message}
        )
    except Exception as exc:
        logger.exception("record_plagiarism_result failed")
        return JSONResponse(status_code=500, content={"detail": str(exc)})
