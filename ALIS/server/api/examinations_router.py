"""E06 — Examinations & Grades API Router

Endpoints:
  E06-S01  POST   /exams/schedules
           GET    /exams/schedules
           GET    /exams/schedules/{id}
           PATCH  /exams/schedules/{id}/status

  E06-S02  POST   /exams/hall-tickets/issue
           GET    /exams/hall-tickets/student/{student_id}

  E06-S03  POST   /exams/grades/bulk
  E06-S04  POST   /exams/results/compute
  E06-S05  POST   /exams/results/publish
           GET    /exams/results/student/{student_id}
           GET    /exams/grades/student/{student_id}

  E06-S06  POST   /exams/transcripts/generate
           GET    /exams/transcripts/student/{student_id}

  E06-S07  POST   /exams/reeval
           POST   /exams/reeval/{id}/decide
           GET    /exams/reeval/pending
           GET    /exams/reeval/student/{student_id}

  E06-S08  GET    /exams/analytics/course/{exam_schedule_id}
           GET    /exams/analytics/semester
           GET    /exams/analytics/student/{student_id}/trend
           GET    /exams/analytics/semester/ai-insights
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from server.core.rbac import Permission, require_permission
from server.examinations.analytics import GradeAnalyticsService
from server.examinations.grades import GradeService
from server.examinations.hall_ticket import HallTicketService
from server.examinations.models import (
    ExamScheduleCreate,
    GradesBulkEntry,
    ReEvalDecision,
    ReEvalRequest,
)
from server.examinations.reeval import ReEvalService
from server.examinations.schedule import ExamScheduleService
from server.examinations.transcript import TranscriptService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/exams", tags=["examinations"])


def _org(r: Request) -> str:
    return getattr(r.state, "tenant_id", "default")


def _actor(r: Request) -> str:
    return getattr(r.state, "user_id", "anonymous")


def _jsonify(obj):
    """Recursively convert Decimal/date/datetime/time to JSON-safe types."""
    from datetime import date, datetime
    from datetime import time as _time
    from decimal import Decimal

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
# E06-S01 — Exam Schedules
# ──────────────────────────────────────────────────────────────


@router.post("/schedules", status_code=201)
@require_permission(Permission.EXAM_PAPER_CREATE)
async def create_schedule(request: Request, body: ExamScheduleCreate) -> JSONResponse:
    result = ExamScheduleService.create(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/schedules")
@require_permission(Permission.EXAM_PAPER_READ)
async def list_schedules(
    request: Request,
    academic_year: str = Query(...),
    semester: int | None = Query(None),
    exam_type: str | None = Query(None),
) -> JSONResponse:
    items = ExamScheduleService.list(_org(request), academic_year, semester, exam_type)
    return JSONResponse(content=_jsonify({"schedules": items, "total": len(items)}))


@router.get("/schedules/{schedule_id}")
@require_permission(Permission.EXAM_PAPER_READ)
async def get_schedule(request: Request, schedule_id: str) -> JSONResponse:
    return JSONResponse(
        content=_jsonify(ExamScheduleService.get(_org(request), schedule_id))
    )


@router.patch("/schedules/{schedule_id}/status")
@require_permission(Permission.EXAM_PAPER_CREATE)
async def update_schedule_status(
    request: Request, schedule_id: str, body: dict
) -> JSONResponse:
    result = ExamScheduleService.update_status(
        _org(request), schedule_id, body["status"], _actor(request)
    )
    return JSONResponse(content=result)


# ──────────────────────────────────────────────────────────────
# E06-S02 — Hall Tickets
# ──────────────────────────────────────────────────────────────


@router.post("/hall-tickets/issue", status_code=201)
@require_permission(Permission.HALL_TICKET_GENERATE)
async def issue_hall_tickets(request: Request, body: dict) -> JSONResponse:
    result = HallTicketService.issue_for_semester(
        org_id=_org(request),
        academic_year=body["academic_year"],
        semester=int(body["semester"]),
        exam_type=body.get("exam_type", "SEMESTER_END"),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=result)


@router.get("/hall-tickets/student/{student_id}")
@require_permission(Permission.MARKS_READ)
async def get_hall_tickets(
    request: Request, student_id: str, academic_year: str = Query(...)
) -> JSONResponse:
    items = HallTicketService.get_for_student(_org(request), student_id, academic_year)
    return JSONResponse(content=_jsonify({"hall_tickets": items}))


# ──────────────────────────────────────────────────────────────
# E06-S03 — Grade Entry
# ──────────────────────────────────────────────────────────────


@router.post("/grades/bulk", status_code=201)
@require_permission(Permission.MARKS_ENTRY)
async def enter_grades(request: Request, body: GradesBulkEntry) -> JSONResponse:
    result = GradeService.enter_grades(_org(request), body, _actor(request))
    return JSONResponse(status_code=201, content=result)


@router.get("/grades/student/{student_id}")
@require_permission(Permission.MARKS_READ)
async def get_student_grades(
    request: Request,
    student_id: str,
    academic_year: str = Query(...),
    semester: int | None = Query(None),
) -> JSONResponse:
    items = GradeService.get_student_grades(
        _org(request), student_id, academic_year, semester
    )
    return JSONResponse(content=_jsonify({"grades": items, "total": len(items)}))


# ──────────────────────────────────────────────────────────────
# E06-S04 — GPA / CGPA Computation
# ──────────────────────────────────────────────────────────────


@router.post("/results/compute")
@require_permission(Permission.MARKS_FINALIZE)
async def compute_result(request: Request, body: dict) -> JSONResponse:
    result = GradeService.compute_semester_result(
        org_id=_org(request),
        student_id=body["student_id"],
        academic_year=body["academic_year"],
        semester=int(body["semester"]),
        actor_id=_actor(request),
    )
    return JSONResponse(content=result)


# ──────────────────────────────────────────────────────────────
# E06-S05 — Publish Results
# ──────────────────────────────────────────────────────────────


@router.post("/results/publish")
@require_permission(Permission.RESULT_PUBLISH)
async def publish_results(request: Request, body: dict) -> JSONResponse:
    result = GradeService.publish_results(
        org_id=_org(request),
        academic_year=body["academic_year"],
        semester=int(body["semester"]),
        actor_id=_actor(request),
    )
    return JSONResponse(content=result)


@router.get("/results/student/{student_id}")
@require_permission(Permission.MARKS_READ)
async def get_student_results(request: Request, student_id: str) -> JSONResponse:
    from server.db_service import execute_query

    rows = execute_query(
        "SELECT * FROM semester_results WHERE student_id = %s AND org_id = %s ORDER BY academic_year, semester",
        (student_id, _org(request)),
    )
    items = [dict(r) for r in rows]
    return JSONResponse(content=_jsonify({"results": items, "total": len(items)}))


# ──────────────────────────────────────────────────────────────
# E06-S06 — Transcripts
# ──────────────────────────────────────────────────────────────


@router.post("/transcripts/generate", status_code=201)
@require_permission(Permission.MARKS_READ)
async def generate_transcript(request: Request, body: dict) -> JSONResponse:
    result = TranscriptService.generate(
        org_id=_org(request),
        student_id=body["student_id"],
        actor_id=_actor(request),
        is_official=body.get("is_official", False),
    )
    return JSONResponse(status_code=201, content=result)


@router.get("/transcripts/student/{student_id}")
@require_permission(Permission.MARKS_READ)
async def list_transcripts(request: Request, student_id: str) -> JSONResponse:
    items = TranscriptService.list_for_student(_org(request), student_id)
    return JSONResponse(content=_jsonify({"transcripts": items}))


# ──────────────────────────────────────────────────────────────
# E06-S07 — Re-evaluation
# ──────────────────────────────────────────────────────────────


@router.post("/reeval", status_code=201)
@require_permission(Permission.MARKS_READ)
async def submit_reeval(request: Request, body: ReEvalRequest) -> JSONResponse:
    result = ReEvalService.submit_request(
        org_id=_org(request),
        student_id=_actor(request),
        req=body,
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=result)


@router.get("/reeval/pending")
@require_permission(Permission.MARKS_FINALIZE)
async def list_pending_reeval(request: Request) -> JSONResponse:
    items = ReEvalService.list_pending(_org(request))
    return JSONResponse(
        content=_jsonify({"reeval_requests": items, "total": len(items)})
    )


@router.get("/reeval/student/{student_id}")
@require_permission(Permission.MARKS_READ)
async def list_student_reeval(request: Request, student_id: str) -> JSONResponse:
    items = ReEvalService.list_for_student(_org(request), student_id)
    return JSONResponse(content=_jsonify({"reeval_requests": items}))


@router.post("/reeval/{reeval_id}/decide")
@require_permission(Permission.MARKS_FINALIZE)
async def decide_reeval(
    request: Request, reeval_id: str, body: ReEvalDecision
) -> JSONResponse:
    result = ReEvalService.decide(_org(request), reeval_id, body, _actor(request))
    return JSONResponse(content=result)


# ──────────────────────────────────────────────────────────────
# E06-S08 — Analytics
# ──────────────────────────────────────────────────────────────


@router.get("/analytics/course/{exam_schedule_id}")
@require_permission(Permission.MARKS_READ)
async def course_analytics(request: Request, exam_schedule_id: str) -> JSONResponse:
    return JSONResponse(
        content=_jsonify(
            GradeAnalyticsService.get_course_statistics(_org(request), exam_schedule_id)
        )
    )


@router.get("/analytics/semester")
@require_permission(Permission.MARKS_READ)
async def semester_analytics(
    request: Request,
    academic_year: str = Query(...),
    semester: int = Query(...),
) -> JSONResponse:
    return JSONResponse(
        content=_jsonify(
            GradeAnalyticsService.get_semester_statistics(
                _org(request), academic_year, semester
            )
        )
    )


@router.get("/analytics/student/{student_id}/trend")
@require_permission(Permission.MARKS_READ)
async def student_performance_trend(request: Request, student_id: str) -> JSONResponse:
    items = GradeAnalyticsService.get_student_performance_trend(
        _org(request), student_id
    )
    return JSONResponse(content=_jsonify({"trend": items}))


@router.get("/analytics/semester/ai-insights")
@require_permission(Permission.MARKS_READ)
async def semester_ai_insights(
    request: Request,
    academic_year: str = Query(...),
    semester: int = Query(...),
) -> JSONResponse:
    return JSONResponse(
        content=_jsonify(
            GradeAnalyticsService.generate_ai_insights(
                _org(request), academic_year, semester
            )
        )
    )


# ──────────────────────────────────────────────────────────────
# E06-S05 — AI Evaluation Faculty Review Queue
# ──────────────────────────────────────────────────────────────


@router.get("/ai-eval/faculty-review-queue")
@require_permission(Permission.MARKS_READ)
async def get_ai_faculty_review_queue(
    request: Request,
    faculty_id: str | None = Query(None),
) -> JSONResponse:
    """Return AI evaluation records pending faculty confirmation (confidence < threshold)."""
    from server.examinations.ai_evaluation_guard import AIEvaluationGuard

    fid = faculty_id or _actor(request)
    items = AIEvaluationGuard.get_faculty_review_queue(_org(request), fid)
    return JSONResponse(content=_jsonify({"items": items, "total": len(items)}))
