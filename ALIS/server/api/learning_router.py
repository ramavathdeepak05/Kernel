"""
In-house Learning Management API Router — P40

Replaces the Moodle LMS stub with a native ALIS learning module.

Routes:
  Materials   POST/GET /learning/courses/{course_id}/materials
              POST     /learning/courses/{course_id}/materials/generate
              GET      /learning/materials/{material_id}
              PATCH    /learning/materials/{material_id}/publish
              PATCH    /learning/materials/{material_id}/archive

  Assignments POST/GET /learning/courses/{course_id}/assignments
              POST     /learning/courses/{course_id}/assignments/generate
              GET      /learning/assignments/{assignment_id}
              PATCH    /learning/assignments/{assignment_id}/publish
              PATCH    /learning/assignments/{assignment_id}/close

  Submissions PUT      /learning/assignments/{assignment_id}/my-submission
              POST     /learning/assignments/{assignment_id}/my-submission/submit
              GET      /learning/assignments/{assignment_id}/my-submission
              GET      /learning/assignments/{assignment_id}/submissions
              PATCH    /learning/submissions/{submission_id}/begin-review
              PATCH    /learning/submissions/{submission_id}/grade
              PATCH    /learning/submissions/{submission_id}/return
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from server.core.rbac import Permission, require_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/learning", tags=["learning"])


# ---------------------------------------------------------------------------
# Helpers (same pattern as academics_router)
# ---------------------------------------------------------------------------


def _jsonify(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonify(i) for i in obj]
    return obj


def _org(r: Request) -> str:
    return getattr(r.state, "tenant_id", "default")


def _actor(r: Request) -> str:
    return getattr(r.state, "user_id", "anonymous")


def _role(r: Request) -> str:
    return getattr(r.state, "user_role", "STUDENT")


def _student_id(request: Request, org_id: str) -> str:
    """Resolve student UUID from the authenticated user_id."""
    from server.db_service import execute_query

    rows = execute_query(
        "SELECT id FROM students WHERE user_id=%s AND org_id=%s",
        (_actor(request), org_id),
    )
    if not rows:
        raise PermissionError("No student profile found for this user")
    return str(rows[0]["id"])


def _fetch_co_context(org_id: str, course_id: str, co_id: str | None) -> dict:
    """Fetch CO data needed to build AI generation variables."""
    from server.db_service import execute_query

    # Course metadata
    course_rows = execute_query(
        "SELECT name, code FROM courses WHERE id=%s AND org_id=%s",
        (course_id, org_id),
    )
    if not course_rows:
        raise ValueError(f"Course {course_id} not found")
    course = course_rows[0]

    # CO data — single CO if specified, else all COs for the course
    if co_id:
        co_rows = execute_query(
            "SELECT code, description, bloom_level FROM course_outcomes WHERE id=%s AND course_id=%s",
            (co_id, course_id),
        )
    else:
        co_rows = execute_query(
            "SELECT code, description, bloom_level FROM course_outcomes WHERE course_id=%s ORDER BY code",
            (course_id,),
        )

    return {
        "course_name": course["name"],
        "course_code": course["code"],
        "co_codes": [r["code"] for r in co_rows] or ["CO1"],
        "co_descriptions": [r["description"] for r in co_rows]
        or ["General understanding"],
        "bloom_levels": [r.get("bloom_level", "Apply") for r in co_rows] or ["Apply"],
    }


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------


@router.post("/courses/{course_id}/materials")
@require_permission(Permission.LEARNING_MANAGE)
async def create_material(course_id: str, request: Request):
    from server.academics.learning_service import CourseMaterialService

    body = await request.json()
    org_id = _org(request)
    result = CourseMaterialService.create_material(
        org_id=org_id,
        course_id=course_id,
        faculty_id=_actor(request),
        title=body["title"],
        material_type=body["material_type"],
        content_body=body.get("content_body"),
        file_url=body.get("file_url"),
        co_id=body.get("co_id"),
        week_number=body.get("week_number"),
    )
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.post("/courses/{course_id}/materials/generate")
@require_permission(Permission.LEARNING_MANAGE)
async def generate_material(course_id: str, request: Request):
    """AI-generate course material from CO + syllabus context."""
    from server.academics.learning_service import CourseMaterialService
    from server.agents.academics.content_generator_v1 import (
        GENERATION_TYPE_TO_MATERIAL_TYPE,
        execute_content_generator,
    )
    from server.core.ai_gateway import AIGatewayContext

    body = await request.json()
    org_id = _org(request)
    generation_type = body.get("generation_type", "lecture_notes")
    co_id = body.get("co_id")

    # Build AI input from course + CO data
    co_context = _fetch_co_context(org_id, course_id, co_id)
    params = body.get("generation_params", {})
    input_data = {
        **co_context,
        "course_id": course_id,
        **params,
    }
    if "week_number" in body:
        input_data["week_number"] = body["week_number"]

    context = AIGatewayContext(
        actor_id=_actor(request),
        actor_role=_role(request),
        actor_type="faculty",
        org_id=org_id,
        module="M2",
        wizard="Learning Content Generator",
    )

    ai_result = execute_content_generator(context, input_data, generation_type)

    # Parse generated body from AI result
    generated_title = body.get(
        "title", f"Generated {generation_type.replace('_', ' ').title()}"
    )
    generated_body = None
    if ai_result and ai_result.content:
        try:
            parsed = json.loads(ai_result.content)
            generated_title = parsed.get("title", generated_title)
            generated_body = parsed.get("body")
        except (json.JSONDecodeError, TypeError):
            generated_body = ai_result.content

    material_type = GENERATION_TYPE_TO_MATERIAL_TYPE.get(generation_type, "OTHER")
    material = CourseMaterialService.create_material(
        org_id=org_id,
        course_id=course_id,
        faculty_id=_actor(request),
        title=generated_title,
        material_type=material_type,
        content_body=generated_body,
        co_id=co_id,
        week_number=body.get("week_number"),
        is_ai_generated=True,
        ai_prompt_name=f"learning.{generation_type}",
        ai_prompt_version=1,
    )

    if body.get("auto_publish"):
        material = CourseMaterialService.publish_material(
            org_id, material["id"], _actor(request)
        )

    return JSONResponse(
        status_code=201,
        content=_jsonify(
            {
                "material": material,
                "ai_confidence": ai_result.confidence_score if ai_result else None,
                "ai_confidence_tier": ai_result.confidence_tier if ai_result else None,
            }
        ),
    )


@router.get("/courses/{course_id}/materials")
@require_permission(Permission.LEARNING_READ)
async def list_materials(
    course_id: str,
    request: Request,
    week: int | None = None,
    type: str | None = None,
):
    from server.academics.learning_service import CourseMaterialService

    items = CourseMaterialService.list_materials(
        org_id=_org(request),
        course_id=course_id,
        actor_role=_role(request),
        week_number=week,
        material_type=type,
    )
    return JSONResponse(content=_jsonify({"materials": items, "total": len(items)}))


@router.get("/materials/{material_id}")
@require_permission(Permission.LEARNING_READ)
async def get_material(material_id: str, request: Request):
    from server.academics.learning_service import CourseMaterialService

    return JSONResponse(
        content=_jsonify(
            CourseMaterialService.get_material(
                _org(request), material_id, _role(request)
            )
        )
    )


@router.patch("/materials/{material_id}/publish")
@require_permission(Permission.LEARNING_MANAGE)
async def publish_material(material_id: str, request: Request):
    from server.academics.learning_service import CourseMaterialService

    return JSONResponse(
        content=_jsonify(
            CourseMaterialService.publish_material(
                _org(request), material_id, _actor(request)
            )
        )
    )


@router.patch("/materials/{material_id}/archive")
@require_permission(Permission.LEARNING_MANAGE)
async def archive_material(material_id: str, request: Request):
    from server.academics.learning_service import CourseMaterialService

    return JSONResponse(
        content=_jsonify(
            CourseMaterialService.archive_material(
                _org(request), material_id, _actor(request)
            )
        )
    )


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


@router.post("/courses/{course_id}/assignments")
@require_permission(Permission.LEARNING_MANAGE)
async def create_assignment(course_id: str, request: Request):
    from server.academics.learning_service import AssignmentService

    body = await request.json()
    result = AssignmentService.create_assignment(
        org_id=_org(request),
        course_id=course_id,
        faculty_id=_actor(request),
        title=body["title"],
        description=body["description"],
        max_marks=Decimal(str(body.get("max_marks", 100))),
        due_date=body["due_date"],
        co_id=body.get("co_id"),
        passing_marks=Decimal(str(body["passing_marks"]))
        if body.get("passing_marks")
        else None,
        allow_late=body.get("allow_late", False),
        late_penalty_pct=Decimal(str(body["late_penalty_pct"]))
        if body.get("late_penalty_pct") is not None
        else None,
    )
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.post("/courses/{course_id}/assignments/generate")
@require_permission(Permission.LEARNING_MANAGE)
async def generate_assignment(course_id: str, request: Request):
    """AI-generate assignment questions with rubric."""
    from server.academics.learning_service import AssignmentService
    from server.agents.academics.content_generator_v1 import execute_content_generator
    from server.core.ai_gateway import AIGatewayContext

    body = await request.json()
    org_id = _org(request)
    co_id = body.get("co_id")

    co_context = _fetch_co_context(org_id, course_id, co_id)
    params = body.get("generation_params", {})
    input_data = {**co_context, "course_id": course_id, **params}

    context = AIGatewayContext(
        actor_id=_actor(request),
        actor_role=_role(request),
        actor_type="faculty",
        org_id=org_id,
        module="M2",
        wizard="Assignment Generator",
    )

    ai_result = execute_content_generator(context, input_data, "assignment_questions")

    generated_description = body.get("title", "AI-Generated Assignment")
    if ai_result and ai_result.content:
        try:
            parsed = json.loads(ai_result.content)
            generated_description = parsed.get("body", generated_description)
        except (json.JSONDecodeError, TypeError):
            generated_description = ai_result.content

    assignment = AssignmentService.create_assignment(
        org_id=org_id,
        course_id=course_id,
        faculty_id=_actor(request),
        title=body.get("title", f"Assignment — {co_context['course_code']}"),
        description=generated_description,
        max_marks=Decimal(str(body.get("max_marks", 100))),
        due_date=body["due_date"],
        co_id=co_id,
        is_ai_generated=True,
        ai_prompt_name="learning.assignment_questions",
        ai_prompt_version=1,
    )

    if body.get("auto_publish"):
        assignment = AssignmentService.publish_assignment(
            org_id, assignment["id"], _actor(request)
        )

    return JSONResponse(
        status_code=201,
        content=_jsonify(
            {
                "assignment": assignment,
                "ai_confidence": ai_result.confidence_score if ai_result else None,
            }
        ),
    )


@router.get("/courses/{course_id}/assignments")
@require_permission(Permission.LEARNING_READ)
async def list_assignments(course_id: str, request: Request):
    from server.academics.learning_service import AssignmentService

    org_id = _org(request)
    student_id = None
    if _role(request).upper() == "STUDENT":
        try:
            student_id = _student_id(request, org_id)
        except PermissionError:
            student_id = None
    items = AssignmentService.list_assignments(
        org_id=org_id,
        course_id=course_id,
        actor_role=_role(request),
        student_id=student_id,
    )
    return JSONResponse(content=_jsonify({"assignments": items, "total": len(items)}))


@router.get("/assignments/{assignment_id}")
@require_permission(Permission.LEARNING_READ)
async def get_assignment(assignment_id: str, request: Request):
    from server.academics.learning_service import AssignmentService

    return JSONResponse(
        content=_jsonify(
            AssignmentService.get_assignment(
                _org(request), assignment_id, _role(request)
            )
        )
    )


@router.patch("/assignments/{assignment_id}/publish")
@require_permission(Permission.LEARNING_MANAGE)
async def publish_assignment(assignment_id: str, request: Request):
    from server.academics.learning_service import AssignmentService

    return JSONResponse(
        content=_jsonify(
            AssignmentService.publish_assignment(
                _org(request), assignment_id, _actor(request)
            )
        )
    )


@router.patch("/assignments/{assignment_id}/close")
@require_permission(Permission.LEARNING_MANAGE)
async def close_assignment(assignment_id: str, request: Request):
    from server.academics.learning_service import AssignmentService

    return JSONResponse(
        content=_jsonify(
            AssignmentService.close_assignment(
                _org(request), assignment_id, _actor(request)
            )
        )
    )


# ---------------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------------


@router.put("/assignments/{assignment_id}/my-submission")
@require_permission(Permission.LEARNING_READ)
async def save_draft_submission(assignment_id: str, request: Request):
    from server.academics.learning_service import SubmissionService

    body = await request.json()
    org_id = _org(request)
    result = SubmissionService.create_or_update_draft(
        org_id=org_id,
        assignment_id=assignment_id,
        student_id=_student_id(request, org_id),
        content_text=body.get("content_text"),
        file_url=body.get("file_url"),
    )
    return JSONResponse(content=_jsonify(result))


@router.post("/assignments/{assignment_id}/my-submission/submit")
@require_permission(Permission.LEARNING_READ)
async def submit_assignment(assignment_id: str, request: Request):
    from server.academics.learning_service import SubmissionService

    org_id = _org(request)
    result = SubmissionService.submit(
        org_id=org_id,
        assignment_id=assignment_id,
        student_id=_student_id(request, org_id),
    )
    return JSONResponse(content=_jsonify(result))


@router.get("/assignments/{assignment_id}/my-submission")
@require_permission(Permission.LEARNING_READ)
async def get_my_submission(assignment_id: str, request: Request):
    from server.academics.learning_service import SubmissionService

    org_id = _org(request)
    result = SubmissionService.get_my_submission(
        org_id=org_id,
        assignment_id=assignment_id,
        student_id=_student_id(request, org_id),
    )
    if result is None:
        return JSONResponse(status_code=404, content={"detail": "No submission found"})
    return JSONResponse(content=_jsonify(result))


@router.get("/assignments/{assignment_id}/submissions")
@require_permission(Permission.LEARNING_MANAGE)
async def list_submissions(
    assignment_id: str,
    request: Request,
    status: str | None = None,
):
    from server.academics.learning_service import SubmissionService

    items = SubmissionService.list_submissions(
        org_id=_org(request),
        assignment_id=assignment_id,
        status_filter=status,
    )
    return JSONResponse(content=_jsonify({"submissions": items, "total": len(items)}))


@router.patch("/submissions/{submission_id}/begin-review")
@require_permission(Permission.LEARNING_MANAGE)
async def begin_review(submission_id: str, request: Request):
    from server.academics.learning_service import SubmissionService

    return JSONResponse(
        content=_jsonify(
            SubmissionService.begin_review(
                _org(request), submission_id, _actor(request)
            )
        )
    )


@router.patch("/submissions/{submission_id}/grade")
@require_permission(Permission.LEARNING_MANAGE)
async def grade_submission(submission_id: str, request: Request):
    from server.academics.learning_service import SubmissionService

    body = await request.json()
    return JSONResponse(
        content=_jsonify(
            SubmissionService.grade_submission(
                org_id=_org(request),
                submission_id=submission_id,
                faculty_id=_actor(request),
                marks_awarded=Decimal(str(body["marks_awarded"])),
                feedback=body.get("feedback"),
            )
        )
    )


@router.patch("/submissions/{submission_id}/return")
@require_permission(Permission.LEARNING_MANAGE)
async def return_submission(submission_id: str, request: Request):
    from server.academics.learning_service import SubmissionService

    return JSONResponse(
        content=_jsonify(
            SubmissionService.return_to_student(
                _org(request), submission_id, _actor(request)
            )
        )
    )
