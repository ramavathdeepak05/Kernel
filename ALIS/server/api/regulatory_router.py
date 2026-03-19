"""E14 — Regulatory & Accreditation API Router

Endpoints:
  GET  /api/v1/regulatory/naac/dashboard            NAAC criterion summary (all 7)
  GET  /api/v1/regulatory/naac/criterion/{n}        Drill-down for one criterion (1–7)
  GET  /api/v1/regulatory/naac/evidence             List NAAC evidence items
  POST /api/v1/regulatory/naac/evidence             Add evidence item
  GET  /api/v1/regulatory/naac/iqac-score           IQAC readiness score
  GET  /api/v1/regulatory/metrics                   Raw regulatory_metrics (all frameworks)
  GET  /api/v1/regulatory/metrics/{key}/trend       Trend for a single metric key
  POST /api/v1/regulatory/nirf/compute              Compute NIRF submission data
  GET  /api/v1/regulatory/nirf/{year}               Get NIRF submission for a year

RBAC:
  COMPLIANCE_READ    — all GET endpoints
  COMPLIANCE_SUBMIT  — POST endpoints (compute, add evidence)

Feature gate: regulatory.naac_evidence_collection must be enabled.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from server.core.feature_flags import feature_flags
from server.core.rbac import Permission, require_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/regulatory", tags=["regulatory"])


def _org(r: Request) -> str:
    return getattr(r.state, "tenant_id", "default")


def _actor(r: Request) -> str:
    return getattr(r.state, "user_id", "anonymous")


def _require_regulatory_flag(org_id: str) -> None:
    """Gate all regulatory endpoints behind the feature flag.

    Raises 403 if the tenant has not enabled regulatory.naac_evidence_collection.
    """
    if not feature_flags.is_enabled("regulatory.naac_evidence_collection", org_id):
        raise HTTPException(
            status_code=403,
            detail=(
                "Regulatory module is not enabled for this institution. "
                "Enable 'regulatory.naac_evidence_collection' feature flag first."
            ),
        )


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class EvidenceCreate(BaseModel):
    criterion: int = Field(..., ge=1, le=7)
    indicator_key: str
    title: str
    academic_year: str
    evidence_type: str = "DOCUMENT"
    file_key: Optional[str] = None
    evidence_data: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# NAAC Dashboard
# ---------------------------------------------------------------------------

@router.get("/naac/dashboard")
@require_permission(Permission.COMPLIANCE_READ)
async def naac_dashboard(
    request: Request,
    academic_year: Optional[str] = Query(default=None),
):
    """Full NAAC criterion summary — all 7 criteria from regulatory_metrics."""
    org_id = _org(request)
    _require_regulatory_flag(org_id)
    try:
        from server.regulatory.naac_service import NAACService
        data = NAACService.get_dashboard(org_id, academic_year)
        return JSONResponse(content=data)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("regulatory: naac dashboard: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/naac/criterion/{criterion}")
@require_permission(Permission.COMPLIANCE_READ)
async def naac_criterion_detail(criterion: int, request: Request):
    """Drill-down metrics for a single NAAC criterion (1–7)."""
    if criterion < 1 or criterion > 7:
        raise HTTPException(status_code=400, detail="Criterion must be between 1 and 7.")
    org_id = _org(request)
    _require_regulatory_flag(org_id)
    try:
        from server.regulatory.naac_service import NAACService
        return JSONResponse(content=NAACService.get_criterion_detail(org_id, criterion))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("regulatory: criterion detail: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/naac/evidence")
@require_permission(Permission.COMPLIANCE_READ)
async def list_evidence(
    request: Request,
    criterion: Optional[int] = Query(default=None),
    academic_year: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    """List NAAC evidence items, optionally filtered."""
    org_id = _org(request)
    _require_regulatory_flag(org_id)
    try:
        from server.regulatory.naac_service import NAACService
        items = NAACService.get_evidence_list(org_id, criterion, academic_year, status)
        return JSONResponse(content={"evidence": items, "total": len(items)})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("regulatory: evidence list: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/naac/evidence")
@require_permission(Permission.COMPLIANCE_SUBMIT)
async def add_evidence(body: EvidenceCreate, request: Request):
    """Add a NAAC evidence item."""
    org_id = _org(request)
    _require_regulatory_flag(org_id)
    try:
        from server.regulatory.naac_service import NAACService
        new_id = NAACService.add_evidence(
            org_id=org_id,
            criterion=body.criterion,
            indicator_key=body.indicator_key,
            title=body.title,
            academic_year=body.academic_year,
            evidence_type=body.evidence_type,
            file_key=body.file_key,
            evidence_data=body.evidence_data,
            collected_by=_actor(request),
        )
        return JSONResponse(content={"id": new_id, "status": "COLLECTED"}, status_code=201)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("regulatory: add evidence: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/naac/iqac-score")
@require_permission(Permission.COMPLIANCE_READ)
async def iqac_score(request: Request):
    """Compute indicative IQAC readiness score from live metrics."""
    org_id = _org(request)
    _require_regulatory_flag(org_id)
    try:
        from server.regulatory.naac_service import NAACService
        return JSONResponse(content=NAACService.compute_iqac_score(org_id))
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("regulatory: iqac score: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Raw metrics
# ---------------------------------------------------------------------------

@router.get("/metrics")
@require_permission(Permission.COMPLIANCE_READ)
async def list_metrics(
    request: Request,
    framework: str = Query(default="NAAC"),
    limit: int = Query(default=100, le=500),
):
    """Latest value per metric key for the given framework."""
    org_id = _org(request)
    _require_regulatory_flag(org_id)
    try:
        from server.regulatory.metrics_service import RegulatoryMetricsService
        rows = RegulatoryMetricsService.get_latest(org_id, framework, limit)
        return JSONResponse(content={"metrics": rows, "total": len(rows), "framework": framework})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("regulatory: metrics list: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/metrics/{metric_key:path}/trend")
@require_permission(Permission.COMPLIANCE_READ)
async def metric_trend(
    metric_key: str,
    request: Request,
    days: int = Query(default=30, le=365),
):
    """Daily values for a single metric key over the past N days."""
    org_id = _org(request)
    _require_regulatory_flag(org_id)
    try:
        from server.regulatory.metrics_service import RegulatoryMetricsService
        rows = RegulatoryMetricsService.get_trend(org_id, metric_key, days)
        return JSONResponse(content={"metric_key": metric_key, "trend": rows, "days": days})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("regulatory: metric trend: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# NIRF
# ---------------------------------------------------------------------------

@router.post("/nirf/compute")
@require_permission(Permission.COMPLIANCE_SUBMIT)
async def compute_nirf(
    request: Request,
    submission_year: int = Query(..., description="NIRF submission year e.g. 2026"),
):
    """Compute NIRF parameter data from regulatory_metrics and persist as DRAFT."""
    org_id = _org(request)
    _require_regulatory_flag(org_id)
    try:
        from server.regulatory.nirf_service import NIRFService
        result = NIRFService.compute_submission(org_id, submission_year)
        return JSONResponse(content=result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("regulatory: nirf compute: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/nirf/{submission_year}")
@require_permission(Permission.COMPLIANCE_READ)
async def get_nirf(submission_year: int, request: Request):
    """Return NIRF submission data for a specific year."""
    org_id = _org(request)
    _require_regulatory_flag(org_id)
    try:
        from server.regulatory.nirf_service import NIRFService
        rows = NIRFService.get_submission(org_id, submission_year)
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No NIRF data found for {submission_year}. Run POST /nirf/compute first.",
            )
        return JSONResponse(content={"submission_year": submission_year, "parameters": rows})
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("regulatory: nirf get: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
