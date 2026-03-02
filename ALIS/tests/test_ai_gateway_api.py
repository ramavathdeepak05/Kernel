"""
ALIS AI Gateway API Tests — E03-S01

Tests for the centralized AI Gateway REST API layer.
Covers:
- Gateway router endpoint validation
- Module registry routing
- Agent registry and execution
- Tenant-awareness
- E00-S06 output schema enforcement

Run:  PYTHONPATH=. pytest tests/test_ai_gateway_api.py -v
"""

import sys
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime


# ============================================================================
# MOCK RBAC DECORATOR (same pattern as test_audit_api.py)
# ============================================================================
# The require_permission decorator's wrapper doesn't use functools.wraps,
# so FastAPI cannot introspect the decorated function's parameters.
# We patch it out before importing the router, following the established
# test pattern in test_audit_api.py.

# Preserve the real rbac module reference for Role/Permission usage
import server.core.rbac as _real_rbac

# Patch require_permission to be a no-op decorator
_original_require_permission = _real_rbac.require_permission

def _mock_require_permission(perm):
    """No-op decorator that preserves the original function signature."""
    def decorator(func):
        return func
    return decorator

_real_rbac.require_permission = _mock_require_permission


# Now import test subjects (with patched decorator)
from fastapi.testclient import TestClient

from server.main import app
from server.core.ai_gateway import (
    AIGateway,
    AIGatewayContext,
    AIInvocationResult,
    AIResponseSchema,
    ConfidenceTier,
    StateImpact,
)
from server.core.rbac import Role, Permission
from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import PermissionDeniedError
from server.agents.admissions.registry import AdmissionsAgentRegistry


client = TestClient(app)


# ============================================================================
# TEARDOWN: Restore original decorator
# ============================================================================

@pytest.fixture(autouse=True, scope="module")
def restore_rbac():
    """Restore the real require_permission after all tests in this module."""
    yield
    _real_rbac.require_permission = _original_require_permission


# =============================================================================
# HEALTH CHECK TESTS
# =============================================================================

class TestAIHealthEndpoint:
    """Tests for GET /api/v1/ai/health."""

    def test_health_returns_200(self):
        """AI health endpoint should return 200 with module info."""
        response = client.get("/api/v1/ai/health")
        assert response.status_code == 200

        data = response.json()
        assert data["gateway"] == "loaded"
        assert "M1" in data["registered_modules"]
        assert data["cloud_violations"] == []

    def test_health_detects_no_cloud_violations(self):
        """Health check should confirm no cloud LLM imports."""
        response = client.get("/api/v1/ai/health")
        data = response.json()

        assert data["status"] == "healthy"
        assert len(data["cloud_violations"]) == 0


# =============================================================================
# ADMISSIONS AGENT REGISTRY TESTS
# =============================================================================

class TestAdmissionsAgentRegistry:
    """Tests for the module-scoped Admissions agent registry."""

    def test_has_eligibility_agent(self):
        """Registry should contain the eligibility evaluator."""
        assert AdmissionsAgentRegistry.has_agent("eligibility_evaluator_v1")

    def test_does_not_have_unknown_agent(self):
        """Registry should not contain unregistered agents."""
        assert not AdmissionsAgentRegistry.has_agent("nonexistent_agent")

    def test_list_agents(self):
        """Should list all registered agent names."""
        agents = AdmissionsAgentRegistry.list_agents()
        assert "eligibility_evaluator_v1" in agents

    def test_list_agents_detail_has_metadata(self):
        """Should list agents with full versioned metadata."""
        details = AdmissionsAgentRegistry.list_agents_detail()
        assert len(details) >= 1

        agent = details[0]
        assert agent["agent_id"] == "eligibility_evaluator_v1"
        assert agent["module"] == "M1"
        assert agent["model_version"] == "llama3_8b_v1"
        assert agent["prompt_version"] == "v1"
        assert agent["invocation_class"] == "EVALUATIVE"

    def test_execute_unknown_agent_raises(self):
        """Executing an unregistered agent should raise ValueError."""
        ctx = AIGatewayContext(
            actor_id="test", actor_role=Role.AI_AGENT, org_id="org-1"
        )
        with pytest.raises(ValueError, match="not registered"):
            AdmissionsAgentRegistry.execute(
                agent_name="nonexistent",
                context=ctx,
                input_data={},
            )


