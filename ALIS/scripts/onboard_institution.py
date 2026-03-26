#!/usr/bin/env python3
"""
ALIS Institution Onboarding Script

Interactive script that provisions a new institution from scratch:
  1. Creates the organization record (STANDALONE or GROUP entity)
  2. Creates department / school records (up to 7)
  3. Creates initial admin accounts (Super Admin, Registrar, Finance Officer, HODs)
  4. Seeds standard policy pack (attendance 75%, late fee 2%, etc.)
  5. Outputs credentials securely

Run AFTER `alembic upgrade head`:
    python scripts/onboard_institution.py

Or non-interactively via env vars:
    ONBOARD_ORG_NAME="Woxsen University" \\
    ONBOARD_SLUG="woxsen" \\
    ONBOARD_ADMIN_EMAIL="admin@woxsen.edu.in" \\
    python scripts/onboard_institution.py --non-interactive
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt
import psycopg2
from psycopg2.extras import RealDictCursor

from server.core.settings import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _connect() -> psycopg2.extensions.connection:
    conn = psycopg2.connect(settings.database_url, cursor_factory=RealDictCursor)
    conn.autocommit = False
    return conn


def _ask(prompt: str, default: str = "", secret: bool = False) -> str:
    if secret:
        value = getpass.getpass(f"{prompt} [{default or '(hidden)'}]: ").strip()
    else:
        value = input(f"{prompt} [{default}]: ").strip()
    return value or default


def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print('─' * 60)


# ---------------------------------------------------------------------------
# Step 1 — Organization
# ---------------------------------------------------------------------------

DEFAULT_SCHOOLS = [
    "School of Business",
    "School of Design",
    "School of Medicine",
    "School of Engineering",
    "School of Law",
    "School of Biosciences",
    "School of Art & Humanities",
]

STANDARD_POLICIES = [
    ("academics.attendance.min_percentage",      "75.0",  "Minimum attendance % required to sit exams",       "academics"),
    ("admissions.eligibility.min_academic_pct",  "55.0",  "Min academic % for AUTO_PROCEED eligibility",      "admissions"),
    ("admissions.offer_letter.validity_days",    "30",    "Days offer letter remains valid for fee payment",  "admissions"),
    ("finance.fee.overdue_grace_days",           "7",     "Grace period after due date before overdue flag",  "finance"),
    ("finance.fee.late_penalty_pct",             "2.0",   "Monthly late fee penalty percentage",              "finance"),
    ("finance.scholarship.max_pct",              "100.0", "Maximum scholarship discount percentage",          "finance"),
    ("hr.leave.casual_days_per_year",            "12",    "Casual leave entitlement per year",                "hr"),
    ("hr.leave.sick_days_per_year",              "10",    "Sick leave entitlement per year",                  "hr"),
    ("hr.leave.earned_days_per_year",            "30",    "Earned leave entitlement per year",                "hr"),
    ("exams.marks.min_passing_pct",              "40.0",  "Minimum % marks required to pass an exam",         "examinations"),
]


def create_organization(cur, name: str, slug: str, city: str, state: str,
                         entity_type: str = "STANDALONE") -> str:
    org_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO organizations (id, name, slug, status, entity_type, metadata)
        VALUES (%s, %s, %s, 'ACTIVE', %s, %s)
        """,
        (org_id, name, slug, entity_type,
         json.dumps({"city": city, "state": state, "onboarded_at": datetime.now(timezone.utc).isoformat()})),
    )
    print(f"  ✓ Organization created: {org_id}")
    return org_id


# ---------------------------------------------------------------------------
# Step 2 — Departments / Schools
# ---------------------------------------------------------------------------

def create_departments(cur, org_id: str, schools: list[str]) -> list[str]:
    dept_ids = []
    for school in schools:
        dept_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO departments (id, org_id, name, code, status)
            VALUES (%s, %s, %s, %s, 'ACTIVE')
            ON CONFLICT DO NOTHING
            """,
            (dept_id, org_id, school,
             school.upper().replace(" ", "_")[:12]),
        )
        dept_ids.append(dept_id)
        print(f"  ✓ Department: {school}")
    return dept_ids


# ---------------------------------------------------------------------------
# Step 3 — Admin accounts
# ---------------------------------------------------------------------------

def create_user(cur, org_id: str, email: str, name: str, role: str,
                password: str) -> str:
    user_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO users
            (id, tenant_id, username, email, display_name, role, status, password_hash, actor_type)
        VALUES (%s, %s, %s, %s, %s, %s, 'ACTIVE', %s, 'human')
        ON CONFLICT (tenant_id, email) DO NOTHING
        """,
        (user_id, org_id, email, email, name, role, _hash(password)),
    )
    return user_id


