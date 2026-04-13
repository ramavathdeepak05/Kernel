"""E18 — Convocation Management API Router

Routes:
  POST   /convocation                               — create convocation event
  GET    /convocation                               — list convocations
  GET    /convocation/{convocation_id}              — get single convocation
  POST   /convocation/{convocation_id}/audit        — run degree audit
  GET    /convocation/{convocation_id}/audit        — get degree audit records
  POST   /convocation/{convocation_id}/gold-medals  — compute gold medals
  GET    /convocation/{convocation_id}/gold-medals  — get gold medal records
  POST   /convocation/{convocation_id}/generate-seating — generate seating plan
  GET    /convocation/{convocation_id}/seating      — get seating records
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from server.convocation.convocation_service import ConvocationService
from server.core.rbac import Permission, require_permission
from server.db_service import execute_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/convocation", tags=["Convocation"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _org(r: Request) -> str:
    return getattr(r.state, "tenant_id", "default")


def _actor(r: Request) -> str:
    return getattr(r.state, "user_id", "anonymous")


def _jsonify(obj):
    """Recursively convert date/datetime/Decimal to JSON-safe types."""
    from datetime import date as _date
    from datetime import datetime
    from decimal import Decimal

    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonify(i) for i in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, _date)):
        return obj.isoformat()
    return obj


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class CreateConvocationBody(BaseModel):
    title: str
    ceremony_date: str  # ISO date string e.g. "2026-11-15"
    academic_year: str  # e.g. "2025-26"
    batch_year: int  # e.g. 2022
    venue: str | None = None
    chief_guest: str | None = None


# ---------------------------------------------------------------------------
# Routes — Convocation CRUD
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
@require_permission(Permission.CONVOCATION_MANAGE)
async def create_convocation(
    request: Request, body: CreateConvocationBody
) -> JSONResponse:
    """Create a new convocation event."""
    result = ConvocationService.create_convocation(
        org_id=_org(request),
        title=body.title,
        ceremony_date=body.ceremony_date,
        academic_year=body.academic_year,
        batch_year=body.batch_year,
        venue=body.venue,
        chief_guest=body.chief_guest,
        created_by=_actor(request),
    )
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.get("")
@require_permission(Permission.CONVOCATION_READ)
async def list_convocations(request: Request) -> JSONResponse:
    """List all convocations for this organisation."""
    items = ConvocationService.list_convocations(org_id=_org(request))
    return JSONResponse(content={"convocations": _jsonify(items), "total": len(items)})


@router.get("/{convocation_id}")
@require_permission(Permission.CONVOCATION_READ)
async def get_convocation(request: Request, convocation_id: str) -> JSONResponse:
    """Get a convocation event with audit summary and gold medal details."""
    result = ConvocationService.get_convocation(
        convocation_id=convocation_id,
        org_id=_org(request),
    )
    return JSONResponse(content=_jsonify(result))


# ---------------------------------------------------------------------------
# Routes — Degree Audit
# ---------------------------------------------------------------------------


@router.post("/{convocation_id}/audit", status_code=202)
@require_permission(Permission.CONVOCATION_MANAGE)
async def run_degree_audit(request: Request, convocation_id: str) -> JSONResponse:
    """Trigger degree eligibility audit for all students in the convocation batch."""
    summary = ConvocationService.run_degree_audit(
        convocation_id=convocation_id,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=202, content=_jsonify(summary))


@router.get("/{convocation_id}/audit")
@require_permission(Permission.CONVOCATION_READ)
async def get_degree_audit_records(
    request: Request, convocation_id: str
) -> JSONResponse:
    """Retrieve all degree audit records for a convocation."""
    org_id = _org(request)

    # Verify the convocation belongs to this org before returning data
    convocation_rows = execute_query(
        "SELECT id FROM convocation_events WHERE id = %s AND org_id = %s",
        (convocation_id, org_id),
    )
    if not convocation_rows:
        from server.core.exceptions import NotFoundError

        raise NotFoundError(f"Convocation {convocation_id} not found")

    records = execute_query(
        """
        SELECT cda.*,
               COALESCE(s.full_name, s.first_name || ' ' || s.last_name, s.id) AS student_name,
               p.name AS program_name, p.code AS program_code
        FROM convocation_degree_audits cda
        JOIN students s ON s.id = cda.student_id
        LEFT JOIN programs p ON p.id = cda.program_id
        WHERE cda.convocation_id = %s
        ORDER BY cda.program_id, student_name
        """,
        (convocation_id,),
    )
    data = [dict(r) for r in records]
    return JSONResponse(content={"audit_records": _jsonify(data), "total": len(data)})


# ---------------------------------------------------------------------------
# Routes — Gold Medals
# ---------------------------------------------------------------------------


@router.post("/{convocation_id}/gold-medals", status_code=201)
@require_permission(Permission.CONVOCATION_MANAGE)
async def compute_gold_medals(request: Request, convocation_id: str) -> JSONResponse:
    """Compute gold medal winners per program (policy-controlled grace exclusion)."""
    medals = ConvocationService.compute_gold_medals(
        convocation_id=convocation_id,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(
        status_code=201, content={"gold_medals": _jsonify(medals), "total": len(medals)}
    )


@router.get("/{convocation_id}/gold-medals")
@require_permission(Permission.CONVOCATION_READ)
async def get_gold_medals(request: Request, convocation_id: str) -> JSONResponse:
    """Retrieve gold medal computation records for a convocation."""
    org_id = _org(request)

    convocation_rows = execute_query(
        "SELECT id FROM convocation_events WHERE id = %s AND org_id = %s",
        (convocation_id, org_id),
    )
    if not convocation_rows:
        from server.core.exceptions import NotFoundError

        raise NotFoundError(f"Convocation {convocation_id} not found")

    medals = execute_query(
        """
        SELECT gmc.*,
               COALESCE(s.full_name, s.first_name || ' ' || s.last_name, s.id) AS student_name,
               p.name AS program_name, p.code AS program_code
        FROM gold_medal_computations gmc
        JOIN students s ON s.id = gmc.student_id
        LEFT JOIN programs p ON p.id = gmc.program_id
        WHERE gmc.convocation_id = %s
        ORDER BY gmc.program_id
        """,
        (convocation_id,),
    )
    data = [dict(m) for m in medals]
    return JSONResponse(content={"gold_medals": _jsonify(data), "total": len(data)})


# ---------------------------------------------------------------------------
# Routes — Seating
# ---------------------------------------------------------------------------


@router.post("/{convocation_id}/generate-seating", status_code=201)
@require_permission(Permission.CONVOCATION_MANAGE)
async def generate_seating(request: Request, convocation_id: str) -> JSONResponse:
    """Generate (or re-generate) the seating plan for all eligible graduates."""
    result = ConvocationService.generate_seating(
        convocation_id=convocation_id,
        org_id=_org(request),
        actor_id=_actor(request),
    )
    return JSONResponse(status_code=201, content=_jsonify(result))


@router.get("/{convocation_id}/seating")
@require_permission(Permission.CONVOCATION_READ)
async def get_seating(request: Request, convocation_id: str) -> JSONResponse:
    """Retrieve the seating plan for a convocation."""
    org_id = _org(request)

    convocation_rows = execute_query(
        "SELECT id FROM convocation_events WHERE id = %s AND org_id = %s",
        (convocation_id, org_id),
    )
    if not convocation_rows:
        from server.core.exceptions import NotFoundError

        raise NotFoundError(f"Convocation {convocation_id} not found")

    seats = execute_query(
        """
        SELECT cs.*,
               COALESCE(s.full_name, s.first_name || ' ' || s.last_name, s.id) AS student_name,
               p.name AS program_name, p.code AS program_code
        FROM convocation_seating cs
        JOIN students s ON s.id = cs.student_id
        LEFT JOIN programs p ON p.id = cs.program_id
        WHERE cs.convocation_id = %s
        ORDER BY cs.overall_position
        """,
        (convocation_id,),
    )
    data = [dict(s) for s in seats]
    return JSONResponse(content={"seating": _jsonify(data), "total": len(data)})
