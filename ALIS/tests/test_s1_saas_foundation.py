"""
S1 SaaS Foundation — Unit Tests

Tests for:
- TenantRegistry  : cache-aside resolution, fallback, invalidation
- DBRouter        : lazy pool creation, double-checked locking, config dispatch
- SubdomainTenantMiddleware : subdomain extraction, cross-tenant guard, static tenant mode
"""
from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_asgi_scope(path: str, host: str = "localhost", token: str = "", tenant_header: str = "") -> dict:
    """Build a minimal ASGI HTTP scope dict."""
    headers = [[b"host", host.encode()]]
    if token:
        headers.append([b"authorization", f"Bearer {token}".encode()])
    if tenant_header:
        headers.append([b"x-tenant-id", tenant_header.encode()])
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers,
        "state": {},
    }


async def _collect_response(app_coro) -> dict:
    """
    Run an ASGI app and collect the status + body.
    Returns {"status": int, "body": bytes}.
    """
    result = {}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            result["status"] = message["status"]
        elif message["type"] == "http.response.body":
            result["body"] = message.get("body", b"")

    await app_coro(receive, send)
    return result


# ===========================================================================
# 1. TenantRegistry
# ===========================================================================

class TestTenantRegistry:

    def _fake_redis(self, cached_data: dict | None = None):
        """Return a fakeredis-like mock."""
        r = MagicMock()
        if cached_data is not None:
            r.get.return_value = json.dumps(cached_data)
        else:
            r.get.return_value = None
        r.setex.return_value = True
        return r

    @pytest.mark.asyncio
    async def test_get_by_id_returns_cached_record(self):
        """Redis cache hit should return without calling control plane."""
        from server.core.tenant_registry import TenantRegistry, TenantRecord

        cached = {
            "tenant_id": "iitb",
            "subdomain": "iitb",
            "region": "in-central",
            "db_url": "postgresql://localhost/iitb",
            "db_url_sync": "postgresql://localhost/iitb",
            "plan": "enterprise",
            "feature_flags": {},
            "status": "active",
        }
        fake_r = self._fake_redis(cached)
        with patch.object(TenantRegistry, "_get_redis", return_value=fake_r):
            record = await TenantRegistry.get_by_id("iitb")

        assert isinstance(record, TenantRecord)
        assert record.tenant_id == "iitb"
        assert record.db_url == "postgresql://localhost/iitb"
        assert record.plan == "enterprise"

    @pytest.mark.asyncio
    async def test_get_by_id_fallback_when_no_control_plane(self):
        """When CONTROL_PLANE_URL is empty and Redis misses, returns settings fallback."""
        from server.core.tenant_registry import TenantRegistry

        fake_r = self._fake_redis(None)  # cache miss
        with patch.object(TenantRegistry, "_get_redis", return_value=fake_r), \
             patch("server.core.settings.settings") as mock_settings:

            mock_settings.control_plane_url = ""
            mock_settings.db_url = "postgresql://localhost/alis_db"
            mock_settings.db_url_sync = "postgresql://localhost/alis_db"
            mock_settings.tenant_db_cache_ttl_seconds = 300

            record = await TenantRegistry.get_by_id("any-tenant")

        assert record.tenant_id == "any-tenant"
        assert record.db_url == "postgresql://localhost/alis_db"
        assert record.status == "active"

    @pytest.mark.asyncio
    async def test_get_by_id_calls_control_plane_on_cache_miss(self):
        """Cache miss + control plane configured → HTTP fetch."""
        from server.core.tenant_registry import TenantRegistry, TenantRecord

        cp_response = {
            "tenant_id": "nit",
            "subdomain": "nit",
            "region": "in-south",
            "db_url": "postgresql://db.nit.example/nit",
            "db_url_sync": "postgresql://db.nit.example/nit",
            "plan": "growth",
            "feature_flags": {"ai": True},
            "status": "active",
        }
        fake_r = self._fake_redis(None)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = cp_response

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch.object(TenantRegistry, "_get_redis", return_value=fake_r), \
             patch("server.core.settings.settings") as mock_settings, \
             patch("httpx.AsyncClient", return_value=mock_client):

            mock_settings.control_plane_url = "https://control.alis.app"
            mock_settings.control_plane_token = "secret"
            mock_settings.tenant_db_cache_ttl_seconds = 300

            record = await TenantRegistry.get_by_id("nit")

        assert record.tenant_id == "nit"
        assert record.plan == "growth"
        assert record.feature_flags == {"ai": True}

    @pytest.mark.asyncio
    async def test_get_by_subdomain_cache_miss_returns_none_for_unknown(self):
        """Unknown subdomain with no control plane → None."""
        from server.core.tenant_registry import TenantRegistry

        fake_r = self._fake_redis(None)
        with patch.object(TenantRegistry, "_get_redis", return_value=fake_r), \
             patch("server.core.settings.settings") as mock_settings:
            mock_settings.control_plane_url = ""
            mock_settings.tenant_db_cache_ttl_seconds = 300

            result = await TenantRegistry.get_by_subdomain("unknown-slug")

        assert result is None

    @pytest.mark.asyncio
    async def test_invalidate_evicts_redis_keys(self):
        """invalidate() should call r.delete on both rec and sub keys."""
        from server.core.tenant_registry import TenantRegistry

        fake_r = self._fake_redis(None)
        with patch.object(TenantRegistry, "_get_redis", return_value=fake_r):
            await TenantRegistry.invalidate("iitb", subdomain="iitb")

        calls = [str(c) for c in fake_r.delete.call_args_list]
        assert any("iitb" in c for c in calls)