# ---------------------------------------------------------------------------
# Step 4 — Standard policy pack
# ---------------------------------------------------------------------------

def seed_policies(cur, org_id: str) -> None:
    for key, value, description, category in STANDARD_POLICIES:
        cur.execute(
            "SELECT id FROM institution_policies WHERE org_id = %s AND key = %s",
            (org_id, key),
        )
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO institution_policies (id, org_id, key, value, description, category)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (str(uuid.uuid4()), org_id, key, value, description, category),
            )
    print(f"  ✓ {len(STANDARD_POLICIES)} standard policies seeded")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="ALIS Institution Onboarding")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Read all values from env vars (no prompts)")
    args = parser.parse_args()
    ni = args.non_interactive

    print("\n╔══════════════════════════════════════════════╗")
    print("║   ALIS — Institution Onboarding Wizard       ║")
    print("╚══════════════════════════════════════════════╝")

    # ── Gather inputs ──────────────────────────────────────────
    _section("Step 1/4 — Organization Details")
    org_name  = os.getenv("ONBOARD_ORG_NAME",  "") if ni else _ask("Institution name",  "Demo University")
    org_slug  = os.getenv("ONBOARD_SLUG",       "") if ni else _ask("Institution slug",  "demo-university")
    city      = os.getenv("ONBOARD_CITY",       "") if ni else _ask("City",              "Hyderabad")
    state     = os.getenv("ONBOARD_STATE",      "") if ni else _ask("State",             "Telangana")

    if not org_name or not org_slug:
        print("ERROR: org_name and slug are required.")
        sys.exit(1)

    _section("Step 2/4 — Schools / Departments")
    if ni:
        raw_schools = os.getenv("ONBOARD_SCHOOLS", "")
        schools = [s.strip() for s in raw_schools.split(",")] if raw_schools else DEFAULT_SCHOOLS
    else:
        print(f"Default schools: {', '.join(DEFAULT_SCHOOLS)}")
        custom = _ask("Press Enter to use defaults, or type comma-separated school names", "")
        schools = [s.strip() for s in custom.split(",")] if custom else DEFAULT_SCHOOLS

    _section("Step 3/4 — Admin Account")
    admin_email = os.getenv("ONBOARD_ADMIN_EMAIL", "") if ni else _ask("Super Admin email", "admin@university.edu")
    admin_name  = os.getenv("ONBOARD_ADMIN_NAME",  "") if ni else _ask("Super Admin name",  "System Administrator")
    if ni:
        admin_pw = os.getenv("ONBOARD_ADMIN_PASSWORD", "Admin@1234!")
    else:
        admin_pw = _ask("Super Admin password (min 12 chars)", "Admin@1234!", secret=True)
        confirm  = _ask("Confirm password", "", secret=True)
        if admin_pw != confirm:
            print("ERROR: Passwords do not match.")
            sys.exit(1)

    if len(admin_pw) < 12:
        print("ERROR: Password must be at least 12 characters.")
        sys.exit(1)

    # ── Execute ────────────────────────────────────────────────
    _section("Step 4/4 — Provisioning")
    conn = _connect()
    cur = conn.cursor()

    try:
        # Check slug not taken
        cur.execute("SELECT id FROM organizations WHERE slug = %s", (org_slug,))
        if cur.fetchone():
            print(f"ERROR: An organization with slug '{org_slug}' already exists.")
            sys.exit(1)

        org_id = create_organization(cur, org_name, org_slug, city, state)
        create_departments(cur, org_id, schools)

        admin_id = create_user(cur, org_id, admin_email, admin_name, "SUPER_ADMIN", admin_pw)
        print(f"  ✓ Super Admin created: {admin_email}")

        seed_policies(cur, org_id)

        conn.commit()
        print(f"\n{'═' * 60}")
        print("  ONBOARDING COMPLETE")
        print(f"  Organization ID : {org_id}")
        print(f"  Admin User ID   : {admin_id}")
        print(f"  Login email     : {admin_email}")
        print(f"  Password        : {'[hidden — as supplied]' if ni else admin_pw}")
        print(f"  Slug (tenant)   : {org_slug}")
        print(f"  Schools         : {len(schools)}")
        print(f"  Policies seeded : {len(STANDARD_POLICIES)}")
        print(f"{'═' * 60}\n")
        print("Next steps:")
        print("  1. Set VITE_TENANT_ID=" + org_slug + " in your .env")
        print("  2. Log in at /login with the Super Admin credentials above")
        print("  3. Create additional staff accounts in Admin → Users")
        print("  4. Run `python scripts/onboard_institution.py` again for additional campuses\n")

    except Exception as exc:
        conn.rollback()
        print(f"\nERROR during provisioning — rolled back all changes.\n{exc}")
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
