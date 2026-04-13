"""
ALIS LLM Model Registry — E03-S02: Local LLM Runtime Integration

MODULE: Platform Core (E03 — AI Gateway & Agents)
LAYER: Layer 2 (Agentic Decisions)
ENTITY: LLMModel

This module manages the lifecycle of locally-hosted LLM models.
It provides registration, lookup, and hot-swap capabilities backed
by the `llm_model_registry` PostgreSQL table.

Hard Rules (E03):
- Local / self-hosted LLMs only (Ollama)
- No external network calls
- No telemetry leaks

Acceptance Criteria (E03-S02):
- [x] Model registry (model name, version, capability)
- [x] Hot-swap support (model upgrades without refactor)
- [x] Deterministic configuration
- [x] Resource limits enforced (num_ctx, num_gpu, num_thread, keep_alive, timeout
      stored in config JSONB and forwarded to OllamaLLM at invocation time)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from pydantic import Field as PydanticField

from .audit import AuditAction, AuditLog

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS
# =============================================================================


class ModelCapability(str, Enum):
    """
    AI role capabilities per ALIS Layer 2 Decision Declaration.

    Every wizard must declare its AI Role as one of these.
    The Model Registry maps each capability to a specific model.
    """

    INFER = "Infer"
    SCORE = "Score"
    PLAN = "Plan"
    EXECUTE = "Execute"


class ModelStatus(str, Enum):
    """Status of a model entry in the registry."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DEPRECATED = "DEPRECATED"


# =============================================================================
# PYDANTIC SCHEMAS (API I/O)
# =============================================================================


class LLMModelRead(BaseModel):
    """Read-only representation of a registered LLM model."""

    id: str
    tenant_id: str
    name: str
    version: str
    capability: str
    is_active: bool
    config: dict[str, Any] = {}
    created_at: datetime | None = None
    updated_at: datetime | None = None


class LLMModelRegister(BaseModel):
    """Schema for registering a new model in the registry."""

    name: str = PydanticField(..., min_length=1, max_length=100)
    version: str = PydanticField(..., min_length=1, max_length=50)
    capability: ModelCapability
    is_active: bool = False
    config: dict[str, Any] = PydanticField(default_factory=lambda: {"temperature": 0.0})


# =============================================================================
# RESOLVED MODEL (Internal dataclass used by AIGateway)
# =============================================================================


@dataclass
class ResolvedModel:
    """
    A resolved model ready for use by the AI Gateway.

    Contains all information needed to instantiate an OllamaLLM.
    """

    id: str
    name: str
    version: str
    capability: str
    ollama_model_tag: str  # e.g. "qwen:1.5-q8"
    config: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# MODEL REGISTRY SERVICE
# =============================================================================


