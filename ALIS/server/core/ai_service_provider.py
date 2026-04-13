"""
AI Service Provider — S3

LangChain-compatible LLM wrapper that proxies inference to the AI Service
microservice (ai_service/). Implements the same interface as OllamaLLM so
it can be used transparently as a drop-in inside InstrumentedLLM.

When AI_SERVICE_URL is set in settings, AIGateway.get_llm() returns one of
these instead of OllamaLLM or ChatOpenAI.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)


class AIServiceLLM:
    """
    Minimal LangChain-compatible LLM interface that delegates to the AI Service.

    Implements `.invoke(prompt)` and `.stream(prompt)` so it can be used
    as a drop-in replacement for OllamaLLM / ChatOpenAI inside InstrumentedLLM.

    This is NOT a full LangChain BaseLanguageModel subclass — it only
    implements the methods that InstrumentedLLM actually calls.
    """

    def __init__(
        self,
        ai_service_url: str,
        ai_service_token: str,
        tenant_id: str,
        task_class: str = "extraction",
        temperature: float = 0.0,
        max_tokens: int = 1024,
        model_override: str | None = None,
        tenant_plan: str = "starter",
        feature_flags: dict | None = None,
        mask_pii: bool = True,
    ) -> None:
        self._url = ai_service_url.rstrip("/")
        self._token = ai_service_token
        self._tenant_id = tenant_id
        self._task_class = task_class
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._model_override = model_override
        self._tenant_plan = tenant_plan
        self._feature_flags = feature_flags or {}
        self._mask_pii = mask_pii

    def _build_payload(self, prompt: str, system_prompt: str | None = None) -> dict:
        payload: dict = {
            "tenant_id": self._tenant_id,
            "tenant_plan": self._tenant_plan,
            "feature_flags": self._feature_flags,
            "prompt": prompt,
            "task_class": self._task_class,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "mask_pii": self._mask_pii,
        }
        if self._model_override:
            payload["model_override"] = self._model_override
        if system_prompt:
            payload["system_prompt"] = system_prompt
        return payload

    def invoke(self, prompt: Any, **kwargs) -> str:
        """
        Synchronous completion.

        `prompt` may be a string or a list of LangChain messages — we
        handle both forms.
        """
        import httpx

        text = self._extract_text(prompt)
        system_prompt = kwargs.get("system_prompt")

        try:
            resp = httpx.post(
                f"{self._url}/v1/complete",
                json=self._build_payload(text, system_prompt=system_prompt),
                headers={"X-AI-Token": self._token},
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json().get("text", "")
        except Exception as exc:
            logger.exception("AIServiceLLM.invoke failed: %s", exc)
            raise RuntimeError(f"AI Service request failed: {exc}") from exc

    def stream(self, prompt: Any, **kwargs) -> Iterator[str]:
        """
        Streaming is not yet supported — falls back to full completion and
        yields the entire response as one chunk. Agents that need streaming
        should call invoke() directly or wait for S3 streaming support.
        """
        yield self.invoke(prompt, **kwargs)

    @staticmethod
    def _extract_text(prompt: Any) -> str:
        """Extract plain string from LangChain message list or raw string."""
        if isinstance(prompt, str):
            return prompt
        if isinstance(prompt, list):
            # LangChain message format: list of HumanMessage / AIMessage / etc.
            parts = []
            for msg in prompt:
                if hasattr(msg, "content"):
                    content = msg.content
                    if isinstance(content, str):
                        parts.append(content)
                    elif isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get("type") == "text":
                                parts.append(block["text"])
                            elif isinstance(block, str):
                                parts.append(block)
                elif isinstance(msg, str):
                    parts.append(msg)
            return "\n".join(parts)
        return str(prompt)

    # -------------------------------------------------------------------------
    # LangChain compatibility shims
    # -------------------------------------------------------------------------

    def __call__(self, prompt: Any, **kwargs) -> str:
        """Allow usage as a callable (some older LangChain code does llm(prompt))."""
        return self.invoke(prompt, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "alis_ai_service"
