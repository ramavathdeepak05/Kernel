"""PostgresAccountRepository — durable, psycopg2-backed account + API-key persistence (ADR-0010).

Implements the `AccountRepository` Protocol structurally. **Synchronous** (psycopg2, already a
dependency): accounts are written only on the infrequent signup / key-issue path, and the auth hot
path reads the in-memory `AccountStore` cache (hydrated at startup), so keeping this sync avoids making
the whole account/auth surface async. A short blocking write on signup is acceptable.

Tables (see migration 006_create_account_tables.py) — control-plane registries, intentionally NOT
under RLS (like quaicu_customer_plans), since `load_all()` must read every tenant's records:
  quaicu_accounts  — one row per account (1:1 with a tenant on signup)
  quaicu_api_keys  — hashed API-key records

Writes use INSERT … ON CONFLICT DO UPDATE so re-persisting is idempotent. All exceptions are wrapped
as `AccountPersistenceError`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from core.account.model import Account, AccountStatus, ApiKey, Member, MemberStatus
from core.errors import AccountPersistenceError
from core.types import TenantId

_UPSERT_ACCOUNT_SQL = """
INSERT INTO quaicu_accounts
    (account_id, tenant_id, email, name, status, created_at, full_name, job_title, phone,
     password_hash, profile, paid_until)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
ON CONFLICT (account_id) DO UPDATE SET
    tenant_id     = EXCLUDED.tenant_id,
    email         = EXCLUDED.email,
    name          = EXCLUDED.name,
    status        = EXCLUDED.status,
    full_name     = EXCLUDED.full_name,
    job_title     = EXCLUDED.job_title,
    phone         = EXCLUDED.phone,
    password_hash = EXCLUDED.password_hash,
    profile       = EXCLUDED.profile,
    paid_until    = EXCLUDED.paid_until
"""

_UPSERT_API_KEY_SQL = """
INSERT INTO quaicu_api_keys (key_id, tenant_id, hashed_secret, created_at, revoked, scopes, member_id)
VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
ON CONFLICT (key_id) DO UPDATE SET
    tenant_id     = EXCLUDED.tenant_id,
    hashed_secret = EXCLUDED.hashed_secret,
    revoked       = EXCLUDED.revoked,
    scopes        = EXCLUDED.scopes,
    member_id     = EXCLUDED.member_id
"""

_UPSERT_MEMBER_SQL = """
INSERT INTO quaicu_members
    (member_id, tenant_id, email, display_name, role, status, created_at, external_id, password_hash)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (member_id) DO UPDATE SET
    email         = EXCLUDED.email,
    display_name  = EXCLUDED.display_name,
    role          = EXCLUDED.role,
    status        = EXCLUDED.status,
    external_id   = EXCLUDED.external_id,
    password_hash = EXCLUDED.password_hash
