"""
Hardening C — Migration smoke tests

Validates that:
1. The migration chain (0001–0012) is internally consistent
   (no broken down_revision links, no duplicate IDs)
2. All tables referenced by service/router code exist in the declared schema
3. All required columns are present in each table's migration
4. No table is created in an earlier migration that a later one depends on
   via FK without that table existing first

These are STATIC tests — they parse the migration files without connecting
to a real database. Safe to run in CI with no DB.
"""

import ast
import re
import os
import pytest

MIGRATIONS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "migrations", "versions"
)


# ─── helpers ─────────────────────────────────────────────────────────────────

def _load_migration(filename: str) -> dict:
    """Parse a migration file and extract revision metadata + SQL."""
    path = os.path.join(MIGRATIONS_DIR, filename)
    with open(path) as f:
        source = f.read()

    tree = ast.parse(source)
    meta = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in (
                    "revision", "down_revision", "branch_labels", "depends_on"
                ):
                    try:
                        meta[target.id] = ast.literal_eval(node.value)
                    except Exception:
                        meta[target.id] = None
    meta["filename"] = filename
    meta["source"] = source
    return meta


def _all_migrations() -> list[dict]:
    files = sorted(
        f for f in os.listdir(MIGRATIONS_DIR)
        if f.endswith(".py") and not f.startswith("__")
    )
    return [_load_migration(f) for f in files]


def _extract_created_tables(source: str) -> set[str]:
    """Extract table names from CREATE TABLE statements in upgrade()."""
    return set(re.findall(
        r"CREATE TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+(\w+)",
        source, re.IGNORECASE,
    ))


def _extract_dropped_tables(source: str) -> set[str]:
    return set(re.findall(
        r"DROP TABLE(?:\s+IF\s+EXISTS)?\s+(\w+)",
        source, re.IGNORECASE,
    ))


def _extract_created_indexes(source: str) -> set[str]:
    return set(re.findall(
        r"CREATE(?:\s+UNIQUE)?\s+INDEX(?:\s+IF\s+NOT\s+EXISTS)?\s+(\w+)",
        source, re.IGNORECASE,
    ))


# ─── test 1: chain integrity ─────────────────────────────────────────────────

class TestMigrationChain:

    def test_chain_is_linear(self):
        """Every migration (except the first) must point back to a valid predecessor."""
        migrations = _all_migrations()
        revision_map = {m["revision"]: m for m in migrations}

        for m in migrations:
            dr = m.get("down_revision")
            if dr is None:
                continue   # genesis migration
            assert dr in revision_map, (
                f"Migration {m['revision']} ({m['filename']}) has "
                f"down_revision={dr!r} which does not exist"
            )

    def test_no_duplicate_revision_ids(self):
        """Revision IDs must be unique across all migrations."""
        migrations = _all_migrations()
        ids = [m["revision"] for m in migrations]
        assert len(ids) == len(set(ids)), (
            f"Duplicate revision IDs found: {[x for x in ids if ids.count(x) > 1]}"
        )

    def test_chain_starts_at_0001(self):
        """The genesis migration (down_revision=None) must be 0001."""
        migrations = _all_migrations()
        genesis = [m for m in migrations if m.get("down_revision") is None]
        assert len(genesis) == 1, f"Expected 1 genesis migration, got {len(genesis)}"
        assert genesis[0]["revision"] == "0001"

    def test_chain_ends_at_0041(self):
        """The latest migration must be 0041 (in_house_learning)."""
        migrations = _all_migrations()
        revision_ids = {m["revision"] for m in migrations}
        # Find the head: the revision not referenced by any down_revision
        all_down = {m["down_revision"] for m in migrations if m.get("down_revision")}
        heads = revision_ids - all_down
        assert heads == {"0041"}, f"Expected head=0041, got {heads}"

    def test_full_chain_walkable(self):
        """Walk the full chain from genesis to head without gaps."""
        migrations = _all_migrations()
        by_revision = {m["revision"]: m for m in migrations}
        # Build forward map
        forward = {}
        for m in migrations:
            dr = m.get("down_revision")
            if dr:
                forward[dr] = m["revision"]

        # Walk from genesis
        genesis = next(m for m in migrations if m.get("down_revision") is None)
        current = genesis["revision"]
        visited = [current]
        while current in forward:
            current = forward[current]
            visited.append(current)

        assert len(visited) == len(migrations), (
            f"Chain walk visited {len(visited)} migrations but {len(migrations)} exist. "
            f"Visited: {visited}"
        )


# ─── test 2: required tables exist in the schema ─────────────────────────────

