# ALIS OS — Product Gap Epics
## Implementation Reference for E15–E20
### QUAICU Pvt. Ltd. | Confidential

**Last updated:** 2026-03-27

This file contains full implementation specs for the product gaps identified
as missing from ALIS v1. Items marked ✅ are fully built and deployed.

---

## Build Status Summary

| Gap | Backend | Frontend | Status |
|---|---|---|---|
| E15 — PhD / Doctoral Research | ✅ phd_service, plagiarism_service, phd_router | ✅ PhDPage | **DONE** |
| E17 — Re-admission & Credit Transfer | ✅ readmission_service, credit_transfer_service | ✅ ReadmissionPage | **DONE** |
| E18 — Convocation Management | ✅ convocation_service, convocation_router | ✅ ConvocationPage | **DONE** |
| E19 — Quota Seat Matrix Engine | ✅ seat_matrix_service, admissions_router | ✅ SeatMatrixPage | **DONE** |
| E20 — OBE / CO-PO Mapping | ✅ obe_service, academics_router | ✅ OBEPage | **DONE** |
| Duplicate Student Detection | ✅ deduplication_service | ❌ No FE page | Backend only |
| Tally / Busy Export | ✅ tally_export.py, finance_router | ❌ No FE trigger | Backend only |
| Regional Languages (6) | — | ✅ i18n/ (EN/TE/HI/KN/TA/MR) | **DONE** |
| Offline PWA | ✅ bulk-sync endpoint | ✅ Dexie + Workbox | **DONE** |
| GST e-Invoice / IRN | ✅ einvoice_service, finance_router | ❌ No FE trigger | Backend only |
| Load Testing Baseline | ✅ infra/loadtest/locustfile.py | — | **DONE** |

---

## Table of Contents

