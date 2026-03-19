# ALIS OS — Admissions Module
### Workflow Specification v2.0
**QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential**
**Connected to:** academic_operations_workflow.md | skill file: references/architecture.md §5, gaps.md E17, E19 | Build Plan Sprint 3 (S3-1), Sprint 7 (S7-1)

---

## Design Principle

AI executes every task. Humans only Approve, Reject, or Escalate at defined gates.

Every applicant state transition is logged with: who triggered it, which rule version ran, what data was evaluated, and when. This audit trail is mandatory — it feeds NAAC C2, AISHE, state compliance, and DPDP consent records simultaneously.

---

## Pipeline Overview

| # | Stage | Primary Actor | Key Output |
|---|-------|---------------|------------|
| 1 | Prospect & Lead Capture | Marketing / Prospect | Lead record in CRM |
| 2 | Application Form Submission | Applicant | Application ID (APP-YEAR-XXXXXX) |
| 3 | Document Collection & Verification | Applicant / Doc Officer | Verified document set |
| 4 | Eligibility Screening | Rules Engine / Admissions Officer | Eligible / Ineligible flag |
| 5 | Entrance Test / Interview | Exam Cell / Panel | Score + remarks |
| 6 | Merit List & Selection | Admissions Committee | Offer list |
| 7 | Offer Letter Issuance | Admissions Office | Signed offer letter |
| 8 | Fee Payment & Seat Confirmation | Applicant / Finance | Receipt + confirmed seat |
| 9 | Final Document Verification | Registrar / Doc Officer | Originals cleared |
| 10 | Enrollment & Roll Number Assignment | Registrar / IT | Student ID + Roll No. |

**New in v2:** Quota Seat Matrix Engine (E19) governs Stage 6 and 8. Re-admission pipeline (E17) branches from Stage 2. DPDP consent capture (E21) is mandatory at Stage 2. Ghost withdrawal resolver (EC-ADM-03) governs Stage 8–10.

---

## DPDP Consent — Mandatory at Stage 2

Before any personal data is written to the database, ALIS captures and logs a consent record per DPDP Act 2023.

```
Consent record fields:
  data_subject_id   → applicant phone + email (pre-enrollment)
  purpose           → 'admissions_processing'
  legal_basis       → 'consent'
  consent_text      → exact text shown to applicant at form submission
  ip_address        → captured at submission
  given_at          → timestamp
```

The application form cannot be submitted without the consent checkbox. Consent records are stored in the `consent_records` table (E21 DPDP module). Every downstream data use (eligibility check, document verification, merit list) references the originating consent record.

---

## Stage 1 — Prospect Awareness & Lead Capture

**Purpose:** Attract prospective students and capture contact before formal application.

**Channels:** University website inquiry form, education fairs, social media lead ads (Meta, Google), counselor outreach, third-party portals (Shiksha, CollegeDekho, Common App).

**Data Captured:** Full name, email, mobile, city/state, course of interest, year of passing, source channel (UTM / event name).

**System Actions:**
- Lead record created in CRM, tagged with source, campaign, course interest
- Automated welcome email + brochure sent
- Lead assigned to counselor for follow-up
- Deduplication on phone + email — duplicate lead merged, not created

**Trigger to Next Stage:** Prospect clicks "Apply Now" OR counselor marks lead as "Ready to Apply."

---

## Stage 2 — Application Form Submission

**Purpose:** Collect structured applicant data. Capture DPDP consent. Generate Application ID as master key for all downstream records.

**Form Sections (multi-step wizard, auto-save after each step):**

| Step | Content |
|------|---------|
| 1 | Account creation — email + phone OTP verification, password |
| 2 | Personal details — name (as on 10th cert), DOB, gender, nationality, category, Aadhaar (optional at this stage) |
| 3 | Contact details — permanent + correspondence address, emergency contact |
| 4 | Academic history — 10th, 12th (or UG for PG programs), board/university, marks, year |
| 5 | Qualifying exam — JEE/NEET/CAT/SAT/university exam, score, year |
| 6 | Program preference — program, specialization, intake batch, second preference |
| 7 | Other — source channel, hostel requirement, scholarship consideration, disability/special needs |
| 8 | Document uploads — minimum required at submission: 10th marksheet, 12th marksheet, photo, ID proof |
| 9 | Review + DPDP consent declaration + digital signature + submit |
| 10 | Payment (if application fee applicable) |