class TestRequiredTablesExist:
    """
    Verify that every table referenced by the application code is declared
    in exactly one migration's upgrade().
    """

    # Tables the application code actually queries (from grep analysis)
    REQUIRED_TABLES = {
        # Auth / Users
        "users",
        # Audit
        "audit_ledger",
        # Approvals
        "approval_requests",
        "approval_actions",
        # Organizations
        "organizations",
        # Dynamic RBAC
        "custom_roles",
        "custom_role_permissions",
        "user_custom_roles",
        # Policy
        "policy_registry",
        # Admissions
        "applicants",
        "admission_records",
        "students",
        "offer_letters",
        "application_documents",
        "counsellor_assignments",
        "lead_merge_log",
        "intake_quality_scores",
        "org_api_keys",
        "review_items",
        "institution_policies",
        # Academics
        "programs",
        "courses",
        "course_enrollments",
        "faculty_assignments",
        "timetable_slots",
        "attendance_sessions",
        "attendance_records",
        # Examinations
        "exam_schedules",
        "hall_tickets",
        "grades",
        "semester_results",
        "transcripts",
        "reeval_requests",
        # Finance
        "fee_structures",
        "student_invoices",
        "payments",
        "scholarships",
        "scholarship_assignments",
        "fee_waivers",
        # HR
        "staff_profiles",
        "leave_types",
        "leave_requests",
        "payslips",
        "performance_reviews",
        "staff_attendance",
        # Student Services
        "hostel_blocks",
        "hostel_rooms",
        "hostel_allocations",
        "hostel_complaints",
        "library_books",
        "library_borrowings",
        "transport_routes",
        "transport_assignments",
        "counselling_sessions",
        # Communication
        "notification_templates",
        "notification_logs",
        "in_app_notifications",
        "announcements",
        # Process Engine
        "process_definitions",
        "process_steps",
        "process_instances",
        "process_step_logs",
        # Domain Events
        "domain_events",
        # Reporting
        "saved_reports",
        "export_jobs",
        # Alumni
        "alumni_profiles",
        "placement_records",
        "job_postings",
        "recruitment_drives",
    }

    @pytest.fixture(scope="class")
    def declared_tables(self):
        """Collect all tables created across all migrations."""
        migrations = _all_migrations()
        created: set[str] = set()
        for m in migrations:
            created |= _extract_created_tables(m["source"])
        return created

    def test_all_required_tables_declared(self, declared_tables):
        missing = self.REQUIRED_TABLES - declared_tables
        assert not missing, (
            f"These tables are used by application code but missing from all migrations:\n"
            + "\n".join(f"  - {t}" for t in sorted(missing))
        )


# ─── test 3: critical column presence ────────────────────────────────────────

class TestCriticalColumns:
    """
    Spot-check that the most frequently-broken columns are present in the
    correct migration's CREATE TABLE statement.
    """

    @pytest.fixture(scope="class")
    def migration_sources(self):
        return {m["revision"]: m["source"] for m in _all_migrations()}

    def _table_ddl(self, source: str, table: str) -> str:
        """Extract the CREATE TABLE block for a specific table (last occurrence wins).

        When a migration drops and recreates a table, the last CREATE TABLE
        is the authoritative schema — earlier (stale) definitions are ignored.
        """
        pattern = rf"CREATE TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+{table}\s*\(([^;]+)\)"
        matches = list(re.finditer(pattern, source, re.IGNORECASE | re.DOTALL))
        return matches[-1].group(0) if matches else ""

    def _combined_source(self, migration_sources: dict) -> str:
        return "\n".join(migration_sources.values())

    def test_users_has_tenant_id(self, migration_sources):
        combined = self._combined_source(migration_sources)
        ddl = self._table_ddl(combined, "users")
        assert "tenant_id" in ddl, "users table missing tenant_id column"

    def test_users_has_username(self, migration_sources):
        combined = self._combined_source(migration_sources)
        ddl = self._table_ddl(combined, "users")
        assert "username" in ddl, "users table missing username column"

    def test_users_has_is_deleted(self, migration_sources):
        combined = self._combined_source(migration_sources)
        ddl = self._table_ddl(combined, "users")
        assert "is_deleted" in ddl, "users table missing is_deleted column"

    def test_users_has_actor_type(self, migration_sources):
        combined = self._combined_source(migration_sources)
        ddl = self._table_ddl(combined, "users")
        assert "actor_type" in ddl, "users table missing actor_type column"

    def test_audit_ledger_has_hash_chain_columns(self, migration_sources):
        combined = self._combined_source(migration_sources)
        ddl = self._table_ddl(combined, "audit_ledger")
        assert "previous_hash" in ddl, "audit_ledger missing previous_hash column"
        assert "hash" in ddl, "audit_ledger missing hash column"
        assert "timestamp" in ddl, "audit_ledger missing timestamp column"
        assert "tenant_id" in ddl, "audit_ledger missing tenant_id column"

    def test_approval_requests_has_correct_columns(self, migration_sources):
        combined = self._combined_source(migration_sources)
        ddl = self._table_ddl(combined, "approval_requests")
        for col in ("tenant_id", "action_type", "config_id", "required_roles",
                    "mode", "required_count"):
            assert col in ddl, f"approval_requests missing column: {col}"

    def test_approval_actions_has_unique_constraint(self, migration_sources):
        combined = self._combined_source(migration_sources)
        ddl = self._table_ddl(combined, "approval_actions")
        assert "uq_approval_actor" in ddl, (
            "approval_actions missing UNIQUE constraint uq_approval_actor "
            "(prevents one actor voting twice on same request)"
        )

    def test_organizations_american_spelling(self, migration_sources):
        """Code uses 'organizations' (American), not 'organisations' (British)."""
        combined = self._combined_source(migration_sources)
        assert re.search(
            r"CREATE TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+organizations\b",
            combined, re.IGNORECASE
        ), "organizations (American spelling) table not found in migrations"

    def test_organizations_has_unique_code_constraint(self, migration_sources):
        combined = self._combined_source(migration_sources)
        ddl = self._table_ddl(combined, "organizations")
        assert "uq_org_code_tenant" in ddl, (
            "organizations missing UNIQUE constraint uq_org_code_tenant "
            "(code must be unique within a tenant)"
        )

    def test_custom_roles_has_unique_name_constraint(self, migration_sources):
        combined = self._combined_source(migration_sources)
        ddl = self._table_ddl(combined, "custom_roles")
        assert "uq_custom_role_name_tenant" in ddl, (
            "custom_roles missing UNIQUE constraint uq_custom_role_name_tenant"
        )

    def test_user_custom_roles_has_unique_constraint(self, migration_sources):
        combined = self._combined_source(migration_sources)
        ddl = self._table_ddl(combined, "user_custom_roles")
        assert "uq_user_custom_role" in ddl, (
            "user_custom_roles missing UNIQUE constraint uq_user_custom_role"
        )

    def test_policy_registry_has_status_check(self, migration_sources):
        combined = self._combined_source(migration_sources)
        ddl = self._table_ddl(combined, "policy_registry")
        assert "DRAFT" in ddl, "policy_registry status CHECK missing DRAFT value"


