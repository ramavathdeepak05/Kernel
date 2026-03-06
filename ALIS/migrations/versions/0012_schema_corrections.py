"""Schema corrections — align DB with current codebase

Revision ID: 0012
Revises: 0011
Create Date: 2026-03-06

Problems fixed:
  1. `users` — 0001 had org_id/name schema; code uses tenant_id/username/display_name/actor_type/is_deleted
  2. `audit_ledger` — 0001 had org_id schema; AuditLedger uses hash-chain schema (tenant_id/hash/previous_hash/timestamp)
  3. `approval_requests` — 0001 had old quorum schema; E02-S02 uses tenant_id/action_type/config_id/required_roles/mode/required_count
  4. `approval_actions` — missing entirely; referenced by approvals_router
  5. `organizations` (American) — missing; 0001 only had `organisations` (British) with different schema
  6. `custom_roles` — missing; referenced by roles_router
  7. `custom_role_permissions` — missing; referenced by roles_router
  8. `user_custom_roles` — missing; referenced by users_router/roles_router
  9. `policy_registry` — missing; referenced by policy_service
 10. Missing indexes on FK columns that are queried frequently
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # 1. USERS — Drop old schema, recreate with correct column names
    #    0001 had: org_id, email, phone, name, role, status, password_hash, metadata
    #    Code uses: tenant_id, username, email, display_name, role, status,
    #               password_hash, actor_type, is_deleted
    # =========================================================================
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("""
    CREATE TABLE users (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id       TEXT NOT NULL,
        username        TEXT NOT NULL,
        email           TEXT,
        display_name    TEXT,
        password_hash   TEXT,
        role            TEXT NOT NULL,
        actor_type      TEXT NOT NULL DEFAULT 'human',
        status          TEXT NOT NULL DEFAULT 'ACTIVE',
        is_deleted      BOOLEAN NOT NULL DEFAULT FALSE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ,
        CONSTRAINT uq_user_username_tenant UNIQUE (tenant_id, username)
    )""")
    op.execute("CREATE INDEX idx_users_tenant ON users(tenant_id, status) WHERE is_deleted = FALSE")
    op.execute("CREATE INDEX idx_users_email ON users(tenant_id, email) WHERE is_deleted = FALSE")
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY users_tenant_isolation ON users
        USING (tenant_id = current_setting('alis.current_tenant', TRUE))
    """)

    # =========================================================================
    # 2. AUDIT_LEDGER — Drop old org_id schema, recreate with hash-chain schema
    #    AuditLedger.log() inserts: tenant_id, actor_id, actor_role, action,
    #    entity_type, entity_id, metadata, timestamp, previous_hash, hash
    # =========================================================================
    op.execute("DROP TABLE IF EXISTS audit_ledger CASCADE")
    op.execute("""
    CREATE TABLE audit_ledger (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id       TEXT NOT NULL,
        actor_id        TEXT NOT NULL,
        actor_role      TEXT,
        action          TEXT NOT NULL,
        entity_type     TEXT,
        entity_id       TEXT,
        metadata        JSONB,
        timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        previous_hash   TEXT,
        hash            TEXT NOT NULL
    )""")
    op.execute("CREATE INDEX idx_audit_tenant_ts ON audit_ledger(tenant_id, timestamp DESC)")
    op.execute("CREATE INDEX idx_audit_entity ON audit_ledger(entity_type, entity_id)")
    op.execute("CREATE INDEX idx_audit_action ON audit_ledger(tenant_id, action)")
    # Hash chain integrity — look up latest entry by tenant
    op.execute("CREATE INDEX idx_audit_latest ON audit_ledger(tenant_id, id DESC)")

    # =========================================================================
    # 3. APPROVAL_REQUESTS — Drop old quorum schema, recreate with E02-S02 schema
    #    0001 had: org_id, workflow_id, quorum_required, approvals, metadata, decided_at
    #    Code uses: tenant_id, action_type, config_id, required_roles, mode,
    #               required_count, context, resolved_at, resolution_reason
    # =========================================================================
    op.execute("DROP TABLE IF EXISTS approval_requests CASCADE")
    op.execute("""
    CREATE TABLE approval_requests (
        id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id           TEXT NOT NULL,
        entity_type         TEXT NOT NULL,
        entity_id           TEXT NOT NULL,
        action_type         TEXT NOT NULL,
        config_id           TEXT NOT NULL,
        status              TEXT NOT NULL DEFAULT 'PENDING',
        requested_by        TEXT NOT NULL,
        required_roles      JSONB NOT NULL DEFAULT '[]',
        mode                TEXT NOT NULL DEFAULT 'single'
                                CHECK (mode IN ('single', 'any', 'all')),
        required_count      INTEGER NOT NULL DEFAULT 1,
        context             JSONB,
        resolved_at         TIMESTAMPTZ,
        resolution_reason   TEXT,
        created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    op.execute("CREATE INDEX idx_approval_req_tenant ON approval_requests(tenant_id, status)")
    op.execute("CREATE INDEX idx_approval_req_entity ON approval_requests(entity_type, entity_id)")
    op.execute("CREATE INDEX idx_approval_req_by ON approval_requests(requested_by, tenant_id)")
    op.execute("ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY approval_requests_tenant_isolation ON approval_requests
        USING (tenant_id = current_setting('alis.current_tenant', TRUE))
    """)

    # =========================================================================
    # 4. APPROVAL_ACTIONS — new table (was missing entirely)
    #    INSERT: id, tenant_id, request_id, actor_id, actor_role, action, comment, acted_at
    # =========================================================================
    op.execute("""
    CREATE TABLE approval_actions (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id   TEXT NOT NULL,
        request_id  UUID NOT NULL REFERENCES approval_requests(id) ON DELETE CASCADE,
        actor_id    TEXT NOT NULL,
        actor_role  TEXT NOT NULL,
        action      TEXT NOT NULL CHECK (action IN ('approve', 'reject')),
        comment     TEXT,
        acted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_approval_actor UNIQUE (request_id, actor_id)
    )""")
    op.execute("CREATE INDEX idx_approval_actions_req ON approval_actions(request_id, acted_at)")
    op.execute("ALTER TABLE approval_actions ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY approval_actions_tenant_isolation ON approval_actions
        USING (tenant_id = current_setting('alis.current_tenant', TRUE))
    """)

    # =========================================================================
    # 5. ORGANIZATIONS (American spelling) — new table
    #    0001 had `organisations` (British) with a different schema.
    #    Code uses `organizations` with: tenant_id, name, code, parent_id,
    #    status, is_deleted, created_by, created_at, updated_at
    # =========================================================================
    op.execute("""
    CREATE TABLE organizations (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id   TEXT NOT NULL,
        name        TEXT NOT NULL,
        code        TEXT NOT NULL,
        parent_id   UUID REFERENCES organizations(id),
        status      TEXT NOT NULL DEFAULT 'ACTIVE',
        is_deleted  BOOLEAN NOT NULL DEFAULT FALSE,
        created_by  TEXT NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ,
        CONSTRAINT uq_org_code_tenant UNIQUE (tenant_id, code)
    )""")
    op.execute("CREATE INDEX idx_org_tenant ON organizations(tenant_id, status) WHERE is_deleted = FALSE")
    op.execute("CREATE INDEX idx_org_parent ON organizations(parent_id) WHERE parent_id IS NOT NULL")
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY organizations_tenant_isolation ON organizations
        USING (tenant_id = current_setting('alis.current_tenant', TRUE))
    """)

    # =========================================================================
    # 6. CUSTOM_ROLES — new table (was missing)
    #    INSERT: id, tenant_id, module, role_name, description, status, created_by, created_at, updated_at
    # =========================================================================
    op.execute("""
    CREATE TABLE custom_roles (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id   TEXT NOT NULL,
        module      TEXT,
        role_name   TEXT NOT NULL,
        description TEXT,
        status      TEXT NOT NULL DEFAULT 'ACTIVE',
        created_by  TEXT NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ,
        CONSTRAINT uq_custom_role_name_tenant UNIQUE (tenant_id, role_name)
    )""")
    op.execute("CREATE INDEX idx_custom_roles_tenant ON custom_roles(tenant_id, status)")
    op.execute("CREATE INDEX idx_custom_roles_module ON custom_roles(tenant_id, module)")
    op.execute("ALTER TABLE custom_roles ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY custom_roles_tenant_isolation ON custom_roles
        USING (tenant_id = current_setting('alis.current_tenant', TRUE))
    """)

    # =========================================================================
    # 7. CUSTOM_ROLE_PERMISSIONS — new table (was missing)
    #    INSERT: id, tenant_id, role_id, permission, status, requested_by, requested_at
    # =========================================================================
    op.execute("""
    CREATE TABLE custom_role_permissions (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id       TEXT NOT NULL,
        role_id         UUID NOT NULL REFERENCES custom_roles(id) ON DELETE CASCADE,
        permission      TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'PENDING'
                            CHECK (status IN ('PENDING', 'APPROVED', 'DENIED')),
        requested_by    TEXT NOT NULL,
        requested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        reviewed_by     TEXT,
        reviewed_at     TIMESTAMPTZ,
        review_note     TEXT
    )""")
    op.execute("CREATE INDEX idx_crp_role ON custom_role_permissions(role_id, status)")
    op.execute("CREATE INDEX idx_crp_tenant_pending ON custom_role_permissions(tenant_id, status) WHERE status = 'PENDING'")
    op.execute("ALTER TABLE custom_role_permissions ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY custom_role_permissions_tenant_isolation ON custom_role_permissions
        USING (tenant_id = current_setting('alis.current_tenant', TRUE))
    """)

    # =========================================================================
    # 8. USER_CUSTOM_ROLES — new table (was missing)
    #    INSERT: id, tenant_id, user_id, role_id, assigned_by, assigned_at
    # =========================================================================
    op.execute("""
    CREATE TABLE user_custom_roles (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id   TEXT NOT NULL,
        user_id     UUID NOT NULL,
        role_id     UUID NOT NULL REFERENCES custom_roles(id) ON DELETE CASCADE,
        assigned_by TEXT NOT NULL,
        assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_user_custom_role UNIQUE (user_id, role_id)
    )""")
    op.execute("CREATE INDEX idx_ucr_user ON user_custom_roles(user_id, tenant_id)")
    op.execute("CREATE INDEX idx_ucr_role ON user_custom_roles(role_id)")
    op.execute("ALTER TABLE user_custom_roles ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY user_custom_roles_tenant_isolation ON user_custom_roles
        USING (tenant_id = current_setting('alis.current_tenant', TRUE))
    """)

    # =========================================================================
    # 9. POLICY_REGISTRY — new table (was missing)
    #    INSERT: id, tenant_id, policy_type, name, description, parameters,
    #            version, status, effective_from, effective_to, content_hash,
    #            created_by, created_at, updated_at, module
    # =========================================================================
    op.execute("""
    CREATE TABLE policy_registry (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tenant_id       TEXT NOT NULL,
        policy_type     TEXT NOT NULL,
        name            TEXT NOT NULL,
        description     TEXT NOT NULL DEFAULT '',
        parameters      JSONB NOT NULL DEFAULT '{}',
        version         INTEGER NOT NULL DEFAULT 1,
        status          TEXT NOT NULL DEFAULT 'DRAFT'
                            CHECK (status IN ('DRAFT', 'SUBMITTED', 'APPROVED', 'ACTIVE', 'SUPERSEDED', 'ARCHIVED')),
        effective_from  TIMESTAMPTZ NOT NULL,
        effective_to    TIMESTAMPTZ,
        content_hash    TEXT NOT NULL,
        created_by      TEXT NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at      TIMESTAMPTZ,
        module          TEXT
    )""")
    op.execute("CREATE INDEX idx_policy_tenant_type ON policy_registry(tenant_id, policy_type, status)")
    op.execute("CREATE INDEX idx_policy_tenant_status ON policy_registry(tenant_id, status)")
    op.execute("CREATE INDEX idx_policy_effective ON policy_registry(tenant_id, effective_from, effective_to)")
    op.execute("ALTER TABLE policy_registry ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY policy_registry_tenant_isolation ON policy_registry
        USING (tenant_id = current_setting('alis.current_tenant', TRUE))
    """)

    # =========================================================================
    # 10. MISSING INDEXES on existing tables
    #     These FK columns are queried frequently but had no indexes in 0001-0011
    # =========================================================================

    # admission_records — queried by applicant_id in enrollment_handover
    # and by payment_reference in confirmation
    op.execute("CREATE INDEX IF NOT EXISTS idx_admission_records_applicant ON admission_records(applicant_id, org_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_admission_records_payment ON admission_records(payment_reference, org_id)")

    # offer_letters — queried by applicant_id in offer_letter service
    op.execute("CREATE INDEX IF NOT EXISTS idx_offer_letters_applicant ON offer_letters(applicant_id, org_id)")

    # application_documents — queried by applicant_id in document verification
    op.execute("CREATE INDEX IF NOT EXISTS idx_app_docs_applicant ON application_documents(applicant_id, org_id)")

    # counsellor_assignments — queried by applicant_id
    op.execute("CREATE INDEX IF NOT EXISTS idx_counsellor_assign_applicant ON counsellor_assignments(applicant_id, org_id)")

    # students — queried by org_id + email for profile lookups
    op.execute("CREATE INDEX IF NOT EXISTS idx_students_email ON students(org_id, email)")

    # course_enrollments — org_id missing index (module-level queries filter by org)
    op.execute("CREATE INDEX IF NOT EXISTS idx_enrollments_org ON course_enrollments(org_id, academic_year)")

    # grades — org_id filter
    op.execute("CREATE INDEX IF NOT EXISTS idx_grades_org ON grades(org_id, academic_year)")


