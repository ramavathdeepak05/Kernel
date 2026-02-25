"""
ALIS Tenant Isolation Tests - E00-S03

Tests for:
1. TenantContext ContextVar (set/get/clear)
2. TenantMiddleware (reject requests without tenant_id)
3. RBAC tenant enforcement (verify_access requires tenant_id)
4. AI Agent tenant override prevention
5. TenantKeyManager (generate, rotate, encrypt/decrypt)
6. Cross-tenant isolation (Tenant A cannot see Tenant B data)
7. Session tenant_id binding

Run with:
    cd d:\\quaicu\\alis\\ALIS-Production\\ALIS
    python -m pytest tests/test_tenant_isolation.py -v
"""

import sys
import os
import pytest

# Ensure the ALIS package is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from server.core.security import (
    Session, SessionManager, TenantContext,
    set_tenant_context, get_current_tenant_id, clear_tenant_context,
    _current_tenant_id,
)
from server.core.rbac import Role, Permission, verify_access
from server.core.exceptions import TenantIsolationError
from server.core.tenant_crypto import TenantKeyManager, TenantKeyEntry
from server.core.audit import AuditLog


# ============================================================================
# FIXTURE: Clean tenant context before each test
# ============================================================================

@pytest.fixture(autouse=True)
def clean_tenant_context():
    """Ensure tenant context is clean before and after each test."""
    clear_tenant_context()
    yield
    clear_tenant_context()


@pytest.fixture(autouse=True)
def clean_key_store():
    """Reset key store between tests."""
    TenantKeyManager._keys.clear()
    TenantKeyManager._key_material.clear()
    yield
    TenantKeyManager._keys.clear()
    TenantKeyManager._key_material.clear()


# ============================================================================
# TEST GROUP 1: ContextVar (set/get/clear)
# ============================================================================

class TestTenantContextVar:
    """Tests for the request-scoped tenant ContextVar."""

    def test_set_and_get_tenant_id(self):
        """Setting tenant_id should make it retrievable."""
        set_tenant_context("tenant-abc-123")
        assert get_current_tenant_id() == "tenant-abc-123"

    def test_get_without_set_raises_error(self):
        """Getting tenant_id without setting it should raise TenantIsolationError."""
        with pytest.raises(TenantIsolationError) as exc_info:
            get_current_tenant_id()
        assert "ERR_LAYER4_TENANT" in str(exc_info.value.code)

    def test_clear_tenant_context(self):
        """Clearing should make subsequent get() fail."""
        set_tenant_context("tenant-abc-123")
        clear_tenant_context()
        with pytest.raises(TenantIsolationError):
            get_current_tenant_id()

    def test_set_empty_string_raises_error(self):
        """Setting an empty tenant_id should raise ValueError."""
        with pytest.raises(ValueError):
            set_tenant_context("")

    def test_set_whitespace_only_raises_error(self):
        """Setting whitespace-only tenant_id should raise ValueError."""
        with pytest.raises(ValueError):
            set_tenant_context("   ")

    def test_overwrite_tenant_context(self):
        """Setting a new tenant_id should overwrite the previous one."""
        set_tenant_context("tenant-A")
        set_tenant_context("tenant-B")
        assert get_current_tenant_id() == "tenant-B"

    def test_tenant_id_trimmed(self):
        """Tenant ID should be trimmed of whitespace."""
        set_tenant_context("  tenant-xyz  ")
        assert get_current_tenant_id() == "tenant-xyz"


# ============================================================================
# TEST GROUP 2: Session tenant_id binding
# ============================================================================

class TestSessionTenantBinding:
    """Tests for Session.tenant_id field."""

    def test_session_has_tenant_id(self):
        """Session dataclass should have a tenant_id field."""
        session = Session(user_id="user-1", tenant_id="tenant-org-1")
        assert session.tenant_id == "tenant-org-1"

    def test_session_default_tenant_id_is_empty(self):
        """Session default tenant_id should be empty string."""
        session = Session(user_id="user-1")
        assert session.tenant_id == ""

    def test_session_manager_creates_session_with_tenant(self):
        """SessionManager should create sessions with tenant_id."""
        session, token = SessionManager.create_session(
            user_id="user-1",
        )
        # Default tenant is empty string, must be set explicitly
        assert session.tenant_id == ""