# ===========================================================================
# 2. DBRouter
# ===========================================================================

class TestDBRouter:

    @pytest.mark.asyncio
    async def test_get_async_pool_lazy_creation(self):
        """Pool is created on first call and reused on second call."""
        from server.db_service import DBRouter
        router = DBRouter()

        mock_pool = MagicMock()
        mock_config = MagicMock(db_url="postgresql://localhost/t1")

        with patch.object(router, "_resolve_config", return_value=mock_config), \
             patch("asyncpg.create_pool", new_callable=AsyncMock, return_value=mock_pool) as mock_create, \
             patch("server.core.settings.settings") as mock_s:

            mock_s.tenant_pool_min = 2
            mock_s.tenant_pool_max = 10

            pool1 = await router.get_async_pool("tenant-1")
            pool2 = await router.get_async_pool("tenant-1")

        # create_pool called exactly once; subsequent calls return the cached pool
        assert mock_create.call_count == 1
        assert pool1 is pool2 is mock_pool

    @pytest.mark.asyncio
    async def test_get_async_pool_separate_pools_per_tenant(self):
        """Two different tenants get two distinct pools."""
        from server.db_service import DBRouter
        router = DBRouter()

        pool_a = MagicMock(name="pool-a")
        pool_b = MagicMock(name="pool-b")
        pools_by_url = {
            "postgresql://localhost/ta": pool_a,
            "postgresql://localhost/tb": pool_b,
        }

        async def fake_resolve(tenant_id: str):
            url = f"postgresql://localhost/{tenant_id[0]}{'a' if tenant_id == 'tenant-a' else 'b'}"
            return MagicMock(db_url=url)

        call_count = [0]
        async def fake_create_pool(dsn, **_kw):
            call_count[0] += 1
            return pool_a if "ta" in dsn else pool_b

        with patch.object(router, "_resolve_config", side_effect=fake_resolve), \
             patch("asyncpg.create_pool", new_callable=AsyncMock, side_effect=fake_create_pool), \
             patch("server.core.settings.settings") as mock_s:

            mock_s.tenant_pool_min = 2
            mock_s.tenant_pool_max = 10

            pa = await router.get_async_pool("tenant-a")
            pb = await router.get_async_pool("tenant-b")

        assert pa is not pb
        assert call_count[0] == 2

    @pytest.mark.asyncio
    async def test_close_all_async_pools(self):
        """close_all_async_pools() closes every pool and clears the map."""
        from server.db_service import DBRouter
        router = DBRouter()

        p1 = AsyncMock()
        p2 = AsyncMock()
        router._async_pools = {"t1": p1, "t2": p2}

        await router.close_all_async_pools()

        p1.close.assert_awaited_once()
        p2.close.assert_awaited_once()
        assert router._async_pools == {}

    def test_get_sync_pool_lazy_creation(self):
        """psycopg2 pool is created once and reused."""
        from server.db_service import DBRouter
        router = DBRouter()

        mock_pool = MagicMock()
        mock_config = MagicMock(db_url_sync="postgresql://localhost/t1")

        with patch.object(router, "_resolve_config_sync", return_value=mock_config), \
             patch("psycopg2.pool.ThreadedConnectionPool", return_value=mock_pool) as mock_tcp, \
             patch("server.core.settings.settings") as mock_s:

            mock_s.tenant_pool_min = 2
            mock_s.tenant_pool_max = 10

            pool1 = router.get_sync_pool("tenant-1")
            pool2 = router.get_sync_pool("tenant-1")

        assert mock_tcp.call_count == 1
        assert pool1 is pool2 is mock_pool


