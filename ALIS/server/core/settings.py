"""
ALIS Infrastructure Settings — P0-S06

Single source of truth for all environment/infrastructure configuration.
Business policy parameters live in ConfigRegistry (config.py).
This file owns: DB, Redis, MinIO, Ollama, SMTP, JWT, Razorpay, CORS.

Usage:
    from server.core.settings import settings
    settings.db_url
    settings.ollama_base_url

Loaded from environment variables. In production, set via .env file
mounted into the Docker container. Never commit .env to git.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),   # supports running from ALIS/ or repo root
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_env: str = Field(default="development", description="development | staging | production")
    app_secret_key: str = Field(default="change-me-in-production-use-32-char-min")
    app_debug: bool = Field(default=False)
    allowed_origins: List[str] = Field(default=["http://localhost:5173", "http://localhost:3000"])

    # -------------------------------------------------------------------------
    # Database (PostgreSQL)
    # -------------------------------------------------------------------------
    db_host: str = Field(default="localhost")
    db_port: int = Field(default=5432)
    db_name: str = Field(default="alis_db")
    db_user: str = Field(default="postgres")
    db_password: str = Field(default="postgres")
    db_pool_min: int = Field(default=5)
    db_pool_max: int = Field(default=80)     # PgBouncer → Postgres; was 20
    pgbouncer_enabled: bool = Field(default=False, description="Route DB connections through PgBouncer")
    pgbouncer_host: str = Field(default="localhost", description="PgBouncer host (set to 'pgbouncer' in docker-compose)")
    pgbouncer_port: int = Field(default=6432, description="PgBouncer port (5432 inside docker network)")

    @property
    def db_url(self) -> str:
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def db_url_async(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    # -------------------------------------------------------------------------
    # Redis (Celery broker + result backend)
    # -------------------------------------------------------------------------
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)
    redis_password: str = Field(default="")

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # -------------------------------------------------------------------------
    # Celery
    # -------------------------------------------------------------------------
    celery_timezone: str = Field(default="Asia/Kolkata")
    celery_task_serializer: str = Field(default="json")
    celery_result_expires: int = Field(default=3600)  # seconds

    # -------------------------------------------------------------------------
    # MinIO (File Storage)
    # -------------------------------------------------------------------------
    minio_endpoint: str = Field(default="localhost:9000")
    minio_access_key: str = Field(default="minioadmin")
    minio_secret_key: str = Field(default="minioadmin")
    minio_bucket: str = Field(default="alis-files")
    minio_secure: bool = Field(default=False)  # True in production with TLS

    # -------------------------------------------------------------------------
    # Ollama (Local AI — used when LLM_API_KEY is not set)
    # -------------------------------------------------------------------------
    ollama_base_url: str = Field(default="http://localhost:11434")
    ollama_embed_model: str = Field(default="nomic-embed-text")
    ollama_timeout_seconds: int = Field(default=120)
    ollama_max_retries: int = Field(default=3)

    # Tiered model routing — map task classes to appropriately sized models.
    # EXTRACTION: slot filling, JSON schema output, structured data — small model is fine.
    # GENERATION: document drafting, briefing summaries, email composition — needs 7B+.
    # REASONING:  eligibility decisions, risk scoring, complex multi-step logic — needs 14B+.
    # Override individual tiers via env vars without touching code.
    ollama_extraction_model: str = Field(
        default="qwen2.5:1.5b-instruct-q8_0",
        description="Model for structured extraction and slot-filling tasks",
    )
    ollama_generation_model: str = Field(
        default="qwen2.5:7b-instruct",
        description="Model for document drafting, summarization, briefing generation",
    )
    ollama_reasoning_model: str = Field(
        default="qwen2.5:14b-instruct",
        description="Model for eligibility decisions, risk scoring, complex reasoning",
    )

    # Backwards-compat alias used by legacy code that still reads ollama_llm_model.
    # Points at the extraction tier so existing callers aren't broken.
    @property
    def ollama_llm_model(self) -> str:
        return self.ollama_extraction_model

    # -------------------------------------------------------------------------
    # External LLM API (OpenAI-compatible — overrides Ollama when set)
    # Supports: NVIDIA NIM, OpenAI, any OpenAI-compatible endpoint
    # -------------------------------------------------------------------------
    llm_api_key: str = Field(default="")
    llm_api_base_url: str = Field(default="")
    llm_api_model: str = Field(default="meta/llama-3.2-3b-instruct")
    llm_api_temperature: float = Field(default=0.2)
    llm_api_max_tokens: int = Field(default=1024)

    @property
    def use_external_llm(self) -> bool:
        """True when an external OpenAI-compatible API is configured."""
        return bool(self.llm_api_key and self.llm_api_base_url)

    # -------------------------------------------------------------------------
    # MFA / Two-Factor Authentication
    # -------------------------------------------------------------------------
    mfa_required_roles: List[str] = Field(
        default=["SUPER_ADMIN", "ADMIN", "REGISTRAR", "FINANCE_OFFICER", "HOD", "COE"],
        description="Roles that must have MFA enabled before a full session is issued.",
    )
    mfa_challenge_token_expire_minutes: int = Field(
        default=5,
        description="Lifetime (minutes) of the short-lived mfa_challenge JWT issued at login.",
    )

    # -------------------------------------------------------------------------
    # JWT Auth
    # -------------------------------------------------------------------------
    jwt_secret_key: str = Field(default="change-me-jwt-secret-32-char-minimum")
    jwt_algorithm: str = Field(
        default="HS256",
        description="HS256 (symmetric, single key) or RS256 (asymmetric, key pair). "
                    "RS256 is recommended for multi-tenant production — rotate keys via JWKS without downtime.",
    )
    jwt_access_token_expire_minutes: int = Field(default=60)
    jwt_refresh_token_expire_days: int = Field(default=7)

    # RS256 migration path — only required when jwt_algorithm = RS256.
    # Generate keys: openssl genrsa -out private.pem 2048 && openssl rsa -in private.pem -pubout -out public.pem
    # Set as env vars with literal newlines preserved (use $'-----BEGIN...\n...' in shell or JSON-encode).
    jwt_rsa_private_key: str = Field(
        default="",
        description="PEM-encoded RSA private key for RS256 token signing. Required when jwt_algorithm=RS256.",
    )
    jwt_rsa_public_key: str = Field(
        default="",
        description="PEM-encoded RSA public key for RS256 token verification. Required when jwt_algorithm=RS256.",
    )

    # -------------------------------------------------------------------------
    # Bootstrap
    # -------------------------------------------------------------------------
    alis_bootstrap_secret: str = Field(default="")
    alis_master_key: str = Field(default="")  # For tenant crypto

    # -------------------------------------------------------------------------
    # SMTP (Email Notifications)
    # -------------------------------------------------------------------------
    smtp_host: str = Field(default="localhost")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from_email: str = Field(default="noreply@alis.local")
    smtp_from_name: str = Field(default="ALIS Institution")
    smtp_use_tls: bool = Field(default=True)

    # -------------------------------------------------------------------------
    # SMS (Pluggable — MSG91 / Twilio)
    # -------------------------------------------------------------------------
    sms_provider: str = Field(default="MSG91")  # MSG91 | TWILIO
    sms_api_key: str = Field(default="")
    sms_sender_id: str = Field(default="ALIS")
    sms_gateway_enabled: bool = Field(default=False)
    sms_timeout_seconds: int = Field(default=10)
    # MSG91
    msg91_auth_key: str = Field(default="")
    msg91_otp_template_id: str = Field(default="")
    msg91_sender_id: str = Field(default="ALISUN")
    # Twilio
    twilio_account_sid: str = Field(default="")
    twilio_auth_token: str = Field(default="")
    twilio_verify_service_sid: str = Field(default="")
    twilio_from_number: str = Field(default="")

    # -------------------------------------------------------------------------
    # WhatsApp (Meta Business API)
    # -------------------------------------------------------------------------
    whatsapp_phone_number_id: str = Field(default="", description="Meta Business phone number ID")
    whatsapp_access_token: str = Field(default="", description="Meta Graph API permanent access token")
    whatsapp_webhook_verify_token: str = Field(default="", description="Webhook verification token")
    whatsapp_timeout_seconds: int = Field(default=10)

    # -------------------------------------------------------------------------
    # Payment Gateway (Razorpay primary, PayU fallback)
    # -------------------------------------------------------------------------
    payment_gateway_enabled: bool = Field(default=False)
    payment_gateway_provider: str = Field(default="RAZORPAY")  # RAZORPAY | PAYU
    payment_gateway_timeout_seconds: int = Field(default=30)
    razorpay_key_id: str = Field(default="")
    razorpay_key_secret: str = Field(default="")
    razorpay_webhook_secret: str = Field(default="")
    razorpay_currency: str = Field(default="INR")
    # PayU
    payu_merchant_key: str = Field(default="")
    payu_merchant_salt: str = Field(default="")

    # -------------------------------------------------------------------------
    # HashiCorp Vault (P0-2 — exam paper encryption + secrets management)
    # -------------------------------------------------------------------------
    vault_addr: str = Field(
        default="http://localhost:8200",
        description="Vault server address. Set VAULT_ADDR env var in production.",
    )
    vault_token: str = Field(
        default="",
        description=(
            "Vault token. Set VAULT_TOKEN env var — never hardcode. "
            "Generate via 'vault operator init' on first boot. "
            "Use AppRole auth for long-running services."
        ),
    )
    vault_transit_mount: str = Field(default="transit")
    vault_kv_mount: str = Field(default="secret")

    @property
    def vault_enabled(self) -> bool:
        return bool(self.vault_addr and self.vault_token)

    # -------------------------------------------------------------------------
    # DigiLocker (Indian Government Document Vault)
    # -------------------------------------------------------------------------
    digilocker_client_id: str = Field(default="")
    digilocker_client_secret: str = Field(default="")
    digilocker_base_url: str = Field(default="https://api.digitallocker.gov.in/public/oauth2/1")
    digilocker_redirect_uri: str = Field(default="")
    digilocker_timeout_seconds: int = Field(default=30)

    @property
    def digilocker_enabled(self) -> bool:
        return bool(self.digilocker_client_id and self.digilocker_client_secret)

    # -------------------------------------------------------------------------
    # NTA (National Testing Agency) Score Import
    # -------------------------------------------------------------------------
    nta_api_key: str = Field(default="")
    nta_base_url: str = Field(default="https://api.nta.ac.in/v1")
    nta_timeout_seconds: int = Field(default=30)

    @property
    def nta_enabled(self) -> bool:
        return bool(self.nta_api_key)

    # -------------------------------------------------------------------------
    # LMS Integration (Moodle / Canvas REST API)
    # -------------------------------------------------------------------------
    lms_base_url: str = Field(default="")
    lms_api_token: str = Field(default="")
    lms_default_course_category: int = Field(default=1)
    lms_timeout_seconds: int = Field(default=30)

    @property
    def lms_enabled(self) -> bool:
        return bool(self.lms_base_url and self.lms_api_token)

    # -------------------------------------------------------------------------
    # Email Provisioning (Google Workspace / Microsoft 365)
    # -------------------------------------------------------------------------
    email_provider: str = Field(
        default="",
        description="GOOGLE | MICROSOFT | SMTP_ONLY (empty = disabled)"
    )
    # Google Workspace
    google_admin_email: str = Field(default="")
    google_service_account_json: str = Field(default="")
    google_domain: str = Field(default="")
    # Microsoft 365
    ms_tenant_id: str = Field(default="")
    ms_client_id: str = Field(default="")
    ms_client_secret: str = Field(default="")
    ms_domain: str = Field(default="")

    @property
    def email_provision_enabled(self) -> bool:
        return self.email_provider in ("GOOGLE", "MICROSOFT")

    # -------------------------------------------------------------------------
    # Drillbit (Plagiarism Detection — PhD module)
    # -------------------------------------------------------------------------
    drillbit_api_key: str = Field(default="", description="Drillbit API key — obtain from drillbit.in")
    drillbit_base_url: str = Field(default="https://api.drillbit.in/v1")
    drillbit_timeout_seconds: int = Field(default=60)

    @property
    def drillbit_enabled(self) -> bool:
        return bool(self.drillbit_api_key)

    # -------------------------------------------------------------------------
    # NIC e-Invoice (GST IRN Generation)
    # -------------------------------------------------------------------------
    nic_einvoice_base_url: str = Field(
        default="https://einv-apisandbox.nic.in",
        description="NIC e-Invoice API. Sandbox: einv-apisandbox.nic.in | Prod: einvoice6.gst.gov.in",
    )
    nic_einvoice_client_id: str = Field(default="")
    nic_einvoice_client_secret: str = Field(default="")
    nic_einvoice_gstin: str = Field(default="", description="Institution GSTIN (15 chars)")
    nic_einvoice_username: str = Field(default="")
    nic_einvoice_password: str = Field(default="")
    nic_einvoice_timeout_seconds: int = Field(default=30)

    @property
    def nic_einvoice_configured(self) -> bool:
        return bool(self.nic_einvoice_client_id and self.nic_einvoice_gstin)

    # -------------------------------------------------------------------------
    # LMS (Moodle / Canvas REST API — student provisioning)
    # -------------------------------------------------------------------------

    # -------------------------------------------------------------------------
    # Observability — Sentry
    # -------------------------------------------------------------------------
    sentry_dsn: str = Field(
        default="",
        description="Sentry DSN for error tracking. Leave empty to disable Sentry.",
    )
    sentry_traces_sample_rate: float = Field(
        default=0.05,
        description="Fraction of transactions to send to Sentry Performance (0.0–1.0). "
                    "0.05 = 5% sampling in production to control volume.",
    )
    sentry_profiles_sample_rate: float = Field(
        default=0.01,
        description="Fraction of sampled transactions to profile. Keep low in production.",
    )

    @property
    def sentry_enabled(self) -> bool:
        return bool(self.sentry_dsn)

    # -------------------------------------------------------------------------
    # Document Storage (S3 / Azure Blob / Local)
    # -------------------------------------------------------------------------
    storage_provider: str = Field(default="LOCAL")  # S3 | AZURE_BLOB | LOCAL
    storage_bucket: str = Field(default="alis-documents")
    storage_region: str = Field(default="ap-south-1")
    alis_data_dir: str = Field(default="data")
    # AWS S3
    aws_access_key_id: str = Field(default="")
    aws_secret_access_key: str = Field(default="")
    # Azure Blob
    azure_storage_connection_string: str = Field(default="")
    azure_storage_account_name: str = Field(default="")
    azure_storage_account_key: str = Field(default="")

    # -------------------------------------------------------------------------
    # PGVector
    # -------------------------------------------------------------------------
    pgvector_dimensions: int = Field(default=768)  # nomic-embed-text output size

    # -------------------------------------------------------------------------
    # AI Service (S3 — dedicated inference microservice)
    # When ai_service_url is empty, AIGateway falls back to direct Ollama.
    # -------------------------------------------------------------------------
    ai_service_url: str = Field(
        default="",
        description="AI Service base URL (e.g. https://ai.alis.app). "
                    "Empty = direct Ollama fallback.",
    )
    ai_service_token: str = Field(
        default="change-me-ai-service-token",
        description="Bearer token for data-plane → AI service calls.",
    )

    # -------------------------------------------------------------------------
    # SaaS Multi-Tenant (S1 — DB-per-tenant routing)
    # Empty control_plane_url = single-tenant mode (backward compat — all
    # tenant queries use the same db_url as the system pool).
    # -------------------------------------------------------------------------
    control_plane_url: str = Field(
        default="",
        description="Control plane base URL (e.g. https://control.alis.app). "
                    "Empty = single-tenant fallback mode.",
    )
    control_plane_token: str = Field(
        default="",
        description="Internal bearer token for control plane → data plane calls.",
    )
    static_tenant_id: str = Field(
        default="",
        description="Tier 2 (dedicated stack): hardcode a single tenant_id, "
                    "bypassing all subdomain and JWT tenant resolution.",
    )
    saas_domain_suffix: str = Field(
        default="alis.app",
        description="Domain suffix used to extract subdomain tenant slug. "
                    "E.g., 'alis.app' → iitb.alis.app → slug='iitb'.",
    )
    tenant_db_cache_ttl_seconds: int = Field(
        default=300,
        description="Redis TTL (seconds) for per-tenant DB config cache.",
    )
    tenant_pool_min: int = Field(
        default=2,
        description="Min connections per per-tenant DB pool (async + sync).",
    )
    tenant_pool_max: int = Field(
        default=10,
        description="Max connections per per-tenant DB pool. "
                    "Total server connections ≈ tenant_count × tenant_pool_max.",
    )

    # -------------------------------------------------------------------------
    # Validators
    # -------------------------------------------------------------------------
    @field_validator("app_env")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(f"app_env must be one of {allowed}")
        return v

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_jwt_algorithm(cls, v: str) -> str:
        allowed = {"HS256", "RS256"}
        if v not in allowed:
            raise ValueError(f"jwt_algorithm must be one of {allowed}")
        return v

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Block startup if insecure defaults are used in production."""
        if self.app_env != "production":
            return self

        _DEFAULTS = {
            "jwt_secret_key": "change-me-jwt-secret-32-char-minimum",
            "app_secret_key": "change-me-in-production-use-32-char-min",
        }
        for field_name, default_val in _DEFAULTS.items():
            val = getattr(self, field_name)
            if val == default_val:
                raise ValueError(
                    f"[SECURITY] {field_name} must be changed from the default value in production. "
                    f"Set it via the {field_name.upper()} environment variable."
                )
            if len(val) < 32:
                raise ValueError(
                    f"[SECURITY] {field_name} must be at least 32 characters in production."
                )

        if not self.alis_master_key:
            raise ValueError(
                "[SECURITY] ALIS_MASTER_KEY must be set in production (required for tenant encryption)."
            )

        if self.jwt_algorithm == "RS256":
            if not self.jwt_rsa_private_key or not self.jwt_rsa_public_key:
                raise ValueError(
                    "[SECURITY] jwt_rsa_private_key and jwt_rsa_public_key are required "
                    "when jwt_algorithm=RS256."
                )

        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance. Use this everywhere."""
    return Settings()


# Module-level singleton — import this directly
settings = get_settings()