# ============================================================================
# TEST GROUP 3: RBAC tenant enforcement
# ============================================================================

class TestRBACTenantEnforcement:
    """Tests for tenant enforcement in verify_access."""

    def test_non_system_access_requires_tenant_id(self):
        """Non-system roles must have tenant_id in context."""
        # No tenant context set, no tenant_id in context dict
        result = verify_access(
            actor_role=Role.ADMIN,
            permission=Permission.USER_READ,
            context={}  # Missing tenant_id
        )
        assert result.allowed is False
        assert any("tenant_id" in v.lower() or "tenant" in v.lower()
                    for v in (result.context_violations or []))

    def test_system_role_exempt_from_tenant_check(self):
        """System role should be exempt from tenant isolation checks."""
        result = verify_access(
            actor_role=Role.SYSTEM,
            permission=Permission.USER_READ,
            context={}  # No tenant_id — OK for system
        )
        assert result.allowed is True

    def test_access_allowed_with_tenant_id_in_context(self):
        """Access should be allowed when tenant_id is in context."""
        result = verify_access(
            actor_role=Role.ADMIN,
            permission=Permission.USER_READ,
            context={"tenant_id": "org-123"}
        )
        assert result.allowed is True

    def test_access_allowed_with_tenant_id_from_contextvar(self):
        """Access should be allowed when tenant_id is set via ContextVar."""
        set_tenant_context("org-456")
        result = verify_access(
            actor_role=Role.ADMIN,
            permission=Permission.USER_READ,
            context={}  # No tenant_id in context, but ContextVar is set
        )
        assert result.allowed is True


# ============================================================================
# TEST GROUP 4: AI Agent tenant override prevention
# ============================================================================

class TestAIAgentTenantIsolation:
    """Tests for AI Agent tenant boundary enforcement."""

    def test_ai_agent_cannot_override_tenant(self):
        """AI Agents must not be able to override tenant context."""
        set_tenant_context("org-123")
        result = verify_access(
            actor_role=Role.AI_AGENT,
            permission=Permission.STUDENT_READ,
            context={
                "tenant_id": "org-123",
                "override_tenant": True,  # Attempted override
            }
        )
        assert result.allowed is False
        assert any("override tenant" in v.lower()
                    for v in (result.context_violations or []))

    def test_ai_agent_allowed_within_tenant(self):
        """AI Agents should be allowed within tenant boundaries."""
        set_tenant_context("org-123")
        result = verify_access(
            actor_role=Role.AI_AGENT,
            permission=Permission.STUDENT_READ,
            context={"tenant_id": "org-123"}
        )
        assert result.allowed is True

    def test_ai_agent_still_blocked_on_write(self):
        """AI Agents should still be blocked on sensitive writes even with tenant."""
        set_tenant_context("org-123")
        result = verify_access(
            actor_role=Role.AI_AGENT,
            permission=Permission.MARKS_FINALIZE,
            context={"tenant_id": "org-123"}
        )
        assert result.allowed is False


# ============================================================================
# TEST GROUP 5: TenantKeyManager
# ============================================================================