# ===========================================================================
# 3. SubdomainTenantMiddleware
# ===========================================================================

class TestSubdomainExtraction:
    """Unit tests for the static _extract_subdomain helper."""

    def _extractor(self, host: str, suffix: str = "alis.app") -> str | None:
        from server.core.security import SubdomainTenantMiddleware
        with patch("server.core.settings.settings") as mock_s:
            mock_s.saas_domain_suffix = suffix
            return SubdomainTenantMiddleware._extract_subdomain(host)

    def test_simple_subdomain(self):
        assert self._extractor("iitb.alis.app") == "iitb"

    def test_subdomain_with_api_prefix(self):
        assert self._extractor("api.iitb.alis.app") == "iitb"

    def test_apex_domain_returns_none(self):
        assert self._extractor("alis.app") is None

    def test_localhost_returns_none(self):
        assert self._extractor("localhost") is None

    def test_ip_returns_none(self):
        assert self._extractor("192.168.1.1") is None

    def test_host_with_port_stripped(self):
        assert self._extractor("iitb.alis.app:8000") == "iitb"

    def test_unknown_domain_returns_none(self):
        assert self._extractor("iitb.example.com") is None


class TestSubdomainTenantMiddlewareASGI:
    """ASGI-level integration tests for SubdomainTenantMiddleware."""

    def _make_middleware(self, tenant_id_captured: list):
        """Build a middleware wrapping a tiny inner app that records the resolved tenant."""
        from server.core.security import SubdomainTenantMiddleware

        async def inner_app(scope, receive, send):
            tid = scope.get("state", {}).get("tenant_id")
            tenant_id_captured.append(tid)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        return SubdomainTenantMiddleware(inner_app)

    @pytest.mark.asyncio
    async def test_static_tenant_id_bypasses_all_resolution(self):
        """STATIC_TENANT_ID env var should short-circuit everything."""
        captured = []
        mw = self._make_middleware(captured)
        scope = _make_asgi_scope("/api/v1/test", host="iitb.alis.app")

        with patch("server.core.settings.settings") as mock_s:
            mock_s.static_tenant_id = "hardcoded-tenant"
            mock_s.saas_domain_suffix = "alis.app"
            await _collect_response(lambda r, s: mw(scope, r, s))

        assert captured[0] == "hardcoded-tenant"

    @pytest.mark.asyncio
    async def test_subdomain_resolves_tenant(self):
        """Valid subdomain on a known tenant resolves correctly."""
        from server.core.tenant_registry import TenantRecord

        captured = []
        mw = self._make_middleware(captured)
        scope = _make_asgi_scope("/api/v1/test", host="nit.alis.app")

        mock_record = TenantRecord(
            tenant_id="nit-uuid",
            subdomain="nit",
            status="active",
            db_url="postgresql://localhost/nit",
            db_url_sync="postgresql://localhost/nit",
        )

        with patch("server.core.settings.settings") as mock_s, \
             patch("server.core.tenant_registry.TenantRegistry.get_by_subdomain",
                   new_callable=AsyncMock, return_value=mock_record):
            mock_s.static_tenant_id = ""
            mock_s.saas_domain_suffix = "alis.app"
            await _collect_response(lambda r, s: mw(scope, r, s))

        assert captured[0] == "nit-uuid"

    @pytest.mark.asyncio
    async def test_suspended_tenant_returns_403(self):
        from server.core.tenant_registry import TenantRecord

        captured = []
        mw = self._make_middleware(captured)
        scope = _make_asgi_scope("/api/v1/test", host="suspended.alis.app")

        mock_record = TenantRecord(
            tenant_id="sus-uuid",
            subdomain="suspended",
            status="suspended",
            db_url="postgresql://localhost/sus",
            db_url_sync="postgresql://localhost/sus",
        )

        with patch("server.core.settings.settings") as mock_s, \
             patch("server.core.tenant_registry.TenantRegistry.get_by_subdomain",
                   new_callable=AsyncMock, return_value=mock_record):
            mock_s.static_tenant_id = ""
            mock_s.saas_domain_suffix = "alis.app"
            result = await _collect_response(lambda r, s: mw(scope, r, s))

        assert result["status"] == 403
        assert b"SUSPENDED" in result["body"].upper()
        assert captured == []  # inner app never called

    @pytest.mark.asyncio
    async def test_cross_tenant_mismatch_returns_403(self):
        """
        Subdomain resolves tenant A but the JWT session carries tenant B.
        Request must be rejected with 403.
        """
        from server.core.tenant_registry import TenantRecord
        from server.core.security import SessionManager

        # Create a real session with a different tenant
        session, token = SessionManager.create_session(
            user_id="user-99",
            tenant_id="tenant-B",
        )

        captured = []
        mw = self._make_middleware(captured)
        scope = _make_asgi_scope("/api/v1/test", host="tenanta.alis.app", token=token)

        mock_record = TenantRecord(
            tenant_id="tenant-A",
            subdomain="tenanta",
            status="active",
            db_url="postgresql://localhost/a",
            db_url_sync="postgresql://localhost/a",
        )

        with patch("server.core.settings.settings") as mock_s, \
             patch("server.core.tenant_registry.TenantRegistry.get_by_subdomain",
                   new_callable=AsyncMock, return_value=mock_record):
            mock_s.static_tenant_id = ""
            mock_s.saas_domain_suffix = "alis.app"
            result = await _collect_response(lambda r, s: mw(scope, r, s))

        assert result["status"] == 403
        assert b"MISMATCH" in result["body"].upper()

    @pytest.mark.asyncio
    async def test_x_tenant_id_fallback_when_no_subdomain(self):
        """Localhost + X-Tenant-ID header should resolve tenant."""
        captured = []
        mw = self._make_middleware(captured)
        scope = _make_asgi_scope(
            "/api/v1/test",
            host="localhost",
            tenant_header="local-tenant",
        )

        with patch("server.core.settings.settings") as mock_s:
            mock_s.static_tenant_id = ""
            mock_s.saas_domain_suffix = "alis.app"
            await _collect_response(lambda r, s: mw(scope, r, s))

        assert captured[0] == "local-tenant"

    @pytest.mark.asyncio
    async def test_missing_tenant_returns_403(self):
        """Request with no resolvable tenant must be rejected."""
        captured = []
        mw = self._make_middleware(captured)
        scope = _make_asgi_scope("/api/v1/test", host="localhost")

        with patch("server.core.settings.settings") as mock_s, \
             patch("server.core.audit.AuditLog.log"):
            mock_s.static_tenant_id = ""
            mock_s.saas_domain_suffix = "alis.app"
            result = await _collect_response(lambda r, s: mw(scope, r, s))

        assert result["status"] == 403

    @pytest.mark.asyncio
    async def test_exempt_paths_skip_middleware(self):
        """Health check and login paths should pass through without tenant resolution."""
        captured = []
        mw = self._make_middleware(captured)

        for path in ("/health", "/api/auth/login"):
            captured.clear()
            scope = _make_asgi_scope(path, host="localhost")
            with patch("server.core.settings.settings") as mock_s:
                mock_s.static_tenant_id = ""
                mock_s.saas_domain_suffix = "alis.app"
                result = await _collect_response(lambda r, s: mw(scope, r, s))

            # Inner app reached (200) and no tenant captured (exempt)
            assert result.get("status") == 200, f"Expected 200 for {path}"


