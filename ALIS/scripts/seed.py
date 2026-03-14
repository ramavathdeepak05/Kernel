#!/usr/bin/env python3
"""
P0-S16 -- ALIS Seed Data Script

Bootstraps a fresh ALIS instance with:
  1. Default organisation
  2. SUPER_ADMIN user
  3. Sample programs (stored in users.metadata / org.metadata)
  4. Core institution policies (used by the autonomous pipeline)
  5. Default notification templates
  6. Academic calendar for current year

Run AFTER alembic upgrade head:
    python scripts/seed.py

Environment variables (from .env):
    SEED_ORG_NAME      -- default: "Demo Institution"
    SEED_ORG_SLUG      -- default: "demo"
    SEED_ADMIN_EMAIL   -- default: "admin@demo.edu"
    SEED_ADMIN_PASSWORD -- default: "Admin@1234"  (CHANGE IN PRODUCTION)
"""

import json
import os
import sys
import uuid
from datetime import date, timedelta

# Allow running from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt as _bcrypt_lib

from server.core.settings import settings


def _hash_password(password: str) -> str:
    return _bcrypt_lib.hashpw(password.encode(), _bcrypt_lib.gensalt()).decode()


class _PwdCompat:
    def hash(self, secret: str) -> str:
        return _hash_password(secret)


_pwd = _PwdCompat()

# ---------------------------------------------------------------------------
# Config (override via env vars)
# ---------------------------------------------------------------------------
ORG_NAME = os.getenv("SEED_ORG_NAME", "Demo Institution")
ORG_SLUG = os.getenv("SEED_ORG_SLUG", "demo")
ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@demo.edu")
ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "Admin@1234")

PROGRAMS = [
    "B.Tech Computer Science",
    "B.Tech Electronics & Communication",
    "MBA",
    "MCA",
    "B.Sc Mathematics",
]

# Institution policies (used by E04-S11 Policy Engine)
POLICIES = [
    {
        "key": "admissions.eligibility.min_academic_percentage",
        "value": 55.0,
        "description": "Minimum academic percentage for AUTO_PROCEED eligibility",
        "category": "admissions",
    },
    {
        "key": "admissions.eligibility.review_band_lower",
        "value": 50.0,
        "description": "Academic percentage above which application goes to REVIEW instead of AUTO_REJECT",
        "category": "admissions",
    },
    {
        "key": "admissions.eligibility.min_entrance_score",
        "value": 40.0,
        "description": "Minimum entrance exam score (out of 100) for AUTO_PROCEED",
        "category": "admissions",
    },
    {
        "key": "admissions.counsellor.max_load",
        "value": 30,
        "description": "Maximum applicants a single counsellor can handle concurrently",
        "category": "admissions",
    },
    {
        "key": "admissions.offer_letter.validity_days",
        "value": 30,
        "description": "Days an offer letter remains valid for fee payment",
        "category": "admissions",
    },
    {
        "key": "finance.fee.overdue_grace_days",
        "value": 7,
        "description": "Grace period after fee due date before overdue flag is set",
        "category": "finance",
    },
    {
        "key": "academics.attendance.min_percentage",
        "value": 75.0,
        "description": "Minimum attendance percentage required to sit exams",
        "category": "academics",
    },
]


