"""
ALIS Tenant Registry — S1 (SaaS Multi-Tenant Foundation)

Resolves per-tenant metadata (DB DSN, plan, feature flags) from Redis cache
or the control plane HTTP API. Used by DBRouter and SubdomainTenantMiddleware.

Resolution priority
-------------------
1. Redis cache      — key: alis:tenant:rec:{tenant_id}, TTL: 5 min (configurable)
2. Control plane    — GET {control_plane_url}/internal/tenants/{tenant_id}/db-config
3. Settings fallback — single-tenant mode when CONTROL_PLANE_URL is empty (backward compat)

The fallback guarantee ensures that upgrading an existing single-tenant ALIS
deployment to S1 requires *zero* config changes — the system continues to use
the existing `settings.db_url` for all queries.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_TENANT_REC_PFX = "alis:tenant:rec:"  # → TenantRecord JSON (keyed by tenant_id)
_TENANT_SUB_PFX = "alis:tenant:sub:"  # → tenant_id string (keyed by subdomain slug)


@dataclass
class TenantRecord:
    """
    Resolved tenant metadata.

    Cached in Redis and consumed by DBRouter (pool key) and
    SubdomainTenantMiddleware (subdomain→tenant_id resolution).
    """

    tenant_id: str
    subdomain: str
    region: str = "in-central"
    db_url: str = ""         # asyncpg postgresql+asyncpg:// DSN
    db_url_sync: str = ""    # psycopg2 postgresql:// DSN
    plan: str = "starter"    # starter | growth | enterprise
    feature_flags: dict = field(default_factory=dict)
    status: str = "active"   # active | suspended | deleted


class TenantRegistry:
    """
    Cache-aside registry for TenantRecord objects.

    All public methods are either async (for FastAPI handlers) or sync
    (suffixed _sync — for Celery workers and psycopg2 code paths).
    """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_redis():
        """Reuse the same Redis factory as the security module."""
        from server.core.security import _get_redis as _sec_get_redis
        return _sec_get_redis()

    @staticmethod
    def _to_dict(r: TenantRecord) -> dict:
        return {
            "tenant_id": r.tenant_id,
            "subdomain": r.subdomain,
            "region": r.region,
            "db_url": r.db_url,
            "db_url_sync": r.db_url_sync,
            "plan": r.plan,
            "feature_flags": r.feature_flags,
            "status": r.status,
        }

    @staticmethod
    def _from_dict(d: dict) -> TenantRecord:
        return TenantRecord(
            tenant_id=d["tenant_id"],
            subdomain=d["subdomain"],
            region=d.get("region", "in-central"),
            db_url=d.get("db_url", ""),
            db_url_sync=d.get("db_url_sync", ""),
            plan=d.get("plan", "starter"),
            feature_flags=d.get("feature_flags", {}),
            status=d.get("status", "active"),
        )

    @classmethod
    def _build_fallback(cls, tenant_id: str) -> TenantRecord:
        """
        Single-tenant fallback when no control plane is configured.

        Returns a record pointing at the same DB as the monolith settings —
        preserving full backward compatibility with pre-SaaS deployments.
        """
        from server.core.settings import settings
        return TenantRecord(
            tenant_id=tenant_id,
            subdomain=tenant_id,
            region="in-central",
            # asyncpg.create_pool() uses plain postgresql:// (not postgresql+asyncpg://)
            db_url=settings.db_url,
            db_url_sync=settings.db_url,
            plan="enterprise",
            feature_flags={},
            status="active",
        )

    @classmethod
    def _cache_record(cls, record: TenantRecord) -> None:
        """Persist record + subdomain index to Redis. Fails silently — cache is advisory."""
        from server.core.settings import settings
        ttl = settings.tenant_db_cache_ttl_seconds
        try:
            r = cls._get_redis()
            payload = json.dumps(cls._to_dict(record))
            r.setex(_TENANT_REC_PFX + record.tenant_id, ttl, payload)
            if record.subdomain:
                r.setex(_TENANT_SUB_PFX + record.subdomain, ttl, record.tenant_id)
        except Exception as exc:
            logger.warning("TenantRegistry: Redis cache write failed: %s", exc)

    # ------------------------------------------------------------------
    # Control plane fetch (async)
    # ------------------------------------------------------------------

    @classmethod
    async def _cp_fetch_by_id(cls, tenant_id: str) -> Optional[TenantRecord]:
        from server.core.settings import settings
        if not settings.control_plane_url:
            return None
        try:
            import httpx
            url = f"{settings.control_plane_url}/internal/tenants/{tenant_id}/db-config"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    url, headers={"X-Internal-Token": settings.control_plane_token}
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return cls._from_dict(resp.json())
        except Exception as exc:
            logger.warning("TenantRegistry: control-plane fetch failed tenant=%s: %s", tenant_id, exc)
            return None

    @classmethod
    async def _cp_fetch_by_subdomain(cls, subdomain: str) -> Optional[TenantRecord]:
        from server.core.settings import settings
        if not settings.control_plane_url:
            return None
        try:
            import httpx
            url = f"{settings.control_plane_url}/internal/tenants/by-subdomain/{subdomain}"
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    url, headers={"X-Internal-Token": settings.control_plane_token}
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return cls._from_dict(resp.json())
        except Exception as exc:
            logger.warning("TenantRegistry: subdomain control-plane fetch failed sub=%s: %s", subdomain, exc)
            return None

    # ------------------------------------------------------------------
    # Control plane fetch (sync — Celery workers)
    # ------------------------------------------------------------------

    @classmethod
    def _cp_fetch_by_id_sync(cls, tenant_id: str) -> Optional[TenantRecord]:
        from server.core.settings import settings
        if not settings.control_plane_url:
            return None
        try:
            import httpx
            url = f"{settings.control_plane_url}/internal/tenants/{tenant_id}/db-config"
            resp = httpx.get(
                url,
                headers={"X-Internal-Token": settings.control_plane_token},
                timeout=5.0,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return cls._from_dict(resp.json())
        except Exception as exc:
            logger.warning("TenantRegistry: sync control-plane fetch failed tenant=%s: %s", tenant_id, exc)
            return None

    # ------------------------------------------------------------------
    # Public API — async
    # ------------------------------------------------------------------

    @classmethod
    async def get_by_id(cls, tenant_id: str) -> TenantRecord:
        """
        Resolve tenant by ID.

        Cache → control plane → settings fallback.
        Always returns a valid TenantRecord (never raises).
        """
        # 1. Redis cache
        try:
            r = cls._get_redis()
            cached = r.get(_TENANT_REC_PFX + tenant_id)
            if cached:
                return cls._from_dict(json.loads(cached))
        except Exception as exc:
            logger.warning("TenantRegistry: Redis read failed: %s", exc)

        # 2. Control plane HTTP
        record = await cls._cp_fetch_by_id(tenant_id)
        if record:
            cls._cache_record(record)
            return record

        # 3. Single-tenant fallback
        record = cls._build_fallback(tenant_id)
        cls._cache_record(record)
        return record

    @classmethod
    async def get_by_subdomain(cls, subdomain: str) -> Optional[TenantRecord]:
        """
        Resolve tenant by subdomain slug.

        Returns None if subdomain is not registered (unknown tenant).
        Used by SubdomainTenantMiddleware.
        """
        # 1. Redis subdomain index
        try:
            r = cls._get_redis()
            tenant_id = r.get(_TENANT_SUB_PFX + subdomain)
            if tenant_id:
                return await cls.get_by_id(tenant_id)
        except Exception as exc:
            logger.warning("TenantRegistry: Redis subdomain lookup failed: %s", exc)

        # 2. Control plane lookup
        record = await cls._cp_fetch_by_subdomain(subdomain)
        if record:
            cls._cache_record(record)
            return record

        return None

    # ------------------------------------------------------------------
    # Public API — sync (Celery workers, psycopg2 code paths)
    # ------------------------------------------------------------------

    @classmethod
    def get_by_id_sync(cls, tenant_id: str) -> TenantRecord:
        """Sync variant of get_by_id — for Celery workers and psycopg2 code."""
        # 1. Redis cache
        try:
            r = cls._get_redis()
            cached = r.get(_TENANT_REC_PFX + tenant_id)
            if cached:
                return cls._from_dict(json.loads(cached))
        except Exception as exc:
            logger.warning("TenantRegistry: Redis sync read failed: %s", exc)

        # 2. Control plane HTTP (sync)
        record = cls._cp_fetch_by_id_sync(tenant_id)
        if record:
            cls._cache_record(record)
            return record

        # 3. Single-tenant fallback
        record = cls._build_fallback(tenant_id)
        cls._cache_record(record)
        return record

    # ------------------------------------------------------------------
    # Cache invalidation
    # ------------------------------------------------------------------

    @classmethod
    async def invalidate(cls, tenant_id: str, subdomain: Optional[str] = None) -> None:
        """
        Evict cached tenant record from Redis.

        Called by control plane webhook on config change (e.g., DB migration,
        plan upgrade, tenant suspension).
        """
        try:
            r = cls._get_redis()
            r.delete(_TENANT_REC_PFX + tenant_id)
            if subdomain:
                r.delete(_TENANT_SUB_PFX + subdomain)
            logger.info("TenantRegistry: evicted cache for tenant=%s", tenant_id)
        except Exception as exc:
            logger.warning("TenantRegistry.invalidate failed: %s", exc)
