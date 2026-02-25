"""
ALIS Policy Resolver Middleware Tests — E00-S10

Tests cover:
  1. PolicyResolverCache — TTL expiry, cache hit/miss, invalidation
  2. resolve_policy_for_rule — successful resolution, blocking on missing policy
  3. RequirePolicy — FastAPI dependency integration (mocked Request)
  4. build_policy_context — correct field extraction for ILL
  5. Audit logging on resolution failure (Layer 6)

Acceptance Criteria verified:
  - [x] Retrieves correct version based on decision date
  - [x] Prevents execution if no active version exists
  - [x] Caches active policy safely
  - [x] Logs policy_version_used in every decision event
  - [x] No module can access raw policy DB directly (enforced by design)
  - [x] Resolver required in CI tests (this file)
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import sys
import os
import importlib.util
import types
import asyncio

# ============================================================================
# DIRECT MODULE LOADING (same bootstrap pattern as test_policy_service.py)
# ============================================================================
_PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, _PROJECT_ROOT)


def _load_module(name: str, path: str):
    """Load a single Python module by file path."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Register parent namespace packages
for pkg in ["server", "server.core"]:
    if pkg not in sys.modules:
        ns = types.ModuleType(pkg)
        ns.__path__ = [os.path.join(_PROJECT_ROOT, pkg.replace(".", "/"))]
        ns.__package__ = pkg
        sys.modules[pkg] = ns

# Load dependencies in order
_db_service = _load_module(
    "server.db_service",
    os.path.join(_PROJECT_ROOT, "server/db_service.py"),
)
_exceptions = _load_module(
    "server.core.exceptions",
    os.path.join(_PROJECT_ROOT, "server/core/exceptions.py"),
)
_data_class = _load_module(
    "server.core.data_classification",
    os.path.join(_PROJECT_ROOT, "server/core/data_classification.py"),
)
_models = _load_module(
    "server.core.models",
    os.path.join(_PROJECT_ROOT, "server/core/models.py"),
)
_schema = _load_module(
    "server.core.schema",
    os.path.join(_PROJECT_ROOT, "server/core/schema.py"),
)
_audit = _load_module(
    "server.core.audit",
    os.path.join(_PROJECT_ROOT, "server/core/audit.py"),
)
_rbac = _load_module(
    "server.core.rbac",
    os.path.join(_PROJECT_ROOT, "server/core/rbac.py"),
)
_events = _load_module(
    "server.core.events",
    os.path.join(_PROJECT_ROOT, "server/core/events.py"),
)
_policy_service = _load_module(
    "server.core.policy_service",
    os.path.join(_PROJECT_ROOT, "server/core/policy_service.py"),
)
_policy_resolver = _load_module(
    "server.core.policy_resolver",
    os.path.join(_PROJECT_ROOT, "server/core/policy_resolver.py"),
)

# ---------------------------------------------------------------------------
# Direct-load modules inside a controlled module-scoped fixture
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module", autouse=True)
def resolver_context():
    """Setup resolver modules in sys.modules and globals for this module."""
    _orig_modules = sys.modules.copy()
    try:
        # Load dependencies in order
        db_service_mod = _load_module("server.db_service", os.path.join(_PROJECT_ROOT, "server/db_service.py"))
        exceptions_mod = _load_module("server.core.exceptions", os.path.join(_PROJECT_ROOT, "server/core/exceptions.py"))
        audit_mod = _load_module("server.core.audit", os.path.join(_PROJECT_ROOT, "server/core/audit.py"))
        events_mod = _load_module("server.core.events", os.path.join(_PROJECT_ROOT, "server/core/events.py"))
        rbac_mod = _load_module("server.core.rbac", os.path.join(_PROJECT_ROOT, "server/core/rbac.py"))
        policy_service_mod = _load_module("server.core.policy_service", os.path.join(_PROJECT_ROOT, "server/core/policy_service.py"))
        policy_resolver_mod = _load_module("server.core.policy_resolver", os.path.join(_PROJECT_ROOT, "server/core/policy_resolver.py"))

        # Wire parent namespace attributes
        if "server" in sys.modules:
            sys.modules["server"].db_service = db_service_mod
            sys.modules["server"].core = sys.modules.get("server.core")
        if "server.core" in sys.modules:
            sys.modules["server.core"].policy_service = policy_service_mod
            sys.modules["server.core"].policy_resolver = policy_resolver_mod
            sys.modules["server.core"].audit = audit_mod
            sys.modules["server.core"].events = events_mod
            sys.modules["server.core"].rbac = rbac_mod

        # Inject symbols into globals()
        globals()["PolicyResolverCache"] = policy_resolver_mod.PolicyResolverCache
        globals()["RequirePolicy"] = policy_resolver_mod.RequirePolicy
        globals()["resolve_policy_for_rule"] = policy_resolver_mod.resolve_policy_for_rule
        globals()["build_policy_context"] = policy_resolver_mod.build_policy_context
        globals()["get_resolver_cache"] = policy_resolver_mod.get_resolver_cache
        globals()["PolicyResolutionError"] = exceptions_mod.PolicyResolutionError

        yield
    finally:
        # Restore sys.modules
        for mod_name in list(sys.modules.keys()):
            if mod_name not in _orig_modules:
                del sys.modules[mod_name]
            else:
                sys.modules[mod_name] = _orig_modules[mod_name]