1. [E15 — PhD / Doctoral Research Module](#e15--phd--doctoral-research-module)
2. [E17 — Re-admission & Credit Transfer](#e17--re-admission--credit-transfer)
3. [E18 — Convocation Management](#e18--convocation-management)
4. [E19 — Quota Seat Matrix Engine](#e19--quota-seat-matrix-engine)
5. [E20 — OBE / CO-PO Mapping](#e20--obe--co-po-mapping-see-architecture-33)
6. [Duplicate Student Detection & Merge](#duplicate-student-detection--merge)
7. [Tally / Busy Accounting Export](#tally--busy-accounting-export)
8. [Regional Language Support](#regional-language-support)
9. [Offline / Low-Bandwidth PWA](#offline--low-bandwidth-pwa)
10. [GST e-Invoice / IRN Generation](#gst-e-invoice--irn-generation)
11. [Load Testing Baseline](#load-testing-baseline)

---

## E15 — PhD / Doctoral Research Module

**Status:** ✅ BUILT (P27). `server/phd/phd_service.py` + `plagiarism_service.py` + `api/phd_router.py` + migration `0026_phd_module`. Frontend: `web/src/pages/phd/PhDPage.tsx`. Spec below retained as reference.

PhD is a milestone-based program, not semester-based. A scholar's lifecycle spans
3–6 years with structured checkpoints mandated by UGC Regulations 2022.

### UGC PhD Lifecycle — 9 Milestones

```
M1  Admission & Registration       (Research Supervisor + DC constituted)
M2  Coursework Completion          (min 8 credits, CGPA ≥ 5.5)
M3  Comprehensive Examination      (written + viva)
M4  Research Proposal Submission   (synopsis submitted to RC)
M5  Pre-Submission Seminar         (open presentation)
M6  Plagiarism Check               (Shodhganga / Urkund, max 10%)
M7  Thesis Submission              (hard + soft copy)
M8  Viva Voce (Open Defense)       (External examiner + RC)
M9  Degree Award                   (Senate approval + certificate)
```

### Core Schema

```sql
CREATE TABLE phd_scholars (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    student_id          UUID NOT NULL REFERENCES students(id),
    registration_number TEXT NOT NULL UNIQUE,  -- e.g. PHD-2023-CSE-001
    program             TEXT NOT NULL,          -- 'Computer Science', 'Management', etc.
    registration_date   DATE NOT NULL,
    expected_submission DATE,                   -- registration_date + max_years
    max_duration_years  INTEGER DEFAULT 6,      -- UGC: min 3, max 6 years
    current_milestone   INTEGER DEFAULT 1,      -- 1–9
    supervisor_id       UUID NOT NULL REFERENCES employees(id),
    co_supervisor_id    UUID REFERENCES employees(id),
    status              TEXT DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE','SUBMITTED','AWARDED','DISCONTINUED','ON_LEAVE')),
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE phd_dc_members (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   UUID NOT NULL,
    scholar_id  UUID NOT NULL REFERENCES phd_scholars(id),
    employee_id UUID NOT NULL REFERENCES employees(id),
    role        TEXT NOT NULL CHECK (role IN ('supervisor','co_supervisor','member','external')),
    appointed_at DATE NOT NULL
);

CREATE TABLE phd_dc_meetings (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    scholar_id      UUID NOT NULL REFERENCES phd_scholars(id),
    meeting_number  INTEGER NOT NULL,   -- 1st DC, 2nd DC, etc.
    meeting_date    DATE NOT NULL,
    progress_summary TEXT NOT NULL,
    recommendations TEXT,
    next_meeting_date DATE,
    minutes_document_url TEXT,
    approved_by     UUID NOT NULL,      -- DC Chairperson
    status          TEXT DEFAULT 'SCHEDULED'
        CHECK (status IN ('SCHEDULED','COMPLETED','CANCELLED'))
);

CREATE TABLE phd_milestones (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    scholar_id      UUID NOT NULL REFERENCES phd_scholars(id),
    milestone       INTEGER NOT NULL CHECK (milestone BETWEEN 1 AND 9),
    status          TEXT DEFAULT 'PENDING'
        CHECK (status IN ('PENDING','IN_PROGRESS','COMPLETED','FAILED')),
    completed_at    TIMESTAMPTZ,
    approved_by     UUID,
    notes           TEXT,
    UNIQUE(scholar_id, milestone)
);

CREATE TABLE phd_plagiarism_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    scholar_id      UUID NOT NULL REFERENCES phd_scholars(id),
    tool_used       TEXT NOT NULL,   -- 'Urkund' | 'Turnitin' | 'Drillbit'
    similarity_pct  DECIMAL(5,2) NOT NULL,
    report_url      TEXT NOT NULL,
    submitted_at    TIMESTAMPTZ NOT NULL,
    passed          BOOLEAN GENERATED ALWAYS AS (similarity_pct <= 10.0) STORED
);
```

### DC Meeting Automation

```python
class PhDDCMeetingWorkflow:
    """
    UGC mandates DC meetings every 6 months.
    AI pre-fills the meeting briefing from scholar's progress data.
    """

    DC_MEETING_INTERVAL_DAYS = 180

    async def schedule_next_dc_meeting(self, scholar_id: UUID, tenant_id: UUID):
        last_meeting = await get_last_dc_meeting(scholar_id, tenant_id)
        next_date = last_meeting.meeting_date + timedelta(days=self.DC_MEETING_INTERVAL_DAYS)

        # Auto-generate briefing document
        briefing = await llm_router.complete(
            task_class=TaskClass.DRAFTING,
            prompt=await self._build_briefing_prompt(scholar_id, tenant_id),
            output_schema=DCMeetingBriefing,
            tenant_id=str(tenant_id),
        )

        await create_dc_meeting(scholar_id=scholar_id, date=next_date, briefing=briefing)
        await notify_dc_members(scholar_id, next_date, tenant_id)

    async def _build_briefing_prompt(self, scholar_id, tenant_id) -> str:
        scholar = await get_phd_scholar(scholar_id, tenant_id)
        milestones = await get_milestone_status(scholar_id, tenant_id)
        publications = await get_scholar_publications(scholar_id, tenant_id)

        return f"""
Generate a DC meeting briefing for PhD scholar {scholar.registration_number}.

Registration date: {scholar.registration_date}
Current milestone: {scholar.current_milestone}/9
Publications: {len(publications)} papers ({sum(1 for p in publications if p.indexed)} indexed)
Milestones completed: {[m.milestone for m in milestones if m.status == 'COMPLETED']}
Days since registration: {(date.today() - scholar.registration_date).days}

Generate a structured briefing with: progress summary, pending milestones,
publication status, timeline assessment (on track / at risk / overdue),
and recommended DC actions.
"""
```

### Plagiarism Check Integration

```python
class PlagiarismCheckService:
    """Integrates with Drillbit (India's most common tool for universities)."""

    async def submit_for_check(self, scholar_id: UUID, thesis_url: str, tenant_id: UUID):
        if not await feature_flags.is_enabled("phd.plagiarism_check", str(tenant_id)):
            # Manual check mode — generate upload instructions for staff
            await create_manual_check_task(scholar_id, thesis_url)
            return

        # Submit to Drillbit API
        result = await drillbit_api.submit(
            document_url=thesis_url,
            author_name=await get_scholar_name(scholar_id),
            institution_id=await get_institution_drillbit_id(tenant_id),
        )
        await poll_for_result(scholar_id, result.job_id, tenant_id)

    async def poll_for_result(self, scholar_id, job_id, tenant_id):
        """Celery task — polls every 15 minutes until result ready."""
        result = await drillbit_api.get_result(job_id)
        if result.status != "COMPLETE":
            raise self.retry(countdown=900)  # retry in 15 min

        await save_plagiarism_report(scholar_id, result, tenant_id)
        if not result.passed:
            # Milestone 6 blocked — notify supervisor + RC
            await notify_plagiarism_failure(scholar_id, result.similarity_pct, tenant_id)
```

### Supervisor Load Balancing

A faculty member cannot supervise more than 8 PhD scholars simultaneously (UGC norm). The AI checks this constraint before allowing a new supervisor assignment.

```python
MAX_PHD_SCHOLARS_PER_SUPERVISOR = 8  # UGC Regulations 2022

async def validate_supervisor_capacity(supervisor_id: UUID, tenant_id: UUID) -> bool:
    active_scholars = await count_active_scholars_for_supervisor(supervisor_id, tenant_id)
    return active_scholars < MAX_PHD_SCHOLARS_PER_SUPERVISOR
```

### Domain Events

```python
# PhD module emits these events
PHD_EVENTS = [
    "phd.registered",              # → HR (supervisor workload), Academics (course enrollment)
    "phd.milestone_completed",     # → Regulatory E14 (PhD progress metrics)
    "phd.plagiarism_passed",       # → unlocks Milestone 7
    "phd.thesis_submitted",        # → Examinations (viva scheduling)
    "phd.degree_awarded",          # → Alumni E12, Regulatory E14
]
```

---

## E17 — Re-admission & Credit Transfer

**Status:** ✅ BUILT (P27). `server/admissions/readmission_service.py` + `credit_transfer_service.py` + migration `0027_readmission`. Frontend: `web/src/pages/admissions/ReadmissionPage.tsx`. Spec retained as reference.

### Re-admission

A student who was detained or voluntarily withdrew can apply to re-join. They retain credit for semesters already completed.

```sql
CREATE TABLE readmission_applications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    original_student_id UUID NOT NULL REFERENCES students(id),
    application_date    DATE NOT NULL,
    reason_for_gap      TEXT NOT NULL,
    gap_years           INTEGER NOT NULL,
    last_semester_completed INTEGER NOT NULL,
    credits_completed   INTEGER NOT NULL,
    target_reentry_semester INTEGER NOT NULL,
    status              TEXT DEFAULT 'SUBMITTED'
        CHECK (status IN ('SUBMITTED','UNDER_REVIEW','APPROVED','REJECTED')),
    approved_by         UUID,
    new_roll_number     TEXT,    -- assigned on approval
    created_at          TIMESTAMPTZ DEFAULT now()
);
```

**State machine:** `SUBMITTED → UNDER_REVIEW → APPROVED / REJECTED`

On approval:
1. Student record is reactivated (status `ARCHIVED → ACTIVE`)
2. A new roll number is generated with a `RE` prefix: `25RE-BCE-0001`
3. Completed semesters are locked — marks and attendance cannot be modified
4. A catch-up assessment is generated for any syllabus revisions since withdrawal
5. `student.readmitted` event fires → Academic module handles catch-up cohort (EC-ADM-02 pattern)

### Inter-College Credit Transfer

```sql
CREATE TABLE credit_transfer_applications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    student_id          UUID NOT NULL,
    source_institution  TEXT NOT NULL,
    source_program      TEXT NOT NULL,
    migration_cert_url  TEXT NOT NULL,
    transcript_url      TEXT NOT NULL,
    equivalency_report_url TEXT,          -- UGC equivalency or AI-generated draft
    courses_claimed     JSONB NOT NULL,   -- [{course_name, credits, grade, year}]
    credits_approved    INTEGER,          -- filled by Academic Committee
    target_semester     INTEGER NOT NULL,
    status              TEXT DEFAULT 'SUBMITTED',
    reviewed_by         UUID,
    created_at          TIMESTAMPTZ DEFAULT now()
);
```

**Credit equivalency AI assist:** The AI drafts a credit equivalency mapping by comparing the source institution's course descriptions (extracted from their transcript) with ALIS's curriculum. The Academic Committee reviews and approves/modifies.

---

## E18 — Convocation Management

**Status:** ✅ BUILT (P27). `server/convocation/convocation_service.py` + `api/convocation_router.py` + migration `0028_convocation`. Frontend: `web/src/pages/convocation/ConvocationPage.tsx`. Spec retained as reference.

Convocation is a high-visibility, high-pressure annual event.

```sql
CREATE TABLE convocation_cycles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    academic_year   TEXT NOT NULL,  -- '2024-25'
    ceremony_date   DATE,
    venue           TEXT,
    chief_guest     TEXT,
    status          TEXT DEFAULT 'PLANNING'
        CHECK (status IN ('PLANNING','CONFIRMED','COMPLETED','CANCELLED')),
    degree_cut_off  DATE NOT NULL,  -- graduation clearance must be done by this date
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE convocation_registrations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    convocation_id  UUID NOT NULL REFERENCES convocation_cycles(id),
    student_id      UUID NOT NULL,
    program         TEXT NOT NULL,
    degree_class    TEXT NOT NULL,   -- 'First Class with Distinction'|'First Class'|'Second Class'|'Pass'
    gold_medal      BOOLEAN DEFAULT false,
    rank_in_program INTEGER,
    attending       BOOLEAN DEFAULT true,
    gown_size       TEXT,
    guest_count     INTEGER DEFAULT 2,
    certificate_printed BOOLEAN DEFAULT false,
    certificate_url TEXT,
    seat_number     TEXT,            -- assigned during seating arrangement
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

**AI automation for convocation:**
1. Auto-runs degree audit for all graduating students (credits, backlogs, dues cleared)
2. Computes degree class and gold medal eligibility using merit list logic
3. Generates batch printing manifest for degree certificates
4. Assigns seating by department, then by rank within department
5. Generates ceremonial programme booklet

**Gold medal rules** — configured in `tenant_policies`:
- Highest CGPA in program with no grace marks, no backlogs, no disciplinary record
- Category-wise gold medals if institution follows that policy
- Grace mark exclusion is enforced (same logic as EC-EXM-04)

---

## E19 — Quota Seat Matrix Engine

**Status:** ✅ BUILT (P27). `server/admissions/seat_matrix_service.py` + admissions_router. Frontend: `web/src/pages/admissions/SeatMatrixPage.tsx`. Spec retained as reference.

The current `seat counter - 1` approach is insufficient. AICTE and state counseling bodies audit quota-wise seat utilisation.

### Core Schema

```sql
CREATE TABLE seat_matrix (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    program_id      UUID NOT NULL,
    intake_year     INTEGER NOT NULL,
    total_intake    INTEGER NOT NULL,      -- AICTE/UGC sanctioned intake
    -- Category-wise breakdowns (must sum to total_intake)
    general_seats   INTEGER NOT NULL,
    sc_seats        INTEGER NOT NULL,
    st_seats        INTEGER NOT NULL,
    obc_ncl_seats   INTEGER NOT NULL,
    ews_seats        INTEGER NOT NULL,
    pwd_seats        INTEGER NOT NULL,     -- supernumerary over total_intake
    -- Quota-wise breakdowns
    management_quota INTEGER DEFAULT 0,
    nri_quota        INTEGER DEFAULT 0,
    sports_quota     INTEGER DEFAULT 0,
    -- Computed in real-time via triggers
    filled_general  INTEGER DEFAULT 0,
    filled_sc       INTEGER DEFAULT 0,
    filled_st       INTEGER DEFAULT 0,
    filled_obc      INTEGER DEFAULT 0,
    filled_ews      INTEGER DEFAULT 0,
    filled_management INTEGER DEFAULT 0,
    filled_nri       INTEGER DEFAULT 0,
    UNIQUE(tenant_id, program_id, intake_year),
    CONSTRAINT category_sum CHECK (
        general_seats + sc_seats + st_seats + obc_ncl_seats + ews_seats + management_quota + nri_quota
        = total_intake
    )
);

-- Trigger: decrements the right counter when a seat is confirmed
CREATE OR REPLACE FUNCTION decrement_seat_counter()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE seat_matrix
    SET filled_general = filled_general + CASE WHEN NEW.category = 'GENERAL' THEN 1 ELSE 0 END,
        filled_sc      = filled_sc      + CASE WHEN NEW.category = 'SC'      THEN 1 ELSE 0 END,
        filled_st      = filled_st      + CASE WHEN NEW.category = 'ST'      THEN 1 ELSE 0 END,
        filled_obc     = filled_obc     + CASE WHEN NEW.category = 'OBC_NCL' THEN 1 ELSE 0 END,
        filled_ews     = filled_ews     + CASE WHEN NEW.category = 'EWS'     THEN 1 ELSE 0 END,
        filled_management = filled_management + CASE WHEN NEW.quota = 'MANAGEMENT' THEN 1 ELSE 0 END,
        filled_nri     = filled_nri     + CASE WHEN NEW.quota = 'NRI'       THEN 1 ELSE 0 END
    WHERE tenant_id = NEW.tenant_id
      AND program_id = NEW.program_id
      AND intake_year = NEW.intake_year;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

**Waitlist activation rule:** When a confirmed seat is released (cancellation, forfeiture), the system auto-identifies the next eligible waitlisted candidate in the correct category/quota. It does not simply take the next overall waitlist rank — it takes the next rank within the same quota bucket that the seat belonged to.

```python
async def activate_next_waitlist_candidate(
    released_seat: SeatRelease,
    tenant_id: UUID,
) -> WaitlistActivation | None:
    # Find next eligible candidate in the same quota + category
    next_candidate = await execute_query("""
        SELECT w.applicant_id, w.rank_in_category
        FROM waitlist_positions w
        WHERE w.tenant_id = $1
          AND w.program_id = $2
          AND w.intake_year = $3
          AND w.category = $4
          AND w.quota = $5
          AND w.status = 'WAITING'
        ORDER BY w.rank_in_category ASC
        LIMIT 1
    """, [str(tenant_id), str(released_seat.program_id),
          released_seat.intake_year, released_seat.category, released_seat.quota])

    if not next_candidate:
        # No same-category candidate — check if seat can be converted
        return await try_seat_conversion(released_seat, tenant_id)

    await notify_waitlist_activation(next_candidate[0]["applicant_id"], tenant_id)
    return WaitlistActivation(applicant_id=next_candidate[0]["applicant_id"])
```

**Live seat matrix dashboard** — real-time view for the Admissions Committee:
- Program-wise seat utilisation (filled / total per quota)
- Category conversion eligibility (unused SC seats can be offered to general after deadline)
- Waitlist depth per category
- Cancellation rate trend (informs waitlist depth planning)

---

## Duplicate Student Detection & Merge

**Status:** ✅ Backend built (P27). `server/admissions/deduplication_service.py` — Jaro-Winkler scoring, dual-auth merge flow. ❌ No frontend page yet. Spec retained as reference.

Over time, duplicate student records accumulate (re-applicants, data entry errors, system migrations).

### Detection

```python
class DuplicateDetectionService:
    SIMILARITY_THRESHOLD = 0.90

    async def find_duplicates(self, tenant_id: UUID) -> list[DuplicateCandidate]:
        all_students = await get_all_students_for_matching(tenant_id)
        candidates = []

        for i, a in enumerate(all_students):
            for b in all_students[i+1:]:
                score = self._compute_similarity(a, b)
                if score >= self.SIMILARITY_THRESHOLD:
                    candidates.append(DuplicateCandidate(
                        student_a=a.id,
                        student_b=b.id,
                        similarity_score=score,
                        matching_fields=self._matching_fields(a, b),
                    ))

        return candidates

    def _compute_similarity(self, a, b) -> float:
        name_score = jaro_winkler(a.full_name.lower(), b.full_name.lower())
        dob_match = 1.0 if a.date_of_birth == b.date_of_birth else 0.0
        phone_match = 1.0 if a.phone == b.phone else 0.0
        return (name_score * 0.5) + (dob_match * 0.3) + (phone_match * 0.2)
```

### Supervised Merge Workflow

```python
class StudentMergeWorkflow:
    """
    Human-supervised merge — staff select the canonical record.
    Never auto-merges. Every merge is fully auditable.
    """

    async def initiate_merge(
        self,
        canonical_id: UUID,   # the record to keep
        duplicate_id: UUID,   # the record to absorb and archive
        initiated_by: UUID,
        tenant_id: UUID,
    ) -> MergeRecord:
        # Dual authorization required — Registrar + one other admin
        merge_task = await create_approval_task(
            type="STUDENT_RECORD_MERGE",
            payload={"canonical": str(canonical_id), "duplicate": str(duplicate_id)},
            required_approvers=["registrar", "super_admin"],
            tenant_id=tenant_id,
        )
        return merge_task

    async def execute_merge(self, merge_record: MergeRecord, tenant_id: UUID):
        """Called after dual authorization is granted."""
        canonical_id = merge_record.canonical_id
        duplicate_id = merge_record.duplicate_id

        async with db.transaction():
            # Reassign all FK references from duplicate to canonical
            for table in FK_TABLES_TO_STUDENT:
                await execute_transaction([(
                    f"UPDATE {table} SET student_id = $1 WHERE student_id = $2 AND tenant_id = $3",
                    [str(canonical_id), str(duplicate_id), str(tenant_id)]
                )])

            # Archive the duplicate — never delete
            await execute_transaction([(
                "UPDATE students SET status = 'MERGED_DUPLICATE', merged_into = $1 WHERE id = $2",
                [str(canonical_id), str(duplicate_id)]
            )])

            await audit_ledger.record(
                event_type="student.records_merged",
                payload={"canonical": str(canonical_id), "duplicate": str(duplicate_id)},
                tenant_id=str(tenant_id),
            )
```

---

## Tally / Busy Accounting Export

**Status:** ✅ Backend built (P27). `server/finance/tally_export.py` — Tally XML + Busy CSV, feature-flagged. Routes wired in `finance_router.py`. ❌ No frontend trigger yet. Spec retained as reference.

Accounts teams use Tally or Busy. ALIS must produce clean exports — not replace these tools.

### Tally XML Export (TallyPrime format)

```python
class TallyExportService:
    """Generates Tally-compatible XML for fee collections and payroll."""

    async def export_fee_collections(
        self,
        tenant_id: UUID,
        date_from: date,
        date_to: date,
    ) -> str:
        collections = await get_fee_collections(tenant_id, date_from, date_to)

        # Build Tally XML envelope
        root = ET.Element("ENVELOPE")
        header = ET.SubElement(root, "HEADER")
        ET.SubElement(header, "TALLYREQUEST").text = "Import Data"

        body = ET.SubElement(root, "BODY")
        import_data = ET.SubElement(body, "IMPORTDATA")
        request_desc = ET.SubElement(import_data, "REQUESTDESC")
        ET.SubElement(request_desc, "REPORTNAME").text = "Vouchers"

        request_data = ET.SubElement(import_data, "REQUESTDATA")
        for collection in collections:
            voucher = ET.SubElement(request_data, "TALLYMESSAGE")
            v = ET.SubElement(voucher, "VOUCHER")
            ET.SubElement(v, "DATE").text = collection.date.strftime("%Y%m%d")
            ET.SubElement(v, "VOUCHERTYPENAME").text = "Receipt"
            ET.SubElement(v, "NARRATION").text = (
                f"Fee receipt {collection.receipt_number} - {collection.student_name}"
            )
            # Debit: Bank / Cash account
            debit_entry = ET.SubElement(v, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(debit_entry, "LEDGERNAME").text = collection.payment_mode_ledger
            ET.SubElement(debit_entry, "ISDEEMEDPOSITIVE").text = "Yes"
            ET.SubElement(debit_entry, "AMOUNT").text = f"-{collection.amount}"
            # Credit: Fee income account
            credit_entry = ET.SubElement(v, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(credit_entry, "LEDGERNAME").text = collection.fee_head_ledger
            ET.SubElement(credit_entry, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(credit_entry, "AMOUNT").text = str(collection.amount)

        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    async def export_payroll_vouchers(self, tenant_id: UUID, payroll_month: str) -> str:
        """Generates salary voucher XML for Tally import."""
        # Same pattern — one voucher per employee
        ...
```

**Busy export** is a CSV format — simpler than Tally XML. Both are generated from the same underlying data, different formatters.

**Finance feature flag:** `finance.tally_export` and `finance.busy_export` — enable per institution based on which accounting software they use.

---

## Regional Language Support

**Status:** ✅ BUILT (P27). `web/src/i18n/` — en.json, te.json, hi.json, kn.json, ta.json, mr.json. `react-i18next` wired. Language preference stored per user. Spec retained as reference.

**Strategy:** Internationalise student-facing and parent-facing UI only. Admin/staff interface remains English. Use `react-i18next` on the frontend.

**Priority languages (by institution geography):**

| State | Language | Unicode Range |
|---|---|---|
| Telangana / AP | Telugu | U+0C00–U+0C7F |
| Karnataka | Kannada | U+0C80–U+0CFF |
| Tamil Nadu | Tamil | U+0B80–U+0BFF |
| Maharashtra | Marathi | U+0900–U+097F (Devanagari) |
| All India | Hindi | U+0900–U+097F (Devanagari) |

**Implementation approach:**

```
web/src/
├── i18n/
│   ├── en.json         ← default (all keys defined here)
│   ├── te.json         ← Telugu
│   ├── kn.json         ← Kannada
│   ├── ta.json         ← Tamil
│   ├── mr.json         ← Marathi
│   └── hi.json         ← Hindi
```

```typescript
// Translation key convention — all keys in snake_case
// en.json example:
{
  "attendance.status.eligible": "Eligible to appear in examination",
  "fee.status.pending": "Fee payment pending",
  "exam.hall_ticket.download": "Download Hall Ticket",
  "guardian.attendance.below_threshold": "Attendance below required 75%"
}

// te.json example:
{
  "attendance.status.eligible": "పరీక్షకు అర్హత ఉంది",
  "fee.status.pending": "రుసుము చెల్లింపు పెండింగ్‌లో ఉంది",
  "exam.hall_ticket.download": "హాల్ టికెట్ డౌన్‌లోడ్ చేయండి"
}
```

**Notification localisation:** SMS and WhatsApp templates are pre-registered in each language with the gateway provider. The Communication module selects the template based on the student/guardian's preferred language (set at enrollment, defaulting to English).

**Language preference:** Stored per user in the `users` table as `preferred_language TEXT DEFAULT 'en'`. Guardian accounts inherit the student's preferred language initially, changeable in settings.

---

## Offline / Low-Bandwidth PWA

**Status:** ✅ BUILT (P28). `web/src/views/AttendanceMarking/offline-store.ts` (Dexie), `sync.ts` (background sync), Workbox runtime caching in vite.config.ts. Route: `/attendance/mark/:sessionId`. Spec retained as reference.

**Scope:** Faculty attendance marking only. This is the highest-value offline use case.
All other ALIS functionality requires connectivity.

**Implementation: Progressive Web App (PWA) for the attendance screen**

```
web/src/
├── service-worker.ts        ← Workbox-based service worker
├── views/
│   └── AttendanceMarking/   ← offline-capable component
│       ├── index.tsx
│       ├── offline-store.ts  ← IndexedDB via Dexie
│       └── sync.ts           ← background sync when online
```

```typescript
// offline-store.ts — IndexedDB schema for offline attendance
import Dexie from 'dexie'

class OfflineAttendanceStore extends Dexie {
  pendingMarks!: Dexie.Table<PendingMark, string>

  constructor() {
    super('alis-attendance-offline')
    this.version(1).stores({
      pendingMarks: 'id, sessionId, markedAt, synced'
    })
  }
}

interface PendingMark {
  id: string                 // local UUID
  sessionId: string
  studentId: string
  status: 'PRESENT' | 'ABSENT' | 'LATE'
  markedAt: string           // ISO timestamp
  synced: boolean
}

// sync.ts — when connectivity restores, push pending marks to API
export async function syncPendingMarks(tenantId: string, authToken: string) {
  const pending = await db.pendingMarks.where('synced').equals(0).toArray()
  if (!pending.length) return

  const response = await fetch('/api/v1/attendance/bulk-sync', {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${authToken}`, 'X-Tenant-ID': tenantId },
    body: JSON.stringify({ marks: pending }),
  })

  if (response.ok) {
    const ids = pending.map(m => m.id)
    await db.pendingMarks.where('id').anyOf(ids).modify({ synced: true })
  }
}
```

**Service worker caching strategy:**
- Attendance marking screen: cache-first (always available offline)
- Student list for a session: pre-cached when faculty opens the session
- All other routes: network-first with offline fallback page

**Feature flag:** `academics.offline_attendance_pwa` — off by default.

---

## GST e-Invoice / IRN Generation

**Status:** ✅ Backend built (P27). `server/finance/einvoice_service.py` + migration `0031_einvoice` (`irn` column on `student_invoices`). Route: `POST /finance/invoices/{id}/generate-irn`. ❌ No frontend trigger. Activate by setting `NIC_EINVOICE_*` env vars. Spec retained as reference.

From April 2025, all GSTIN-registered entities above ₹5 crore annual turnover must generate e-Invoices (Invoice Reference Numbers) for B2B transactions via the GST portal.

```sql
ALTER TABLE invoices
    ADD COLUMN irn          TEXT UNIQUE,           -- Invoice Reference Number from GST portal
    ADD COLUMN irn_generated_at TIMESTAMPTZ,
    ADD COLUMN qr_code_data TEXT,                  -- QR code content for e-invoice
    ADD COLUMN einvoice_ack_number TEXT,
    ADD COLUMN einvoice_status TEXT DEFAULT 'NOT_APPLICABLE'
        CHECK (einvoice_status IN (
            'NOT_APPLICABLE',  -- B2C or below threshold
            'PENDING',         -- B2B, threshold crossed, not yet generated
            'GENERATED',       -- IRN assigned
            'CANCELLED'        -- cancelled within 24 hours
        ));
```

```python
class EInvoiceService:
    """Integrates with NIC's e-Invoice API (sandbox + production)."""

    async def generate_irn(self, invoice_id: UUID, tenant_id: UUID) -> str:
        invoice = await get_invoice(invoice_id, tenant_id)
        tenant = await get_tenant_gstin(tenant_id)

        if not self._is_einvoice_applicable(invoice, tenant):
            return None  # B2C or below threshold — skip

        payload = {
            "Version": "1.1",
            "TranDtls": {"TaxSch": "GST", "SupTyp": "B2B", "RegRev": "N"},
            "DocDtls": {
                "Typ": "INV",
                "No": invoice.invoice_number,
                "Dt": invoice.invoice_date.strftime("%d/%m/%Y"),
            },
            "SellerDtls": {
                "Gstin": tenant.gstin,
                "TrdNm": tenant.legal_name,
                "Addr1": tenant.address,
                "Loc": tenant.city,
                "Pin": tenant.pincode,
                "Stcd": tenant.state_code,
            },
            "BuyerDtls": {
                "Gstin": invoice.buyer_gstin or "URP",  # URP = unregistered person
                "TrdNm": invoice.buyer_name,
                "Pos": invoice.place_of_supply_code,
                "Addr1": invoice.buyer_address,
                "Stcd": invoice.buyer_state_code,
            },
            "ValDtls": {
                "AssVal": str(invoice.taxable_amount),
                "CgstVal": str(invoice.cgst_amount),
                "SgstVal": str(invoice.sgst_amount),
                "TotInvVal": str(invoice.total_amount),
            },
        }

        response = await nic_einvoice_api.generate_irn(payload, tenant.gstin, tenant.gstin_auth_token)

        await execute_transaction([(
            """UPDATE invoices
               SET irn = $1, irn_generated_at = now(),
                   qr_code_data = $2, einvoice_ack_number = $3,
                   einvoice_status = 'GENERATED'
               WHERE id = $4 AND tenant_id = $5""",
            [response.irn, response.signed_qr_code, response.ack_number,
             str(invoice_id), str(tenant_id)]
        )])

        return response.irn

    def _is_einvoice_applicable(self, invoice, tenant) -> bool:
        return (
            invoice.buyer_gstin is not None       # B2B transaction
            and tenant.annual_turnover >= 5_00_00_000  # ≥ ₹5 crore
            and invoice.is_gst_taxable             # taxable supply
        )
```

**Feature flag:** `finance.einvoice_enabled` — off by default, enabled when institution crosses the turnover threshold.

---

## Load Testing Baseline

**Status:** ✅ BUILT (P27). `infra/loadtest/locustfile.py` — RegistrarUser + StudentUser scenarios. Targets: 200 concurrent p95<500ms, 2000 concurrent (result day) p95<2s. Run: `locust -f infra/loadtest/locustfile.py`. Spec retained as reference.

Before any pilot go-live, establish the system's capacity limits.

### Locust test scenarios

```python
# locust_alis.py — run with: locust -f locust_alis.py --host https://pilot.alis.internal

from locust import HttpUser, task, between

class RegistrarUser(HttpUser):
    wait_time = between(1, 3)
    weight = 1  # 1 registrar per 100 students

    @task
    def view_approval_queue(self):
        self.client.get("/api/v1/approvals/queue",
            headers={"X-Tenant-ID": TENANT_ID, "Authorization": f"Bearer {REGISTRAR_TOKEN}"})

    @task(3)
    def approve_item(self):
        self.client.post(f"/api/v1/approvals/{APPROVAL_ID}/approve",
            headers={"X-Tenant-ID": TENANT_ID, "Authorization": f"Bearer {REGISTRAR_TOKEN}"})


class StudentUser(HttpUser):
    wait_time = between(0.5, 2)
    weight = 100  # simulate 100 students per registrar

    @task(5)
    def view_results(self):
        self.client.get("/api/v1/students/me/results",
            headers={"X-Tenant-ID": TENANT_ID, "Authorization": f"Bearer {STUDENT_TOKEN}"})

    @task(3)
    def download_hall_ticket(self):
        self.client.get("/api/v1/examinations/hall-ticket",
            headers={"X-Tenant-ID": TENANT_ID, "Authorization": f"Bearer {STUDENT_TOKEN}"})

    @task(2)
    def check_attendance(self):
        self.client.get("/api/v1/students/me/attendance",
            headers={"X-Tenant-ID": TENANT_ID, "Authorization": f"Bearer {STUDENT_TOKEN}"})
```

### Target metrics (must pass before go-live)

| Scenario | Concurrent users | p95 latency target | Error rate target |
|---|---|---|---|
| Normal operations | 200 | < 500ms | < 0.1% |
| Result publication day | 2000 | < 2s | < 1% |
| Fee payment deadline | 500 | < 1s | < 0.5% |
| Exam hall ticket release | 1000 | < 1s | < 0.5% |

**Run load tests against a staging environment with production-equivalent data volume
(minimum 5,000 student records, 500 employee records, 2 years of historical data)
before signing off on any institution go-live.**

---

*Document version: 1.0 | March 2026*
*QUAICU Pvt. Ltd. Engineering | Confidential*
