"""Feature Flags API — Institutional Feature Toggle Management

Endpoints:
  GET  /api/v1/admin/feature-flags               List all flags for tenant
  GET  /api/v1/admin/feature-flags/{flag_key}    Get single flag
  PUT  /api/v1/admin/feature-flags/{flag_key}    Enable/disable + config update
  POST /api/v1/admin/feature-flags/seed          Seed default flags (onboarding)
  POST /api/v1/admin/feature-flags/invalidate    Invalidate entire tenant cache

RBAC:
  FEATURE_FLAG_READ   — list / get
  FEATURE_FLAG_MANAGE — put / seed / invalidate  (ADMIN + SUPER_ADMIN only)

Reference: ALIS-skills/references/architecture.md §12
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from server.core.feature_flags import feature_flags
from server.core.rbac import Permission, require_permission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/admin/feature-flags", tags=["feature-flags"])


def _org(r: Request) -> str:
    return getattr(r.state, "tenant_id", "default")


def _actor(r: Request) -> str:
    return getattr(r.state, "user_id", "anonymous")


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class FlagUpdate(BaseModel):
    enabled: bool
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)


class FlagResponse(BaseModel):
    flag_key: str
    enabled: bool
    config: Dict[str, Any]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("")
@require_permission(Permission.FEATURE_FLAG_READ)
async def list_flags(request: Request):
    """Return all feature flags for the calling tenant."""
    try:
        flags = feature_flags.get_all(_org(request))
        return JSONResponse(content={
            "flags": [
                {"flag_key": k, "enabled": v["enabled"], "config": v["config"]}
                for k, v in flags.items()
            ],
            "total": len(flags),
        })
    except Exception as exc:
        logger.error("feature_flags list: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{flag_key:path}")
@require_permission(Permission.FEATURE_FLAG_READ)
async def get_flag(flag_key: str, request: Request):
    """Return a single flag by key (dot-notation, e.g. academics.ai_ppt_generation)."""
    try:
        org_id = _org(request)
        enabled = feature_flags.is_enabled(flag_key, org_id)
        config = feature_flags.get_config(flag_key, org_id, default={})
        return JSONResponse(content={
            "flag_key": flag_key,
            "enabled": enabled,
            "config": config or {},
        })
    except Exception as exc:
        logger.error("feature_flags get %s: %s", flag_key, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.put("/{flag_key:path}")
@require_permission(Permission.FEATURE_FLAG_MANAGE)
async def update_flag(flag_key: str, body: FlagUpdate, request: Request):
    """Enable or disable a flag and optionally update its config parameters."""
    try:
        feature_flags.set_flag(
            flag_key=flag_key,
            tenant_id=_org(request),
            enabled=body.enabled,
            config=body.config or {},
            actor_id=_actor(request),
        )
        return JSONResponse(content={
            "flag_key": flag_key,
            "enabled": body.enabled,
            "config": body.config or {},
            "updated_by": _actor(request),
        })
    except Exception as exc:
        logger.error("feature_flags update %s: %s", flag_key, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/seed")
@require_permission(Permission.FEATURE_FLAG_MANAGE)
async def seed_defaults(request: Request):
    """Seed the default flag set for this tenant.

    Idempotent — skips flags that already exist.
    Typically called once during institution onboarding.
    """
    try:
        org_id = _org(request)
        created = feature_flags.seed_defaults(org_id, actor_id=_actor(request))
        return JSONResponse(content={
            "org_id": org_id,
            "flags_created": created,
            "message": f"Seeded {created} default flags (skipped existing).",
        })
    except Exception as exc:
        logger.error("feature_flags seed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/invalidate")
@require_permission(Permission.FEATURE_FLAG_MANAGE)
async def invalidate_cache(request: Request):
    """Flush the Redis cache for all flags of this tenant.

    Use after bulk imports or direct DB updates that bypassed set_flag().
    """
    try:
        feature_flags.invalidate_all(_org(request))
        return JSONResponse(content={"message": "Feature flag cache invalidated."})
    except Exception as exc:
        logger.error("feature_flags invalidate: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