# ===========================================================================
# 4. execute_query_async routes through DBRouter
# ===========================================================================

class TestExecuteQueryRouting:

    @pytest.mark.asyncio
    async def test_execute_query_async_uses_db_router(self):
        """execute_query_async should call _db_router.get_async_pool, not the system pool."""
        import server.db_service as db_svc
        from server.core.security import _current_tenant_id

        token = _current_tenant_id.set("tenant-xyz")
        try:
            # asyncpg pool.acquire() and conn.transaction() are both used as
            # `async with ...:` so they need proper __aenter__/__aexit__, not coroutines.
            class _FakeTxn:
                async def __aenter__(self): return self
                async def __aexit__(self, *_): return False

            mock_conn = MagicMock()
            mock_conn.fetch = AsyncMock(return_value=[])
            mock_conn.execute = AsyncMock()
            mock_conn.transaction.return_value = _FakeTxn()

            class _FakeAcquire:
                async def __aenter__(self): return mock_conn
                async def __aexit__(self, *_): return False

            mock_pool = MagicMock()
            mock_pool.acquire.return_value = _FakeAcquire()

            with patch.object(db_svc._db_router, "get_async_pool", new_callable=AsyncMock,
                              return_value=mock_pool) as mock_get_pool:
                await db_svc.execute_query_async("SELECT 1")
                mock_get_pool.assert_awaited_once_with("tenant-xyz")
        finally:
            _current_tenant_id.reset(token)
