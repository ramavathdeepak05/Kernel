"""
S3 AI Service — Unit Tests

Covers:
- PIIMasker     : regex patterns, determinism, multi-type, round-trip unmask
- BudgetTracker : check, record, reset, plan limits
- ProviderRouter : selection logic (VPC Ollama default, managed override, model mapping)
- HTTP API       : /v1/complete, /v1/embed, /v1/budget — via TestClient
- AIServiceLLM   : _extract_text, invoke proxy, error handling
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis():
    import fakeredis
    server = fakeredis.FakeServer()
    client = fakeredis.FakeRedis(server=server, decode_responses=True)
    with patch("ai_service.budget._get_redis", return_value=client):
        yield client


@pytest.fixture
def test_app(fake_redis):
    from ai_service.main import create_app
    return TestClient(create_app(), raise_server_exceptions=True)


def _headers() -> dict:
    from ai_service.settings import settings
    return {"X-AI-Token": settings.ai_service_token}


# ===========================================================================
# 1. PII Masker
# ===========================================================================

class TestPIIMasker:

    def _session(self):
        from ai_service.pii_masker import MaskingSession
        return MaskingSession(salt="test-salt-fixed")

    def test_masks_email(self):
        from ai_service.pii_masker import PIIMasker
        s = self._session()
        result = PIIMasker.mask("Contact me at ravi@example.com for details.", s)
        assert "ravi@example.com" not in result
        assert "[EMAIL_" in result

    def test_masks_application_id(self):
        from ai_service.pii_masker import PIIMasker
        s = self._session()
        result = PIIMasker.mask("Check application APP-2025-000089 status.", s)
        assert "APP-2025-000089" not in result
        assert "[APP_ID_" in result

    def test_masks_aadhaar(self):
        from ai_service.pii_masker import PIIMasker
        s = self._session()
        result = PIIMasker.mask("Aadhaar number: 2345 6789 0123", s)
        assert "2345 6789 0123" not in result

    def test_masks_phone(self):
        from ai_service.pii_masker import PIIMasker
        s = self._session()
        result = PIIMasker.mask("Call 9876543210 for support.", s)
        assert "9876543210" not in result

    def test_masks_uuid(self):
        from ai_service.pii_masker import PIIMasker
        s = self._session()
        uid = "550e8400-e29b-41d4-a716-446655440000"
        result = PIIMasker.mask(f"User ID: {uid}", s)
        assert uid not in result

    def test_deterministic_same_value_same_token(self):
        """Same value + same session → same token (multi-turn coherence)."""
        from ai_service.pii_masker import PIIMasker
        s = self._session()
        r1 = PIIMasker.mask("ravi@example.com", s)
        r2 = PIIMasker.mask("ravi@example.com", s)
        assert r1 == r2

    def test_different_values_different_tokens(self):
        from ai_service.pii_masker import PIIMasker
        s = self._session()
        r1 = PIIMasker.mask("a@example.com", s)
        r2 = PIIMasker.mask("b@example.com", s)
        assert r1 != r2

    def test_unmask_restores_original(self):
        from ai_service.pii_masker import PIIMasker
        s = self._session()
        original = "Contact ravi@example.com or APP-2025-000001."
        masked = PIIMasker.mask(original, s)
        restored = PIIMasker.unmask(masked, s)
        assert "ravi@example.com" in restored
        assert "APP-2025-000001" in restored

    def test_no_pii_text_unchanged(self):
        from ai_service.pii_masker import PIIMasker
        s = self._session()
        text = "The admissions count for 2025 is 150 students."
        result = PIIMasker.mask(text, s)
        assert result == text

    def test_token_map_populated(self):
        from ai_service.pii_masker import PIIMasker
        s = self._session()
        PIIMasker.mask("ravi@example.com", s)
        assert len(s.token_map) == 1
        assert "ravi@example.com" in s.token_map


# ===========================================================================
# 2. Budget Tracker
# ===========================================================================

class TestBudgetTracker:

    def test_initial_usage_is_zero(self, fake_redis):
        from ai_service import budget as bgt
        assert bgt.get_usage("tenant-abc") == 0

    def test_record_and_get_usage(self, fake_redis):
        from ai_service import budget as bgt
        bgt.record_usage("tenant-abc", 500)
        bgt.record_usage("tenant-abc", 300)
        assert bgt.get_usage("tenant-abc") == 800

    def test_check_budget_within_limit(self, fake_redis):
        from ai_service import budget as bgt
        allowed, used, limit = bgt.check_budget("t1", "starter", 1000)
        assert allowed is True
        assert used == 0

    def test_check_budget_exceeds_limit(self, fake_redis):
        from ai_service import budget as bgt
        from ai_service.settings import settings
        # Record usage just below the limit
        bgt.record_usage("t2", settings.budget_starter_monthly_tokens)
        allowed, used, limit = bgt.check_budget("t2", "starter", 1)
        assert allowed is False

    def test_reset_usage(self, fake_redis):
        from ai_service import budget as bgt
        bgt.record_usage("t3", 1000)
        bgt.reset_usage("t3")
        assert bgt.get_usage("t3") == 0

    def test_tenants_isolated(self, fake_redis):
        from ai_service import budget as bgt
        bgt.record_usage("ta", 1000)
        bgt.record_usage("tb", 2000)
        assert bgt.get_usage("ta") == 1000
        assert bgt.get_usage("tb") == 2000

    def test_enterprise_plan_higher_limit(self, fake_redis):
        from ai_service import budget as bgt
        from ai_service.settings import settings
        _, _, limit_s = bgt.check_budget("t", "starter", 0)
        _, _, limit_e = bgt.check_budget("t", "enterprise", 0)
        assert limit_e > limit_s


# ===========================================================================
# 3. Provider Router
# ===========================================================================

class TestProviderRouter:

    def test_default_returns_vpc_ollama(self):
        from ai_service.providers import ProviderRouter, VpcOllamaProvider
        with patch("ai_service.settings.settings") as mock_s:
            mock_s.azure_openai_enabled = False
            mock_s.aws_bedrock_enabled = False
            mock_s.gcp_vertex_enabled = False
            mock_s.ollama_extraction_model = "qwen2.5:1.5b"
            mock_s.ollama_generation_model = "qwen2.5:7b"
            mock_s.ollama_reasoning_model = "qwen2.5:14b"
            prov, model = ProviderRouter.select("extraction")
        assert isinstance(prov, VpcOllamaProvider)
        assert model == "qwen2.5:1.5b"

    def test_explicit_provider_override(self):
        from ai_service.providers import ProviderRouter, AzureOpenAIProvider
        with patch("ai_service.settings.settings") as mock_s:
            mock_s.azure_openai_enabled = True
            mock_s.azure_openai_deployment_generation = "gpt-4o"
            prov, model = ProviderRouter.select("generation", explicit_provider="azure_openai")
        assert isinstance(prov, AzureOpenAIProvider)
        assert model == "gpt-4o"

    def test_enterprise_managed_flag_selects_managed(self):
        """enterprise plan + ai_managed=true → first available managed provider."""
        from ai_service.providers import ProviderRouter, AzureOpenAIProvider
        with patch("ai_service.settings.settings") as mock_s:
            mock_s.azure_openai_enabled = True
            mock_s.aws_bedrock_enabled = False
            mock_s.gcp_vertex_enabled = False
            mock_s.azure_openai_deployment_extraction = "gpt-4o-mini"
            prov, model = ProviderRouter.select(
                "extraction",
                tenant_plan="enterprise",
                feature_flags={"ai_managed": True},
            )
        assert isinstance(prov, AzureOpenAIProvider)

    def test_growth_plan_with_managed_flag_still_uses_ollama(self):
        """Only enterprise plan gets managed inference."""
        from ai_service.providers import ProviderRouter, VpcOllamaProvider
        with patch("ai_service.settings.settings") as mock_s:
            mock_s.azure_openai_enabled = True
            mock_s.aws_bedrock_enabled = False
            mock_s.gcp_vertex_enabled = False
            mock_s.ollama_extraction_model = "qwen2.5:1.5b"
            mock_s.ollama_generation_model = "qwen2.5:7b"
            mock_s.ollama_reasoning_model = "qwen2.5:14b"
            prov, _ = ProviderRouter.select(
                "extraction",
                tenant_plan="growth",
                feature_flags={"ai_managed": True},
            )
        assert isinstance(prov, VpcOllamaProvider)

    def test_task_class_model_mapping_ollama(self):
        from ai_service.providers import ProviderRouter
        with patch("ai_service.settings.settings") as mock_s:
            mock_s.azure_openai_enabled = False
            mock_s.aws_bedrock_enabled = False
            mock_s.gcp_vertex_enabled = False
            mock_s.ollama_extraction_model = "small"
            mock_s.ollama_generation_model = "medium"
            mock_s.ollama_reasoning_model = "large"
            _, m_ext = ProviderRouter.select("extraction")
            _, m_gen = ProviderRouter.select("generation")
            _, m_rea = ProviderRouter.select("reasoning")
        assert m_ext == "small"
        assert m_gen == "medium"
        assert m_rea == "large"


# ===========================================================================
# 4. HTTP API
# ===========================================================================

class TestCompleteEndpoint:

    def _mock_provider(self, response_text: str = "mocked response"):
        mock_prov = MagicMock()
        mock_prov.name = "vpc_ollama"
        mock_prov.complete.return_value = response_text
        return mock_prov

    def test_complete_returns_200(self, test_app):
        mock_prov = self._mock_provider()
        with patch("ai_service.providers.ProviderRouter.select", return_value=(mock_prov, "qwen2.5:1.5b")):
            resp = test_app.post(
                "/v1/complete",
                json={
                    "tenant_id": "t-test",
                    "prompt": "How many applications are pending?",
                    "task_class": "extraction",
                },
                headers=_headers(),
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["text"] == "mocked response"
        assert data["provider"] == "vpc_ollama"
        assert "tokens_used" in data

    def test_complete_masks_pii_in_prompt(self, test_app):
        """PII in prompt should be masked before reaching the provider."""
        captured_prompts = []

        def fake_complete(model, prompt, **kwargs):
            captured_prompts.append(prompt)
            return "ok"

        mock_prov = MagicMock()
        mock_prov.name = "vpc_ollama"
        mock_prov.complete.side_effect = fake_complete

        with patch("ai_service.providers.ProviderRouter.select", return_value=(mock_prov, "m")):
            test_app.post(
                "/v1/complete",
                json={
                    "tenant_id": "t-test",
                    "prompt": "Status of APP-2025-000089 for ravi@iitb.ac.in?",
                    "mask_pii": True,
                },
                headers=_headers(),
            )

        assert len(captured_prompts) == 1
        assert "APP-2025-000089" not in captured_prompts[0]
        assert "ravi@iitb.ac.in" not in captured_prompts[0]

    def test_complete_budget_exceeded_returns_429(self, test_app, fake_redis):
        from ai_service import budget as bgt
        from ai_service.settings import settings
        bgt.record_usage("t-broke", settings.budget_starter_monthly_tokens)

        resp = test_app.post(
            "/v1/complete",
            json={
                "tenant_id": "t-broke",
                "tenant_plan": "starter",
                "prompt": "any",
                "max_tokens": 100,
            },
            headers=_headers(),
        )
        assert resp.status_code == 429

    def test_complete_requires_auth_token(self, test_app):
        resp = test_app.post(
            "/v1/complete",
            json={"tenant_id": "t", "prompt": "hi"},
        )
        assert resp.status_code in (401, 422)

    def test_complete_provider_error_returns_502(self, test_app):
        mock_prov = MagicMock()
        mock_prov.name = "vpc_ollama"
        mock_prov.complete.side_effect = ConnectionRefusedError("ollama down")

        with patch("ai_service.providers.ProviderRouter.select", return_value=(mock_prov, "m")):
            resp = test_app.post(
                "/v1/complete",
                json={"tenant_id": "t", "prompt": "hi"},
                headers=_headers(),
            )
        assert resp.status_code == 502


class TestEmbedEndpoint:

    def test_embed_returns_embeddings(self, test_app):
        mock_prov = MagicMock()
        mock_prov.name = "vpc_ollama"
        mock_prov.embed.return_value = [[0.1, 0.2, 0.3]]

        with patch("ai_service.providers.VpcOllamaProvider", return_value=mock_prov):
            resp = test_app.post(
                "/v1/embed",
                json={"tenant_id": "t", "texts": ["hello world"]},
                headers=_headers(),
            )
        assert resp.status_code == 200
        assert resp.json()["embeddings"] == [[0.1, 0.2, 0.3]]


class TestBudgetEndpoints:

    def test_get_budget(self, test_app, fake_redis):
        from ai_service import budget as bgt
        bgt.record_usage("t-budget", 1234)
        resp = test_app.get(
            "/v1/budget/t-budget?plan=starter",
            headers=_headers(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tokens_used"] == 1234
        assert data["tenant_id"] == "t-budget"

    def test_reset_budget(self, test_app, fake_redis):
        from ai_service import budget as bgt
        bgt.record_usage("t-reset", 5000)
        resp = test_app.post("/v1/budget/t-reset/reset", headers=_headers())
        assert resp.status_code == 200
        assert bgt.get_usage("t-reset") == 0

    def test_health_endpoint(self, test_app):
        resp = test_app.get("/health")
        assert resp.status_code == 200
        assert resp.json()["service"] == "ai-service"


# ===========================================================================
# 5. AIServiceLLM (data plane wrapper)
# ===========================================================================

class TestAIServiceLLM:

    def test_extract_text_from_string(self):
        from ALIS.server.core.ai_service_provider import AIServiceLLM
        assert AIServiceLLM._extract_text("hello") == "hello"

    def test_extract_text_from_message_list(self):
        from ALIS.server.core.ai_service_provider import AIServiceLLM
        msg = MagicMock()
        msg.content = "what is the status?"
        assert AIServiceLLM._extract_text([msg]) == "what is the status?"

    def test_invoke_calls_ai_service(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "ALIS"))
        from server.core.ai_service_provider import AIServiceLLM
        import httpx

        llm = AIServiceLLM(
            ai_service_url="http://ai-service:8002",
            ai_service_token="test-token",
            tenant_id="t-invoke",
            task_class="extraction",
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"text": "42 applications pending"}

        with patch("httpx.post", return_value=mock_resp) as mock_post:
            result = llm.invoke("How many applications are pending?")

        assert result == "42 applications pending"
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1]["json"]
        assert payload["tenant_id"] == "t-invoke"
        assert payload["task_class"] == "extraction"

    def test_invoke_raises_on_http_error(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "ALIS"))
        from server.core.ai_service_provider import AIServiceLLM

        llm = AIServiceLLM(
            ai_service_url="http://ai-service:8002",
            ai_service_token="test-token",
            tenant_id="t-err",
        )
        with patch("httpx.post", side_effect=ConnectionRefusedError("refused")):
            with pytest.raises(RuntimeError, match="AI Service request failed"):
                llm.invoke("test prompt")

    def test_llm_type_property(self):
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "ALIS"))
        from server.core.ai_service_provider import AIServiceLLM
        llm = AIServiceLLM("http://x", "tok", "tid")
        assert llm._llm_type == "alis_ai_service"
