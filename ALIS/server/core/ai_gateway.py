"""
ALIS AI Gateway - E03-S01

MODULE: Platform Core (E03 - AI Gateway & Agents)
LAYER: Layer 2 (Agentic Decisions)
ENTITY: AIGateway

This module implements the centralized AI Gateway service.
All AI model invocations MUST go through this gateway.

Must Align With:
- Blueprint B — AI Agent Architecture
- "Agents draft, rules decide"
- "AI is read-only with respect to state"
- "No cloud LLM usage"

Acceptance Criteria (E03-S01):
- [x] Single API surface for AI calls
- [x] No direct model invocation elsewhere in codebase
- [x] Request/response fully logged (metadata only)
- [x] RBAC-protected access
- [x] Tenant-aware invocation
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from functools import wraps
from uuid import uuid4
from datetime import datetime
import logging

from langchain_ollama import OllamaLLM
from langchain_core.language_models.base import BaseLanguageModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

from .rbac import Role, Permission, verify_access, AccessResult
from .audit import AuditLog, AuditAction
from .config import ConfigRegistry
from .exceptions import PermissionDeniedError


logger = logging.getLogger(__name__)


# --- Gateway Context ---

@dataclass
class AIGatewayContext:
    """
    Context for AI Gateway invocations.

    This context is passed to every AI call and used for:
    - RBAC verification
    - Audit logging
    - Tenant isolation
    """
    actor_id: str
    actor_type: str = "system"  # human, ai_agent, system
    actor_role: Role = Role.SYSTEM

    # Tenant/Organization context
    org_id: Optional[str] = None

    # Module/Wizard context
    module: Optional[str] = None  # M1, M2, etc.
    wizard: Optional[str] = None

    # Request tracing
    request_id: str = field(default_factory=lambda: str(uuid4()))
    correlation_id: Optional[str] = None

    # Additional metadata
    metadata: Optional[Dict[str, Any]] = None


# --- Gateway Invocation Result ---

@dataclass
class AIInvocationResult:
    """Result of an AI Gateway invocation."""
    success: bool
    content: Optional[str] = None
    error: Optional[str] = None
    request_id: str = ""
    model: str = ""
    latency_ms: float = 0.0
    token_count: Optional[int] = None


# --- Instrumented LLM Wrapper ---

class InstrumentedLLM:
    """
    Wrapper around LangChain LLM that enforces RBAC and logs invocations.

    This wrapper intercepts all LLM calls to:
    1. Verify RBAC permissions before invocation
    2. Log invocation metadata to audit log
    3. Measure latency and track usage

    The wrapper is transparent to LangGraph - it can be used as a drop-in
    replacement for any LangChain LLM.
    """

    def __init__(
        self,
        llm: BaseLanguageModel,
        context: AIGatewayContext,
        model_name: str
    ):
        self._llm = llm
        self._context = context
        self._model_name = model_name

    def invoke(self, input_text: str, **kwargs) -> AIInvocationResult:
        """
        Invoke the LLM with RBAC checking and audit logging.

        Args:
            input_text: The prompt to send to the LLM
            **kwargs: Additional arguments passed to the LLM

        Returns:
            AIInvocationResult with the response or error
        """
        request_id = str(uuid4())
        start_time = datetime.utcnow()

        # --- Step 0: Lockdown Check (E00-S05) ---
        # During lockdown ALL AI invocations are blocked regardless of role.
        from .lockdown import LockdownManager
        LockdownManager.assert_ai_allowed(actor_id=self._context.actor_id)

        # --- Step 1: RBAC Check ---
        access_result = verify_access(
            actor_role=self._context.actor_role,
            permission=Permission.AI_INVOKE,
            context={"action": "invoke", "module": self._context.module}
        )

        if not access_result.allowed:
            # Log denied access
            AuditLog.log(
                action=AuditAction.ACCESS_DENIED,
                actor_id=self._context.actor_id,
                actor_type=self._context.actor_type,
                actor_role=self._context.actor_role.value if self._context.actor_role else None,
                entity_type="ai_gateway",
                entity_id=request_id,
                success=False,
                failure_reason=access_result.reason,
                org_id=self._context.org_id,
                module=self._context.module,
                wizard=self._context.wizard,
                metadata={
                    "permission": Permission.AI_INVOKE.value,
                    "violations": access_result.context_violations
                }
            )
            raise PermissionDeniedError(
                message=f"AI Gateway access denied: {access_result.reason}",
                details={"violations": access_result.context_violations}
            )

        # --- Step 1.5: E00-S01 — AI Context Scrubbing ---
        # Mask sensitive fields in context metadata before LLM sees them.
        # The input_text prompt itself is passed through, but any structured
        # context data attached via metadata is scrubbed.
        _sensitive_fields_scrubbed = False
        if self._context.metadata:
            from .data_classification import DataMasker
            entity_type = self._context.metadata.get("entity_type", "")
            if entity_type:
                self._context.metadata = DataMasker.mask_for_ai_context(
                    self._context.metadata, entity_type
                )
                _sensitive_fields_scrubbed = True

        # --- Step 2: LLM Invocation ---
        try:
            response = self._llm.invoke(input_text, **kwargs)
            content = response if isinstance(response, str) else str(response)
            success = True
            error = None
        except Exception as e:
            logger.exception(f"LLM invocation failed: {e}")
            content = None
            success = False
            error = str(e)

        # --- Step 3: Calculate Metrics ---
        end_time = datetime.utcnow()
        latency_ms = (end_time - start_time).total_seconds() * 1000

        # --- Step 4: Audit Log (Metadata Only - No PII/Prompt Content) ---
        AuditLog.log(
            action=AuditAction.AI_INVOCATION,
            actor_id=self._context.actor_id,
            actor_type=self._context.actor_type,
            actor_role=self._context.actor_role.value if self._context.actor_role else None,
            entity_type="ai_gateway",
            entity_id=request_id,
            success=success,
            failure_reason=error,
            org_id=self._context.org_id,
            module=self._context.module,
            wizard=self._context.wizard,
            metadata={
                "model": self._model_name,
                "latency_ms": latency_ms,
                "prompt_length": len(input_text),
                "response_length": len(content) if content else 0,
                "correlation_id": self._context.correlation_id
            }
        )

        return AIInvocationResult(
            success=success,
            content=content,
            error=error,
            request_id=request_id,
            model=self._model_name,
            latency_ms=latency_ms
        )

    def __getattr__(self, name):
        """Proxy all other attributes to the underlying LLM."""
        return getattr(self._llm, name)


# --- AI Gateway Service ---

class AIGateway:
    """
    Centralized AI Gateway for ALIS.

    This is the ONLY authorized entry point for AI model invocations.
    Direct instantiation of Ollama or other LLM classes is forbidden.

    Usage:
        context = AIGatewayContext(actor_id="agent-123", actor_role=Role.AI_AGENT)
        llm = AIGateway.get_llm(context)
        result = llm.invoke("Analyze this document...")

    Hard Constraints (E03):
    - Local / self-hosted LLMs only (Ollama)
    - No OpenAI, Anthropic, or external cloud inference
    - All invocations are logged
    - RBAC is enforced
    """

    # Forbidden imports (for static analysis / linting)
    _FORBIDDEN_IMPORTS = [
        "openai",
        "anthropic",
        "langchain_openai",
        "langchain_anthropic",
    ]

    @classmethod
    def get_llm(
        cls,
        context: AIGatewayContext,
        model_name: Optional[str] = None,
        temperature: float = 0.0
    ) -> InstrumentedLLM:
        """
        Get an instrumented LLM instance for AI operations.

        This is the ONLY way to obtain an LLM instance in ALIS.

        Args:
            context: AIGatewayContext with actor and tenant information
            model_name: Optional model override (defaults to config)
            temperature: LLM temperature (default 0.0 for deterministic)

        Returns:
            InstrumentedLLM that can be used with LangGraph

        Raises:
            PermissionDeniedError: If actor lacks AI_INVOKE permission
        """
        # Get config values
        base_url = ConfigRegistry.get(
            ConfigRegistry.LLM_BASE_URL,
            "http://localhost:11434"
        )
        default_model = ConfigRegistry.get(
            ConfigRegistry.LLM_MODEL_NAME,
            "llama3"
        )
        model = model_name or default_model

        # Create Ollama LLM (Local only - NO CLOUD)
        llm = OllamaLLM(
            base_url=base_url,
            model=model,
            temperature=temperature
        )

        # Wrap with instrumentation
        return InstrumentedLLM(
            llm=llm,
            context=context,
            model_name=model
        )

    @classmethod
    def check_access(cls, context: AIGatewayContext) -> AccessResult:
        """
        Pre-check if a context has permission to use AI Gateway.

        Useful for early validation before building complex agent graphs.
        """
        return verify_access(
            actor_role=context.actor_role,
            permission=Permission.AI_INVOKE,
            context={"action": "invoke", "module": context.module}
        )

    @classmethod
    def validate_no_cloud_imports(cls) -> List[str]:
        """
        Static validation helper to detect forbidden cloud LLM imports.

        Returns list of any forbidden imports found.
        This is intended for use in CI/CD pipelines.
        """
        import sys
        violations = []
        for forbidden in cls._FORBIDDEN_IMPORTS:
            if forbidden in sys.modules:
                violations.append(f"Forbidden import detected: {forbidden}")
        return violations
