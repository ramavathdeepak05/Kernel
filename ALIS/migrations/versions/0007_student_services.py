"""Student Services module (M6)

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-05
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # E09-S01 — Hostel Management
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS hostel_blocks (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id      TEXT NOT NULL,
        name        TEXT NOT NULL,
        gender      TEXT NOT NULL DEFAULT 'ANY',  -- MALE | FEMALE | ANY
        total_rooms INT NOT NULL DEFAULT 0,
        warden_id   UUID REFERENCES users(id),
        is_active   BOOLEAN NOT NULL DEFAULT TRUE,
        UNIQUE(org_id, name)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS hostel_rooms (
        id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id      TEXT NOT NULL,
        block_id    UUID NOT NULL REFERENCES hostel_blocks(id),
        room_number TEXT NOT NULL,
        room_type   TEXT NOT NULL DEFAULT 'SHARED',  -- SINGLE | DOUBLE | TRIPLE | SHARED
        capacity    INT NOT NULL DEFAULT 2,
        floor       INT NOT NULL DEFAULT 0,
        amenities   TEXT[],
        is_active   BOOLEAN NOT NULL DEFAULT TRUE,
        UNIQUE(org_id, block_id, room_number)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS hostel_allocations (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        room_id         UUID NOT NULL REFERENCES hostel_rooms(id),
        academic_year   TEXT NOT NULL,
        check_in_date   DATE NOT NULL,
        check_out_date  DATE,
        status          TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE | VACATED | TRANSFERRED
        allocated_by    TEXT NOT NULL,
        allocated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        notes           TEXT,
        UNIQUE(student_id, academic_year)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS hostel_complaints (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        room_id         UUID REFERENCES hostel_rooms(id),
        category        TEXT NOT NULL,  -- MAINTENANCE | CLEANLINESS | SECURITY | FOOD | OTHER
        description     TEXT NOT NULL,
        status          TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN | IN_PROGRESS | RESOLVED | CLOSED
        priority        TEXT NOT NULL DEFAULT 'MEDIUM',  -- LOW | MEDIUM | HIGH | URGENT
        assigned_to     TEXT,
        resolved_at     TIMESTAMPTZ,
        resolution_note TEXT,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_hostel_alloc_student ON hostel_allocations(student_id, academic_year)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hostel_alloc_room ON hostel_allocations(room_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hostel_complaint_org ON hostel_complaints(org_id, status)")

    # -------------------------------------------------------------------------
    # E09-S02 — Library Management
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS library_books (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        isbn            TEXT,
        title           TEXT NOT NULL,
        author          TEXT NOT NULL,
        publisher       TEXT,
        edition         TEXT,
        year_published  INT,
        category        TEXT,
        total_copies    INT NOT NULL DEFAULT 1,
        available_copies INT NOT NULL DEFAULT 1,
        location        TEXT,   -- shelf/rack
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_library_book_isbn ON library_books(org_id, isbn)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_library_book_title ON library_books USING gin(to_tsvector('english', title || ' ' || author))")

    op.execute("""
    CREATE TABLE IF NOT EXISTS library_borrowings (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        book_id         UUID NOT NULL REFERENCES library_books(id),
        borrower_id     UUID NOT NULL REFERENCES users(id),
        borrower_type   TEXT NOT NULL DEFAULT 'STUDENT',  -- STUDENT | STAFF
        issued_date     DATE NOT NULL DEFAULT CURRENT_DATE,
        due_date        DATE NOT NULL,
        returned_date   DATE,
        status          TEXT NOT NULL DEFAULT 'BORROWED',  -- BORROWED | RETURNED | OVERDUE | LOST
        fine_amount     DECIMAL(8,2) NOT NULL DEFAULT 0,
        fine_paid       BOOLEAN NOT NULL DEFAULT FALSE,
        issued_by       TEXT NOT NULL
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_borrowing_borrower ON library_borrowings(borrower_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_borrowing_book ON library_borrowings(book_id, status)")

    # -------------------------------------------------------------------------
    # E09-S03 — Transport Management
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS transport_routes (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        route_name      TEXT NOT NULL,
        route_code      TEXT NOT NULL,
        stops           JSONB NOT NULL DEFAULT '[]',  -- [{name, time, order}]
        vehicle_number  TEXT,
        driver_name     TEXT,
        driver_contact  TEXT,
        capacity        INT NOT NULL DEFAULT 40,
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        UNIQUE(org_id, route_code)
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS transport_assignments (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        route_id        UUID NOT NULL REFERENCES transport_routes(id),
        stop_name       TEXT NOT NULL,
        academic_year   TEXT NOT NULL,
        pass_number     TEXT NOT NULL UNIQUE,
        valid_from      DATE NOT NULL,
        valid_to        DATE,
        status          TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE | CANCELLED
        assigned_by     TEXT NOT NULL,
        assigned_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE(student_id, academic_year)
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_transport_assign_route ON transport_assignments(route_id, status)")

    # -------------------------------------------------------------------------
    # E09-S04 — Student Counselling
    # -------------------------------------------------------------------------
    op.execute("""
    CREATE TABLE IF NOT EXISTS counselling_sessions (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        counsellor_id   UUID NOT NULL REFERENCES users(id),
        session_date    DATE NOT NULL,
        session_type    TEXT NOT NULL DEFAULT 'ACADEMIC',  -- ACADEMIC | PERSONAL | CAREER | CRISIS
        duration_mins   INT NOT NULL DEFAULT 30,
        notes           TEXT,           -- encrypted at rest ideally
        follow_up_date  DATE,
        is_confidential BOOLEAN NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")

    op.execute("""
    CREATE TABLE IF NOT EXISTS counselling_referrals (
        id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        org_id          TEXT NOT NULL,
        student_id      UUID NOT NULL REFERENCES students(id),
        referred_by     UUID NOT NULL REFERENCES users(id),
        referred_to     TEXT NOT NULL,   -- external professional / hospital
        reason          TEXT NOT NULL,
        urgency         TEXT NOT NULL DEFAULT 'ROUTINE',  -- ROUTINE | URGENT | EMERGENCY
        status          TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | ACCEPTED | COMPLETED
        referral_date   DATE NOT NULL DEFAULT CURRENT_DATE,
        notes           TEXT
    )""")

    op.execute("CREATE INDEX IF NOT EXISTS idx_counselling_student ON counselling_sessions(student_id, session_date)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_counselling_counsellor ON counselling_sessions(counsellor_id, session_date)")

    # -------------------------------------------------------------------------
    # RLS
    # -------------------------------------------------------------------------
    for table in [
        "hostel_blocks", "hostel_rooms", "hostel_allocations", "hostel_complaints",
        "library_books", "library_borrowings",
        "transport_routes", "transport_assignments",
        "counselling_sessions", "counselling_referrals",
    ]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"""
            CREATE POLICY IF NOT EXISTS {table}_tenant_isolation
            ON {table}
            USING (org_id::text = current_setting('alis.current_tenant', TRUE))
        """)


def downgrade() -> None:
    for t in [
        "counselling_referrals", "counselling_sessions",
        "transport_assignments", "transport_routes",
        "library_borrowings", "library_books",
        "hostel_complaints", "hostel_allocations",
        "hostel_rooms", "hostel_blocks",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
