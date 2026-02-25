"""
ALIS AI Gateway Tests - E03-S01

Tests for the centralized AI Gateway service.
Verifies RBAC enforcement, audit logging, and local-only constraints.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Import test subjects
from server.core.ai_gateway import (
    AIGateway,
    AIGatewayContext,
    AIInvocationResult,
    InstrumentedLLM
)
from server.core.rbac import Role, Permission
from server.core.audit import AuditLog, AuditAction
from server.core.exceptions import PermissionDeniedError
from uuid import uuid4

@pytest.fixture(autouse=True)
def mock_audit_log_in_memory():
    """Mock AuditLog to use in-memory storage for AI Gateway tests."""
    AuditLog._entries = []
    
    def mock_log(**kwargs):
        entry = MagicMock()
        # Enums to values for easier comparison in some tests
        action = kwargs.get("action")
        if hasattr(action, "value"): action = action.value
        
        # Set attributes
        setattr(entry, "action", action)
        setattr(entry, "actor_id", kwargs.get("actor_id"))
        setattr(entry, "actor_type", kwargs.get("actor_type", "system"))
        setattr(entry, "module", kwargs.get("module"))
        setattr(entry, "success", kwargs.get("success", True))
        setattr(entry, "failure_reason", kwargs.get("failure_reason"))
        setattr(entry, "metadata", kwargs.get("metadata", {}))
        setattr(entry, "id", str(uuid4()))
        
        # Ensure __str__ doesn't contain prompt if metadata is there
        entry.__str__.return_value = f"AuditEntry(action={action})"
        
        AuditLog._entries.append(entry)
        return entry

    def mock_query(**kwargs):
        results = []
        for entry in AuditLog._entries:
            match = True
            for k, v in kwargs.items():
                val = getattr(entry, k, None)
                target = v.value if hasattr(v, "value") else v
                if val != target:
                    match = False
                    break
            if match:
                results.append(entry)
        return results

    with patch.object(AuditLog, "log", side_effect=mock_log), \
         patch.object(AuditLog, "query", side_effect=mock_query):
        yield AuditLog._entries
    """Tests for AIGatewayContext."""

    def test_context_defaults(self):
        """Context should have sensible defaults."""
        ctx = AIGatewayContext(actor_id="test-actor")

        assert ctx.actor_id == "test-actor"
        assert ctx.actor_type == "system"
        assert ctx.actor_role == Role.SYSTEM
        assert ctx.request_id is not None
        assert len(ctx.request_id) == 36  # UUID format

    def test_context_with_module(self):
        """Context should accept module and wizard info."""
        ctx = AIGatewayContext(
            actor_id="agent-123",
            actor_role=Role.AI_AGENT,
            module="M1",
            wizard="Eligibility Eval"
        )

        assert ctx.module == "M1"
        assert ctx.wizard == "Eligibility Eval"


class TestAIGateway:
    """Tests for AIGateway class."""

    def test_get_llm_returns_instrumented_llm(self):
        """get_llm should return an InstrumentedLLM wrapper."""
        ctx = AIGatewayContext(
            actor_id="test-agent",
            actor_role=Role.AI_AGENT
        )

        with patch('server.core.ai_gateway.OllamaLLM') as mock_ollama:
            mock_ollama.return_value = Mock()
            llm = AIGateway.get_llm(ctx)

            assert isinstance(llm, InstrumentedLLM)
            mock_ollama.assert_called_once()

    def test_get_llm_uses_config_defaults(self):
        """get_llm should use config values for base_url and model."""
        ctx = AIGatewayContext(
            actor_id="test-agent",
            actor_role=Role.AI_AGENT
        )

        with patch('server.core.ai_gateway.OllamaLLM') as mock_ollama:
            with patch('server.core.ai_gateway.ConfigRegistry') as mock_config:
                # Mock the class attributes for key names
                mock_config.LLM_BASE_URL = "ai.llm.base_url"
                mock_config.LLM_MODEL_NAME = "ai.llm.model_name"
                mock_config.get.side_effect = lambda key, default: {
                    "ai.llm.base_url": "http://test:11434",
                    "ai.llm.model_name": "test-model"
                }.get(key, default)

                mock_ollama.return_value = Mock()
                AIGateway.get_llm(ctx)

                # Verify Ollama was configured with config values
                call_kwargs = mock_ollama.call_args[1]
                assert call_kwargs["base_url"] == "http://test:11434"
                assert call_kwargs["model"] == "test-model"

    def test_get_llm_allows_model_override(self):
        """get_llm should allow model name override."""
        ctx = AIGatewayContext(
            actor_id="test-agent",
            actor_role=Role.AI_AGENT
        )

        with patch('server.core.ai_gateway.OllamaLLM') as mock_ollama:
            mock_ollama.return_value = Mock()
            AIGateway.get_llm(ctx, model_name="qwen2.5")

            call_kwargs = mock_ollama.call_args[1]
            assert call_kwargs["model"] == "qwen2.5"


class TestInstrumentedLLM:
    """Tests for InstrumentedLLM wrapper."""

    def setup_method(self):
        """Setup test fixtures."""
        self.mock_llm = Mock()
        self.ctx = AIGatewayContext(
            actor_id="test-agent",
            actor_role=Role.AI_AGENT,
            module="M1"
        )
        self.instrumented = InstrumentedLLM(
            llm=self.mock_llm,
            context=self.ctx,
            model_name="llama3"
        )
        # Clear audit log entries from previous tests
        AuditLog._entries = []

    def test_invoke_success_logs_audit(self):
        """Successful invocation should log to audit."""
        self.mock_llm.invoke.return_value = "Test response"

        result = self.instrumented.invoke("Test prompt")

        assert result.success is True
        assert result.content == "Test response"
        assert result.model == "llama3"
        assert result.latency_ms >= 0

        # Verify audit log
        entries = AuditLog.query(action=AuditAction.AI_INVOCATION)
        assert len(entries) >= 1
        entry = entries[0]
        assert entry.actor_id == "test-agent"
        assert entry.actor_type == "system"
        assert entry.module == "M1"
        assert entry.success is True

    def test_invoke_failure_logs_audit(self):
        """Failed invocation should log error to audit."""
        self.mock_llm.invoke.side_effect = Exception("LLM Error")

        result = self.instrumented.invoke("Test prompt")

        assert result.success is False
        assert result.error == "LLM Error"

        # Verify audit log captures failure
        entries = AuditLog.query(action=AuditAction.AI_INVOCATION)
        assert len(entries) >= 1
        entry = entries[0]
        assert entry.success is False
        assert "LLM Error" in entry.failure_reason


class TestRBACEnforcement:
    """Tests for RBAC enforcement in AI Gateway."""

    def setup_method(self):
        """Setup test fixtures."""
        AuditLog._entries = []

    def test_student_role_denied_ai_invoke(self):
        """Students should NOT be able to invoke AI Gateway."""
        ctx = AIGatewayContext(
            actor_id="student-123",
            actor_role=Role.STUDENT
        )

        with patch('server.core.ai_gateway.OllamaLLM') as mock_ollama:
            mock_llm = Mock()
            mock_ollama.return_value = mock_llm

            llm = AIGateway.get_llm(ctx)

            # Invocation should raise permission denied
            with pytest.raises(PermissionDeniedError):
                llm.invoke("Test prompt")

            # Verify access denied was logged
            entries = AuditLog.query(action=AuditAction.ACCESS_DENIED)
            assert len(entries) >= 1

    def test_ai_agent_role_allowed_invoke(self):
        """AI Agents should be able to invoke AI Gateway."""
        ctx = AIGatewayContext(
            actor_id="agent-123",
            actor_role=Role.AI_AGENT
        )

        with patch('server.core.ai_gateway.OllamaLLM') as mock_ollama:
            mock_llm = Mock()
            mock_llm.invoke.return_value = "Response"
            mock_ollama.return_value = mock_llm

            llm = AIGateway.get_llm(ctx)
            result = llm.invoke("Test prompt")

            assert result.success is True

    def test_system_role_allowed_invoke(self):
        """System role should be able to invoke AI Gateway."""
        ctx = AIGatewayContext(
            actor_id="system",
            actor_role=Role.SYSTEM
        )

        with patch('server.core.ai_gateway.OllamaLLM') as mock_ollama:
            mock_llm = Mock()
            mock_llm.invoke.return_value = "Response"
            mock_ollama.return_value = mock_llm

            llm = AIGateway.get_llm(ctx)
            result = llm.invoke("Test prompt")

            assert result.success is True


class TestNoCloudConstraint:
    """Tests for the 'No Cloud LLM' constraint."""

    def test_validate_no_cloud_imports_clean(self):
        """Should return empty list when no cloud imports present."""
        violations = AIGateway.validate_no_cloud_imports()

        # Should not detect any forbidden imports in our clean environment
        assert "openai" not in [v for v in violations]
        assert "anthropic" not in [v for v in violations]

    def test_forbidden_imports_list(self):
        """Verify forbidden imports list is correct."""
        forbidden = AIGateway._FORBIDDEN_IMPORTS

        assert "openai" in forbidden
        assert "anthropic" in forbidden
        assert "langchain_openai" in forbidden
        assert "langchain_anthropic" in forbidden


class TestAuditMetadata:
    """Tests for audit log metadata."""

    def setup_method(self):
        """Setup test fixtures."""
        AuditLog._entries = []

    def test_audit_contains_model_info(self):
        """Audit log should contain model information."""
        ctx = AIGatewayContext(
            actor_id="agent-123",
            actor_role=Role.AI_AGENT
        )

        with patch('server.core.ai_gateway.OllamaLLM') as mock_ollama:
            mock_llm = Mock()
            mock_llm.invoke.return_value = "Response"
            mock_ollama.return_value = mock_llm

            llm = AIGateway.get_llm(ctx)
            llm.invoke("Test prompt")

            entries = AuditLog.query(action=AuditAction.AI_INVOCATION)
            assert len(entries) >= 1
            entry = entries[0]
            assert entry.metadata is not None
            assert "model" in entry.metadata
            assert "latency_ms" in entry.metadata
            assert "prompt_length" in entry.metadata
            assert "response_length" in entry.metadata

    def test_audit_does_not_contain_prompt_content(self):
        """Audit log should NOT contain actual prompt content (PII safety)."""
        ctx = AIGatewayContext(
            actor_id="agent-123",
            actor_role=Role.AI_AGENT
        )

        sensitive_prompt = "Analyze student John Doe SSN 123-45-6789"

        with patch('server.core.ai_gateway.OllamaLLM') as mock_ollama:
            mock_llm = Mock()
            mock_llm.invoke.return_value = "Response"
            mock_ollama.return_value = mock_llm

            llm = AIGateway.get_llm(ctx)
            llm.invoke(sensitive_prompt)

            entries = AuditLog.query(action=AuditAction.AI_INVOCATION)
            entry = entries[0]

            # Audit should NOT contain the actual prompt
            assert sensitive_prompt not in str(entry)
            assert "John Doe" not in str(entry)
            assert "123-45-6789" not in str(entry)

            # But should contain metadata like length
            assert entry.metadata["prompt_length"] == len(sensitive_prompt)
