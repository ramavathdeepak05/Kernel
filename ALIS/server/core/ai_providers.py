"""
ALIS AI Provider Registry — Per-tenant AI API extensibility

Enables institutions (tenants) to bring their own AI API keys and providers.
Each tenant can configure one or more AI providers via the admin API.
The AIGateway resolves the correct provider at invocation time based on:

1. Tenant-level provider config (if set → use tenant's own API)
2. Platform-level external LLM config (if set → use global API)
3. Local Ollama (default fallback)

Supported providers:
- openai          — OpenAI API (gpt-4o, gpt-4-turbo, etc.)
- azure_openai    — Azure OpenAI Service (requires deployment name)
- anthropic       — Anthropic API (claude-3.5-sonnet, etc.)
- google          — Google AI (gemini-1.5-pro, etc.)
- ollama          — Self-hosted Ollama instance (custom URL)
- openai_compat   — Any OpenAI-compatible API (NVIDIA NIM, Together, Groq, etc.)

Security:
- API keys are encrypted at rest via Vault (transit engine) or Fernet
- Keys are NEVER returned in API responses (masked to last 4 chars)
- All provider invocations are audit-logged with tenant context
- Provider config changes require ADMIN or SUPER_ADMIN role
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from langchain_core.language_models.base import BaseLanguageModel

logger = logging.getLogger(__name__)


# =============================================================================
# Provider Types
# =============================================================================

class AIProviderType(str, Enum):
    """Supported AI provider backends."""
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"
    OPENAI_COMPAT = "openai_compat"


# =============================================================================
# Provider Config
# =============================================================================

@dataclass
class AIProviderConfig:
    """Per-tenant AI provider configuration."""
    id: str
    tenant_id: str
    provider_type: AIProviderType
    display_name: str
    api_key_encrypted: str          # Encrypted — never exposed in API responses
    api_base_url: str               # e.g., https://api.openai.com/v1
    model_name: str                 # e.g., gpt-4o
    max_tokens: int = 2048
    temperature: float = 0.2
    is_active: bool = True
    # Azure-specific
    azure_deployment: str = ""
    azure_api_version: str = "2024-02-01"
    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# =============================================================================
# Provider Factory — creates LangChain LLM from config
# =============================================================================

class AIProviderFactory:
    """
    Creates LangChain BaseLanguageModel instances from provider configs.

    Each provider type has a specific factory method that constructs
    the appropriate LangChain wrapper.
    """

    @classmethod
    def create_llm(
        cls,
        config: AIProviderConfig,
        decrypted_api_key: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> BaseLanguageModel:
        """Create an LLM instance from a provider config."""
        _temp = temperature if temperature is not None else config.temperature
        _max = max_tokens if max_tokens is not None else config.max_tokens

        factory_map = {
            AIProviderType.OPENAI: cls._create_openai,
            AIProviderType.AZURE_OPENAI: cls._create_azure_openai,
            AIProviderType.ANTHROPIC: cls._create_anthropic,
            AIProviderType.GOOGLE: cls._create_google,
            AIProviderType.OLLAMA: cls._create_ollama,
            AIProviderType.OPENAI_COMPAT: cls._create_openai_compat,
        }

        factory = factory_map.get(config.provider_type)
        if not factory:
            raise ValueError(f"Unsupported AI provider type: {config.provider_type}")

        return factory(config, decrypted_api_key, _temp, _max)

    @staticmethod
    def _create_openai(config: AIProviderConfig, api_key: str, temp: float, max_tokens: int) -> BaseLanguageModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            api_key=api_key,
            model=config.model_name,
            temperature=temp,
            max_tokens=max_tokens,
            streaming=False,
        )

    @staticmethod
    def _create_azure_openai(config: AIProviderConfig, api_key: str, temp: float, max_tokens: int) -> BaseLanguageModel:
        from langchain_openai import AzureChatOpenAI
        return AzureChatOpenAI(
            api_key=api_key,
            azure_endpoint=config.api_base_url,
            azure_deployment=config.azure_deployment,
            api_version=config.azure_api_version,
            temperature=temp,
            max_tokens=max_tokens,
            streaming=False,
        )

    @staticmethod
    def _create_anthropic(config: AIProviderConfig, api_key: str, temp: float, max_tokens: int) -> BaseLanguageModel:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            api_key=api_key,
            model=config.model_name,
            temperature=temp,
            max_tokens=max_tokens,
        )

    @staticmethod
    def _create_google(config: AIProviderConfig, api_key: str, temp: float, max_tokens: int) -> BaseLanguageModel:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            google_api_key=api_key,
            model=config.model_name,
            temperature=temp,
            max_output_tokens=max_tokens,
        )

    @staticmethod
    def _create_ollama(config: AIProviderConfig, _api_key: str, temp: float, _max_tokens: int) -> BaseLanguageModel:
        from langchain_ollama import OllamaLLM
        return OllamaLLM(
            base_url=config.api_base_url,
            model=config.model_name,
            temperature=temp,
        )

    @staticmethod
    def _create_openai_compat(config: AIProviderConfig, api_key: str, temp: float, max_tokens: int) -> BaseLanguageModel:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            base_url=config.api_base_url,
            api_key=api_key,
            model=config.model_name,
            temperature=temp,
            max_tokens=max_tokens,
            streaming=False,
        )


# =============================================================================
# Tenant Provider Service — CRUD + resolution
# =============================================================================

class TenantAIProviderService:
    """
    Manages per-tenant AI provider configurations.

    CRUD operations store configs in the `ai_provider_configs` table.
    API keys are encrypted before storage using Vault transit or Fernet.
    """

    @classmethod
    def get_active_provider(cls, tenant_id: str) -> Optional[AIProviderConfig]:
        """Get the active AI provider config for a tenant. Returns None if using platform default."""
        from server.db_service import execute_query
        rows = execute_query(
            "SELECT * FROM ai_provider_configs WHERE tenant_id = %s AND is_active = TRUE "
            "ORDER BY updated_at DESC LIMIT 1",
            (tenant_id,),
            tenant_id=tenant_id,
        )
        if not rows:
            return None
        row = rows[0]
        return AIProviderConfig(
            id=str(row["id"]),
            tenant_id=str(row["tenant_id"]),
            provider_type=AIProviderType(row["provider_type"]),
            display_name=row.get("display_name", ""),
            api_key_encrypted=row.get("api_key_encrypted", ""),
            api_base_url=row.get("api_base_url", ""),
            model_name=row.get("model_name", ""),
            max_tokens=row.get("max_tokens", 2048),
            temperature=float(row.get("temperature", 0.2)),
            is_active=row.get("is_active", True),
            azure_deployment=row.get("azure_deployment", ""),
            azure_api_version=row.get("azure_api_version", "2024-02-01"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    @classmethod
    def list_providers(cls, tenant_id: str) -> List[Dict[str, Any]]:
        """List all AI provider configs for a tenant (API keys masked)."""
        from server.db_service import execute_query
        rows = execute_query(
            "SELECT id, tenant_id, provider_type, display_name, api_base_url, model_name, "
            "max_tokens, temperature, is_active, azure_deployment, azure_api_version, "
            "created_at, updated_at FROM ai_provider_configs WHERE tenant_id = %s "
            "ORDER BY created_at DESC",
            (tenant_id,),
            tenant_id=tenant_id,
        )
        return [dict(r) for r in rows]

    @classmethod
    def create_provider(
        cls,
        tenant_id: str,
        provider_type: str,
        display_name: str,
        api_key: str,
        api_base_url: str,
        model_name: str,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        azure_deployment: str = "",
        azure_api_version: str = "2024-02-01",
        actor_id: str = "system",
    ) -> str:
        """Create a new AI provider config. Returns the config ID."""
        from server.db_service import execute_transaction
        from server.core.audit import AuditLog, AuditAction

        # Encrypt the API key before storage
        encrypted_key = cls._encrypt_key(api_key, tenant_id)
        config_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # Deactivate any existing active provider for this tenant
        execute_transaction([
            (
                "UPDATE ai_provider_configs SET is_active = FALSE, updated_at = %s "
                "WHERE tenant_id = %s AND is_active = TRUE",
                (now, tenant_id),
            ),
            (
                "INSERT INTO ai_provider_configs "
                "(id, tenant_id, provider_type, display_name, api_key_encrypted, "
                "api_base_url, model_name, max_tokens, temperature, is_active, "
                "azure_deployment, azure_api_version, created_at, updated_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s, %s)",
                (
                    config_id, tenant_id, provider_type, display_name, encrypted_key,
                    api_base_url, model_name, max_tokens, temperature,
                    azure_deployment, azure_api_version, now, now,
                ),
            ),
        ], tenant_id=tenant_id)

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_role="admin",
            entity_type="ai_provider_config",
            entity_id=config_id,
            tenant_id=tenant_id,
            metadata={
                "provider_type": provider_type,
                "model_name": model_name,
                "api_base_url": api_base_url,
            },
        )
        return config_id

    @classmethod
    def delete_provider(cls, tenant_id: str, config_id: str, actor_id: str = "system") -> bool:
        """Delete an AI provider config."""
        from server.db_service import execute_transaction
        from server.core.audit import AuditLog, AuditAction

        execute_transaction([
            (
                "DELETE FROM ai_provider_configs WHERE id = %s AND tenant_id = %s",
                (config_id, tenant_id),
            ),
        ], tenant_id=tenant_id)

        AuditLog.log(
            action=AuditAction.DELETE,
            actor_id=actor_id,
            actor_role="admin",
            entity_type="ai_provider_config",
            entity_id=config_id,
            tenant_id=tenant_id,
        )
        return True

    @classmethod
    def decrypt_key(cls, config: AIProviderConfig) -> str:
        """Decrypt the API key for an invocation. Never expose this in API responses."""
        return cls._decrypt_key(config.api_key_encrypted, config.tenant_id)

    # ------------------------------------------------------------------
    # Encryption helpers
    # ------------------------------------------------------------------

    @classmethod
    def _encrypt_key(cls, plaintext: str, tenant_id: str) -> str:
        """Encrypt API key using Vault transit or Fernet fallback."""
        try:
            from server.core.vault_client import get_vault_client
            vault = get_vault_client()
            if vault._is_available():
                return vault.encrypt_data(plaintext, context=f"ai_provider:{tenant_id}")
        except Exception:
            pass
        # Fernet fallback
        from server.core.settings import settings
        from cryptography.fernet import Fernet
        import base64
        import hashlib
        key = base64.urlsafe_b64encode(hashlib.sha256(
            (settings.app_secret_key + tenant_id).encode()
        ).digest())
        return Fernet(key).encrypt(plaintext.encode()).decode()

    @classmethod
    def _decrypt_key(cls, ciphertext: str, tenant_id: str) -> str:
        """Decrypt API key."""
        try:
            from server.core.vault_client import get_vault_client
            vault = get_vault_client()
            if vault._is_available():
                return vault.decrypt_data(ciphertext, context=f"ai_provider:{tenant_id}")
        except Exception:
            pass
        from server.core.settings import settings
        from cryptography.fernet import Fernet
        import base64
        import hashlib
        key = base64.urlsafe_b64encode(hashlib.sha256(
            (settings.app_secret_key + tenant_id).encode()
        ).digest())
        return Fernet(key).decrypt(ciphertext.encode()).decode()


# =============================================================================
# resolve_llm_for_tenant — called by AIGateway.get_llm()
# =============================================================================

def resolve_llm_for_tenant(
    tenant_id: str,
    capability: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Optional[BaseLanguageModel]:
    """
    Resolve a tenant-specific LLM if configured, otherwise return None
    (caller falls back to platform default Ollama / external LLM).

    This is the integration point called from AIGateway.get_llm().
    """
    config = TenantAIProviderService.get_active_provider(tenant_id)
    if not config:
        return None

    try:
        api_key = TenantAIProviderService.decrypt_key(config)
        llm = AIProviderFactory.create_llm(
            config=config,
            decrypted_api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        logger.info(
            "AI provider resolved for tenant=%s: %s/%s",
            tenant_id, config.provider_type.value, config.model_name,
        )
        return llm
    except Exception as exc:
        logger.warning(
            "Failed to create tenant AI provider for tenant=%s: %s — falling back to platform default",
            tenant_id, exc,
        )
        return None