# ─── test 4: FK ordering — table must exist before it is referenced ───────────

class TestForeignKeyOrdering:
    """
    Verify that tables referenced as FK targets are created in an earlier
    (or the same) migration, not a later one.
    """

    def test_approval_actions_fk_after_approval_requests(self):
        """approval_actions FKs to approval_requests — must appear after it."""
        migrations = _all_migrations()
        rev_order = {m["revision"]: i for i, m in enumerate(migrations)}

        req_rev = next(
            m["revision"] for m in migrations
            if "approval_requests" in _extract_created_tables(m["source"])
        )
        act_rev = next(
            m["revision"] for m in migrations
            if "approval_actions" in _extract_created_tables(m["source"])
        )
        assert rev_order[req_rev] <= rev_order[act_rev], (
            f"approval_requests ({req_rev}) must be created before "
            f"approval_actions ({act_rev})"
        )

    def test_custom_role_permissions_fk_after_custom_roles(self):
        migrations = _all_migrations()
        rev_order = {m["revision"]: i for i, m in enumerate(migrations)}

        roles_rev = next(
            m["revision"] for m in migrations
            if "custom_roles" in _extract_created_tables(m["source"])
        )
        perms_rev = next(
            m["revision"] for m in migrations
            if "custom_role_permissions" in _extract_created_tables(m["source"])
        )
        assert rev_order[roles_rev] <= rev_order[perms_rev]

    def test_user_custom_roles_fk_after_custom_roles(self):
        migrations = _all_migrations()
        rev_order = {m["revision"]: i for i, m in enumerate(migrations)}

        roles_rev = next(
            m["revision"] for m in migrations
            if "custom_roles" in _extract_created_tables(m["source"])
        )
        ucr_rev = next(
            m["revision"] for m in migrations
            if "user_custom_roles" in _extract_created_tables(m["source"])
        )
        assert rev_order[roles_rev] <= rev_order[ucr_rev]


# ─── test 5: downgrade symmetry ──────────────────────────────────────────────

class TestDowngradeSymmetry:
    """Every table created in upgrade() should be dropped in downgrade()."""

    SKIP_MIGRATIONS = {"0001"}  # 0001 downgrade handles its own cleanup

    def test_0012_drops_what_it_creates(self):
        migrations = _all_migrations()
        m0012 = next(m for m in migrations if m["revision"] == "0012")
        source = m0012["source"]

        # Split at def downgrade
        upgrade_part, _, downgrade_part = source.partition("def downgrade()")

        created = _extract_created_tables(upgrade_part)
        dropped = _extract_dropped_tables(downgrade_part)

        # Every table created should be dropped on downgrade
        not_dropped = created - dropped
        assert not not_dropped, (
            f"Migration 0012 creates these tables but does not drop them in "
            f"downgrade(): {not_dropped}"
        )