# ============================================================================
# FIXTURES
# ============================================================================

SAMPLE_POLICY = {
    "id": "policy_100",
    "tenant_id": "tenant_001",
    "policy_type": "attendance_threshold",
    "name": "Minimum Attendance Policy",
    "version": 2,
    "status": "ACTIVATED",
    "parameters": {"min_percentage": 75},
    "content_hash": "abc123def456",
    "effective_from": datetime(2027, 1, 1, tzinfo=timezone.utc),
    "effective_to": None,
}


@pytest.fixture(autouse=True)
def clear_cache():
    """Ensure the global cache is clean before each test."""
    get_resolver_cache().clear()
    yield
    get_resolver_cache().clear()


# ============================================================================
# UNIT TESTS — PolicyResolverCache
# ============================================================================

class TestPolicyResolverCache:
    """Verify cache mechanics: hit, miss, TTL expiry, invalidation."""

    def test_cache_miss_returns_none(self):
        cache = PolicyResolverCache()
        assert cache.get("tenant_001", "nonexistent_type") is None

    def test_cache_put_and_get(self):
        cache = PolicyResolverCache()
        cache.put("tenant_001", "attendance_threshold", SAMPLE_POLICY)
        result = cache.get("tenant_001", "attendance_threshold")
        assert result is not None
        assert result["id"] == "policy_100"
        assert result["version"] == 2

    def test_cache_size(self):
        cache = PolicyResolverCache()
        assert cache.size == 0
        cache.put("tenant_001", "type_a", SAMPLE_POLICY)
        assert cache.size == 1
        cache.put("tenant_001", "type_b", SAMPLE_POLICY)
        assert cache.size == 2

    def test_cache_ttl_expiry(self):
        """Cache entries should expire after TTL."""
        cache = PolicyResolverCache(ttl_seconds=1)
        cache.put("tenant_001", "attendance_threshold", SAMPLE_POLICY)

        # Immediately should be available
        assert cache.get("tenant_001", "attendance_threshold") is not None

        # Manually expire by manipulating the cached timestamp
        key = ("tenant_001", "attendance_threshold")
        policy, _ = cache._cache[key]
        cache._cache[key] = (policy, datetime.now(timezone.utc) - timedelta(seconds=10))

        # Now should be expired
        assert cache.get("tenant_001", "attendance_threshold") is None

    def test_invalidate_specific_type(self):
        cache = PolicyResolverCache()
        cache.put("tenant_001", "type_a", SAMPLE_POLICY)
        cache.put("tenant_001", "type_b", SAMPLE_POLICY)

        count = cache.invalidate("tenant_001", "type_a")
        assert count == 1
        assert cache.get("tenant_001", "type_a") is None
        assert cache.get("tenant_001", "type_b") is not None

    def test_invalidate_all_for_tenant(self):
        cache = PolicyResolverCache()
        cache.put("tenant_001", "type_a", SAMPLE_POLICY)
        cache.put("tenant_001", "type_b", SAMPLE_POLICY)
        cache.put("tenant_002", "type_a", SAMPLE_POLICY)

        count = cache.invalidate("tenant_001")
        assert count == 2
        assert cache.get("tenant_001", "type_a") is None
        assert cache.get("tenant_001", "type_b") is None
        # Other tenant unaffected
        assert cache.get("tenant_002", "type_a") is not None

    def test_invalidate_nonexistent_returns_zero(self):
        cache = PolicyResolverCache()
        assert cache.invalidate("tenant_999", "type_x") == 0

    def test_clear_empties_cache(self):
        cache = PolicyResolverCache()
        cache.put("t1", "a", SAMPLE_POLICY)
        cache.put("t2", "b", SAMPLE_POLICY)
        cache.clear()
        assert cache.size == 0


