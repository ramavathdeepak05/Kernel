"""
AI Service Pydantic Models — S3
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CompleteRequest(BaseModel):
    """Body for POST /v1/complete"""

    tenant_id: str
    tenant_plan: str = Field(default="starter")
    feature_flags: Dict[str, Any] = Field(default_factory=dict)

    prompt: str
    system_prompt: Optional[str] = None
    task_class: str = Field(
        default="extraction",
        description="extraction | generation | reasoning",
    )
    provider: Optional[str] = Field(
        default=None,
        description="Force a specific provider: vpc_ollama | azure_openai | aws_bedrock | gcp_vertex",
    )
    model_override: Optional[str] = Field(
        default=None,
        description="Force a specific model name (expert use only).",
    )
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=32768)

    # PII handling
    mask_pii: bool = Field(
        default=True,
        description="Mask PII in prompt before sending to provider. "
                    "Set False only for fully trusted on-prem VPC Ollama.",
    )
    unmask_response: bool = Field(
        default=False,
        description="Enterprise-only: restore masked PII tokens in the response. "
                    "Requires the caller to hold the session key for unmasking.",
    )


class CompleteResponse(BaseModel):
    """Response for POST /v1/complete"""

    text: str
    provider: str
    model: str
    tokens_used: Optional[int] = None
    budget_remaining: Optional[int] = None
    pii_masked: bool = False
    session_id: Optional[str] = None   # Present when unmask_response=True


class EmbedRequest(BaseModel):
    """Body for POST /v1/embed"""

    tenant_id: str
    tenant_plan: str = Field(default="starter")
    texts: List[str]
    model: Optional[str] = None   # Defaults to settings.ollama_embed_model


class EmbedResponse(BaseModel):
    embeddings: List[List[float]]
    model: str
    provider: str


class BudgetStatusResponse(BaseModel):
    tenant_id: str
    plan: str
    tokens_used: int
    tokens_limit: int
    tokens_remaining: int
    period: str   # "YYYY-MM"
