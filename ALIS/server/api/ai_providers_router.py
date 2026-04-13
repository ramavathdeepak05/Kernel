"""
ALIS AI Provider Management API — Per-tenant AI extensibility

Allows institution admins to configure their own AI providers (OpenAI, Anthropic,
Azure, Google, or any OpenAI-compatible API) instead of using the platform default.

Endpoints:
    GET    /api/v1/ai/providers           — List configured providers (keys masked)
    POST   /api/v1/ai/providers           — Add a new AI provider
    DELETE /api/v1/ai/providers/{id}       — Remove a provider
    POST   /api/v1/ai/providers/test       — Test a provider config (dry run)

Security:
    - ADMIN or SUPER_ADMIN role required
    - API keys encrypted at rest (Vault transit / Fernet)
    - Keys never returned in responses
"""

from __future__ import annotations
from server.core.rbac import Permission, require_permission

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from server.core.ai_providers import (
    AIProviderConfig,
    AIProviderFactory,
    AIProviderType,
    TenantAIProviderService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai/providers", tags=["ai-providers"])


# =============================================================================
# Request models
# =============================================================================


class CreateProviderRequest(BaseModel):
    provider_type: str = Field(
        ...,
        description="Provider type: openai, azure_openai, anthropic, google, ollama, openai_compat",
    )
    display_name: str = Field(..., min_length=1, max_length=128)
    api_key: str = Field(..., min_length=1, description="API key (encrypted at rest)")
    api_base_url: str = Field(
        default="",
        description="Base URL (required for azure_openai, ollama, openai_compat)",
    )
    model_name: str = Field(
        ..., min_length=1, description="Model name (e.g., gpt-4o, claude-3.5-sonnet)"
    )
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    azure_deployment: str = Field(
        default="", description="Azure deployment name (azure_openai only)"
    )
    azure_api_version: str = Field(default="2024-02-01")


class TestProviderRequest(BaseModel):
    provider_type: str
    api_key: str
    api_base_url: str = ""
    model_name: str
    azure_deployment: str = ""
    azure_api_version: str = "2024-02-01"


# =============================================================================
# Helpers
# =============================================================================


def _require_admin(request: Request):
    """Extract session and verify ADMIN/SUPER_ADMIN role."""
    from server.core.security import SessionManager

    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None, JSONResponse(
            status_code=401, content={"error": "Bearer token required"}
        )
    token = auth[7:].strip()
    session = SessionManager.validate_token(token)
    if not session:
        return None, JSONResponse(
            status_code=401, content={"error": "Invalid or expired token"}
        )
    # Check role
    from server.db_service import execute_query

    rows = execute_query(
        "SELECT role FROM users WHERE id = %s AND is_deleted = FALSE",
        (session.user_id,),
        tenant_id=session.tenant_id,
    )
    if not rows or rows[0]["role"] not in ("SUPER_ADMIN", "ADMIN"):
        return None, JSONResponse(
            status_code=403, content={"error": "ADMIN or SUPER_ADMIN role required"}
        )
    return session, None


# =============================================================================
# Endpoints
# =============================================================================


@router.get("")
@require_permission(Permission.CONFIG_READ)
async def list_providers(request: Request) -> JSONResponse:
    """List all AI provider configs for the current tenant (API keys masked)."""
    session, err = _require_admin(request)
    if err:
        return err
    providers = TenantAIProviderService.list_providers(session.tenant_id)
    return JSONResponse(status_code=200, content={"providers": providers})


@router.post("")
@require_permission(Permission.CONFIG_WRITE)
async def create_provider(
    request: Request, body: CreateProviderRequest
) -> JSONResponse:
    """Add a new AI provider for the current tenant."""
    session, err = _require_admin(request)
    if err:
        return err

    # Validate provider type
    try:
        AIProviderType(body.provider_type)
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={
                "error": f"Invalid provider_type: {body.provider_type}",
                "valid_types": [t.value for t in AIProviderType],
            },
        )

    config_id = TenantAIProviderService.create_provider(
        tenant_id=session.tenant_id,
        provider_type=body.provider_type,
        display_name=body.display_name,
        api_key=body.api_key,
        api_base_url=body.api_base_url,
        model_name=body.model_name,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
        azure_deployment=body.azure_deployment,
        azure_api_version=body.azure_api_version,
        actor_id=session.user_id,
    )

    return JSONResponse(
        status_code=201,
        content={"id": config_id, "message": "AI provider configured successfully"},
    )


@router.delete("/{config_id}")
@require_permission(Permission.CONFIG_WRITE)
async def delete_provider(request: Request, config_id: str) -> JSONResponse:
    """Remove an AI provider config."""
    session, err = _require_admin(request)
    if err:
        return err

    TenantAIProviderService.delete_provider(
        tenant_id=session.tenant_id,
        config_id=config_id,
        actor_id=session.user_id,
    )
    return JSONResponse(status_code=200, content={"message": "AI provider removed"})


@router.post("/test")
@require_permission(Permission.CONFIG_WRITE)
async def test_provider(request: Request, body: TestProviderRequest) -> JSONResponse:
    """Test an AI provider config with a simple prompt (dry run)."""
    session, err = _require_admin(request)
    if err:
        return err

    try:
        config = AIProviderConfig(
            id="test",
            tenant_id=session.tenant_id,
            provider_type=AIProviderType(body.provider_type),
            display_name="Test",
            api_key_encrypted="",
            api_base_url=body.api_base_url,
            model_name=body.model_name,
            azure_deployment=body.azure_deployment,
            azure_api_version=body.azure_api_version,
        )
        llm = AIProviderFactory.create_llm(
            config=config,
            decrypted_api_key=body.api_key,
            temperature=0.0,
            max_tokens=50,
        )
        result = llm.invoke("Say 'hello' in one word.")
        content = result if isinstance(result, str) else str(result)
        return JSONResponse(
            status_code=200,
            content={"success": True, "response": content[:200]},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(exc)},
        )