class ModelRegistry:
    """
    LLM Model Registry backed by PostgreSQL.

    Provides:
    - Registration of new models
    - Lookup of active model by capability + tenant
    - Hot-swap: activate a new model for a capability (deactivates old one)

    All mutations are audited.
    """

    @staticmethod
    def _format_ollama_tag(name: str, version: str) -> str:
        """
        Format the Ollama model tag from name and version.

        Examples:
            ("qwen", "1.5-q8")  -> "qwen:1.5-q8"
            ("llama3", "8b")    -> "llama3:8b"
        """
        return f"{name}:{version}"

    # -----------------------------------------------------------------
    # REGISTER
    # -----------------------------------------------------------------
    @classmethod
    def register_model(
        cls,
        tenant_id: str,
        model: LLMModelRegister,
        registered_by: str,
    ) -> str:
        """
        Register a new model in the registry.

        If `model.is_active` is True, any existing active model for the
        same capability+tenant is deactivated first (hot-swap).

        Args:
            tenant_id: Tenant/org scope
            model: Registration payload
            registered_by: Actor who initiated registration

        Returns:
            The newly created model ID.
        """
        from ..db_service import execute_transaction

        model_id = str(uuid4())
        now = datetime.now(timezone.utc)

        queries = []

        # If activating, deactivate any current active model for this
        # capability first (atomic swap inside the same transaction).
        if model.is_active:
            deactivate_sql = (
                "UPDATE llm_model_registry "
                "SET is_active = FALSE, updated_at = %s "
                "WHERE tenant_id = %s AND capability = %s AND is_active = TRUE",
                (now, tenant_id, model.capability.value),
            )
            queries.append(deactivate_sql)

        insert_sql = (
            "INSERT INTO llm_model_registry "
            "(id, tenant_id, name, version, capability, is_active, config, "
            "created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                model_id,
                tenant_id,
                model.name,
                model.version,
                model.capability.value,
                model.is_active,
                __import__("json").dumps(model.config),
                now,
                now,
            ),
        )
        queries.append(insert_sql)

        execute_transaction(queries, tenant_id=tenant_id)

        # Audit
        AuditLog.log(
            action=AuditAction.CONFIG_CHANGE,
            actor_id=registered_by,
            actor_type="human",
            entity_type="llm_model_registry",
            entity_id=model_id,
            action_detail=f"Registered model {model.name}:{model.version} "
            f"for capability {model.capability.value}",
            org_id=tenant_id,
            metadata={
                "name": model.name,
                "version": model.version,
                "capability": model.capability.value,
                "is_active": model.is_active,
            },
        )

        logger.info(
            f"E03-S02: Model registered — id={model_id} "
            f"name={model.name}:{model.version} "
            f"capability={model.capability.value} active={model.is_active}"
        )
        return model_id

    # -----------------------------------------------------------------
    # LOOKUP
    # -----------------------------------------------------------------
    @classmethod
    def get_active_model(
        cls,
        capability: str,
        tenant_id: str,
    ) -> ResolvedModel | None:
        """
        Retrieve the currently active model for a capability + tenant.

        This is the primary lookup used by AIGateway.get_llm().
        Returns None if no active model is found.

        Args:
            capability: One of Infer, Score, Plan, Execute
            tenant_id: Tenant/org scope

        Returns:
            ResolvedModel or None
        """
        from ..db_service import execute_query

        rows = execute_query(
            "SELECT id, name, version, capability, config "
            "FROM llm_model_registry "
            "WHERE capability = %s AND is_active = TRUE "
            "LIMIT 1",
            (capability,),
            tenant_id=tenant_id,
        )

        if not rows:
            logger.warning(
                f"E03-S02: No active model for capability={capability} "
                f"tenant={tenant_id}"
            )
            return None

        row = rows[0]
        config = row["config"] if isinstance(row["config"], dict) else {}

        return ResolvedModel(
            id=row["id"],
            name=row["name"],
            version=row["version"],
            capability=row["capability"],
            ollama_model_tag=cls._format_ollama_tag(row["name"], row["version"]),
            config=config,
        )

    # -----------------------------------------------------------------
    # HOT-SWAP
    # -----------------------------------------------------------------
    @classmethod
    def swap_active_model(
        cls,
        capability: str,
        new_model_id: str,
        tenant_id: str,
        swapped_by: str,
    ) -> None:
        """
        Activate a specific model for a capability, deactivating
        whichever model was active before.

        This is the hot-swap operation — no code changes needed, the
        next AIGateway.get_llm() call picks up the new model.

        Args:
            capability: Target capability
            new_model_id: ID of the model to activate
            tenant_id: Tenant/org scope
            swapped_by: Actor performing the swap
        """
        from ..db_service import execute_transaction

        now = datetime.now(timezone.utc)

        queries = [
            # Step 1: Deactivate current active for this capability
            (
                "UPDATE llm_model_registry "
                "SET is_active = FALSE, updated_at = %s "
                "WHERE tenant_id = %s AND capability = %s AND is_active = TRUE",
                (now, tenant_id, capability),
            ),
            # Step 2: Activate the target model
            (
                "UPDATE llm_model_registry "
                "SET is_active = TRUE, updated_at = %s "
                "WHERE id = %s AND tenant_id = %s",
                (now, new_model_id, tenant_id),
            ),
        ]

        execute_transaction(queries, tenant_id=tenant_id)

        AuditLog.log(
            action=AuditAction.CONFIG_CHANGE,
            actor_id=swapped_by,
            actor_type="human",
            entity_type="llm_model_registry",
            entity_id=new_model_id,
            action_detail=f"Hot-swapped active model for capability {capability}",
            org_id=tenant_id,
            metadata={
                "capability": capability,
                "new_model_id": new_model_id,
            },
        )

        logger.info(
            f"E03-S02: Hot-swap complete — capability={capability} "
            f"new_model_id={new_model_id}"
        )

    # -----------------------------------------------------------------
    # LIST
    # -----------------------------------------------------------------
    @classmethod
    def list_models(
        cls,
        tenant_id: str,
        capability: str | None = None,
    ) -> list[LLMModelRead]:
        """
        List all registered models for a tenant, optionally filtered
        by capability.
        """
        from ..db_service import execute_query

        if capability:
            rows = execute_query(
                "SELECT id, tenant_id, name, version, capability, "
                "is_active, config, created_at, updated_at "
                "FROM llm_model_registry "
                "WHERE capability = %s "
                "ORDER BY created_at DESC",
                (capability,),
                tenant_id=tenant_id,
            )
        else:
            rows = execute_query(
                "SELECT id, tenant_id, name, version, capability, "
                "is_active, config, created_at, updated_at "
                "FROM llm_model_registry "
                "ORDER BY created_at DESC",
                tenant_id=tenant_id,
            )

        return [LLMModelRead(**row) for row in rows]