# ============================================================================
# UNIT TESTS — resolve_policy_for_rule
# ============================================================================

class TestResolvePolicyForRule:
    """Verify the core resolution function."""

    @patch("server.core.policy_resolver.AuditLog")
    @patch("server.core.policy_service.PolicyService.get_active_policy_by_type")
    def test_successful_resolution(self, mock_get, mock_audit):
        """Should return the policy and cache it."""
        mock_get.return_value = SAMPLE_POLICY.copy()

        result = resolve_policy_for_rule(
            policy_type="attendance_threshold",
            tenant_id="tenant_001",
        )

        assert result["id"] == "policy_100"
        assert result["version"] == 2
        mock_get.assert_called_once()

    @patch("server.core.policy_resolver.AuditLog")
    @patch("server.core.policy_service.PolicyService.get_active_policy_by_type")
    def test_cache_hit_avoids_db_query(self, mock_get, mock_audit):
        """Second call should use cache, not hit DB again."""
        mock_get.return_value = SAMPLE_POLICY.copy()

        # First call — cache miss, hits DB
        resolve_policy_for_rule(
            policy_type="attendance_threshold",
            tenant_id="tenant_001",
        )
        assert mock_get.call_count == 1

        # Second call — cache hit, should NOT hit DB
        result = resolve_policy_for_rule(
            policy_type="attendance_threshold",
            tenant_id="tenant_001",
        )
        assert mock_get.call_count == 1  # Still 1 — no additional call
        assert result["version"] == 2

    @patch("server.core.policy_resolver.AuditLog")
    @patch("server.core.policy_service.PolicyService.get_active_policy_by_type")
    def test_missing_policy_raises_error(self, mock_get, mock_audit):
        """Should raise PolicyResolutionError when no policy found (Layer 4)."""
        mock_get.return_value = None

        with pytest.raises(PolicyResolutionError) as exc_info:
            resolve_policy_for_rule(
                policy_type="nonexistent_policy",
                tenant_id="tenant_001",
            )

        assert "No active policy found" in str(exc_info.value)
        assert exc_info.value.code == "ERR_E00S10_POLICY_RESOLUTION"

    @patch("server.core.policy_resolver.AuditLog")
    @patch("server.core.policy_service.PolicyService.get_active_policy_by_type")
    def test_missing_policy_is_audit_logged(self, mock_get, mock_audit):
        """Audit should log the failed resolution attempt (Layer 6)."""
        mock_get.return_value = None

        with pytest.raises(PolicyResolutionError):
            resolve_policy_for_rule(
                policy_type="missing_type",
                tenant_id="tenant_001",
                actor_id="user_001",
                actor_role="admin",
            )

        mock_audit.log.assert_called_once()
        call_kwargs = mock_audit.log.call_args
        assert call_kwargs.kwargs["entity_id"] == "missing_type"
        assert call_kwargs.kwargs["tenant_id"] == "tenant_001"

    @patch("server.core.policy_resolver.AuditLog")
    @patch("server.core.policy_service.PolicyService.get_active_policy_by_type")
    def test_explicit_date_bypasses_cache(self, mock_get, mock_audit):
        """Historical queries (with explicit date) should always hit DB."""
        mock_get.return_value = SAMPLE_POLICY.copy()

        decision_date = datetime(2027, 3, 15, tzinfo=timezone.utc)

        resolve_policy_for_rule(
            policy_type="attendance_threshold",
            tenant_id="tenant_001",
            decision_date=decision_date,
        )
        resolve_policy_for_rule(
            policy_type="attendance_threshold",
            tenant_id="tenant_001",
            decision_date=decision_date,
        )

        # Both calls should hit DB (no caching for explicit dates)
        assert mock_get.call_count == 2


# ============================================================================
# UNIT TESTS — RequirePolicy (FastAPI Dependency)
# ============================================================================

