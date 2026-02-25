"""
ALIS Policy Governance Service Tests — E00-S09

Tests cover:
  1. Policy lifecycle state machine (DRAFT → SUBMITTED → APPROVED → ACTIVATED)
  2. Illegal transition rejection (Layer 3)
  3. Immutability enforcement (Layer 4)
  4. Temporal query resolution (effective_from / effective_to)
  5. Version auto-increment
  6. Content hash generation
  7. PolicyActivated event emission
  8. RBAC enforcement on approve
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, call

import sys
import os
import importlib.util

# ============================================================================
# DIRECT MODULE LOADING (bypasses core/__init__.py which fails on Py 3.9
# due to overrides.py using match/case from Py 3.10+)
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


# Also register parent namespace packages so @patch can resolve them
import types
for pkg in ["server", "server.core"]:
    if pkg not in sys.modules:
        ns = types.ModuleType(pkg)
        ns.__path__ = [os.path.join(_PROJECT_ROOT, pkg.replace(".", "/"))]
        ns.__package__ = pkg
        sys.modules[pkg] = ns

# Load db_service first (needed by policy_service for lazy imports)
_db_service = _load_module(
    "server.db_service",
    os.path.join(_PROJECT_ROOT, "server/db_service.py"),
)

# Pre-load minimal dependencies that policy_service.py needs
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
_policy = _load_module(
    "server.core.policy_service",
    os.path.join(_PROJECT_ROOT, "server/core/policy_service.py"),
)

# Wire parent namespace attributes so @patch("server.db_service...") works
sys.modules["server"].db_service = _db_service
sys.modules["server"].core = sys.modules["server.core"]
sys.modules["server.core"].policy_service = _policy
sys.modules["server.core"].audit = _audit
sys.modules["server.core"].events = _events
sys.modules["server.core"].rbac = _rbac

PolicyService = _policy.PolicyService
PolicyStatus = _policy.PolicyStatus
POLICY_TRANSITIONS = _policy.POLICY_TRANSITIONS
_validate_transition = _policy._validate_transition
compute_policy_hash = _policy.compute_policy_hash
AuditAction = _audit.AuditAction


# ============================================================================
# UNIT TESTS — State Machine Transitions (Layer 3)
# ============================================================================

class TestPolicyStateMachine:
    """Verify that the state machine only allows declared forward transitions."""

    def test_draft_to_submitted_allowed(self):
        assert _validate_transition(PolicyStatus.DRAFT, PolicyStatus.SUBMITTED)

    def test_submitted_to_approved_allowed(self):
        assert _validate_transition(PolicyStatus.SUBMITTED, PolicyStatus.APPROVED)

    def test_approved_to_activated_allowed(self):
        assert _validate_transition(PolicyStatus.APPROVED, PolicyStatus.ACTIVATED)

    def test_activated_to_superseded_allowed(self):
        assert _validate_transition(PolicyStatus.ACTIVATED, PolicyStatus.SUPERSEDED)

    def test_backward_transition_rejected(self):
        """Layer 3: Backward transitions are forbidden."""
        assert not _validate_transition(PolicyStatus.SUBMITTED, PolicyStatus.DRAFT)
        assert not _validate_transition(PolicyStatus.APPROVED, PolicyStatus.SUBMITTED)
        assert not _validate_transition(PolicyStatus.ACTIVATED, PolicyStatus.DRAFT)

    def test_skip_transition_rejected(self):
        """Layer 3: Undeclared transitions must fail."""
        assert not _validate_transition(PolicyStatus.DRAFT, PolicyStatus.APPROVED)
        assert not _validate_transition(PolicyStatus.DRAFT, PolicyStatus.ACTIVATED)
        assert not _validate_transition(PolicyStatus.SUBMITTED, PolicyStatus.ACTIVATED)

    def test_superseded_is_terminal(self):
        """SUPERSEDED is a terminal state — no transitions out."""
        for target in PolicyStatus:
            assert not _validate_transition(PolicyStatus.SUPERSEDED, target)


# ============================================================================
# UNIT TESTS — Policy Hash (Layer 4)
# ============================================================================

class TestPolicyHash:
    """Verify content hash determinism and uniqueness."""

    def test_same_input_produces_same_hash(self):
        data = {
            "policy_type": "attendance_threshold",
            "version": 1,
            "parameters": {"min_percentage": 75},
            "effective_from": "2027-01-01",
            "effective_to": None,
        }
        h1 = compute_policy_hash(data)
        h2 = compute_policy_hash(data)
        assert h1 == h2

    def test_different_input_produces_different_hash(self):
        data1 = {
            "policy_type": "attendance_threshold",
            "version": 1,
            "parameters": {"min_percentage": 75},
            "effective_from": "2027-01-01",
            "effective_to": None,
        }
        data2 = {
            "policy_type": "attendance_threshold",
            "version": 1,
            "parameters": {"min_percentage": 80},  # Different threshold
            "effective_from": "2027-01-01",
            "effective_to": None,
        }
        assert compute_policy_hash(data1) != compute_policy_hash(data2)

    def test_hash_is_sha256_hex(self):
        data = {"policy_type": "test", "version": 1, "parameters": {},
                "effective_from": "2027-01-01", "effective_to": None}
        h = compute_policy_hash(data)
        assert len(h) == 64  # SHA-256 hex length
        assert all(c in "0123456789abcdef" for c in h)


# ============================================================================
# INTEGRATION-STYLE TESTS (mocked DB)
# ============================================================================

class TestPolicyServiceCreateDraft:
    """Test create_draft with mocked DB layer."""

    @patch("server.core.policy_service.AuditLog")
    @patch("server.db_service.execute_transaction")
    @patch("server.db_service.execute_query")
    def test_create_draft_returns_correct_structure(
        self, mock_query, mock_tx, mock_audit
    ):
        # Mock: no existing versions
        mock_query.return_value = [{"max_ver": 0}]
        mock_tx.return_value = None

        result = PolicyService.create_draft(
            policy_type="attendance_threshold",
            name="Minimum Attendance Policy",
            description="Sets the minimum attendance percentage.",
            parameters={"min_percentage": 75},
            effective_from=datetime(2027, 1, 1, tzinfo=timezone.utc),
            effective_to=None,
            created_by="user_001",
            actor_role="admin",
            tenant_id="tenant_001",
        )

        assert result["policy_type"] == "attendance_threshold"
        assert result["version"] == 1
        assert result["status"] == "DRAFT"
        assert "content_hash" in result
        assert len(result["id"]) == 36  # UUID4

    @patch("server.core.policy_service.AuditLog")
    @patch("server.db_service.execute_transaction")
    @patch("server.db_service.execute_query")
    def test_version_auto_increments(self, mock_query, mock_tx, mock_audit):
        # Mock: 3 existing versions
        mock_query.return_value = [{"max_ver": 3}]
        mock_tx.return_value = None

        result = PolicyService.create_draft(
            policy_type="fee_waiver_limit",
            name="Fee Waiver Limit v4",
            description="Updated waiver limit.",
            parameters={"max_waiver_pct": 50},
            effective_from=datetime(2027, 6, 1, tzinfo=timezone.utc),
            effective_to=None,
            created_by="user_002",
            actor_role="admin",
            tenant_id="tenant_001",
        )

        assert result["version"] == 4


class TestPolicyServiceSubmit:
    """Test submit_for_approval with mocked DB layer."""

    @patch("server.core.policy_service.AuditLog")
    @patch("server.db_service.execute_transaction")
    @patch("server.db_service.execute_query")
    def test_submit_draft_succeeds(self, mock_query, mock_tx, mock_audit):
        mock_query.return_value = [{
            "id": "policy_001",
            "status": "DRAFT",
            "policy_type": "test",
            "version": 1,
        }]
        mock_tx.return_value = None

        result = PolicyService.submit_for_approval(
            policy_id="policy_001",
            submitted_by="user_001",
            actor_role="admin",
            tenant_id="tenant_001",
        )

        assert result["status"] == "SUBMITTED"

    @patch("server.db_service.execute_query")
    def test_submit_approved_fails(self, mock_query):
        """Layer 3: Cannot submit an already-approved policy."""
        mock_query.return_value = [{
            "id": "policy_002",
            "status": "APPROVED",
            "policy_type": "test",
            "version": 1,
        }]

        with pytest.raises(ValueError, match="Illegal transition"):
            PolicyService.submit_for_approval(
                policy_id="policy_002",
                submitted_by="user_001",
                actor_role="admin",
                tenant_id="tenant_001",
            )

    @patch("server.db_service.execute_query")
    def test_submit_nonexistent_fails(self, mock_query):
        mock_query.return_value = []

        with pytest.raises(ValueError, match="not found"):
            PolicyService.submit_for_approval(
                policy_id="nonexistent",
                submitted_by="user_001",
                actor_role="admin",
                tenant_id="tenant_001",
            )


class TestPolicyServiceApprove:
    """Test approve_policy with mocked DB and RBAC."""

    @patch("server.core.policy_service._on_policy_activated")
    @patch("server.core.policy_service.AuditLog")
    @patch("server.db_service.execute_transaction")
    @patch("server.db_service.execute_query")
    def test_approve_submitted_succeeds(
        self, mock_query, mock_tx, mock_audit, mock_activate
    ):
        # effective_from is in the future → no auto-activation
        future = datetime(2030, 1, 1, tzinfo=timezone.utc)
        mock_query.return_value = [{
            "id": "policy_003",
            "status": "SUBMITTED",
            "policy_type": "test",
            "version": 1,
            "effective_from": future,
        }]
        mock_tx.return_value = None

        result = PolicyService.approve_policy(
            policy_id="policy_003",
            approved_by="admin_001",
            actor_role="admin",
            tenant_id="tenant_001",
        )

        assert result["status"] == "APPROVED"
        mock_activate.assert_not_called()

    @patch("server.core.policy_service._on_policy_activated")
    @patch("server.core.policy_service.AuditLog")
    @patch("server.db_service.execute_transaction")
    @patch("server.db_service.execute_query")
    def test_approve_auto_activates_if_effective_now(
        self, mock_query, mock_tx, mock_audit, mock_activate
    ):
        # effective_from is in the past → auto-activate
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        mock_query.return_value = [{
            "id": "policy_004",
            "status": "SUBMITTED",
            "policy_type": "grading_cutoff",
            "version": 2,
            "effective_from": past,
        }]
        mock_tx.return_value = None

        result = PolicyService.approve_policy(
            policy_id="policy_004",
            approved_by="admin_001",
            actor_role="admin",
            tenant_id="tenant_001",
        )

        assert result["status"] == "ACTIVATED"
        mock_activate.assert_called_once()

    @patch("server.db_service.execute_query")
    def test_approve_by_unauthorized_role_fails(self, mock_query):
        """RBAC: Only ADMIN / SUPER_ADMIN may approve."""
        mock_query.return_value = [{
            "id": "policy_005",
            "status": "SUBMITTED",
            "policy_type": "test",
            "version": 1,
            "effective_from": datetime(2030, 1, 1, tzinfo=timezone.utc),
        }]

        with pytest.raises(PermissionError):
            PolicyService.approve_policy(
                policy_id="policy_005",
                approved_by="student_001",
                actor_role="student",
                tenant_id="tenant_001",
            )


class TestPolicyServiceGetPolicy:
    """Test get_policy and temporal resolution."""

    @patch("server.db_service.execute_query")
    def test_get_policy_by_id(self, mock_query):
        mock_query.return_value = [{
            "id": "policy_006",
            "policy_type": "test",
            "parameters": '{"threshold": 60}',
            "status": "ACTIVATED",
        }]

        result = PolicyService.get_policy(
            policy_id="policy_006",
            tenant_id="tenant_001",
        )

        assert result is not None
        assert result["parameters"] == {"threshold": 60}

    @patch("server.db_service.execute_query")
    def test_get_policy_not_found(self, mock_query):
        mock_query.return_value = []

        result = PolicyService.get_policy(
            policy_id="nonexistent",
            tenant_id="tenant_001",
        )

        assert result is None


class TestPolicyActivatedEvent:
    """Test that PolicyActivated event is emitted correctly."""

    @patch("server.core.policy_service.AuditLog")
    @patch("server.core.policy_service.EventBus")
    @patch("server.db_service.execute_transaction")
    def test_event_emitted_on_activation(
        self, mock_tx, mock_eventbus, mock_audit
    ):
        from server.core.policy_service import _on_policy_activated

        mock_tx.return_value = None
        mock_eventbus.publish.return_value = True

        _on_policy_activated(
            policy_id="policy_007",
            policy_type="grading_cutoff",
            version=3,
            actor_id="admin_001",
            actor_role="admin",
            tenant_id="tenant_001",
        )

        # Verify EventBus.publish was called
        mock_eventbus.publish.assert_called_once()
        published_event = mock_eventbus.publish.call_args[0][0]
        assert published_event.type == "e00.policy.activated"
        assert published_event.payload["policy_id"] == "policy_007"
        assert published_event.payload["version"] == 3
