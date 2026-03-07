"""
0014 — Full admissions workflow (Stages 1–10)

Adds all tables required to implement the complete 10-stage admissions
pipeline as documented in university_admissions_workflow.md:

  Stage 1  — Lead capture & CRM (leads, lead_activities, consultants, referrals)
  Stage 2  — Application form (academic_qualifications, entrance_exam_scores,
              program_preferences; expand applicants)
  Stage 3  — Document management v2 (per-document status, re-upload tracking)
  Stage 5  — Entrance test & interview (admissions_tests, test_slots,
              test_registrations, test_scores, interview_panels,
              interview_schedules, interview_scorecards)
  Stage 6  — Merit list & waitlist (seat_matrix, merit_list_policies,
              merit_lists, merit_list_entries, waitlist_entries)
  Stage 7  — Offer management v2 (offer_responses; expand offer_letters)
  Stage 8  — Payment v2 (demand_draft_uploads, refund_requests)
  Stage 9  — Final document verification (final_verifications,
              final_verification_items, verification_discrepancies)
  Stage 10 — Enrollment provisioning (enrollment_provisioning)
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _idx(name: str, table: str, cols: str) -> None:
    op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({cols})")


# ===========================================================================
# UPGRADE
# ===========================================================================

def upgrade() -> None:

    # -----------------------------------------------------------------------
    # STAGE 1 — Lead capture & source attribution
    # -----------------------------------------------------------------------

    op.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,

            -- Contact
            full_name       TEXT NOT NULL,
            email           TEXT NOT NULL,
            phone           TEXT NOT NULL,
            city            TEXT,
            state_region    TEXT,

            -- Interest
            course_interest TEXT,
            intake_year     TEXT,           -- e.g. "2025"

            -- Source attribution
            source_type     TEXT NOT NULL DEFAULT 'WEBSITE',
            -- WEBSITE | REFERRAL_STUDENT | REFERRAL_STAFF | CONSULTANT |
            -- SOCIAL_AD | EDUCATION_FAIR | THIRD_PARTY_PORTAL | WALK_IN | OTHER
            source_detail   TEXT,           -- portal name, event name, etc.
            utm_source      TEXT,
            utm_medium      TEXT,
            utm_campaign    TEXT,
            utm_term        TEXT,
            utm_content     TEXT,

            -- Referral attribution
            referred_by_user_id TEXT,       -- for student/staff referrals
            consultant_id       UUID,       -- for third-party consultants

            -- CRM lifecycle
            status          TEXT NOT NULL DEFAULT 'NEW',
            -- NEW | CONTACTED | INTERESTED | READY_TO_APPLY | CONVERTED |
            -- NOT_INTERESTED | UNRESPONSIVE | DISQUALIFIED
            assigned_counsellor_id TEXT,
            last_contacted_at      TIMESTAMPTZ,
            next_followup_at       TIMESTAMPTZ,
            disqualify_reason      TEXT,

            -- Conversion
            converted_applicant_id UUID,    -- set when lead → applicant
            converted_at           TIMESTAMPTZ,

            metadata        JSONB NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS lead_activities (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            lead_id         UUID NOT NULL REFERENCES leads(id),
            activity_type   TEXT NOT NULL,
            -- EMAIL_SENT | SMS_SENT | CALL_LOGGED | NOTE | STATUS_CHANGE |
            -- DOCUMENT_SHARED | MEETING_SCHEDULED | WHATSAPP_SENT
            summary         TEXT NOT NULL,
            actor_id        TEXT NOT NULL,
            metadata        JSONB NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS consultants (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            name            TEXT NOT NULL,
            company_name    TEXT,
            email           TEXT NOT NULL,
            phone           TEXT NOT NULL,
            city            TEXT,
            state_region    TEXT,
            status          TEXT NOT NULL DEFAULT 'ACTIVE',
            -- ACTIVE | SUSPENDED | TERMINATED
            commission_rate DECIMAL(5,2) NOT NULL DEFAULT 0.00,
            -- Percentage of fee as commission
            commission_type TEXT NOT NULL DEFAULT 'FLAT',
            -- FLAT | PERCENTAGE
            commission_amount DECIMAL(12,2),
            -- Fixed amount if FLAT type
            portal_user_id  TEXT,           -- ALIS user linked to this consultant
            agreement_signed_at TIMESTAMPTZ,
            agreement_doc_path  TEXT,
            metadata        JSONB NOT NULL DEFAULT '{}',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS consultant_referrals (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            consultant_id   UUID NOT NULL REFERENCES consultants(id),
            lead_id         UUID REFERENCES leads(id),
            applicant_id    UUID REFERENCES applicants(id),
            -- Both filled when lead converts
            referral_code   TEXT,
            status          TEXT NOT NULL DEFAULT 'PENDING',
            -- PENDING | ENROLLED | INELIGIBLE | WITHDRAWN
            commission_status TEXT NOT NULL DEFAULT 'UNPAID',
            -- UNPAID | APPROVED | PAID | REJECTED
            commission_amount DECIMAL(12,2),
            commission_paid_at TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS referral_codes (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            code            TEXT NOT NULL,
            referrer_type   TEXT NOT NULL,  -- STUDENT | STAFF | CONSULTANT
            referrer_id     TEXT NOT NULL,  -- user_id or consultant_id
            max_uses        INT,            -- NULL = unlimited
            use_count       INT NOT NULL DEFAULT 0,
            expires_at      TIMESTAMPTZ,
            status          TEXT NOT NULL DEFAULT 'ACTIVE',
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(org_id, code)
        )
    """)

    # -----------------------------------------------------------------------
    # STAGE 2 — Application form expansion (expand existing applicants table)
    # -----------------------------------------------------------------------

    # Personal details
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS application_id TEXT UNIQUE")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS date_of_birth DATE")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS gender TEXT")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS nationality TEXT DEFAULT 'Indian'")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'GENERAL'")
    # GENERAL | SC | ST | OBC_NCL | EWS | PWD
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS aadhaar_number TEXT")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS permanent_address JSONB")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS correspondence_address JSONB")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS emergency_contact JSONB")

    # Program preferences
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS second_program_preference TEXT")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS intake_batch TEXT")
    # e.g. "July-2025"
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS study_mode TEXT DEFAULT 'FULL_TIME'")
    # FULL_TIME | PART_TIME | ONLINE

    # Intake flags
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS hostel_required BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS scholarship_required BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS has_disability BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS special_requirements TEXT")

    # Work experience (PG programs)
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS work_experience_months INT")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS work_experience_detail JSONB")

    # Declaration
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS declaration_accepted BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS declaration_accepted_at TIMESTAMPTZ")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS digital_signature TEXT")

    # Application lifecycle
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS application_fee_paid BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS application_fee_amount DECIMAL(10,2)")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS application_fee_ref TEXT")

    # Source attribution (expanded from source_channel)
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS lead_id UUID REFERENCES leads(id)")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS referred_by_user_id TEXT")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS consultant_id UUID REFERENCES consultants(id)")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS utm_source TEXT")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS utm_medium TEXT")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS utm_campaign TEXT")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS referral_code TEXT")

    # Academic qualifications (normalized — one row per level)
    op.execute("""
        CREATE TABLE IF NOT EXISTS academic_qualifications (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            applicant_id    UUID NOT NULL REFERENCES applicants(id),

            level           TEXT NOT NULL,
            -- TENTH | TWELFTH | UG | PG | DIPLOMA | OTHER
            board_university TEXT NOT NULL,
            institution_name TEXT NOT NULL,
            year_of_passing INT,
            appearing       BOOLEAN NOT NULL DEFAULT FALSE,
            -- TRUE if result awaited

            subjects        JSONB NOT NULL DEFAULT '[]',
            -- [{"name": "Physics", "marks_obtained": 89, "total_marks": 100}, ...]
            total_marks     INT,
            marks_obtained  INT,
            percentage      DECIMAL(5,2),
            cgpa            DECIMAL(4,2),    -- for UG/PG with grade system
            grade_scale     DECIMAL(4,2),    -- e.g. 10.0 for 10-point CGPA
            pass_status     TEXT DEFAULT 'PASSED',
            -- PASSED | COMPARTMENT | APPEARING | FAILED
            certificate_number TEXT,

            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ
        )
    """)

    # Entrance exam scores
    op.execute("""
        CREATE TABLE IF NOT EXISTS entrance_exam_scores (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            applicant_id    UUID NOT NULL REFERENCES applicants(id),

            exam_name       TEXT NOT NULL,
            -- JEE_MAINS | JEE_ADVANCED | NEET | CAT | MAT | XAT | SAT |
            -- UNIVERSITY_EXAM | STATE_CET | OTHER
            exam_roll_number TEXT,
            exam_year       INT,
            score           DECIMAL(10,4),  -- raw score
            percentile      DECIMAL(6,4),
            rank            INT,
            score_detail    JSONB DEFAULT '{}',
            -- section-wise breakdown
            is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
            verified_method TEXT,
            -- SELF_REPORTED | OFFICIAL_API | NTA_FILE_IMPORT | MANUAL_OFFICER

            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Program preferences (ordered list)
    op.execute("""
        CREATE TABLE IF NOT EXISTS program_preferences (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            applicant_id    UUID NOT NULL REFERENCES applicants(id),
            preference_order INT NOT NULL DEFAULT 1,
            program_name    TEXT NOT NULL,
            specialization  TEXT,
            intake_batch    TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(applicant_id, preference_order)
        )
    """)

    # -----------------------------------------------------------------------
    # STAGE 3 — Document management v2
    # -----------------------------------------------------------------------

    # Expand application_documents
    op.execute("ALTER TABLE application_documents ADD COLUMN IF NOT EXISTS doc_status TEXT NOT NULL DEFAULT 'PENDING'")
    # PENDING | UNDER_REVIEW | APPROVED | REJECTED | REUPLOAD_REQUESTED
    op.execute("ALTER TABLE application_documents ADD COLUMN IF NOT EXISTS rejection_reason TEXT")
    op.execute("ALTER TABLE application_documents ADD COLUMN IF NOT EXISTS reupload_count INT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE application_documents ADD COLUMN IF NOT EXISTS reupload_deadline TIMESTAMPTZ")
    op.execute("ALTER TABLE application_documents ADD COLUMN IF NOT EXISTS file_size_bytes INT")
    op.execute("ALTER TABLE application_documents ADD COLUMN IF NOT EXISTS file_mime_type TEXT")
    op.execute("ALTER TABLE application_documents ADD COLUMN IF NOT EXISTS original_file_name TEXT")
    op.execute("ALTER TABLE application_documents ADD COLUMN IF NOT EXISTS digilocker_verified BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE application_documents ADD COLUMN IF NOT EXISTS ocr_extracted JSONB")
    # OCR-extracted values for cross-check with application form

    # -----------------------------------------------------------------------
    # STAGE 5A — Admissions entrance tests
    # -----------------------------------------------------------------------

    op.execute("""
        CREATE TABLE IF NOT EXISTS admissions_tests (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            name            TEXT NOT NULL,
            test_type       TEXT NOT NULL,
            -- WRITTEN | ONLINE_PROCTORED | INTERVIEW_PI | INTERVIEW_GD |
            -- PORTFOLIO_REVIEW | EXTERNAL_SCORE_ONLY
            program_name    TEXT,           -- NULL = applies to all programs
            intake_batch    TEXT NOT NULL,
            mode            TEXT NOT NULL DEFAULT 'OFFLINE',
            -- ONLINE | OFFLINE | HYBRID
            duration_minutes INT,
            total_marks     INT,
            passing_marks   INT,
            sections        JSONB NOT NULL DEFAULT '[]',
            -- [{"name": "Quant", "max_marks": 50}, ...]
            instructions    TEXT,
            proctoring_tool TEXT,           -- Mettl | TalView | iProctor | NONE
            external_test   BOOLEAN NOT NULL DEFAULT FALSE,
            -- TRUE for JEE/NEET — no slot scheduling needed
            status          TEXT NOT NULL DEFAULT 'DRAFT',
            -- DRAFT | PUBLISHED | ONGOING | COMPLETED | CANCELLED
            created_by      TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS test_slots (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            test_id         UUID NOT NULL REFERENCES admissions_tests(id),
            slot_date       DATE NOT NULL,
            start_time      TIME NOT NULL,
            end_time        TIME NOT NULL,
            venue           TEXT,           -- NULL for online
            online_link     TEXT,           -- NULL for offline
            capacity        INT NOT NULL,
            booked_count    INT NOT NULL DEFAULT 0,
            status          TEXT NOT NULL DEFAULT 'OPEN',
            -- OPEN | FULL | CANCELLED | COMPLETED
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS test_registrations (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            test_id         UUID NOT NULL REFERENCES admissions_tests(id),
            slot_id         UUID REFERENCES test_slots(id),
            applicant_id    UUID NOT NULL REFERENCES applicants(id),
            admit_card_path TEXT,
            admit_card_sent_at TIMESTAMPTZ,
            attendance_status TEXT DEFAULT 'REGISTERED',
            -- REGISTERED | PRESENT | ABSENT | CANCELLED
            registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(test_id, applicant_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS test_scores (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            test_id         UUID NOT NULL REFERENCES admissions_tests(id),
            applicant_id    UUID NOT NULL REFERENCES applicants(id),
            total_score     DECIMAL(10,4),
            section_scores  JSONB NOT NULL DEFAULT '{}',
            -- {"Quant": 42, "Verbal": 38, ...}
            percentile      DECIMAL(6,4),
            rank_in_test    INT,
            remarks         TEXT,
            entered_by      TEXT NOT NULL,
            entered_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(test_id, applicant_id)
        )
    """)

    # -----------------------------------------------------------------------
    # STAGE 5B — Interview management
    # -----------------------------------------------------------------------

    op.execute("""
        CREATE TABLE IF NOT EXISTS interview_panels (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            name            TEXT NOT NULL,
            program_name    TEXT,
            intake_batch    TEXT NOT NULL,
            panel_members   JSONB NOT NULL DEFAULT '[]',
            -- [{"user_id": "...", "name": "...", "role": "HOD"}, ...]
            evaluation_parameters JSONB NOT NULL DEFAULT '[]',
            -- [{"name": "Communication", "max_score": 10}, ...]
            status          TEXT NOT NULL DEFAULT 'ACTIVE',
            created_by      TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS interview_schedules (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            panel_id        UUID NOT NULL REFERENCES interview_panels(id),
            applicant_id    UUID NOT NULL REFERENCES applicants(id),
            interview_type  TEXT NOT NULL DEFAULT 'PI',
            -- PI | GD | PORTFOLIO
            scheduled_at    TIMESTAMPTZ NOT NULL,
            duration_minutes INT DEFAULT 30,
            mode            TEXT NOT NULL DEFAULT 'OFFLINE',
            -- ONLINE | OFFLINE
            venue           TEXT,
            online_link     TEXT,
            calendar_invite_sent BOOLEAN NOT NULL DEFAULT FALSE,
            attendance_status TEXT DEFAULT 'SCHEDULED',
            -- SCHEDULED | COMPLETED | ABSENT | CANCELLED | RESCHEDULED
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS interview_scorecards (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            schedule_id     UUID NOT NULL REFERENCES interview_schedules(id),
            applicant_id    UUID NOT NULL REFERENCES applicants(id),
            evaluator_id    TEXT NOT NULL,
            parameter_scores JSONB NOT NULL DEFAULT '{}',
            -- {"Communication": 8, "Knowledge": 7, "Aptitude": 9, ...}
            total_score     DECIMAL(10,4),
            qualitative_remarks TEXT,
            recommendation  TEXT,
            -- STRONG_ADMIT | ADMIT | BORDERLINE | REJECT
            submitted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(schedule_id, evaluator_id)
        )
    """)

    # -----------------------------------------------------------------------
    # STAGE 6A — Seat matrix
    # -----------------------------------------------------------------------

    op.execute("""
        CREATE TABLE IF NOT EXISTS seat_matrix (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            program_name    TEXT NOT NULL,
            specialization  TEXT,
            intake_batch    TEXT NOT NULL,
            category        TEXT NOT NULL DEFAULT 'GENERAL',
            -- GENERAL | SC | ST | OBC_NCL | EWS | PWD | NRI | MANAGEMENT
            total_seats     INT NOT NULL,
            filled_seats    INT NOT NULL DEFAULT 0,
            blocked_seats   INT NOT NULL DEFAULT 0,
            -- seats held pending payment (released on timeout)
            created_by      TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ,
            UNIQUE(org_id, program_name, intake_batch, category)
        )
    """)

    # -----------------------------------------------------------------------
    # STAGE 6B — Merit list & waitlist
    # -----------------------------------------------------------------------

    op.execute("""
        CREATE TABLE IF NOT EXISTS merit_list_policies (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            program_name    TEXT NOT NULL,
            intake_batch    TEXT NOT NULL,
            formula         JSONB NOT NULL DEFAULT '{}',
            -- {"academic_pct": 0.35, "entrance_score": 0.45,
            --  "interview_score": 0.15, "diversity_bonus": 0.05}
            tiebreaker_order JSONB NOT NULL DEFAULT '[]',
            -- ["academic_pct", "entrance_score", "age"]
            waitlist_depth_factor DECIMAL(4,2) DEFAULT 1.5,
            -- multiply intake by this to size waitlist
            approved_by     TEXT,
            approved_at     TIMESTAMPTZ,
            created_by      TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(org_id, program_name, intake_batch)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS merit_lists (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            program_name    TEXT NOT NULL,
            specialization  TEXT,
            intake_batch    TEXT NOT NULL,
            category        TEXT NOT NULL DEFAULT 'GENERAL',
            list_type       TEXT NOT NULL DEFAULT 'MERIT',
            -- MERIT | WAITLIST | MANAGEMENT_QUOTA | NRI
            version         INT NOT NULL DEFAULT 1,
            -- Increment on each regeneration; only latest is ACTIVE
            status          TEXT NOT NULL DEFAULT 'DRAFT',
            -- DRAFT | UNDER_REVIEW | APPROVED | PUBLISHED | SUPERSEDED
            cutoff_score    DECIMAL(10,4),
            total_entries   INT NOT NULL DEFAULT 0,
            published_at    TIMESTAMPTZ,
            approved_by     TEXT,
            approved_at     TIMESTAMPTZ,
            generated_by    TEXT NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS merit_list_entries (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            merit_list_id   UUID NOT NULL REFERENCES merit_lists(id),
            applicant_id    UUID NOT NULL REFERENCES applicants(id),
            rank            INT NOT NULL,
            composite_score DECIMAL(10,4) NOT NULL,
            score_breakdown JSONB NOT NULL DEFAULT '{}',
            -- {"academic_pct": 8.5, "entrance_score": 9.2, ...}
            status          TEXT NOT NULL DEFAULT 'PENDING',
            -- PENDING | OFFER_SENT | ACCEPTED | DECLINED | EXPIRED | WAITLIST_ACTIVATED
            offer_sent_at   TIMESTAMPTZ,
            response_deadline TIMESTAMPTZ,
            UNIQUE(merit_list_id, applicant_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS waitlist_entries (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            merit_list_id   UUID NOT NULL REFERENCES merit_lists(id),
            applicant_id    UUID NOT NULL REFERENCES applicants(id),
            waitlist_rank   INT NOT NULL,
            composite_score DECIMAL(10,4) NOT NULL,
            status          TEXT NOT NULL DEFAULT 'WAITING',
            -- WAITING | ACTIVATED | DECLINED | EXPIRED | LAPSED
            activated_at    TIMESTAMPTZ,    -- when moved to merit list
            notification_sent_at TIMESTAMPTZ,
            response_deadline    TIMESTAMPTZ,
            UNIQUE(merit_list_id, applicant_id)
        )
    """)

    # -----------------------------------------------------------------------
    # STAGE 7 — Offer management v2
    # -----------------------------------------------------------------------

    # Expand offer_letters
    op.execute("ALTER TABLE offer_letters ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ")
    op.execute("ALTER TABLE offer_letters ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ")
    op.execute("ALTER TABLE offer_letters ADD COLUMN IF NOT EXISTS declined_at TIMESTAMPTZ")
    op.execute("ALTER TABLE offer_letters ADD COLUMN IF NOT EXISTS acceptance_status TEXT DEFAULT 'PENDING'")
    # PENDING | ACCEPTED | DECLINED | EXPIRED
    op.execute("ALTER TABLE offer_letters ADD COLUMN IF NOT EXISTS digital_signature_ref TEXT")
    op.execute("ALTER TABLE offer_letters ADD COLUMN IF NOT EXISTS merit_list_entry_id UUID REFERENCES merit_list_entries(id)")
    op.execute("ALTER TABLE offer_letters ADD COLUMN IF NOT EXISTS delivery_status TEXT DEFAULT 'PENDING'")
    # PENDING | SENT | OPENED | BOUNCED
    op.execute("ALTER TABLE offer_letters ADD COLUMN IF NOT EXISTS email_opened_at TIMESTAMPTZ")
    op.execute("ALTER TABLE offer_letters ADD COLUMN IF NOT EXISTS t3_reminder_sent BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE offer_letters ADD COLUMN IF NOT EXISTS t1_reminder_sent BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE offer_letters ADD COLUMN IF NOT EXISTS fee_structure JSONB DEFAULT '{}'")
    # Full fee breakdown shown in offer letter

    # -----------------------------------------------------------------------
    # STAGE 8 — Payment v2
    # -----------------------------------------------------------------------

    op.execute("""
        CREATE TABLE IF NOT EXISTS demand_draft_uploads (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            applicant_id    UUID NOT NULL REFERENCES applicants(id),
            dd_number       TEXT NOT NULL,
            bank_name       TEXT NOT NULL,
            branch_name     TEXT,
            amount          DECIMAL(12,2) NOT NULL,
            dd_date         DATE NOT NULL,
            scan_file_path  TEXT,
            verification_status TEXT NOT NULL DEFAULT 'PENDING',
            -- PENDING | VERIFIED | REJECTED
            verified_by     TEXT,
            verified_at     TIMESTAMPTZ,
            rejection_reason TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS refund_requests (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            applicant_id    UUID NOT NULL REFERENCES applicants(id),
            payment_id      UUID REFERENCES payments(id),
            amount_paid     DECIMAL(12,2) NOT NULL,
            refund_amount   DECIMAL(12,2) NOT NULL,
            refund_policy_slab TEXT,
            -- e.g. "BEFORE_15_DAYS_100PCT"
            reason          TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'REQUESTED',
            -- REQUESTED | UNDER_REVIEW | APPROVED | REJECTED | PROCESSED
            requested_by    TEXT NOT NULL,
            reviewed_by     TEXT,
            reviewed_at     TIMESTAMPTZ,
            review_notes    TEXT,
            processed_at    TIMESTAMPTZ,
            gateway_refund_id TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ
        )
    """)

    # -----------------------------------------------------------------------
    # STAGE 9 — Final document verification
    # -----------------------------------------------------------------------

    op.execute("""
        CREATE TABLE IF NOT EXISTS final_verifications (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            applicant_id    UUID NOT NULL REFERENCES applicants(id) UNIQUE,
            verification_mode TEXT NOT NULL DEFAULT 'IN_PERSON',
            -- IN_PERSON | DIGILOCKER | COURIER
            reporting_date  DATE,
            status          TEXT NOT NULL DEFAULT 'PENDING',
            -- PENDING | IN_PROGRESS | VERIFIED | DISCREPANCY_FOUND |
            -- CLEARED_WITH_UNDERTAKING | REJECTED
            assigned_officer TEXT,
            completed_at    TIMESTAMPTZ,
            notes           TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS final_verification_items (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            verification_id UUID NOT NULL REFERENCES final_verifications(id),
            doc_type        TEXT NOT NULL,
            outcome         TEXT NOT NULL DEFAULT 'PENDING',
            -- PENDING | VERIFIED | DISCREPANCY | NOT_PRODUCED
            discrepancy_detail TEXT,
            officer_notes   TEXT,
            checked_at      TIMESTAMPTZ,
            checked_by      TEXT
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS verification_discrepancies (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            verification_id UUID NOT NULL REFERENCES final_verifications(id),
            applicant_id    UUID NOT NULL REFERENCES applicants(id),
            doc_type        TEXT NOT NULL,
            discrepancy_type TEXT NOT NULL,
            -- DATA_MISMATCH | SUSPECTED_FRAUD | DOCUMENT_MISSING |
            -- DOCUMENT_EXPIRED | UNRECOGNIZED_BOARD
            description     TEXT NOT NULL,
            severity        TEXT NOT NULL DEFAULT 'MEDIUM',
            -- LOW | MEDIUM | HIGH | CRITICAL
            escalated_to    TEXT,
            -- Role/user escalated to
            resolution      TEXT,
            resolved_at     TIMESTAMPTZ,
            resolved_by     TEXT,
            status          TEXT NOT NULL DEFAULT 'OPEN',
            -- OPEN | UNDER_REVIEW | RESOLVED | ESCALATED | CLOSED_REJECTED
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ
        )
    """)

    # -----------------------------------------------------------------------
    # STAGE 10 — Enrollment provisioning
    # -----------------------------------------------------------------------

    op.execute("""
        CREATE TABLE IF NOT EXISTS enrollment_provisioning (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id          TEXT NOT NULL,
            applicant_id    UUID NOT NULL REFERENCES applicants(id) UNIQUE,
            student_id      UUID REFERENCES students(id),

            -- Identity
            roll_number     TEXT,
            university_reg_number TEXT,

            -- Provisioning status per system
            lms_status      TEXT NOT NULL DEFAULT 'PENDING',
            lms_account_id  TEXT,
            lms_created_at  TIMESTAMPTZ,

            email_status    TEXT NOT NULL DEFAULT 'PENDING',
            university_email TEXT,
            email_created_at TIMESTAMPTZ,

            library_status  TEXT NOT NULL DEFAULT 'PENDING',
            library_member_id TEXT,
            library_created_at TIMESTAMPTZ,

            id_card_status  TEXT NOT NULL DEFAULT 'PENDING',
            id_card_dispatched_at TIMESTAMPTZ,

            erp_status      TEXT NOT NULL DEFAULT 'PENDING',
            -- PENDING | SYNCED | EXPORT_READY | FAILED
            erp_synced_at   TIMESTAMPTZ,
            erp_export_path TEXT,
            -- path to CSV if manual export

            welcome_email_sent BOOLEAN NOT NULL DEFAULT FALSE,
            parent_email_sent  BOOLEAN NOT NULL DEFAULT FALSE,

            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ
        )
    """)

    # -----------------------------------------------------------------------
    # INDEXES — all new tables + expanded columns
    # -----------------------------------------------------------------------

    # Leads
    _idx("idx_leads_org_id",           "leads",           "org_id")
    _idx("idx_leads_email",            "leads",           "org_id, email")
    _idx("idx_leads_phone",            "leads",           "org_id, phone")
    _idx("idx_leads_status",           "leads",           "org_id, status")
    _idx("idx_leads_consultant_id",    "leads",           "consultant_id")
    _idx("idx_leads_counsellor",       "leads",           "assigned_counsellor_id")
    _idx("idx_leads_converted",        "leads",           "converted_applicant_id")
    _idx("idx_lead_activities_lead",   "lead_activities", "lead_id")
    _idx("idx_lead_activities_org",    "lead_activities", "org_id")
    _idx("idx_consultants_org",        "consultants",     "org_id")
    _idx("idx_consultant_referrals_consultant", "consultant_referrals", "consultant_id")
    _idx("idx_consultant_referrals_applicant",  "consultant_referrals", "applicant_id")
    _idx("idx_referral_codes_org",     "referral_codes",  "org_id, code")

    # Applicant expansions
    _idx("idx_applicants_application_id", "applicants", "application_id")
    _idx("idx_applicants_lead_id",        "applicants", "lead_id")
    _idx("idx_applicants_intake_batch",   "applicants", "org_id, intake_batch")
    _idx("idx_applicants_category",       "applicants", "org_id, category")

    # Academic qualifications
    _idx("idx_academic_quals_applicant", "academic_qualifications", "applicant_id")
    _idx("idx_academic_quals_org",       "academic_qualifications", "org_id")

    # Entrance scores
    _idx("idx_entrance_scores_applicant", "entrance_exam_scores", "applicant_id")
    _idx("idx_entrance_scores_org",       "entrance_exam_scores", "org_id")

    # Program preferences
    _idx("idx_prog_prefs_applicant", "program_preferences", "applicant_id")

    # Admissions tests
    _idx("idx_admissions_tests_org",   "admissions_tests",    "org_id")
    _idx("idx_admissions_tests_batch", "admissions_tests",    "org_id, intake_batch")
    _idx("idx_test_slots_test",        "test_slots",          "test_id")
    _idx("idx_test_slots_date",        "test_slots",          "test_id, slot_date")
    _idx("idx_test_regs_test",         "test_registrations",  "test_id")
    _idx("idx_test_regs_applicant",    "test_registrations",  "applicant_id")
    _idx("idx_test_scores_test",       "test_scores",         "test_id")
    _idx("idx_test_scores_applicant",  "test_scores",         "applicant_id")

    # Interview
    _idx("idx_interview_panels_org",      "interview_panels",     "org_id")
    _idx("idx_interview_schedules_panel", "interview_schedules",  "panel_id")
    _idx("idx_interview_schedules_app",   "interview_schedules",  "applicant_id")
    _idx("idx_interview_scorecards_sch",  "interview_scorecards", "schedule_id")
    _idx("idx_interview_scorecards_app",  "interview_scorecards", "applicant_id")

    # Seat matrix
    _idx("idx_seat_matrix_org",     "seat_matrix", "org_id")
    _idx("idx_seat_matrix_program", "seat_matrix", "org_id, program_name, intake_batch")

    # Merit lists
    _idx("idx_merit_policies_org",     "merit_list_policies", "org_id")
    _idx("idx_merit_lists_org",        "merit_lists",         "org_id")
    _idx("idx_merit_lists_program",    "merit_lists",         "org_id, program_name, intake_batch, category")
    _idx("idx_merit_lists_status",     "merit_lists",         "status")
    _idx("idx_merit_entries_list",     "merit_list_entries",  "merit_list_id")
    _idx("idx_merit_entries_app",      "merit_list_entries",  "applicant_id")
    _idx("idx_merit_entries_rank",     "merit_list_entries",  "merit_list_id, rank")
    _idx("idx_waitlist_list",          "waitlist_entries",    "merit_list_id")
    _idx("idx_waitlist_app",           "waitlist_entries",    "applicant_id")
    _idx("idx_waitlist_rank",          "waitlist_entries",    "merit_list_id, waitlist_rank")
    _idx("idx_waitlist_status",        "waitlist_entries",    "status")

    # Payment v2
    _idx("idx_dd_uploads_applicant", "demand_draft_uploads", "applicant_id")
    _idx("idx_dd_uploads_status",    "demand_draft_uploads", "verification_status")
    _idx("idx_refund_requests_app",  "refund_requests",      "applicant_id")
    _idx("idx_refund_requests_status","refund_requests",     "status")

    # Final verification
    _idx("idx_final_verif_applicant",     "final_verifications",       "applicant_id")
    _idx("idx_final_verif_status",        "final_verifications",       "status")
    _idx("idx_final_verif_items_verif",   "final_verification_items",  "verification_id")
    _idx("idx_discrepancies_verif",       "verification_discrepancies","verification_id")
    _idx("idx_discrepancies_applicant",   "verification_discrepancies","applicant_id")
    _idx("idx_discrepancies_status",      "verification_discrepancies","status")

    # Enrollment provisioning
    _idx("idx_enrollment_prov_applicant", "enrollment_provisioning", "applicant_id")
    _idx("idx_enrollment_prov_student",   "enrollment_provisioning", "student_id")


# ===========================================================================
# DOWNGRADE
# ===========================================================================

def downgrade() -> None:
    # Drop new tables (reverse order of FK dependencies)
    tables = [
        "enrollment_provisioning",
        "verification_discrepancies",
        "final_verification_items",
        "final_verifications",
        "refund_requests",
        "demand_draft_uploads",
        "waitlist_entries",
        "merit_list_entries",
        "merit_lists",
        "merit_list_policies",
        "seat_matrix",
        "interview_scorecards",
        "interview_schedules",
        "interview_panels",
        "test_scores",
        "test_registrations",
        "test_slots",
        "admissions_tests",
        "program_preferences",
        "entrance_exam_scores",
        "academic_qualifications",
        "referral_codes",
        "consultant_referrals",
        "consultants",
        "lead_activities",
        "leads",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")

    # Remove added columns (offer_letters)
    for col in ["expires_at", "accepted_at", "declined_at", "acceptance_status",
                "digital_signature_ref", "merit_list_entry_id", "delivery_status",
                "email_opened_at", "t3_reminder_sent", "t1_reminder_sent", "fee_structure"]:
        op.execute(f"ALTER TABLE offer_letters DROP COLUMN IF EXISTS {col}")

    # Remove added columns (application_documents)
    for col in ["doc_status", "rejection_reason", "reupload_count", "reupload_deadline",
                "file_size_bytes", "file_mime_type", "original_file_name",
                "digilocker_verified", "ocr_extracted"]:
        op.execute(f"ALTER TABLE application_documents DROP COLUMN IF EXISTS {col}")

    # Remove added columns (applicants) — too many to list individually; skip in downgrade
    # The table existed before and the new cols are non-destructive additions.