**System Actions on Submission:**
- DPDP consent record created (E21) — mandatory before any data write
- Unique Application ID generated: `APP-{YEAR}-{6-digit-seq}`
- Application saved as draft until final submission
- On submission: timestamp recorded, status → `Submitted`
- Acknowledgment email sent with Application ID

**Intake Modes:**
- Public URL portal (primary — ~90% of applicants)
- Agent-assisted / walk-in (counselor submits on applicant's behalf)
- CSV/API import pipeline (for NTA/CUET centralized exam applicants — no form, bulk import)

**Re-Admission Branch (E17):**
If applicant selects "I am a returning student" during Step 1, the system branches to the Re-admission pipeline (see E17 section below). Standard admissions pipeline does not apply.

**Trigger to Next Stage:** Status = `Submitted` + payment confirmed (if applicable).

---

## Stage 3 — Document Collection & Verification

**Purpose:** Collect and verify all supporting documents before eligibility screening runs.

**Documents Required:**
- 10th mark sheet, 12th mark sheet (or equivalent)
- Transfer Certificate (TC), Character Certificate
- Migration Certificate (if applicable)
- Category Certificate (SC/ST/OBC/EWS)
- Passport-size photographs (×2)
- Aadhaar card / Government ID
- Entrance test scorecard
- Gap certificate (if applicable)
- NRI/International: Passport + Visa + equivalency certificate

**Verification Levels:**

| Level | Method | Notes |
|-------|--------|-------|
| L1 — Format | Automated | File format (PDF/JPG/PNG), size, resolution (min DPI), completeness against checklist |
| L2 — Content | OCR + Manual officer | AI extracts marks, cross-checks with application form data; officer confirms authenticity |
| L3 — Source | DigiLocker API / Board API | Definitive verification; academic certificates verified at source |

**Document Fraud Detection (EC-ADM-04):**
- DigiLocker API is the ground truth for academic certificates. OCR-only sets confidence < 0.5 and routes to MANUAL_FORENSIC queue regardless of format quality.
- Anomaly signals that trigger POTENTIAL_FORGERY flag: perfect formatting + no DigiLocker match, re-upload attempts exceeding threshold (configurable, default 3), inconsistent font/seal across pages.
- Flagged applications escalate to Admissions Officer + Registrar — not auto-rejected.

**System Actions:**
- Each upload tagged with document type
- Per-document status: Approved / Rejected / Pending
- If rejected: reason recorded, applicant notified with re-upload link
- Reminder SMS auto-sent at T-3 days and T-1 day for pending uploads

**Trigger to Next Stage:** All mandatory documents = `Approved`. Status → `Documents Verified`.

---

## Stage 4 — Eligibility Screening

**Purpose:** Hard gate. Determine whether the applicant meets minimum eligibility criteria. Ineligible applicants do not proceed.

**Eligibility Criteria (configurable per program per batch via PolicyEngine):**
- Minimum % in 12th (e.g., 50% aggregate; 55% PCM for Engineering)
- Mandatory subjects (e.g., Physics + Chemistry + Maths for B.Tech)
- Valid qualifying exam score (JEE rank, NEET score, CAT percentile)
- Age criteria (e.g., NEET mandates min. 17 years)
- Category-specific relaxations (SC/ST/OBC as per UGC norms — stored in `tenant_policies`, not hardcoded)
- Board/university must be on recognized list

**Rules Engine:** `PolicyEngine.evaluate('admissions_eligibility', applicant_data, tenant_id)` — reads `tenant_policies` at runtime. Every eligibility decision stores the policy version used. No hardcoded thresholds anywhere in application code.

**Identity Mismatch Handling (EC-ADM-01):**
Name variants across documents (10th, Aadhaar, JEE scorecard) are evaluated using Jaro-Winkler similarity (threshold ≥ 0.85). Scores below threshold route to KYC_RECONCILIATION queue — not auto-rejected. Aadhaar eKYC API name is used as ground truth when available.

```
name_variants JSONB stored on application record:
  [{"source": "10th", "name": "Sai Kumar Reddy"},
   {"source": "aadhaar", "name": "K. Sai Kumar"},
   {"source": "jee", "name": "Sai K Reddy"}]
```

**Late Joiners / State Counseling (EC-ADM-02):**
Applicants joining after semester start via state counseling are tagged `LATE_JOINER`. On enrollment:
- All past sessions pre-marked `EXCUSED_LATE_JOINER` — excluded from attendance denominator
- `CatchUpCohortWorkflow` (Temporal) generates compressed assignment deadlines
- Standard penalty rules do not apply to the excused period

**Edge Cases:**
- Awaiting results (12th appearing): provisional eligibility, confirmed on final marks
- Compartment/supplementary candidates: handled per institution policy (configurable)
- Foreign qualifications: equivalency check required before rule engine runs

**Trigger to Next Stage:** Status = `Eligible`.

---

## Stage 5 — Entrance Test / Interview

**Purpose:** Assess applicant beyond academic records.

**Sub-processes by program type:**
- Entrance Test — most undergraduate programs
- Personal Interview (PI) — MBA, Law, Design, PhD
- Group Discussion (GD) — management programs
- Portfolio Review — Design, Architecture, Fine Arts
- External score only (JEE/NEET/CAT) — score ingestion, no internal test

**Scheduling:** Applicant self-selects slot from available dates/modes. Admit card or test link auto-generated and emailed. Calendar invites sent for interviews with panel details.

**Data Captured:** Test scores (section-wise), interview scores (per parameter), GD/portfolio scores, panel qualitative remarks, attendance / no-show status.

**System Actions:**
- Online test: proctoring integration (Mettl, TalView, iProctor)
- Objective scores auto-calculated
- Interview scorecard filled by panel in system
- All scores tied to Application ID

**Trigger to Next Stage:** All required assessments completed and scores recorded. Status → `Assessment Complete`.

---

## Stage 6 — Merit List Generation & Selection

**Purpose:** Rank all eligible applicants using a composite score. Generate the selection list within intake capacity — enforced by the Quota Seat Matrix Engine (E19).

**Composite Score Formula (configurable in `tenant_policies`):**
- 12th marks: 30–40%
- Entrance test score: 40–50%
- Interview/GD score: 10–20%
- Extracurricular / diversity bonus: 0–10%

**Quota Seat Matrix Engine (E19) — New in v2:**
The old "seat counter - 1" approach is replaced by the full quota seat matrix. Every seat allocation is tracked by category AND quota bucket simultaneously.

```sql
seat_matrix tracks per program per intake_year:
  total_intake → category breakdown (General/SC/ST/OBC/EWS/PwD)
  → quota breakdown (Management/NRI/Sports)
  → filled_per_category (real-time, updated by PostgreSQL trigger)
  → waitlist_depth_per_category
```

Waitlist activation: when a confirmed seat is released (cancellation, forfeiture), the next candidate is identified within the SAME quota + category bucket — not the overall waitlist rank. Category conversion eligibility (unused SC seats offered to general after configurable deadline) is enforced by the seat matrix engine, not manually.

**List Types:**
- First Merit List (main offer list up to intake capacity)
- Waitlist (ranked reserve per category/quota, activated automatically)
- Category-wise lists (General, SC, ST, OBC, EWS, NRI/Management quota)
- Program-wise lists (each specialization has its own list)

**System Actions:**
- Composite score calculated per applicant
- Ranked list generated per program + category + quota
- Cut-off scores determined
- List reviewed and approved by Admissions Committee
- Merit list published on portal + emailed to selected applicants

**Trigger to Next Stage:** Committee approval. Status → `Offer Pending` for selected applicants.

---

## Stage 7 — Offer Letter Issuance

**Purpose:** Issue formal, signed offer of admission specifying program, batch, fee structure, and acceptance deadline.

**Offer Letter Contents:**
- University letterhead + Registrar/Dean digital signature (Aadhaar eSign or DocuSign)
- Applicant name + Application ID
- Program name, specialization, intake year/semester
- Provisional admission note (subject to document verification)
- Fee structure (from the batch-specific `fee_structures` record — version-locked)
- Scholarship/fee waiver details (if applicable)
- Acceptance deadline
- Documents required on joining day
- Contact details for queries

**Delivery:** Email (system-generated PDF) + downloadable from applicant portal + physical copy for walk-in cases.

**System Actions:**
- Offer letter auto-generated from template using merged applicant data
- Unique offer reference number embedded
- Delivery status tracked (sent / opened / bounced)
- Offer expiry timer starts
- Reminder emails at T-3 days and T-1 day before deadline

**Trigger to Next Stage:** Applicant clicks "Accept Offer" OR pays confirmation fee. Status → `Offer Accepted`.

---

## Stage 8 — Fee Payment & Seat Confirmation

**Purpose:** Collect confirmation fee as proof of commitment. Seat formally reserved only after payment.

**Fee Structure Versioning (Go-Live Blocker — New in v2):**
Fee structures are version-locked per intake batch. A student confirmed in 2025 is billed under the 2025 fee structure for all 4 years — even if the institution revises fees in 2026. The `student_fee_assignments` record created at this stage is immutable after creation. See Finance Module §5.1 for full specification.

**Payment Modes:**
- Online gateway (Debit/Credit Card, Net Banking, UPI) — Razorpay (primary), PayU (fallback)
- Demand Draft (for rural/offline applicants)
- NEFT/RTGS (for NRI/international applicants)

**Webhook Drop Resilience (EC-ADM-05):**
Razorpay webhook failures are handled by the `PaymentDisputeWorkflow` (Temporal):
1. Student submits UTR number via dispute portal
2. System lifts access restrictions for 48 hours
3. System queries Razorpay API directly to verify payment
4. If captured: payment posted to ledger permanently
5. If not found after 48 hours: restriction restored + Finance Officer alerted
6. All webhook processing is idempotent — `payment_webhook_log` table prevents duplicate posting

**System Actions:**
- Payment link generated and sent to applicant
- On success: PDF receipt generated, status → `Seat Confirmed`
- Seat matrix counter decremented in the correct category/quota bucket (E19 trigger)
- Finance ledger entry created

**Refund Logic:**
Cancellation date vs. UGC policy slab determines refund eligibility. Refund request triggers Finance FM-3 workflow automatically.

**Trigger to Next Stage:** Payment confirmed, receipt generated. Status → `Seat Confirmed`.

---

## Stage 9 — Final Document Verification

**Purpose:** Verify original documents (physical or DigiLocker) against uploaded copies. Hard gate before enrollment.

**Verification Modes:**
- In-person on Reporting Day (applicant brings originals to campus)
- DigiLocker-linked (auto-verified via API)
- Courier + physical dispatch (remote/NRI applicants)

**Ghost Withdrawal Prevention (EC-ADM-03):**
A seat-confirmed applicant who does not report on Reporting Day enters the `REPORTING_PENDING` state. The `ReportingGateWorkflow` (Temporal) manages:
1. Day 1: Reminder SMS + email sent
2. Day 2: Second reminder + parent notification
3. Day 3: Forfeiture warning — student has 48 hours to report or respond
4. Day 5 (configurable SLA): If no response, seat forfeited — waitlist activated immediately in correct category/quota bucket

Feature flag: `admissions.biometric_reporting_gate` — enables biometric check-in verification on Reporting Day.

**Documents Verified:**
Original 10th and 12th mark sheets + certificates, Transfer Certificate, Migration Certificate, Category certificate, Character certificate, Medical fitness certificate (select programs), Gap certificate with affidavit, Government ID (Aadhaar/Passport).

**System Actions:**
- Officer reviews uploaded copies side-by-side with originals in system
- Per-document outcome: Verified / Discrepancy Found / Not Produced
- Discrepancy → escalated to Admissions Committee; applicant given notice period
- All clear → status → `Documents Verified — Final`

**Trigger to Next Stage:** All documents = `Verified — Final`. Status → `Ready for Enrollment`.

---

## Stage 10 — Enrollment & Roll Number Assignment

**Purpose:** Convert the confirmed applicant into an enrolled student with a permanent institutional identity across all systems.

**Actions at This Stage:**
- Enrollment form finalized
- Roll number assigned: `{YY}{ProgramCode}{Sequential}` e.g., `25BCE0001`
  - Re-admitted students: `{YY}RE-{ProgramCode}-{SEQ}` e.g., `25RE-BCE-0001` (E17)
  - Lateral entry: separate series (configurable)
- University Registration Number (URN) generated
- Student ID card created and dispatched

**EVENT: `student.enrolled` fires immediately on this status change.**

All downstream provisioning is event-driven — no manual steps:
- Academic module: batch + section + mentor assigned, LMS provisioned, timetable slot reserved, risk baseline built
- Finance: fee schedule generated (version-locked to intake batch), first invoice issued
- Student Services: hostel room allotted (if opted), library membership activated
- HR: mentor notified
- Regulatory: enrollment data fed to NAAC C2, AISHE, UGC annual return metrics

**Payload of `student.enrolled` event:**

| Field | Used For |
|-------|----------|
| Student ID / Roll No. | Master key across all records |
| Full name | All documents, certificates, ID card |
| Program + Specialization | Curriculum assignment |
| Intake year + Semester | Academic calendar alignment |
| Category (SC/ST/OBC/EWS) | Scholarship tracking, reservation reporting |
| Email + phone | All notifications |
| Parent/guardian contact | Attendance alerts, mentorship comms |
| Entrance score + 12th marks | Mentorship risk baseline |
| Hostel assignment (Y/N) | Warden notification, risk weight |
| Elective preferences | LMS course shell enrollment |
| fee_category | Fee schedule computation |
| is_late_joiner | Catch-up cohort workflow trigger |
| is_readmission | Re-admission handling flag |

**Post-Enrollment Triggers (fully automated):**
- Welcome email with all credentials
- Orientation schedule
- Reporting and joining instructions
- Parent/guardian notification
- DPDP consent record updated: enrollment confirmed, all downstream data uses logged

**Terminal Stage.** Student moves into the Student Information System under Academic Operations.

---

## E17 — Re-Admission & Credit Transfer

*(Full spec: references/gaps.md E17)*

**Re-Admission Branch:**
Activated when an applicant selects "Returning student" at Stage 2. Standard admissions pipeline does not apply.

**State Machine:** `SUBMITTED → UNDER_REVIEW → APPROVED / REJECTED`

**On Approval:**
1. Student record reactivated (status `ARCHIVED → ACTIVE`)
2. RE-prefixed roll number generated
3. Completed semesters locked — marks and attendance immutable
4. `student.readmitted` event fires → `CatchUpCohortWorkflow` triggered in Academics
5. Credit transfer evaluation workflow initiated if returning from different institution

**Credit Transfer:**
For students transferring from another university: AI drafts credit equivalency mapping comparing source transcript with ALIS curriculum. Academic Committee reviews and approves. `credit_transfer_applications` table tracks all equivalency decisions with full audit trail.

---

## E19 — Quota Seat Matrix Engine

*(Full spec: references/gaps.md E19)*

**Summary of integration with Admissions:**
- At Stage 6 (merit list): seat availability shown in real-time per category + quota bucket
- At Stage 8 (fee payment): confirmed seat decrements the correct bucket via PostgreSQL trigger
- At Stage 8 (cancellation): seat returned to correct bucket, waitlist activated for that bucket only
- Category conversion: unused SC seats eligible for general after configurable deadline — enforced by seat matrix engine, not manually

---

## Application Status State Machine

| Status | Meaning |
|--------|---------|
| `Lead Captured` | Prospect in CRM, not yet applied |
| `Application Draft` | Form started, not submitted |
| `Submitted` | Form submitted; payment pending or N/A |
| `Pending Payment` | Application fee due |
| `Documents Pending` | Awaiting document uploads |
| `Under Document Review` | Officer reviewing uploads |
| `Documents Verified` | First-level check cleared |
| `KYC_RECONCILIATION` | Name mismatch — under review (EC-ADM-01) |
| `POTENTIAL_FORGERY` | Document fraud signal — escalated (EC-ADM-04) |
| `Eligibility Screening` | Rule engine running |
| `Eligible` | Passed eligibility check |
| `Ineligible` | Failed eligibility check (with reason + policy version) |
| `Assessment Scheduled` | Test/interview slot booked |
| `Assessment Complete` | Scores recorded |
| `Merit List Generated` | Ranked list published |
| `Offer Issued` | Offer letter sent |
| `Offer Accepted` | Applicant confirmed |
| `Offer Declined / Expired` | Seat freed; next waitlist candidate triggered (correct bucket) |
| `Seat Confirmed` | Fee paid; seat reserved |
| `REPORTING_PENDING` | Fee paid but applicant has not reported (EC-ADM-03) |
| `Final Verification Pending` | Awaiting original document check |
| `Ready for Enrollment` | All verifications cleared |
| `Enrolled` | Student record + roll number created |
| `Re-Admission Pending` | Re-admission application under review (E17) |
| `Re-Admitted` | Returning student enrolled with RE-prefix roll number |
| `Cancelled / Withdrawn` | Applicant dropped at any stage |
| `Forfeited` | Ghost withdrawal — seat released to waitlist (EC-ADM-03) |

---

## Edge Cases in This Module

| ID | Edge Case | Status | Spec Location |
|----|-----------|--------|---------------|
| EC-ADM-01 | Identity mismatch across documents | P1 — Sprint 2 | references/edge-cases.md |
| EC-ADM-02 | State counseling late joiners | P1 — Sprint 2 | references/edge-cases.md |
| EC-ADM-03 | Ghost withdrawal — seat occupied by absent student | P0 — Sprint 1 | references/edge-cases.md |
| EC-ADM-04 | Forged document — OCR passes, document is fake | P0 — Sprint 1 | references/edge-cases.md |
| EC-ADM-05 | Razorpay webhook drop on fee payment | P0 — Sprint 1 | references/edge-cases.md |

---

## Automated Communication Touchpoints

| Trigger Event | Channel | Recipient | Content |
|--------------|---------|-----------|---------|
| Lead captured | Email | Prospect | Welcome + brochure |
| Application submitted | Email | Applicant | Acknowledgment + Application ID |
| DPDP consent confirmed | Email | Applicant | Consent receipt + data processing notice |
| Application fee due | Email + SMS | Applicant | Payment link |
| Document rejected | Email + portal | Applicant | Reason + re-upload link |
| Identity mismatch flagged | Email | Applicant | KYC reconciliation instructions |
| Eligibility result | Email | Applicant | Eligible / Ineligible with reason + policy version |
| Test scheduled | Email | Applicant | Admit card or test link |
| Merit list published | Email + portal | Applicant | Selected / Waitlisted / Rejected |
| Offer issued | Email | Applicant | Offer letter PDF |
| Offer deadline T-3 | Email + SMS | Applicant | Reminder with link |
| Offer deadline T-1 | SMS | Applicant | Final reminder |
| Seat confirmed | Email | Applicant + Parent | Receipt + next steps |
| Reporting day reminder | Email + SMS | Applicant | Date, documents to bring |
| Reporting Day missed (Day 1) | SMS + Email | Applicant + Parent | Reminder + consequence warning |
| Forfeiture warning | Email + SMS | Applicant + Parent | 48-hour deadline |
| WhatsApp (if enabled) | WhatsApp | Student + Parent | All key milestones via MSG91 template |
| Enrollment complete | Email | Student + Parent | Welcome, credentials, orientation |

---

## Role-Based Access Map

| Role | Access Scope |
|------|-------------|
| Applicant | Self-service portal: fill form, upload docs, pay fees, track status, download letters |
| Admissions Counselor | CRM: manage leads, assist applicants, view status |
| Document Verification Officer | Review + approve/reject documents; send re-upload requests |
| Admissions Officer | Full application review, manual status updates, eligibility overrides (logged) |
| Exam Cell | Schedule tests, upload scores, generate admit cards |
| Interview Panel Member | View assigned applications + documents; fill scorecard only |
| Admissions Committee | Approve merit lists, set cut-offs, manage quotas, override decisions |
| Finance / Accounts | View payments, reconcile, process refunds, generate reports |
| Registrar | Final enrollment, roll number assignment, official record generation |
| IT Admin | System config, user management, integration monitoring |
| Dean / Director | Read-only dashboards, analytics, exception approvals |
| Guardian (E16) | Read-only view of child's application status (post-enrollment portal) |

---

## Shadow Mode Behaviour (Go-Live Blocker)

During shadow mode onboarding (see architecture.md §28), all outbound communications from this module are suppressed. Eligibility checks, merit list computation, and seat matrix operations run in full — but no emails, SMS, or WhatsApp messages are sent to applicants. Staff see what ALIS would have done vs. what was actually done manually, and flag divergences. Go-live is blocked until divergence on key metrics (seat counter accuracy, eligibility verdict accuracy) is below threshold for 5 consecutive days.

---

## Data Migration (Go-Live Blocker)

For institutions onboarding mid-cycle with existing applicant data in spreadsheets or legacy ERPs:
- CSV import template available for: applications, documents status, payment records
- Validation layer runs every row through the same rules engine before committing
- Dry-run mode shows what will be created without writing to the database
- Duplicate detection: Jaro-Winkler match on (name + DOB + phone) before inserting
- All imported records tagged `data_source = 'migration_pipeline'` in audit ledger

See architecture.md §27 for full migration pipeline specification.

---

## V2 Hooks — WhatsApp Interface

When ALIS V2 WhatsApp control is live (see V2 plan), applicants and parents will be able to:
- Check application status by sending a message
- Receive all key milestone notifications via WhatsApp
- Complete certain confirmation actions (offer acceptance) via reply

The Admissions module's communication layer is already structured for this — every notification dispatches to `WhatsAppChannel` if the `communication.whatsapp` flag is enabled. No changes to Admissions business logic required for V2.

---

## Integration Checklist

| Integration | Purpose | Mode |
|-------------|---------|------|
| Razorpay / PayU | Fee collection | REST API + webhook (idempotent) |
| DigiLocker API | Academic certificate verification | REST API (NIC) |
| MSG91 | SMS + WhatsApp notifications | REST API |
| SendGrid / AWS SES | Transactional emails | REST API |
| CRM | Lead management | LeadSquared / webhook |
| SIS/ERP | Student master records | API if available; CSV export fallback |
| Moodle / Canvas | LMS account creation (post-enrollment) | REST API |
| Google Workspace / Microsoft 365 | Student email provisioning | Admin API |
| NTA / Board APIs | External score import | File import pipeline (CSV/Excel) |
| HashiCorp Vault | Secure credential storage | Internal |
| E21 DPDP Module | Consent capture and logging | Internal event |
| E19 Seat Matrix | Real-time seat availability | Internal trigger |

---

## SLA & Escalation Matrix

| Gate | Approver | SLA | Breach Action |
|------|----------|-----|---------------|
| Document review | Doc Verification Officer | 3 business days | Escalates to Admissions Officer |
| Eligibility override | Admissions Director | 2 business days | Escalates to Admissions Committee |
| Shortlist approval | HR Officer + HOD | 3 business days | Dean reviews if HOD delays |
| Merit list approval | Admissions Committee | 5 business days | Dean + VC review |
| Offer acceptance window | Applicant | Per offer letter (typically 7 days) | Offer expired; next waitlist candidate activated |
| Reporting day response | Applicant | 5 days from Reporting Day | Seat forfeited; waitlist activated (EC-ADM-03) |
| Final document verification | Admissions Verification Officer | Reporting day | Registrar escalated |
| Enrollment processing | Registrar | 1 business day after docs cleared | Dean notified |

---

*Document version: 2.0 | March 2026*
*Supersedes: Admissions.md v1.0*
*QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential*
*Cross-references: academic_operations_workflow.md | finance_workflow.md | references/architecture.md §5, §21–§28 | references/gaps.md E17, E19 | references/edge-cases.md EC-ADM-01 through EC-ADM-05*
