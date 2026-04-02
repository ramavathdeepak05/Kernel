"""
AI Provider Adapters — S3

Unified interface for all inference backends:
  - VpcOllamaProvider  — local Ollama inside the data-plane VPC
  - AzureOpenAIProvider — Azure OpenAI managed service
  - BedrockProvider     — AWS Bedrock
  - VertexProvider      — GCP Vertex AI

Each provider implements:
  complete(model, prompt, temperature, max_tokens) → str
  embed(texts) → list[list[float]]

Provider selection is done by ProviderRouter based on:
  1. Explicit `provider` request param
  2. Task class + tenant plan + feature flags
  3. VPC Ollama fallback (always available within the VPC)
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class BaseProvider(ABC):

    @abstractmethod
    def complete(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        system_prompt: Optional[str] = None,
    ) -> str: ...

    @abstractmethod
    def embed(self, texts: List[str], model: str) -> List[List[float]]: ...

    @property
    @abstractmethod
    def name(self) -> str: ...


# ---------------------------------------------------------------------------
# VPC Ollama (primary)
# ---------------------------------------------------------------------------

class VpcOllamaProvider(BaseProvider):
    """
    Calls Ollama running in the same VPC as the AI Service.
    Uses Ollama's native HTTP API (not LangChain) for simplicity and
    direct control over the request lifecycle.
    """

    name = "vpc_ollama"

    def complete(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        system_prompt: Optional[str] = None,
    ) -> str:
        import httpx
        from ai_service.settings import settings

        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if system_prompt:
            payload["system"] = system_prompt

        resp = httpx.post(
            f"{settings.ollama_base_url}/api/generate",
            json=payload,
            timeout=settings.ollama_timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json().get("response", "")

    def embed(self, texts: List[str], model: str) -> List[List[float]]:
        import httpx
        from ai_service.settings import settings

        embeddings = []
        for text in texts:
            resp = httpx.post(
                f"{settings.ollama_base_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=settings.ollama_timeout_seconds,
            )
            resp.raise_for_status()
            embeddings.append(resp.json().get("embedding", []))
        return embeddings


# ---------------------------------------------------------------------------
# Azure OpenAI (managed)
# ---------------------------------------------------------------------------

class AzureOpenAIProvider(BaseProvider):

    name = "azure_openai"

    def complete(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        system_prompt: Optional[str] = None,
    ) -> str:
        from ai_service.settings import settings
        try:
            from openai import AzureOpenAI
        except ImportError:
            raise RuntimeError("openai package required for Azure OpenAI provider")

        client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def embed(self, texts: List[str], model: str) -> List[List[float]]:
        from ai_service.settings import settings
        try:
            from openai import AzureOpenAI
        except ImportError:
            raise RuntimeError("openai package required for Azure OpenAI embeddings")

        client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        resp = client.embeddings.create(input=texts, model=model)
        return [item.embedding for item in resp.data]


# ---------------------------------------------------------------------------
# AWS Bedrock
# ---------------------------------------------------------------------------

class BedrockProvider(BaseProvider):

    name = "aws_bedrock"

    def complete(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        system_prompt: Optional[str] = None,
    ) -> str:
        import json
        from ai_service.settings import settings
        try:
            import boto3
        except ImportError:
            raise RuntimeError("boto3 required for AWS Bedrock provider")

        client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_bedrock_region,
            aws_access_key_id=settings.aws_bedrock_access_key,
            aws_secret_access_key=settings.aws_bedrock_secret_key,
        )

        # Amazon Nova models use the Converse API
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        kwargs: dict = {
            "modelId": model,
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if system_prompt:
            kwargs["system"] = [{"text": system_prompt}]

        resp = client.converse(**kwargs)
        return resp["output"]["message"]["content"][0]["text"]

    def embed(self, texts: List[str], model: str) -> List[List[float]]:
        import json
        from ai_service.settings import settings
        try:
            import boto3
        except ImportError:
            raise RuntimeError("boto3 required for AWS Bedrock embeddings")

        client = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_bedrock_region,
            aws_access_key_id=settings.aws_bedrock_access_key,
            aws_secret_access_key=settings.aws_bedrock_secret_key,
        )
        result = []
        for text in texts:
            body = json.dumps({"inputText": text})
            resp = client.invoke_model(
                modelId=model,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            result.append(json.loads(resp["body"].read())["embedding"])
        return result


# ---------------------------------------------------------------------------
# GCP Vertex AI
# ---------------------------------------------------------------------------

class VertexProvider(BaseProvider):

    name = "gcp_vertex"

    def complete(
        self,
        model: str,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        system_prompt: Optional[str] = None,
    ) -> str:
        from ai_service.settings import settings
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel, GenerationConfig
        except ImportError:
            raise RuntimeError("google-cloud-aiplatform required for Vertex AI provider")

        vertexai.init(project=settings.gcp_project_id, location=settings.gcp_location)
        mdl = GenerativeModel(
            model,
            system_instruction=system_prompt if system_prompt else None,
        )
        response = mdl.generate_content(
            prompt,
            generation_config=GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return response.text

    def embed(self, texts: List[str], model: str) -> List[List[float]]:
        from ai_service.settings import settings
        try:
            import vertexai
            from vertexai.language_models import TextEmbeddingModel
        except ImportError:
            raise RuntimeError("google-cloud-aiplatform required for Vertex AI embeddings")

        vertexai.init(project=settings.gcp_project_id, location=settings.gcp_location)
        mdl = TextEmbeddingModel.from_pretrained(model)
        return [emb.values for emb in mdl.get_embeddings(texts)]


# ---------------------------------------------------------------------------
# Provider Router
# ---------------------------------------------------------------------------

class ProviderRouter:
    """
    Selects the right provider + model for a given request.

    Selection logic
    ---------------
    1. Explicit `provider` in request → use that provider
    2. `use_managed=True` in tenant feature flags → prefer managed (Azure/Bedrock/Vertex)
    3. Default: VPC Ollama
    """

    @staticmethod
    def _ollama() -> VpcOllamaProvider:
        return VpcOllamaProvider()

    @staticmethod
    def _managed_provider() -> Optional[BaseProvider]:
        """Return first available managed provider."""
        from ai_service.settings import settings
        if settings.azure_openai_enabled:
            return AzureOpenAIProvider()
        if settings.aws_bedrock_enabled:
            return BedrockProvider()
        if settings.gcp_vertex_enabled:
            return VertexProvider()
        return None

    @classmethod
    def select(
        cls,
        task_class: str,             # extraction | generation | reasoning
        tenant_plan: str = "starter",
        feature_flags: dict | None = None,
        explicit_provider: Optional[str] = None,
    ) -> tuple[BaseProvider, str]:
        """
        Returns (provider, model_name) for the given request parameters.
        """
        from ai_service.settings import settings
        flags = feature_flags or {}

        # 1. Explicit provider override
        if explicit_provider == "azure_openai":
            prov = AzureOpenAIProvider()
        elif explicit_provider == "aws_bedrock":
            prov = BedrockProvider()
        elif explicit_provider == "gcp_vertex":
            prov = VertexProvider()
        elif explicit_provider == "vpc_ollama":
            prov = cls._ollama()
        else:
            # 2. Tenant feature flag: ai_managed=true → prefer managed
            use_managed = flags.get("ai_managed", False) and tenant_plan == "enterprise"
            managed = cls._managed_provider() if use_managed else None
            prov = managed or cls._ollama()

        # 3. Model selection by task class + provider
        model = cls._select_model(prov.name, task_class, settings)
        return prov, model

    @staticmethod
    def _select_model(provider_name: str, task_class: str, settings) -> str:
        tc = task_class.lower()
        if provider_name == "vpc_ollama":
            if tc == "extraction":
                return settings.ollama_extraction_model
            if tc == "generation":
                return settings.ollama_generation_model
            return settings.ollama_reasoning_model
        if provider_name == "azure_openai":
            if tc == "extraction":
                return settings.azure_openai_deployment_extraction
            if tc == "generation":
                return settings.azure_openai_deployment_generation
            return settings.azure_openai_deployment_reasoning
        if provider_name == "aws_bedrock":
            if tc == "extraction":
                return settings.aws_bedrock_model_extraction
            if tc == "generation":
                return settings.aws_bedrock_model_generation
            return settings.aws_bedrock_model_reasoning
        if provider_name == "gcp_vertex":
            if tc == "extraction":
                return settings.gcp_vertex_model_extraction
            if tc == "generation":
                return settings.gcp_vertex_model_generation
            return settings.gcp_vertex_model_reasoning
        # Unknown provider — fall back to Ollama extraction model
        return settings.ollama_extraction_model
