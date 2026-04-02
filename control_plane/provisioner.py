"""
Tenant Provisioner — S2

Handles the full lifecycle of creating (or destroying) a per-tenant database.

Provision flow
--------------
1. Allocate DB credentials (generate or accept from caller)
2. CREATE DATABASE alis_{subdomain} via admin DSN (autocommit — DDL)
3. Run all Alembic migrations against the new DB (sets up full schema)
4. Insert tenant record into cp_tenants
5. Log to cp_provisioning_log

Suspend / Delete flows are intentionally conservative:
- Suspend: set status = 'suspended', leave DB intact
- Delete: set status = 'deleted', optionally DROP DATABASE (requires explicit flag)
"""
from __future__ import annotations

import logging
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _generate_db_password(length: int = 32) -> str:
    """Generate a cryptographically strong DB password."""
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _admin_conn():
    """
    Return a psycopg2 connection to the admin DB (postgres).
    Autocommit is required for CREATE DATABASE / DROP DATABASE.
    """
    import psycopg2
    from control_plane.settings import settings
    conn = psycopg2.connect(dsn=settings.cp_pg_admin_url)
    conn.autocommit = True
    return conn


def _db_exists(db_name: str) -> bool:
    conn = _admin_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
            return cur.fetchone() is not None
    finally:
        conn.close()


def _create_database(db_name: str, owner: str) -> None:
    """CREATE DATABASE if not exists."""
    if _db_exists(db_name):
        logger.info("Provisioner: database %s already exists — skipping CREATE", db_name)
        return
    conn = _admin_conn()
    try:
        with conn.cursor() as cur:
            # Cannot use %s for identifiers — sanitise manually
            safe_name = "".join(c for c in db_name if c.isalnum() or c == "_")
            safe_owner = "".join(c for c in owner if c.isalnum() or c == "_")
            cur.execute(f'CREATE DATABASE "{safe_name}" OWNER "{safe_owner}"')
        logger.info("Provisioner: database %s created.", db_name)
    finally:
        conn.close()


def _create_db_user(db_user: str, db_password: str) -> None:
    """CREATE ROLE (user) if it doesn't already exist."""
    conn = _admin_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (db_user,))
            if cur.fetchone():
                logger.info("Provisioner: DB user %s already exists.", db_user)
                return
            safe_user = "".join(c for c in db_user if c.isalnum() or c == "_")
            cur.execute(
                f"CREATE ROLE \"{safe_user}\" LOGIN PASSWORD %s",
                (db_password,),
            )
            logger.info("Provisioner: DB user %s created.", db_user)
    finally:
        conn.close()


def _grant_privileges(db_name: str, db_user: str) -> None:
    """GRANT all privileges on the new database to the tenant user."""
    conn = _admin_conn()
    try:
        with conn.cursor() as cur:
            safe_name = "".join(c for c in db_name if c.isalnum() or c == "_")
            safe_user = "".join(c for c in db_user if c.isalnum() or c == "_")
            cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{safe_name}" TO "{safe_user}"')
        logger.info("Provisioner: granted privileges on %s to %s", db_name, db_user)
    finally:
        conn.close()