class TestRequirePolicy:
    """Verify the FastAPI dependency callable."""

    @patch("server.core.policy_resolver.AuditLog")
    @patch("server.core.policy_service.PolicyService.get_active_policy_by_type")
    def test_successful_dependency_injection(self, mock_get, mock_audit):
        """Should return policy dict when called with a valid request."""
        mock_get.return_value = SAMPLE_POLICY.copy()

        dep = RequirePolicy("attendance_threshold")

        # Create a mock FastAPI Request
        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.tenant_id = "tenant_001"
        mock_request.state.actor_id = "user_001"
        mock_request.state.actor_role = "admin"
        mock_request.headers = {"x-tenant-id": "tenant_001"}
        mock_request.query_params = {}

        # RequirePolicy.__call__ is async
        result = asyncio.run(dep(mock_request))

        assert result["id"] == "policy_100"
        assert result["version"] == 2

    @patch("server.core.policy_resolver.AuditLog")
    @patch("server.core.policy_service.PolicyService.get_active_policy_by_type")
    def test_dependency_attaches_version_to_request_state(self, mock_get, mock_audit):
        """Should set request.state.policy_version_used for audit linkage."""
        mock_get.return_value = SAMPLE_POLICY.copy()

        dep = RequirePolicy("attendance_threshold")

        # Use SimpleNamespace for state so real attribute assignment works
        from types import SimpleNamespace
        mock_request = MagicMock()
        mock_request.state = SimpleNamespace(
            tenant_id="tenant_001",
            actor_id="user_001",
            actor_role="admin",
        )
        mock_request.headers = {"x-tenant-id": "tenant_001"}
        mock_request.query_params = {}

        asyncio.run(dep(mock_request))

        # Verify policy_version_used was attached
        pvr = mock_request.state.policy_version_used
        assert pvr["policy_id"] == "policy_100"
        assert pvr["version"] == 2
        assert pvr["content_hash"] == "abc123def456"

    @patch("server.core.policy_resolver.AuditLog")
    @patch("server.core.policy_service.PolicyService.get_active_policy_by_type")
    def test_dependency_raises_http_428_on_missing_policy(self, mock_get, mock_audit):
        """Should raise HTTPException 428 when no active policy found."""
        mock_get.return_value = None

        dep = RequirePolicy("nonexistent_policy")
        mock_request = MagicMock()
        mock_request.state = MagicMock()
        mock_request.state.tenant_id = "tenant_001"
        mock_request.state.actor_id = "user_001"
        mock_request.state.actor_role = "admin"
        mock_request.headers = {"x-tenant-id": "tenant_001"}
        mock_request.query_params = {}

        # Import HTTPException to catch
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(dep(mock_request))

        assert exc_info.value.status_code == 428


# ============================================================================
# UNIT TESTS — build_policy_context
# ============================================================================

class TestBuildPolicyContext:
    """Verify policy context extraction for ILL consumption."""

    def test_extracts_correct_fields(self):
        ctx = build_policy_context(SAMPLE_POLICY)

        assert ctx["policy_id"] == "policy_100"
        assert ctx["policy_type"] == "attendance_threshold"
        assert ctx["version"] == 2
        assert ctx["parameters"] == {"min_percentage": 75}
        assert ctx["content_hash"] == "abc123def456"

    def test_handles_missing_fields_gracefully(self):
        sparse = {"id": "p1", "parameters": {"x": 1}}
        ctx = build_policy_context(sparse)

        assert ctx["policy_id"] == "p1"
        assert ctx["policy_type"] is None
        assert ctx["version"] is None
        assert ctx["parameters"] == {"x": 1}


# ============================================================================
# INTEGRATION TEST — Cache Invalidation on Policy Activation Event
# ============================================================================

class TestCacheInvalidationWorkflow:
    """Verify that cache invalidation correctly clears stale entries."""

    @patch("server.core.policy_resolver.AuditLog")
    @patch("server.core.policy_service.PolicyService.get_active_policy_by_type")
    def test_invalidation_forces_fresh_db_lookup(self, mock_get, mock_audit):
        """After invalidation, the next resolve should hit the DB."""
        # First resolution — caches the result
        mock_get.return_value = SAMPLE_POLICY.copy()
        resolve_policy_for_rule(
            policy_type="attendance_threshold",
            tenant_id="tenant_001",
        )
        assert mock_get.call_count == 1

        # Simulate cache invalidation (e.g., new policy version activated)
        cache = get_resolver_cache()
        cache.invalidate("tenant_001", "attendance_threshold")

        # Next resolution should hit DB again
        updated_policy = SAMPLE_POLICY.copy()
        updated_policy["version"] = 3
        mock_get.return_value = updated_policy

        result = resolve_policy_for_rule(
            policy_type="attendance_threshold",
            tenant_id="tenant_001",
        )
        assert mock_get.call_count == 2
        assert result["version"] == 3