def downgrade() -> None:
    # Remove new indexes
    op.execute("DROP INDEX IF EXISTS idx_grades_org")
    op.execute("DROP INDEX IF EXISTS idx_enrollments_org")
    op.execute("DROP INDEX IF EXISTS idx_students_email")
    op.execute("DROP INDEX IF EXISTS idx_counsellor_assign_applicant")
    op.execute("DROP INDEX IF EXISTS idx_app_docs_applicant")
    op.execute("DROP INDEX IF EXISTS idx_offer_letters_applicant")
    op.execute("DROP INDEX IF EXISTS idx_admission_records_payment")
    op.execute("DROP INDEX IF EXISTS idx_admission_records_applicant")

    # Drop new tables (order respects FK dependencies)
    op.execute("DROP TABLE IF EXISTS policy_registry CASCADE")
    op.execute("DROP TABLE IF EXISTS user_custom_roles CASCADE")
    op.execute("DROP TABLE IF EXISTS custom_role_permissions CASCADE")
    op.execute("DROP TABLE IF EXISTS custom_roles CASCADE")
    op.execute("DROP TABLE IF EXISTS organizations CASCADE")
    op.execute("DROP TABLE IF EXISTS approval_actions CASCADE")
    op.execute("DROP TABLE IF EXISTS approval_requests CASCADE")
    op.execute("DROP TABLE IF EXISTS audit_ledger CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
