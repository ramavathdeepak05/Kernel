"""
AI Service Router — S3

Endpoints:
  POST /v1/complete   — LLM completion with PII masking + budget enforcement
  POST /v1/embed      — Text embeddings
  GET  /v1/budget/{tenant_id} — Token budget status
  POST /v1/budget/{tenant_id}/reset — Admin: reset monthly usage
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from ai_service.models import (
    BudgetStatusResponse,
    CompleteRequest,
    CompleteResponse,
    EmbedRequest,
    EmbedResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _require_service_token(x_ai_token: str = Header(..., alias="X-AI-Token")) -> None:
    from ai_service.settings import settings
    import secrets
    if not secrets.compare_digest(x_ai_token, settings.ai_service_token):
        raise HTTPException(status_code=401, detail="Invalid AI service token")


# ---------------------------------------------------------------------------
# /v1/complete
# ---------------------------------------------------------------------------

@router.post(
    "/v1/complete",
    response_model=CompleteResponse,
    dependencies=[Depends(_require_service_token)],
    summary="LLM completion with PII masking and budget enforcement",
)
async def complete(req: CompleteRequest) -> CompleteResponse:
    from ai_service import budget as bgt
    from ai_service.pii_masker import PIIMasker, MaskingSession
    from ai_service.providers import ProviderRouter
    from ai_service.settings import settings
    import asyncio

    # 1. Budget pre-check (non-blocking on error)
    allowed, used, limit = bgt.check_budget(req.tenant_id, req.tenant_plan, req.max_tokens)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Monthly token budget exceeded",
                "used": used,
                "limit": limit,
                "plan": req.tenant_plan,
            },
        )

    # 2. PII masking
    masking_session = MaskingSession()
    prompt = req.prompt
    system_prompt = req.system_prompt
    pii_masked = False

    if req.mask_pii and settings.pii_masking_enabled:
        prompt = PIIMasker.mask(prompt, masking_session)
        if system_prompt:
            system_prompt = PIIMasker.mask(system_prompt, masking_session)
        pii_masked = bool(masking_session.token_map)

    # 3. Provider + model selection
    provider, model = ProviderRouter.select(
        task_class=req.task_class,
        tenant_plan=req.tenant_plan,
        feature_flags=req.feature_flags,
        explicit_provider=req.provider,
    )
    if req.model_override:
        model = req.model_override

    # 4. Inference (blocking I/O — run in thread pool)
    try:
        text = await asyncio.to_thread(
            provider.complete,
            model=model,
            prompt=prompt,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            system_prompt=system_prompt,
        )
    except Exception as exc:
        logger.exception("AI Service: inference failed provider=%s model=%s: %s", provider.name, model, exc)
        raise HTTPException(status_code=502, detail=f"Inference failed: {exc}")

    # 5. Unmask response (enterprise only, when requested)
    session_id = None
    if req.unmask_response and pii_masked:
        text = PIIMasker.unmask(text, masking_session)
        session_id = masking_session.session_id

    # 6. Token usage accounting (rough estimate: 1 token ≈ 4 chars)
    tokens_used = max(1, (len(prompt) + len(text)) // 4)
    bgt.record_usage(req.tenant_id, tokens_used)

    budget_remaining = max(0, limit - used - tokens_used)

    return CompleteResponse(
        text=text,
        provider=provider.name,
        model=model,
        tokens_used=tokens_used,
        budget_remaining=budget_remaining,
        pii_masked=pii_masked,
        session_id=session_id,
    )


# ---------------------------------------------------------------------------
# /v1/embed
# ---------------------------------------------------------------------------

@router.post(
    "/v1/embed",
    response_model=EmbedResponse,
    dependencies=[Depends(_require_service_token)],
    summary="Text embedding generation",
)
async def embed(req: EmbedRequest) -> EmbedResponse:
    from ai_service.providers import VpcOllamaProvider
    from ai_service.settings import settings
    import asyncio

    provider = VpcOllamaProvider()
    model = req.model or settings.ollama_embed_model

    try:
        embeddings = await asyncio.to_thread(
            provider.embed,
            texts=req.texts,
            model=model,
        )
    except Exception as exc:
        logger.exception("AI Service: embed failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc}")

    return EmbedResponse(embeddings=embeddings, model=model, provider="vpc_ollama")


# ---------------------------------------------------------------------------
# /v1/budget
# ---------------------------------------------------------------------------

@router.get(
    "/v1/budget/{tenant_id}",
    response_model=BudgetStatusResponse,
    dependencies=[Depends(_require_service_token)],
    summary="Get monthly token budget status for a tenant",
)
def get_budget(tenant_id: str, plan: str = "starter") -> BudgetStatusResponse:
    from ai_service import budget as bgt
    from ai_service.settings import settings
    from datetime import datetime, timezone

    used = bgt.get_usage(tenant_id)
    limit = bgt._plan_limit(plan)

    return BudgetStatusResponse(
        tenant_id=tenant_id,
        plan=plan,
        tokens_used=used,
        tokens_limit=limit,
        tokens_remaining=max(0, limit - used),
        period=datetime.now(timezone.utc).strftime("%Y-%m"),
    )


@router.post(
    "/v1/budget/{tenant_id}/reset",
    dependencies=[Depends(_require_service_token)],
    summary="Admin: reset monthly token usage for a tenant",
)
def reset_budget(tenant_id: str) -> dict:
    from ai_service import budget as bgt
    bgt.reset_usage(tenant_id)
    return {"tenant_id": tenant_id, "reset": True}