# =============================================================================
# GATEWAY ROUTER — INVOKE ENDPOINT TESTS
# =============================================================================

class TestGatewayInvokeEndpoint:
    """Tests for POST /api/v1/ai/invoke."""

    def test_invoke_invalid_module_returns_400(self):
        """Invoking a non-existent module should return 400."""
        response = client.post(
            "/api/v1/ai/invoke",
            json={
                "actor_id": "agent-1",
                "actor_role": "ai_agent",
                "org_id": "org-1",
                "module": "M99",
                "agent_name": "test_agent",
                "input_data": {},
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "ERR_AI_MODULE_NOT_FOUND"

    def test_invoke_invalid_agent_returns_400(self):
        """Invoking a non-existent agent in a valid module should return 400."""
        response = client.post(
            "/api/v1/ai/invoke",
            json={
                "actor_id": "agent-1",
                "actor_role": "ai_agent",
                "org_id": "org-1",
                "module": "M1",
                "agent_name": "nonexistent_agent",
                "input_data": {},
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "ERR_AI_AGENT_NOT_FOUND"
        assert "eligibility_evaluator_v1" in data["details"]["available_agents"]

    def test_invoke_valid_agent_success(self):
        """Invoking a valid agent with mocked execution should return 200."""
        mock_result = AIInvocationResult(
            success=True,
            content=json.dumps({
                "eligibility_score": 0.85,
                "confidence_tier": "HIGH",
                "proposed_state": "ELIGIBLE",
                "draft_verdict": "Applicant meets criteria",
            }),
            request_id="test-req-id",
            model="llama3",
            latency_ms=123.4,
        )

        with patch.object(
            AdmissionsAgentRegistry, "execute", return_value=mock_result
        ):
            response = client.post(
                "/api/v1/ai/invoke",
                json={
                    "actor_id": "agent-1",
                    "actor_role": "ai_agent",
                    "org_id": "org-1",
                    "module": "M1",
                    "agent_name": "eligibility_evaluator_v1",
                    "input_data": {
                        "marksheet_text": "Math: 85, Science: 90",
                        "admission_criteria": "Minimum 50%",
                    },
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["module"] == "M1"
            assert data["agent_name"] == "eligibility_evaluator_v1"
            assert data["model"] == "llama3"

    def test_invoke_missing_required_field_returns_422(self):
        """Missing required fields should return 422 (Pydantic validation)."""
        response = client.post(
            "/api/v1/ai/invoke",
            json={
                "actor_id": "agent-1",
                # Missing actor_role, org_id, module, agent_name
            },
        )
        assert response.status_code == 422

    def test_invoke_returns_tenant_context(self):
        """Response should reflect the tenant context (org_id)."""
        mock_result = AIInvocationResult(
            success=True,
            content="{}",
            request_id="req-123",
            model="llama3",
        )

        with patch.object(
            AdmissionsAgentRegistry, "execute", return_value=mock_result
        ) as mock_exec:
            response = client.post(
                "/api/v1/ai/invoke",
                json={
                    "actor_id": "agent-1",
                    "actor_role": "ai_agent",
                    "org_id": "tenant-xyz",
                    "module": "M1",
                    "agent_name": "eligibility_evaluator_v1",
                    "input_data": {},
                },
            )
            assert response.status_code == 200

            # Verify the context passed to execute had the right org_id
            call_args = mock_exec.call_args
            context = call_args.kwargs["context"]
            assert context.org_id == "tenant-xyz"


# =============================================================================
# GATEWAY ROUTER — AGENT LIST ENDPOINT TESTS
# =============================================================================

class TestGatewayAgentListEndpoint:
    """Tests for GET /api/v1/ai/agents/{module}."""

    def test_list_agents_for_valid_module(self):
        """Should list all agents for a valid module."""
        response = client.get("/api/v1/ai/agents/M1")
        assert response.status_code == 200

        data = response.json()
        assert data["module"] == "M1"
        assert len(data["agents"]) >= 1
        assert data["agents"][0]["agent_id"] == "eligibility_evaluator_v1"

    def test_list_agents_for_invalid_module(self):
        """Should return 404 for a non-existent module."""
        response = client.get("/api/v1/ai/agents/M99")
        assert response.status_code == 404
        data = response.json()
        assert data["code"] == "ERR_AI_MODULE_NOT_FOUND"


# =============================================================================
# E00-S06 SCHEMA ENFORCEMENT TESTS
# =============================================================================

class TestSchemaEnforcement:
    """Tests for AI output schema enforcement through the gateway."""

    def test_valid_schema_accepted(self):
        """AIResponseSchema should accept valid structured output."""
        schema = AIResponseSchema(
            decision="ELIGIBLE",
            confidence_score=0.85,
            confidence_tier=ConfidenceTier.HIGH,
            state_impact="Draft",
            reasoning="Meets all criteria",
        )
        assert schema.decision == "ELIGIBLE"
        assert schema.confidence_score == 0.85
        assert schema.state_impact == "Draft"

    def test_forbidden_state_impact_final_rejected(self):
        """STATE_IMPACT='Final' should be rejected per E00-S06."""
        with pytest.raises(ValueError, match="Forbidden STATE_IMPACT"):
            AIResponseSchema(
                decision="ELIGIBLE",
                confidence_score=0.9,
                confidence_tier=ConfidenceTier.HIGH,
                state_impact="Final",
            )

    def test_forbidden_state_impact_commit_rejected(self):
        """STATE_IMPACT='Commit' should be rejected per E00-S06."""
        with pytest.raises(ValueError, match="Forbidden STATE_IMPACT"):
            AIResponseSchema(
                decision="ELIGIBLE",
                confidence_score=0.9,
                confidence_tier=ConfidenceTier.HIGH,
                state_impact="Commit",
            )

    def test_forbidden_state_impact_override_rejected(self):
        """STATE_IMPACT='Override' should be rejected per E00-S06."""
        with pytest.raises(ValueError, match="Forbidden STATE_IMPACT"):
            AIResponseSchema(
                decision="ELIGIBLE",
                confidence_score=0.9,
                confidence_tier=ConfidenceTier.HIGH,
                state_impact="Override",
            )

    def test_provisional_only_state_impact_allowed(self):
        """STATE_IMPACT='ProvisionalOnly' should be allowed."""
        schema = AIResponseSchema(
            decision="PROVISIONALLY_ELIGIBLE",
            confidence_score=0.6,
            confidence_tier=ConfidenceTier.MEDIUM,
            state_impact="ProvisionalOnly",
        )
        assert schema.state_impact == "ProvisionalOnly"

    def test_confidence_score_bounds(self):
        """Confidence score must be between 0.0 and 1.0."""
        with pytest.raises(ValueError):
            AIResponseSchema(
                decision="TEST",
                confidence_score=1.5,  # Out of bounds
                confidence_tier=ConfidenceTier.HIGH,
                state_impact="Draft",
            )


# =============================================================================
# SYSTEM ENTRYPOINT TESTS
# =============================================================================

class TestMainApp:
    """Tests for the FastAPI application entrypoint."""

    def test_app_has_health_endpoint(self):
        """Main health endpoint should be accessible."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "ALIS"

    def test_app_has_docs(self):
        """OpenAPI docs should be available."""
        response = client.get("/docs")
        assert response.status_code == 200
