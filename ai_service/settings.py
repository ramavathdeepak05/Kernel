"""
AI Service Settings — S3
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AIServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = Field(default="development")

    # -------------------------------------------------------------------------
    # Internal auth — data planes present this token on calls to /v1/*
    # -------------------------------------------------------------------------
    ai_service_token: str = Field(
        default="change-me-ai-service-token",
        description="Bearer token data planes use to authenticate with the AI Service.",
    )

    # -------------------------------------------------------------------------
    # Provider: VPC Ollama (primary — low latency, no PII leaves VPC)
    # -------------------------------------------------------------------------
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_timeout_seconds: int = Field(default=120)

    # Tiered model routing (mirrors ALIS data plane settings)
    ollama_extraction_model: str = Field(default="qwen2.5:1.5b-instruct-q8_0")
    ollama_generation_model: str = Field(default="qwen2.5:7b-instruct")
    ollama_reasoning_model: str = Field(default="qwen2.5:14b-instruct")
    ollama_embed_model: str = Field(default="nomic-embed-text")

    # -------------------------------------------------------------------------
    # Provider: Azure OpenAI (managed — used when Ollama is unavailable or
    # tenant plan = enterprise + feature_flag ai_managed=true)
    # -------------------------------------------------------------------------
    azure_openai_endpoint: str = Field(default="")
    azure_openai_api_key: str = Field(default="")
    azure_openai_api_version: str = Field(default="2024-02-01")
    azure_openai_deployment_extraction: str = Field(default="gpt-4o-mini")
    azure_openai_deployment_generation: str = Field(default="gpt-4o")
    azure_openai_deployment_reasoning: str = Field(default="gpt-4o")

    @property
    def azure_openai_enabled(self) -> bool:
        return bool(self.azure_openai_endpoint and self.azure_openai_api_key)

    # -------------------------------------------------------------------------
    # Provider: AWS Bedrock
    # -------------------------------------------------------------------------
    aws_bedrock_region: str = Field(default="us-east-1")
    aws_bedrock_access_key: str = Field(default="")
    aws_bedrock_secret_key: str = Field(default="")
    aws_bedrock_model_extraction: str = Field(default="amazon.nova-micro-v1:0")
    aws_bedrock_model_generation: str = Field(default="amazon.nova-lite-v1:0")
    aws_bedrock_model_reasoning: str = Field(default="amazon.nova-pro-v1:0")

    @property
    def aws_bedrock_enabled(self) -> bool:
        return bool(self.aws_bedrock_access_key and self.aws_bedrock_secret_key)

    # -------------------------------------------------------------------------
    # Provider: GCP Vertex AI
    # -------------------------------------------------------------------------
    gcp_project_id: str = Field(default="")
    gcp_location: str = Field(default="us-central1")
    gcp_service_account_json: str = Field(default="")
    gcp_vertex_model_extraction: str = Field(default="gemini-1.5-flash")
    gcp_vertex_model_generation: str = Field(default="gemini-1.5-pro")
    gcp_vertex_model_reasoning: str = Field(default="gemini-1.5-pro")

    @property
    def gcp_vertex_enabled(self) -> bool:
        return bool(self.gcp_project_id and self.gcp_service_account_json)

    # -------------------------------------------------------------------------
    # PII masking
    # -------------------------------------------------------------------------
    pii_masking_enabled: bool = Field(default=True)
    # Tier 2 enterprise tenants may opt out of PII masking for on-prem Ollama
    pii_masking_bypass_for_vpc_ollama: bool = Field(
        default=False,
        description="When True, PII masking is skipped for VPC Ollama calls only. "
                    "Safe ONLY when Ollama runs in a private VPC with no internet egress.",
    )

    # -------------------------------------------------------------------------
    # Per-tenant token budgets (default values; overridden per plan)
    # -------------------------------------------------------------------------
    budget_starter_monthly_tokens: int = Field(default=100_000)
    budget_growth_monthly_tokens: int = Field(default=1_000_000)
    budget_enterprise_monthly_tokens: int = Field(default=10_000_000)

    # -------------------------------------------------------------------------
    # Redis (for token budget tracking)
    # -------------------------------------------------------------------------
    redis_url: str = Field(default="redis://localhost:6379/1")

    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"]
    )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> AIServiceSettings:
    return AIServiceSettings()


settings = get_settings()