def _run_migrations(db_url: str) -> None:
    """
    Run all Alembic migrations against the given DB URL.

    Uses subprocess to invoke `alembic upgrade head` with a custom DB URL,
    avoiding any import-time side effects of loading ALIS models.
    """
    import os
    import subprocess
    from control_plane.settings import settings

    alembic_ini = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", settings.alembic_config_path)
    )

    if not os.path.exists(alembic_ini):
        logger.warning(
            "Provisioner: alembic.ini not found at %s — skipping migrations. "
            "Run migrations manually for tenant DB.",
            alembic_ini,
        )
        return

    env = {**os.environ, "DATABASE_URL": db_url}
    result = subprocess.run(
        ["alembic", "-c", alembic_ini, "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Alembic migrations failed for {db_url}:\n{result.stderr}"
        )
    logger.info("Provisioner: migrations applied successfully.")


def _log_provision(tenant_id: str, action: str, status: str, error: Optional[str] = None) -> None:
    try:
        from control_plane import db as cp_db
        cp_db.execute(
            """
            INSERT INTO cp_provisioning_log (tenant_id, action, status, finished_at, error)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (tenant_id, action, status, datetime.now(timezone.utc), error),
        )
    except Exception as exc:
        logger.warning("Provisioner: failed to write provisioning log: %s", exc)


class TenantProvisioner:
    """
    Synchronous tenant lifecycle manager.

    All methods are synchronous — provisioning is a background Celery task,
    not an in-request operation. The HTTP endpoint enqueues the task and
    returns immediately with status='provisioning'.
    """

    @staticmethod
    def provision(
        tenant_id: str,
        subdomain: str,
        display_name: str,
        region: str = "in-central",
        plan: str = "starter",
        feature_flags: dict | None = None,
        # Optional override: caller supplies their own DB details (Tier 2)
        db_host: Optional[str] = None,
        db_port: Optional[int] = None,
        db_user_override: Optional[str] = None,
        db_password_override: Optional[str] = None,
    ) -> dict:
        """
        Full provision flow. Returns the completed tenant record dict.

        Raises RuntimeError on any step failure — the Celery task will retry.
        """
        from control_plane.settings import settings
        from control_plane.crypto import encrypt
        from control_plane import db as cp_db

        # 1. Resolve DB location
        host = db_host or settings.cp_pg_admin_host
        port = db_port or settings.cp_pg_admin_port
        db_name = f"alis_{subdomain.replace('-', '_')}"
        db_user = db_user_override or f"alis_{subdomain.replace('-', '_')}"
        db_password = db_password_override or _generate_db_password()

        logger.info("Provisioner: starting provision for tenant=%s subdomain=%s", tenant_id, subdomain)

        # 2. Create DB user
        _create_db_user(db_user, db_password)

        # 3. Create database
        _create_database(db_name, db_user)

        # 4. Grant privileges
        _grant_privileges(db_name, db_user)

        # 5. Construct DSN
        db_url_sync = f"postgresql://{db_user}:{db_password}@{host}:{port}/{db_name}"
        db_url = db_url_sync  # asyncpg uses same format

        # 6. Run Alembic migrations
        try:
            _run_migrations(db_url_sync)
        except RuntimeError as exc:
            _log_provision(tenant_id, "provision", "failed", str(exc))
            raise

        # 7. Encrypt password and store tenant record
        db_password_enc = encrypt(db_password)

        cp_db.execute(
            """
            INSERT INTO cp_tenants
                (tenant_id, subdomain, display_name, region, db_host, db_port,
                 db_name, db_user, db_password_enc, plan, feature_flags, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, 'active')
            ON CONFLICT (tenant_id) DO UPDATE SET
                status = 'active',
                updated_at = NOW()
            """,
            (
                tenant_id, subdomain, display_name, region,
                host, port, db_name, db_user, db_password_enc,
                plan,
                __import__("json").dumps(feature_flags or {}),
            ),
        )

        # 8. S5: Provision per-tenant S3 bucket
        bucket_name = None
        try:
            from control_plane.bucket_provisioner import BucketProvisioner
            bp = BucketProvisioner()
            bucket_name = bp.provision(tenant_id)
        except Exception as exc:
            # Non-fatal — data plane can still function without dedicated bucket
            logger.warning("Provisioner: S3 bucket provisioning failed for %s: %s", tenant_id, exc)

        # 9. S5: Write DB credentials to Vault
        try:
            from control_plane.vault_client import TenantSecretsManager
            vsm = TenantSecretsManager(region=region)
            vsm.write_db_credentials(
                tenant_id=tenant_id,
                db_user=db_user,
                db_password=db_password,
                db_name=db_name,
                db_host=host,
                db_port=port,
            )
            if bucket_name:
                vsm.write_s3_credentials(
                    tenant_id=tenant_id,
                    bucket=bucket_name,
                    access_key=settings.s3_access_key,
                    secret_key=settings.s3_secret_key,
                )
        except Exception as exc:
            logger.warning("Provisioner: Vault secret write failed for %s: %s", tenant_id, exc)

        # 10. Update bucket_name in tenant record (if provisioned)
        if bucket_name:
            try:
                cp_db.execute(
                    "UPDATE cp_tenants SET bucket_name = %s WHERE tenant_id = %s",
                    (bucket_name, tenant_id),
                )
            except Exception:
                pass  # column may not exist in older schemas — non-fatal

        # 11. S10: Provision DNS record
        dns_record_id = None
        try:
            from control_plane.dns_manager import TenantDNSManager
            dns_mgr = TenantDNSManager()
            dns_record_id = dns_mgr.provision_dns(
                subdomain=subdomain,
                target=settings.dns_lb_target,
            )
        except Exception as exc:
            logger.warning("Provisioner: DNS provisioning failed for %s: %s", subdomain, exc)

        _log_provision(tenant_id, "provision", "completed")
        logger.info("Provisioner: tenant=%s provisioned successfully.", tenant_id)

        return {
            "tenant_id": tenant_id,
            "subdomain": subdomain,
            "db_url": db_url,
            "db_url_sync": db_url_sync,
            "bucket_name": bucket_name,
            "dns_record_id": dns_record_id,
            "status": "active",
        }

    @staticmethod
    def suspend(tenant_id: str) -> None:
        """Suspend a tenant (blocks all requests via SubdomainTenantMiddleware)."""
        from control_plane import db as cp_db

        cp_db.execute(
            """
            UPDATE cp_tenants
            SET status = 'suspended', suspended_at = NOW(), updated_at = NOW()
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        _log_provision(tenant_id, "suspend", "completed")
        logger.info("Provisioner: tenant=%s suspended.", tenant_id)

    @staticmethod
    def reactivate(tenant_id: str) -> None:
        """Reactivate a previously suspended tenant."""
        from control_plane import db as cp_db

        cp_db.execute(
            """
            UPDATE cp_tenants
            SET status = 'active', suspended_at = NULL, updated_at = NOW()
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        _log_provision(tenant_id, "reactivate", "completed")
        logger.info("Provisioner: tenant=%s reactivated.", tenant_id)

    @staticmethod
    def delete(tenant_id: str, drop_database: bool = False) -> None:
        """
        Soft-delete a tenant.

        drop_database=False (default): marks deleted, keeps DB intact (safe — recoverable).
        drop_database=True: also DROPs the database. IRREVERSIBLE.
        """
        from control_plane import db as cp_db

        row = cp_db.query(
            "SELECT subdomain, db_name, db_user FROM cp_tenants WHERE tenant_id = %s",
            (tenant_id,),
        )
        if not row:
            raise ValueError(f"Tenant {tenant_id} not found")
        rec = row[0]

        cp_db.execute(
            """
            UPDATE cp_tenants
            SET status = 'deleted', deleted_at = NOW(), updated_at = NOW()
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )

        if drop_database:
            conn = _admin_conn()
            try:
                with conn.cursor() as cur:
                    safe_name = "".join(c for c in rec["db_name"] if c.isalnum() or c == "_")
                    # Terminate active connections before dropping
                    cur.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = %s AND pid <> pg_backend_pid()",
                        (rec["db_name"],),
                    )
                    cur.execute(f'DROP DATABASE IF EXISTS "{safe_name}"')
                logger.info("Provisioner: database %s dropped.", rec["db_name"])
            finally:
                conn.close()

        # S5: Destroy S3 bucket (archive first by default)
        try:
            from control_plane.bucket_provisioner import BucketProvisioner
            BucketProvisioner().destroy(tenant_id, archive_first=True)
        except Exception as exc:
            logger.warning("Provisioner: S3 bucket destroy failed for %s: %s", tenant_id, exc)

        # S5: Delete Vault secrets
        try:
            from control_plane.vault_client import TenantSecretsManager
            TenantSecretsManager().delete_all(tenant_id)
        except Exception as exc:
            logger.warning("Provisioner: Vault secret delete failed for %s: %s", tenant_id, exc)

        # S10: Remove DNS record
        try:
            from control_plane.dns_manager import TenantDNSManager
            TenantDNSManager().deprovision_dns(subdomain=rec["subdomain"])
        except Exception as exc:
            logger.warning("Provisioner: DNS deprovisioning failed for %s: %s", tenant_id, exc)

        _log_provision(tenant_id, "delete", "completed")
        logger.info("Provisioner: tenant=%s deleted (drop_database=%s).", tenant_id, drop_database)
