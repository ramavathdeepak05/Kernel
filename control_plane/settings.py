"""
Control Plane Settings — S2

Standalone settings for the control plane service.
Loaded from environment variables (same .env convention as the data plane).

The control plane has its own database (alis_control) on the same Postgres
instance by default, but can point at a completely separate host in
multi-region deployments.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ControlPlaneSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_env: str = Field(default="development")

    # -------------------------------------------------------------------------
    # Control Plane own database (alis_control)
    # -------------------------------------------------------------------------
    cp_db_host: str = Field(default="localhost")
    cp_db_port: int = Field(default=5432)
    cp_db_name: str = Field(default="alis_control")
    cp_db_user: str = Field(default="postgres")
    cp_db_password: str = Field(default="postgres")

    @property
    def cp_db_url(self) -> str:
        return (
            f"postgresql://{self.cp_db_user}:{self.cp_db_password}"
            f"@{self.cp_db_host}:{self.cp_db_port}/{self.cp_db_name}"
        )

    # -------------------------------------------------------------------------
    # Postgres superuser DSN — used by Provisioner to CREATE DATABASE
    # In managed Postgres (Azure/GCP), this is a privileged service account.
    # -------------------------------------------------------------------------
    cp_pg_admin_host: str = Field(default="localhost")
    cp_pg_admin_port: int = Field(default=5432)
    cp_pg_admin_db: str = Field(default="postgres")      # connect to postgres DB to run CREATE DATABASE
    cp_pg_admin_user: str = Field(default="postgres")
    cp_pg_admin_password: str = Field(default="postgres")

    @property
    def cp_pg_admin_url(self) -> str:
        return (
            f"postgresql://{self.cp_pg_admin_user}:{self.cp_pg_admin_password}"
            f"@{self.cp_pg_admin_host}:{self.cp_pg_admin_port}/{self.cp_pg_admin_db}"
        )

    # -------------------------------------------------------------------------
    # Data plane Alembic migrations path
    # Used by Provisioner to run migrations on newly created tenant DBs.
    # Defaults to the ALIS/migrations directory (same monorepo).
    # -------------------------------------------------------------------------
    alembic_config_path: str = Field(
        default="ALIS/migrations/alembic.ini",
        description="Path to alembic.ini relative to repo root.",
    )

    # -------------------------------------------------------------------------
    # Internal auth — data planes present this token on /internal/* calls
    # -------------------------------------------------------------------------
    internal_token: str = Field(
        default="change-me-internal-token",
        description="Bearer token for data-plane → control-plane internal calls.",
    )

    # -------------------------------------------------------------------------
    # Admin auth — ALIS superadmin JWT secret (reused for admin API)
    # -------------------------------------------------------------------------
    admin_jwt_secret: str = Field(default="change-me-jwt-secret-32-char-minimum")
    admin_jwt_algorithm: str = Field(default="HS256")

    # -------------------------------------------------------------------------
    # Encryption — tenant DB password encryption
    # Same ALIS_MASTER_KEY as data plane; must match.
    # -------------------------------------------------------------------------
    alis_master_key: str = Field(default="")

    # -------------------------------------------------------------------------
    # S5: S3 / MinIO — per-tenant bucket provisioning
    # -------------------------------------------------------------------------
    s3_endpoint_url: str = Field(
        default="http://localhost:9000",
        description="MinIO or S3-compatible endpoint. Empty = use real AWS S3.",
    )
    s3_access_key: str = Field(default="minioadmin")
    s3_secret_key: str = Field(default="minioadmin")
    s3_region: str = Field(default="us-east-1")
    s3_force_path_style: bool = Field(
        default=True,
        description="True for MinIO; False for AWS S3.",
    )

    # -------------------------------------------------------------------------
    # S5: HashiCorp Vault — per-tenant secrets
    # -------------------------------------------------------------------------
    vault_addr: str = Field(
        default="",
        description="Vault server address. Empty = Vault disabled (dev mode).",
    )
    vault_token: str = Field(default="", description="Static root token (dev only).")
    vault_role_id: str = Field(default="", description="AppRole role_id (production).")
    vault_secret_id: str = Field(default="", description="AppRole secret_id (production).")
    vault_mount_point: str = Field(default="secret", description="KV v2 mount point.")

    # -------------------------------------------------------------------------
    # S10: DNS — per-tenant subdomain record management
    # -------------------------------------------------------------------------
    cloudflare_api_token: str = Field(default="", description="Cloudflare API token (Zone:DNS:Edit).")
    cloudflare_zone_id: str = Field(default="", description="Cloudflare zone ID for alis.app.")
    route53_hosted_zone_id: str = Field(default="", description="AWS Route53 hosted zone ID.")
    azure_dns_resource_group: str = Field(default="")
    azure_dns_zone_name: str = Field(default="")
    dns_lb_target: str = Field(
        default="data-plane.alis.app",
        description="CNAME target for tenant subdomains (load balancer hostname).",
    )

    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    allowed_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"]
    )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> ControlPlaneSettings:
    return ControlPlaneSettings()


settings = get_settings()