"""

_SELECT_MEMBERS_SQL = (
    "SELECT member_id, tenant_id, email, COALESCE(display_name, ''), role, status, created_at, "
    "COALESCE(external_id, ''), COALESCE(password_hash, '') FROM quaicu_members"
)

_SELECT_ACCOUNTS_SQL = (
    "SELECT account_id, tenant_id, email, name, status, created_at, "
    "COALESCE(full_name, ''), COALESCE(job_title, ''), COALESCE(phone, ''), "
    "COALESCE(password_hash, ''), COALESCE(profile, '{}'), paid_until FROM quaicu_accounts"
)
_SELECT_API_KEYS_SQL = (
    "SELECT key_id, tenant_id, hashed_secret, created_at, revoked, scopes, "
    "COALESCE(member_id, '') FROM quaicu_api_keys"
)

_SELECT_ACCOUNT_BY_EMAIL_SQL = _SELECT_ACCOUNTS_SQL + " WHERE lower(email) = lower(%s)"


def _scopes_from(raw: Any) -> frozenset[str]:
    if isinstance(raw, str):
        raw = json.loads(raw)
    return frozenset(str(s) for s in (raw or []))


def _row_to_account(r: Any) -> Account:
    profile = r[10]
    if isinstance(profile, str):  # some drivers return jsonb as text
        profile = json.loads(profile or "{}")
    return Account(
        account_id=r[0],
        tenant_id=TenantId(r[1]),
        email=r[2],
        name=r[3],
        status=AccountStatus(r[4]),
        created_at=r[5],
        full_name=r[6],
        job_title=r[7],
        phone=r[8],
        password_hash=r[9],
        profile=profile or {},
        paid_until=r[11],
    )


class PostgresAccountRepository:
    """Sync psycopg2-backed `AccountRepository`. ``connect`` is injectable for tests."""

    def __init__(self, dsn: str, *, connect: Callable[[], Any] | None = None) -> None:
        self._dsn = dsn
        self._connect_fn = connect

    def _connect(self) -> Any:
        if self._connect_fn is not None:
            return self._connect_fn()
        import psycopg2  # lazy; already a dependency (alembic uses it)

        return psycopg2.connect(self._dsn)

    def _run(self, fn: Callable[[Any], Any], op: str) -> Any:
        try:
            conn = self._connect()
            try:
                with conn.cursor() as cur:
                    result = fn(cur)
                conn.commit()
                return result
            finally:
                conn.close()
        except AccountPersistenceError:
            raise
        except Exception as exc:  # noqa: BLE001 — any backend failure is a persistence error
            raise AccountPersistenceError(f"account {op} failed: {exc}") from exc

    # ── AccountRepository ─────────────────────────────────────────────────────

    def load_all(self) -> tuple[list[Account], list[ApiKey]]:
        def _load(cur: Any) -> tuple[list[Account], list[ApiKey]]:
            cur.execute(_SELECT_ACCOUNTS_SQL)
            accounts = [_row_to_account(r) for r in cur.fetchall()]
            cur.execute(_SELECT_API_KEYS_SQL)
            keys = [
                ApiKey(
                    key_id=r[0],
                    tenant_id=TenantId(r[1]),
                    hashed_secret=r[2],
                    created_at=r[3],
                    revoked=bool(r[4]),
                    scopes=_scopes_from(r[5]),
                    member_id=r[6],
                )
                for r in cur.fetchall()
            ]
            return accounts, keys

        return self._run(_load, "load_all")

    def load_members(self) -> list[Member]:
        def _load(cur: Any) -> list[Member]:
            cur.execute(_SELECT_MEMBERS_SQL)
            return [
                Member(
                    member_id=r[0],
                    tenant_id=TenantId(r[1]),
                    email=r[2],
                    display_name=r[3],
                    role=r[4],
                    status=MemberStatus(r[5]),
                    created_at=r[6],
                    external_id=r[7],
                    password_hash=r[8],
                )
                for r in cur.fetchall()
            ]

        return self._run(_load, "load_members")

    def save_member(self, member: Member) -> None:
        self._run(
            lambda cur: cur.execute(
                _UPSERT_MEMBER_SQL,
                (
                    member.member_id,
                    str(member.tenant_id),
                    member.email,
                    member.display_name,
                    member.role,
                    member.status.value,
                    member.created_at,
                    member.external_id,
                    member.password_hash,
                ),
            ),
            "save_member",
        )

    def replace_member(self, member: Member) -> None:
        self.save_member(member)  # upsert handles update (role/status/external_id)

    def get_account_by_email(self, email: str) -> Account | None:
        def _q(cur: Any) -> Account | None:
            cur.execute(_SELECT_ACCOUNT_BY_EMAIL_SQL, (email,))
            row = cur.fetchone()
            return _row_to_account(row) if row else None

        return self._run(_q, "get_account_by_email")

    def save_account(self, account: Account) -> None:
        self._run(
            lambda cur: cur.execute(
                _UPSERT_ACCOUNT_SQL,
                (
                    account.account_id,
                    str(account.tenant_id),
                    account.email,
                    account.name,
                    account.status.value,
                    account.created_at,
                    account.full_name,
                    account.job_title,
                    account.phone,
                    account.password_hash,
                    json.dumps(dict(account.profile)),
                    account.paid_until,
                ),
            ),
            "save_account",
        )

    def save_api_key(self, key: ApiKey) -> None:
        self._run(lambda cur: cur.execute(_UPSERT_API_KEY_SQL, self._api_key_params(key)), "save_api_key")

    def replace_api_key(self, key: ApiKey) -> None:
        # Upsert handles both insert and update (e.g. revoked flips).
        self.save_api_key(key)

    @staticmethod
    def _api_key_params(key: ApiKey) -> tuple:
        return (
            key.key_id,
            str(key.tenant_id),
            key.hashed_secret,
            key.created_at,
            key.revoked,
            json.dumps(sorted(key.scopes)),
            key.member_id,
        )

    def close(self) -> None:
        # Connection-per-operation; nothing persistent to close.
        return None