def seed(conn: psycopg2.extensions.connection) -> None:
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # ----------------------------------------------------------------
    # 1. Organisation
    # ----------------------------------------------------------------
    print(f"  -> Organisation: {ORG_NAME} ({ORG_SLUG})")
    cur.execute("SELECT id FROM organisations WHERE slug = %s", (ORG_SLUG,))
    existing_org = cur.fetchone()
    if existing_org:
        org_id = str(existing_org["id"])
        print(f"    Already exists: {org_id}")
    else:
        org_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO organisations (id, name, slug, status, metadata)
            VALUES (%s, %s, %s, 'ACTIVE', %s)
            """,
            (org_id, ORG_NAME, ORG_SLUG, json.dumps({"programs": PROGRAMS})),
        )
        print(f"    Created: {org_id}")

    # ----------------------------------------------------------------
    # 2. SUPER_ADMIN user
    # ----------------------------------------------------------------
    print(f"  -> SUPER_ADMIN: {ADMIN_EMAIL}")
    cur.execute(
        "SELECT id FROM users WHERE tenant_id = %s AND email = %s",
        (org_id, ADMIN_EMAIL),
    )
    if cur.fetchone():
        print("    Already exists -- skipping")
    else:
        admin_id = str(uuid.uuid4())
        pw_hash = _pwd.hash(ADMIN_PASSWORD)
        cur.execute(
            """
            INSERT INTO users (id, tenant_id, username, email, display_name, role, status, password_hash, actor_type)
            VALUES (%s, %s, %s, %s, 'System Administrator', 'SUPER_ADMIN', 'ACTIVE', %s, 'human')
            """,
            (admin_id, org_id, ADMIN_EMAIL, ADMIN_EMAIL, pw_hash),
        )
        print(f"    Created: {admin_id}")

    # ----------------------------------------------------------------
    # 3. Institution policies
    # ----------------------------------------------------------------
    print("  -> Institution policies")
    # institution_policies table created by E04-S10 migration.
    # For now store as org metadata key if table doesn't exist yet.
    try:
        cur.execute("SELECT 1 FROM institution_policies LIMIT 1")
        for p in POLICIES:
            cur.execute(
                "SELECT id FROM institution_policies WHERE org_id = %s AND key = %s",
                (org_id, p["key"]),
            )
            if not cur.fetchone():
                cur.execute(
                    """
                    INSERT INTO institution_policies
                        (id, org_id, key, value, description, category)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        str(uuid.uuid4()),
                        org_id,
                        p["key"],
                        json.dumps(p["value"]),
                        p["description"],
                        p["category"],
                    ),
                )
        print(f"    Inserted {len(POLICIES)} policies")
    except psycopg2.errors.UndefinedTable:
        conn.rollback()  # clear the error
        # Re-start the transaction
        cur = conn.cursor(cursor_factory=RealDictCursor)
        print("    institution_policies table not yet created (runs in E04-S10 migration) -- skipping")

    # ----------------------------------------------------------------
    # 4. Academic calendar (current year, single semester)
    # ----------------------------------------------------------------
    print("  -> Academic calendar")
    academic_year = f"{date.today().year}-{date.today().year + 1}"
    cur.execute(
        "SELECT id FROM academic_calendars WHERE org_id = %s AND academic_year = %s",
        (org_id, academic_year),
    )
    if cur.fetchone():
        print(f"    Calendar {academic_year} already exists -- skipping")
    else:
        cal_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO academic_calendars (id, org_id, name, academic_year, is_active)
            VALUES (%s, %s, %s, %s, TRUE)
            """,
            (cal_id, org_id, f"AY {academic_year}", academic_year),
        )
        today = date.today()
        phases = [
            ("ENROLLMENT_OPEN",  today,                    today + timedelta(days=60)),
            ("CLASSES",          today + timedelta(days=61), today + timedelta(days=180)),
            ("ATTENDANCE_LOCK",  today + timedelta(days=175), today + timedelta(days=180)),
            ("EXAM_REGISTRATION",today + timedelta(days=175), today + timedelta(days=190)),
            ("EXAM_PERIOD",      today + timedelta(days=191), today + timedelta(days=220)),
            ("RESULTS",          today + timedelta(days=221), today + timedelta(days=240)),
            ("SEMESTER_BREAK",   today + timedelta(days=241), today + timedelta(days=300)),
        ]
        for phase_name, start, end in phases:
            cur.execute(
                """
                INSERT INTO calendar_phases (id, calendar_id, phase_name, start_date, end_date)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (str(uuid.uuid4()), cal_id, phase_name, start, end),
            )
        print(f"    Created calendar {academic_year} with {len(phases)} phases")

    conn.commit()
    print("\n  Done. OK")


def main() -> None:
    print(f"\nALIS Seed Script -- {ORG_NAME}")
    print("=" * 50)
    print(f"  DB: {settings.db_url.replace(settings.db_password, '***')}")

    try:
        conn = psycopg2.connect(settings.db_url)
    except Exception as exc:
        print(f"\n  ERROR: Cannot connect to database -- {exc}")
        sys.exit(1)

    try:
        seed(conn)
    except Exception as exc:
        conn.rollback()
        print(f"\n  ERROR: Seed failed -- {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