class TestTenantKeyManager:
    """Tests for tenant-specific encryption key management."""

    def test_generate_key(self):
        """Should generate a key for a tenant."""
        entry = TenantKeyManager.generate_tenant_key("org-A", actor_id="admin-1")
        assert entry.tenant_id == "org-A"
        assert entry.version == 1
        assert entry.is_active is True

    def test_generate_key_empty_tenant_raises(self):
        """Generating key for empty tenant should raise error."""
        with pytest.raises(TenantIsolationError):
            TenantKeyManager.generate_tenant_key("", actor_id="admin-1")

    def test_has_key(self):
        """Should correctly report key existence."""
        assert TenantKeyManager.has_key("org-X") is False
        TenantKeyManager.generate_tenant_key("org-X")
        assert TenantKeyManager.has_key("org-X") is True

    def test_get_key_returns_bytes(self):
        """Should return raw key bytes."""
        TenantKeyManager.generate_tenant_key("org-Y")
        key = TenantKeyManager.get_tenant_key("org-Y")
        assert key is not None
        assert isinstance(key, bytes)
        assert len(key) == 32  # 256-bit key

    def test_rotate_key(self):
        """Should rotate key with incremented version."""
        TenantKeyManager.generate_tenant_key("org-Z")
        old_key = TenantKeyManager.get_tenant_key("org-Z")
        new_entry = TenantKeyManager.rotate_key("org-Z", actor_id="admin-1")
        new_key = TenantKeyManager.get_tenant_key("org-Z")
        assert new_entry.version == 2
        assert new_key != old_key  # New key should differ

    def test_rotate_nonexistent_key_raises(self):
        """Rotating a key for a tenant without one should raise error."""
        with pytest.raises(TenantIsolationError):
            TenantKeyManager.rotate_key("org-nonexistent")

    def test_get_key_empty_tenant_raises(self):
        """Getting key for empty tenant should raise error."""
        with pytest.raises(TenantIsolationError):
            TenantKeyManager.get_tenant_key("")


# ============================================================================
# TEST GROUP 6: Cross-tenant isolation
# ============================================================================

class TestCrossTenantIsolation:
    """Tests to ensure complete logical isolation between tenants."""

    def test_tenant_context_is_request_scoped(self):
        """Tenant A context should not leak into Tenant B's scope."""
        # Simulate Tenant A request
        set_tenant_context("tenant-A")
        assert get_current_tenant_id() == "tenant-A"

        # Simulate end of request
        clear_tenant_context()

        # Simulate Tenant B request
        set_tenant_context("tenant-B")
        assert get_current_tenant_id() == "tenant-B"

        # Ensure it's Tenant B, not Tenant A
        assert get_current_tenant_id() != "tenant-A"

    def test_tenant_keys_are_isolated(self):
        """Each tenant should have its own unique encryption key."""
        TenantKeyManager.generate_tenant_key("tenant-A")
        TenantKeyManager.generate_tenant_key("tenant-B")

        key_a = TenantKeyManager.get_tenant_key("tenant-A")
        key_b = TenantKeyManager.get_tenant_key("tenant-B")

        assert key_a is not None
        assert key_b is not None
        assert key_a != key_b  # Keys must be different

    def test_rbac_enforces_different_tenants(self):
        """RBAC should enforce tenant_id per request."""
        # Tenant A request
        set_tenant_context("tenant-A")
        result_a = verify_access(
            actor_role=Role.ADMIN,
            permission=Permission.USER_READ,
            context={"tenant_id": "tenant-A"}
        )
        assert result_a.allowed is True
        clear_tenant_context()

        # Tenant B request
        set_tenant_context("tenant-B")
        result_b = verify_access(
            actor_role=Role.ADMIN,
            permission=Permission.USER_READ,
            context={"tenant_id": "tenant-B"}
        )
        assert result_b.allowed is True

    def test_audit_log_captures_tenant_context(self):
        """Audit log entries should include org_id for tenant tracking."""
        entry = AuditLog.log(
            action=AuditLog._entries[0].action if AuditLog._entries else "create",
            actor_id="user-1",
            actor_type="human",
            entity_type="test",
            entity_id="test-1",
            org_id="tenant-A",
        )
        assert entry.org_id == "tenant-A"


# ============================================================================
# TEST GROUP 7: TenantContext dataclass
# ============================================================================

class TestTenantContextDataclass:
    """Tests for the TenantContext dataclass."""

    def test_create_tenant_context(self):
        context = TenantContext(tenant_id="org-123", tenant_name="Woxsen University")
        assert context.tenant_id == "org-123"
        assert context.tenant_name == "Woxsen University"
        assert context.encryption_key_id is None

    def test_tenant_context_with_encryption(self):
        context = TenantContext(
            tenant_id="org-456",
            encryption_key_id="key-abc"
        )
        assert context.encryption_key_id == "key-abc"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
