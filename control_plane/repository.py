"""
Tenant Repository — S2

Data-access layer for cp_tenants. Used by the router and the provisioner.
Converts raw DB rows to TenantRecord/TenantSummary models.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from control_plane.models import TenantRecord, TenantSummary

logger = logging.getLogger(__name__)


def _row_to_record(row: dict) -> TenantRecord:
    from control_plane.crypto import decrypt
    from control_plane.settings import settings

    host = row["db_host"]
    port = row["db_port"]
    db_name = row["db_name"]
    db_user = row["db_user"]
    db_password = decrypt(row["db_password_enc"])

    db_url = f"postgresql://{db_user}:{db_password}@{host}:{port}/{db_name}"
    db_url_sync = db_url

    return TenantRecord(
        tenant_id=str(row["tenant_id"]),
        subdomain=row["subdomain"],
        display_name=row["display_name"],
        region=row["region"],
        db_url=db_url,
        db_url_sync=db_url_sync,
        plan=row["plan"],
        feature_flags=row.get("feature_flags") or {},
        status=row["status"],
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        suspended_at=row.get("suspended_at"),
    )


def _row_to_summary(row: dict) -> TenantSummary:
    return TenantSummary(
        tenant_id=str(row["tenant_id"]),
        subdomain=row["subdomain"],
        display_name=row["display_name"],
        region=row["region"],
        plan=row["plan"],
        status=row["status"],
        created_at=row.get("created_at"),
    )


class TenantRepository:

    @staticmethod
    def get_by_id(tenant_id: str) -> Optional[TenantRecord]:
        from control_plane import db as cp_db
        rows = cp_db.query(
            "SELECT * FROM cp_tenants WHERE tenant_id = %s AND status != 'deleted'",
            (tenant_id,),
        )
        return _row_to_record(rows[0]) if rows else None

    @staticmethod
    def get_by_subdomain(subdomain: str) -> Optional[TenantRecord]:
        from control_plane import db as cp_db
        rows = cp_db.query(
            "SELECT * FROM cp_tenants WHERE subdomain = %s AND status != 'deleted'",
            (subdomain,),
        )
        return _row_to_record(rows[0]) if rows else None

    @staticmethod
    def list_tenants(
        status: Optional[str] = None,
        region: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[List[TenantSummary], int]:
        from control_plane import db as cp_db

        where_clauses = ["status != 'deleted'"]
        params: list = []

        if status:
            where_clauses.append("status = %s")
            params.append(status)
        if region:
            where_clauses.append("region = %s")
            params.append(region)

        where = " AND ".join(where_clauses)

        count_rows = cp_db.query(f"SELECT COUNT(*) as n FROM cp_tenants WHERE {where}", tuple(params))
        total = count_rows[0]["n"] if count_rows else 0

        rows = cp_db.query(
            f"SELECT tenant_id, subdomain, display_name, region, plan, status, created_at "
            f"FROM cp_tenants WHERE {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
            tuple(params) + (limit, offset),
        )
        return [_row_to_summary(r) for r in rows], total

    @staticmethod
    def update(
        tenant_id: str,
        display_name: Optional[str] = None,
        plan: Optional[str] = None,
        feature_flags: Optional[dict] = None,
        region: Optional[str] = None,
    ) -> Optional[TenantRecord]:
        import json
        from control_plane import db as cp_db

        sets = ["updated_at = NOW()"]
        params: list = []

        if display_name is not None:
            sets.append("display_name = %s")
            params.append(display_name)
        if plan is not None:
            sets.append("plan = %s")
            params.append(plan)
        if feature_flags is not None:
            sets.append("feature_flags = %s::jsonb")
            params.append(json.dumps(feature_flags))
        if region is not None:
            sets.append("region = %s")
            params.append(region)

        if len(sets) == 1:
            return TenantRepository.get_by_id(tenant_id)

        params.append(tenant_id)
        cp_db.execute(
            f"UPDATE cp_tenants SET {', '.join(sets)} WHERE tenant_id = %s",
            tuple(params),
        )
        return TenantRepository.get_by_id(tenant_id)
