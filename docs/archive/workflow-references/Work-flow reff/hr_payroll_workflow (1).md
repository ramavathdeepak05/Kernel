# HR & Payroll Module Workflow
### Full Automation Reference — ALIS OS Module E08
#### Model: AI Executes Everything. Actors Approve.
#### QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential

---

## Document Map

This document covers the full HR & Payroll module (E08) of ALIS OS.

**Connected documents:**
- `finance_workflow.md` — FM-5 owns salary computation and disbursement; HR supplies inputs
- `academic_operations_workflow.md` — faculty timetable assignment, CAS appraisal Category I data, EC-ACA-02 faculty attrition handover
- `examination_workflow.md` — invigilator assignments, exam duty leave
- `regulatory_accreditation_workflow.md` — consumes faculty qualification data, API scores, training records, research publications for NAAC/NIRF/AICTE/AISHE/UGC

**Cross-references to skill files:**
- Edge cases: `references/edge-cases.md` — EC-HR-01, EC-HR-02, EC-HR-03
- MFA requirement: `references/architecture.md` §23 — HR Officer role is in `MFA_REQUIRED_ROLES`
- DPDP employee data: `references/architecture.md` §22 — E21 consent and erasure apply to employee records
- Build sequence: `ALIS_BUILD_PLAN.md` — Sprint 3 (EC-HR-01, EC-HR-02), Sprint 4 (EC-HR-03)

---

## Core Operating Principle

AI executes every task. Humans (Actors) only Approve, Reject, or Escalate at defined gates.

All six HR domains operate on this model:
- AI drafts every job advertisement, appointment letter, payslip, appraisal form,
  training plan, and exit document — without staff initiation
- Every approval gate has a defined SLA with auto-escalation on breach
- Employee data flows bidirectionally with Finance Module FM-5 (payroll computation)
  — HR supplies inputs; FM-5 owns computation and disbursement
- UGC Regulations 2018 (operative) and Draft 2025 norms (tracked) govern faculty
  recruitment, qualification verification, and CAS promotions
- All employee records maintained under DPDP Act 2023 — accessible only by
  authorised roles, with bank account numbers and Aadhaar partially masked in all
  views except Finance Officer
- HR module is a primary data source for the Regulatory module (E14):
  faculty qualification %, PhD %, NET/SLET %, research publications, training
  completion, and sanctioned vs. filled positions are consumed by NAAC, NIRF,
  AICTE, AISHE, and UGC returns

**MFA required:** HR Officer role is in `MFA_REQUIRED_ROLES`. Every login requires
TOTP. See `references/architecture.md` §23.

---

## Employee Categories in Scope

| Category | Designation Examples | Pay Structure | UGC Norms Apply |
|---|---|---|---|
| Teaching Faculty (Full-time) | Assistant Professor, Associate Professor, Professor | 7th CPC Academic Pay Level (10 / 13A / 14) | Yes — NET/PhD mandatory |
| Non-Teaching Staff | Lab Technician, Library Staff, Sports Coach | Institutional pay scale | No |
| Contract / Visiting Faculty | Guest Lecturer, Adjunct Faculty | Per-lecture / per-semester contract | Yes — same eligibility norms |
| Administrative Staff | Registrar, Accounts Officer, Office Assistant | Institutional pay scale | No |
| Management / Leadership | VC, Registrar, Dean, HOD | Senior pay scale / management grade | Yes (VC/Dean) |

**Contract / Visiting Faculty note (UGC Draft 2025):**
Appointment max 6 months per UGC Draft 2025 norms. Same eligibility norms as
permanent faculty. Visiting faculty payment is governed by EC-HR-01 (see below).

---

## Actors

| Actor | Scope of Authority | Escalation Path |
|---|---|---|
| HR Officer | All 6 HR domains — primary operator | VC / Registrar |
| HOD | Faculty recruitment initiation, performance appraisal for their department, leave approval | Dean → VC |
| Dean | Senior faculty appointments, promotion recommendations, disciplinary referrals | VC |
| VC / Registrar | All appointments, final promotion orders, separation approvals | Board / Governing Body |
| Finance Officer | Payroll input validation, statutory deduction approvals (shared with FM-5) | VC |
| Employee | Self-service: leave, document requests, appraisal self-assessment, training registration | HR Officer |
| Selection Committee | Faculty selection (UGC-mandated composition) | VC |

---

## Module Overview

| # | HR Domain | Primary Trigger | Primary Actor | Stages |
|---|---|---|---|---|
| HR-1 | Recruitment & Onboarding | VC sanctions vacancy / HOD raises requisition | HR Officer + Selection Committee | 10 stages |
| HR-2 | Employee Records & Contracts | `employee.joined` event | HR Officer | 6 stages |
| HR-3 | Attendance & Leave Management | Daily cycle (auto) / Employee leave application | HR Officer + HOD | 7 stages |
| HR-4 | Performance Appraisal | Annual appraisal cycle start (configurable) | HR Officer + HOD + Dean | 8 stages |
| HR-5 | Training & Development | Post-appraisal gap analysis / Management directive | HR Officer + HOD | 6 stages |
| HR-6 | Separation & Exit Management | Employee resignation / contract end / retirement | HR Officer + Dean + VC | 8 stages |

---

## HR-Finance Boundary (Shared Payroll Model)

HR and Finance share payroll stages. The boundary is strictly defined:

| Stage | Owner | Action | Event |
|---|---|---|---|
| Attendance & LOP computation | HR-3 | AI computes working days, LOP, on-duty | `payroll.inputs_ready` → FM-5 |
| Increment / grade change | HR-2 / HR-4 | AI computes revised pay level | `pay_revision.ready` → FM-5 |
| Full & final settlement | HR-6 | AI computes EL encashment + gratuity | `final_settlement.ready` → FM-5 |
| New joinee payroll | HR-1 | AI sends joining date, pay scale, TDS declaration | `employee.joined` → FM-5 |
| Visiting faculty billing | HR-3 (EC-HR-01) | AI computes from session log | `payroll.inputs_ready` → FM-5 |
| Gross salary computation | FM-5 | AI computes gross per grade table | Internal to FM-5 |
| Statutory deductions (PF/ESI/PT/TDS) | FM-5 | AI computes and schedules deposits | Internal to FM-5 |
| Payslip generation | FM-5 | AI generates and distributes | `payslip.issued` → HR-2 (stored in employee file) |
| Form 16 | FM-5 | AI generates annual TDS certificate | `form16.issued` → HR-2 (stored in employee file) |

**Rule:** HR never touches salary computation. Finance never touches attendance or
leave records. Data flows via events only.

---

## HR-1: Recruitment & Onboarding

**Trigger:** VC sanctions a new position, OR HOD raises a Manpower Requisition for a
vacant post, OR contract faculty's term nears end and a replacement is needed. AI
initiates the recruitment workflow automatically on sanction.

**Gate:** Vacancy cannot be sanctioned until `budget.approved` event has fired from
FM-6 for the relevant budget head. The system validates budget availability before
allowing the PR to proceed.

**UGC Minimum Qualifications (Regulations 2018 — operative):**

| Position | Minimum Qualification | Additional Requirement |
|---|---|---|
| Assistant Professor | Master's degree ≥ 55% + NET/SLET/SET | OR PhD as per UGC (Minimum Standards) Regulations 2009 |
| Associate Professor | PhD + 8 years teaching/research experience | Min 7 research publications in peer-reviewed/UGC-listed journals |
| Professor | PhD + 10 years experience (post-PhD) | Min 10 research publications + evidence of PhD guidance |
| Contract / Guest Faculty | Same as Assistant Professor | Max 6 months per UGC Draft 2025; same eligibility norms |
| Non-Teaching / Admin Staff | As per institutional requirements | No UGC mandate; institutional policy applies |
| VC | As per university statute | Selection by Search Committee per UGC/State norms |

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 1.1 | Manpower Requisition | HOD submits requisition via portal. AI validates: position exists in sanctioned strength, budget head available in FM-6 (`budget.approved` event fired), workload justifies new hire. | VC approves requisition. Dean endorses. | Requisition approved. `vacancy.sanctioned` event. | 5 business days |
| 1.2 | Job Advertisement Drafting | AI drafts advertisement per UGC format: post title, department, pay scale (7th CPC level), minimum qualifications (NET/PhD as applicable), application deadline, selection committee composition, reservation roster (SC/ST/OBC/EWS per roster point). | HR Officer reviews. VC approves before publication. | Advertisement published on institutional website, UGC portal, and configured job boards. | 2 business days post-sanction |
| 1.3 | Application Screening | Receives online applications. Extracts structured data: qualifications, publications, experience, NET/PhD status. Runs UGC eligibility check automatically. Flags ineligible applications with specific reason. Generates eligible applicant list. | HR Officer reviews flagged borderline cases. | Eligible applicant list generated. Ineligible applicants notified with reason. | Application window close date |
| 1.4 | Shortlisting | Ranks eligible applicants by configurable criteria: qualification score, research publications count, teaching experience, API scores (if provided). Generates shortlist of top N candidates. Notifies shortlisted candidates with interview date/mode. | HR Officer + HOD review and approve or adjust. | Shortlist approved. Interview call letters sent. | 5 business days post-application close |
| 1.5 | Selection Committee Constitution | AI generates Selection Committee composition per UGC Regulations: VC (Chairperson), 3 external subject experts (from VC-approved panel), HOD, SC/ST/OBC/Women representative (if applicable). Schedules meeting. | VC nominates external experts. Confirms committee composition. | Selection Committee constituted. Meeting scheduled. | 7 business days post-shortlisting |
| 1.6 | Interview & Selection | AI sends pre-interview dossier to each committee member: candidate CV, eligibility verification, research publication list, UGC API score summary. Records committee proceedings digitally. Captures merit list with scores. | Selection Committee conducts interview/seminar. Records verdict and merit rank. VC approves final merit list. | Merit list approved. `selection.complete` event. Selected candidate notified. | Per interview date |
| 1.7 | Offer Letter Generation | AI drafts appointment letter: designation, department, pay scale, date of joining, probation period, terms and conditions, bond (if applicable), service rules reference. | VC signs appointment letter (digital signature). | Appointment letter issued. Acceptance deadline set (typically 15 days). | 3 business days post-selection |
| 1.8 | Pre-Joining Verification | Candidate submits joining documents: original certificates, experience letters, research publications, medical fitness, police verification. AI runs completeness check. Flags missing or suspicious documents. | HR Officer verifies originals on joining day. | Document verification complete. Pre-joining report generated. | Joining date |
| 1.9 | System Onboarding | On joining: AI creates Employee ID (format: `EMP + dept_code + sequential`). Provisions email, LMS access, library membership, payroll record, attendance system entry. Sends welcome kit (org chart, policies, academic calendar, IT credentials). | HR Officer confirms physical joining. | `employee.joined` event fired. All access provisioned. Employee master record created. | Joining day |
| 1.10 | Induction Programme | AI schedules induction: HR policies session, campus tour, department orientation, Academics module briefing, Finance self-service walkthrough. Tracks attendance. Sends completion certificate. | HOD conducts department-level orientation. HR Officer hosts HR policy session. | Induction completion recorded in employee profile. Probation clock starts. | First week of joining |

**Cross-module note:** `employee.joined` is consumed by:
- Finance FM-5 → creates payroll record
- Academics → adds faculty to timetable assignment pool
- Library → creates staff membership
- Regulatory E14 → updates sanctioned vs. filled positions count, faculty qualification %

**Faculty attrition cross-reference:** When `separation.initiated` fires during
an active semester, the Academic module triggers `CourseHandoverWorkflow` (EC-ACA-02
in `academic_operations_workflow.md`). HR module's role: initiate the no-dues process,
revoke system accesses on last working day, and ensure the Academic module receives the
separation event before LMS access is revoked (to allow handover package generation).

---

## HR-2: Employee Records & Contracts

**Trigger:** `employee.joined` event. AI auto-creates the master employee record.

**DPDP Act 2023 — employee data handling:**
Employee records contain sensitive personal data subject to the DPDP Act.
Specific requirements enforced by the system:
- Bank account numbers: partially masked in all views except Finance Officer
  (`XXXX XXXX 1234` format)
- Aadhaar number: masked entirely in all UI views; stored encrypted at rest
- Salary data: accessible only to Finance Officer, HR Officer, and the employee
  themselves — not to HOD or Dean
- On separation: employee PII is archived (not deleted) with a 7-year retention
  period for statutory compliance (PF, ESI, TDS, Gratuity Act)
- Employee can request data export (DPDP right to access) via the self-service
  portal; HR Officer receives the request and approves the export
- Employee cannot request erasure while statutory retention period is active

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 2.1 | Master Record Creation | Creates employee master: Employee ID, name, designation, department, date of joining, pay scale, category, PAN, Aadhaar (masked), bank account (masked), PF UAN, ESI IP number, emergency contact. | HR Officer verifies all data against original documents. | Employee master record live. All downstream modules receive data via `employee.joined`. | Joining day (instant) |
| 2.2 | Contract & Service Agreement | AI drafts service agreement per category: full-time (permanent/probation), contract (fixed-term with end date), visiting faculty (per-semester with per-lecture rate per EC-HR-01 schema). Includes: probation period, notice period, IP ownership clause, moonlighting policy, confidentiality. | VC countersigns permanent appointments. Dean countersigns contract faculty. Employee signs (digital). | Signed contract stored in employee digital vault. Contract end date set — auto-reminder 60 days before expiry. | 2 business days post-joining |
| 2.3 | Document Vault | Maintains encrypted digital file per employee: joining documents, certificates, appointment letter, contract, increments, promotions, disciplinary records, training certificates, appraisal reports. Tracks document expiry (e.g., medical fitness certificate — annual renewal). | HR Officer uploads verified originals. | Document vault complete. Missing / expiring document alerts sent automatically. | Ongoing |
| 2.4 | Probation Management | Tracks probation period (1–2 years for full-time, configurable). At midpoint: generates probation review form. At end: generates confirmation report with HOD input. | HOD submits probation review. VC signs confirmation order or extends probation. | `employee.confirmed` or `probation.extended` event. FM-5 payroll updated for any confirmation increment. | At probation milestones |
| 2.5 | Increment Management | Annual increment: AI computes per pay scale rules (3% annual increment on basic for 7th CPC scales; configurable for institutional scales). Generates increment order. Updates pay scale. Sends `pay_revision.ready` to FM-5. | Finance Officer approves increment batch. VC signs for HOD and above. | Increment order issued. FM-5 payroll updated. Employee notified. | Annually (April 1 or joining anniversary — configurable) |
| 2.6 | Statutory Compliance Records | Maintains UAN-linked PF records (ECR monthly). ESI records for eligible employees (salary ≤ ₹21,000). PT deduction records per Telangana schedule. Gratuity eligibility tracking (5-year service threshold). POSH register (ICC compliance tracking). | Finance Officer reviews statutory records quarterly. | Statutory records current. Gratuity liability computed and reported to management annually. | Ongoing (monthly for PF/ESI) |

**Shared faculty (EC-HR-03):**
For faculty teaching across departments, the employee master must use the
`employee_department_assignments` table with `weight_pct` per department.
See the edge case section below. Single-department records remain unchanged.

---

## HR-3: Attendance & Leave Management

**Trigger:** Daily attendance cycle runs automatically. Leave applications submitted
by employees via self-service portal.

**Leave Types in Scope:**

| Leave Type | Entitlement | Carry Forward | Encashable |
|---|---|---|---|
| Casual Leave (CL) | 12 days / year | No | No |
| Earned Leave (EL) | 30 days / year (accrues 2.5 days/month) | Yes — max 300 days | Yes (on retirement/separation) |
| Medical / Sick Leave (ML) | 10 days / year | Yes — max 180 days | No |
| Maternity Leave | 26 weeks (first 2 children) | N/A | No |
| Paternity Leave | 15 days | No | No |
| Study Leave | As per institutional policy | N/A | No |
| Duty Leave | For official work (conferences, exam duty) | N/A | No |
| Special Casual Leave | Election duty, blood donation, etc. | N/A | No |
| Loss of Pay (LOP) | Beyond entitlement | N/A | Deducted from salary |

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 3.1 | Daily Attendance Marking | Pulls biometric / RFID / manual data. Marks each employee: PRESENT / ABSENT / HALF-DAY / ON-DUTY / ON-LEAVE. Reconciles with approved leave records. Flags discrepancies (absent but no leave applied). | HR Officer resolves flagged discrepancies within 2 days. | Daily attendance register updated. `attendance.daily` event fired. | Daily (auto, end of shift) |
| 3.2 | Leave Application Processing | Employee submits via portal. AI checks: leave balance available, no exam/critical schedule conflict (reads Academic Calendar), no excessive concurrent team absence. Classifies as routine or requires escalation. | HOD approves/rejects for faculty and staff. HR Officer approves for admin staff. | Leave approved/rejected. Calendar updated. Attendance system updated. Applicant notified. | 2 business days |
| 3.3 | Leave Balance Tracking | Monthly: credits EL accrual (2.5 days/month). Tracks CL, ML utilisation. Carries forward EL per rules. Flags employees with negative balance (LOP). Generates leave balance statement on employee portal (always current). | HR Officer resolves disputes. | Leave balances updated. LOP flag sent to FM-5 for payroll deduction. | Monthly (auto) |
| 3.4 | Duty Leave & On-Duty Management | Faculty attending conference, exam duty, university visit submits on-duty request with event details. AI validates legitimacy. Records duty leave — does not deduct from leave balance. | HOD approves on-duty request. Dean approves for international travel. | Duty leave recorded. Attendance marked ON-DUTY. Travel advance request routed to FM-4 if applicable. | 3 business days |
| 3.5 | Maternity / Paternity Leave | Employee applies with medical/birth certificate. AI verifies entitlement (child count for maternity). Marks attendance for entire period. Coordinates with FM-5 for full pay maintenance. Triggers replacement faculty arrangement via Academic module. | HR Officer confirms documents. VC approves maternity leave order. | Leave sanctioned. Full pay maintained. `maternity.leave.started` event → Academic module for course coverage. | 5 business days |
| 3.6 | Absenteeism Monitoring | Weekly: identifies employees with ≥ 3 unplanned absences in a month or attendance below 85% (configurable). Generates absenteeism alert. Auto-drafts warning letter for HR Officer review. Chronic absenteeism (3+ months) escalated to Dean. | HR Officer reviews and issues warning letter. Dean initiates formal action for chronic cases. | Absenteeism alerts generated. Warning letters issued. | Weekly (auto) |
| 3.7 | Payroll Input File (visiting faculty — EC-HR-01) | On payroll cut-off date: for regular staff — generates payroll input file per employee (working days, LOP, on-duty, OT if applicable). For visiting faculty — computes from `visiting_faculty_session_log` where `payable = true`. Sends to FM-5. | HR Officer reviews and certifies payroll input file. | `payroll.inputs_ready` event fired to FM-5. | 20th of each month |

### EC-HR-01 — Visiting Faculty Session Billing (P1 — Sprint 3)

**Trigger:** Guest lecturers paid per lecture. 3 sessions were cancelled (campus
event), 2 extra unplanned tutorials were added. The automated payroll run uses the
timetable-scheduled count, not the actual delivered count.

**What breaks:** Over- or under-payment. Contractual dispute. A payroll reversal
in the next cycle creates resentment. Both over- and under-payment are legally
problematic for a contract engagement.

**Fix: Timesheet-to-Payroll Bridge with OTP confirmation**

```sql
CREATE TABLE visiting_faculty_session_log (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL,
    faculty_id        UUID NOT NULL,
    timetable_slot_id UUID,              -- NULL for unscheduled sessions
    session_date      DATE NOT NULL,
    start_time        TIME NOT NULL,
    end_time          TIME NOT NULL,
    session_type      TEXT NOT NULL
        CHECK (session_type IN ('lecture', 'tutorial', 'lab', 'other')),
    status            TEXT NOT NULL
        CHECK (status IN (
            'SCHEDULED',
            'DELIVERED',
            'CANCELLED',
            'UNSCHEDULED_ADDED'
        )),
    faculty_confirmed BOOLEAN DEFAULT false,
    faculty_otp_used  TEXT,              -- OTP used to confirm session delivery
    confirmed_at      TIMESTAMPTZ,
    hod_verified      BOOLEAN DEFAULT false,  -- required for UNSCHEDULED_ADDED sessions
    hod_verified_at   TIMESTAMPTZ,
    rate_per_session  DECIMAL(10,2),     -- pulled from contract at session creation
    payable           BOOLEAN GENERATED ALWAYS AS (
                          faculty_confirmed AND status = 'DELIVERED'
                      ) STORED
);
```

**Flow:**
1. AI sends an OTP via SMS to the faculty member at the scheduled start time of each session
2. Faculty confirms OTP → session marked `DELIVERED` and `faculty_confirmed = true`
3. No OTP confirmation within 30 minutes of scheduled start → session flagged for HOD review
4. Unscheduled sessions added by faculty (e.g., an extra tutorial) require `hod_verified = true` before `payable = true`
5. Cancelled sessions are marked `CANCELLED` by the timetable system automatically (from EC-ACA-02 handling)

**Payroll computation query:**
```sql
SELECT SUM(rate_per_session) AS payable_amount
FROM visiting_faculty_session_log
WHERE faculty_id = $1
  AND tenant_id = $2
  AND DATE_TRUNC('month', session_date) = $3  -- payroll month
  AND payable = true;
```

This query is the only input to FM-5 for visiting faculty. The timetable-scheduled
count is never used directly for payment.

---

## HR-4: Performance Appraisal

**Trigger:** Annual appraisal cycle initiated at configurable date (default: March 1).
AI auto-distributes appraisal forms.

**Appraisal Framework:**

| Employee Category | Appraisal System | Used For |
|---|---|---|
| Teaching Faculty | PBAS / API Score (UGC framework) | CAS Promotion, Annual Increment, NAAC |
| Non-Teaching Staff | Annual Confidential Report (ACR) | Increment, Confirmation, Promotion |
| Contract / Visiting Faculty | Simplified scorecard | Contract renewal decision |
| Administrative Staff | KRA-based appraisal | Increment, Promotion |
| Management / Leadership | 360° feedback + Board review | Board decision |

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 4.1 | Appraisal Cycle Initiation | On cycle start date: auto-distributes forms per employee category. Pre-fills: employee details, designation, department, period under review, existing pay level. For faculty: pulls Category I data from Academics module (lectures delivered, students mentored, assignments evaluated) and Category III data from `PublicationDiscoveryService` (see EC-HR-02). | HR Officer reviews pre-filled data before distribution. | Forms distributed. Employees notified. Submission deadline set (typically 21 days). | Cycle start date (auto) |
| 4.2 | Self-Assessment Submission | Faculty submits Category I, II, III self-assessment. AI validates: checks publications against research database (Scopus/UGC-listed journals cross-reference), validates conference attendance against certificates, computes provisional API score per UGC formula. Flags unsubstantiated claims. AI score is always `AI_COMPUTED` draft — faculty must Accept to transfer liability (EC-HR-02). | Employee submits and resolves AI flags before final submission. | Self-assessment submitted and validated. Provisional API score computed. | 21 days post-distribution |
| 4.3 | Student Feedback Integration | Pulls student feedback scores from Academics module (per faculty, per course). Computes average feedback score. Integrates into Category I teaching score. | No action — fully automated. | Student feedback score integrated. Faculty can view their score. | Concurrent with self-assessment window |
| 4.4 | HOD Assessment | AI generates HOD assessment form pre-filled with: faculty self-assessment, student feedback, provisional API score, attendance record, committees served. HOD rates qualitative parameters. For shared faculty (EC-HR-03): HOD assessment form is split per department. | HOD reviews and fills qualitative assessment. Submits to Dean. | HOD assessment recorded. Combined score (self + HOD) computed. | 10 days post-self-assessment deadline |
| 4.5 | Dean Review | AI generates Dean summary per department: all appraisals, average scores, outliers. Flags significant discrepancy between self-assessment and HOD assessment (> 20% gap). | Dean reviews departmental summary. Resolves discrepancies. Endorses or modifies HOD assessments. | Dean-endorsed appraisals locked. Final score computed. | 7 days post-HOD submission |
| 4.6 | Appraisal Communication | AI generates individual appraisal report: final score, performance grade, strengths, areas of improvement. Sends to employee. Opens grievance window (10 days for employee to raise dispute). | Employee acknowledges. Raises dispute if any (routed to HR Officer → Dean). | Appraisal reports issued. Grievance window opened. | 5 business days post-Dean review |
| 4.7 | Increment Linkage | Maps appraisal grade to increment eligibility. Outstanding/VG/Good → increment processed. Satisfactory → increment with caution flag (Dean note). Unsatisfactory → increment withheld pending improvement plan. Sends `pay_revision.ready` to FM-5 / HR-2. | Finance Officer approves increment batch. VC signs for HOD and above. | Increment orders generated or withheld. FM-5 updated. Employee notified. | Concurrent with increment cycle (April) |
| 4.8 | CAS Promotion Processing | Tracks years of service at each level. When eligible: generates CAS application, compiles API dossier. Routes to Screening Committee. For Professor level: routes to full Selection Committee (interview/seminar mandatory per UGC). | Screening Committee reviews CAS application. Selection Committee conducts interview for Professor level. VC approves promotion order. | CAS promotion order issued. Designation and pay level updated in employee record and FM-5. `employee.promoted` event. | Per UGC CAS timeline (within 3 months of eligibility) |

**API Score Categories (UGC Framework — Teaching Faculty):**

| Category | Activities | Max Score |
|---|---|---|
| Category I | Teaching, tutorials, practicals, student mentoring, exam evaluation, course file maintenance | 125 per year |
| Category II | Co-curricular activities, extension work, professional development, committee memberships, administrative roles | 25 per year |
| Category III | Research publications (UGC-listed/Scopus/SCI), books, patents, sponsored projects, PhD guidance, awards | No cap — verified on evidence |

**CAS Promotion Eligibility Thresholds (UGC Regulations 2018):**

| Promotion | Service Required | Min API Score | Additional |
|---|---|---|---|
| Asst. Prof. Stage 1 → 2 | 4 years in Stage 1 | 100/year (Cat I+II) | — |
| Asst. Prof. Stage 2 → 3 | 5 years in Stage 2 | 100/year (Cat I+II) + Cat III score | — |
| Asst. Prof. → Assoc. Prof. | 3 years in Stage 3 | 300 (Cat III over assessment period) | Interview/seminar by Selection Committee |
| Assoc. Prof. → Professor | 3 years as Assoc. Prof. | 400 (Cat III over assessment period) | 10 publications + PhD guidance |

### EC-HR-02 — CAS Promotion API Score Disputes (P1 — Sprint 3)

**Trigger:** AI computes a faculty member's API score and it falls slightly below
the CAS promotion threshold. The faculty member disputes it, claiming a publication
in an obscure journal was not recognized — or that their ORCID profile has a paper
the system missed.

**What breaks:** If AI's score is treated as final, the faculty may miss a promotion
they are entitled to. If every dispute requires full manual recomputation from scratch,
the process is unmanageable at scale.

**Fix: Draft Computation with liability transfer**

```python
class APIScoreDraftStatus(str, Enum):
    AI_COMPUTED        = "ai_computed"         # AI's initial calculation
    FACULTY_REVIEWING  = "faculty_reviewing"
    FACULTY_DISPUTED   = "faculty_disputed"    # faculty raises specific dispute
    DISPUTE_RESOLVED   = "dispute_resolved"
    FACULTY_ACCEPTED   = "faculty_accepted"    # faculty clicks Accept — liability transfers
    HOD_VERIFIED       = "hod_verified"
    SUBMITTED_FOR_CAS  = "submitted_for_cas"

class APIScoreDispute(BaseModel):
    draft_id: UUID
    category: str                        # 'I' | 'II' | 'III'
    disputed_item_type: str              # 'publication' | 'project' | 'award' | 'course'
    claimed_points: float
    evidence_url: str                    # DOI, URL, or document upload
    journal_issn: str | None
    scopus_id: str | None
    dispute_reason: str
```

**Liability transfer rule:** When faculty clicks "Accept" on the API draft score,
they formally accept the computed figure. Disputes raised after accepting require
a separate appeal to the IQAC. This prevents endless post-submission challenges
while still protecting faculty from genuine system errors.

**ORCID/Scopus autonomous discovery (runs weekly):**

```python
class PublicationDiscoveryService:
    """Runs weekly per faculty member. Drafts publications for faculty verification."""

    async def discover_publications(self, faculty: Employee) -> list[PublicationDraft]:
        results = []

        # Search by name + institution affiliation
        scopus_pubs = await scopus_api.search(
            author=faculty.full_name,
            affiliation=faculty.institution_name,
        )

        # Search by ORCID if registered (higher accuracy)
        if faculty.orcid_id:
            orcid_pubs = await orcid_api.get_works(faculty.orcid_id)
            results.extend(orcid_pubs)

        results.extend(scopus_pubs)

        # Create draft entries — faculty only needs to click Verify
        return [
            PublicationDraft(
                faculty_id=faculty.id,
                title=pub.title,
                journal=pub.journal,
                issn=pub.issn,
                doi=pub.doi,
                year=pub.year,
                indexed_in=pub.indexes,        # Scopus / SCI / UGC-listed
                suggested_api_points=compute_api_points(pub),
                status="AWAITING_FACULTY_VERIFICATION",
            )
            for pub in deduplicate(results)
        ]
```

Faculty receives a weekly "New publications found — please verify" notification.
One-click verification adds the publication to their API score. This also feeds
the Regulatory module (E14) — NAAC C3 research output and NIRF RP score.

**Feature flag:** `hr.publication_discovery` — requires Scopus API key per institution.

---

## HR-5: Training & Development

**Trigger:** Post-appraisal training gap identified (from HR-4 Stage 4.6 areas of
improvement), OR management directive, OR UGC/NAAC requirement for faculty development.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 5.1 | Training Needs Identification | Post-appraisal: AI extracts development areas per employee from appraisal reports. Clusters needs across departments (e.g., 12 faculty need research methodology training). Identifies UGC mandatory programmes: Orientation (new faculty), Refresher Course (every 3 years), FDP. Generates institution-wide TNA report. | HR Officer reviews TNA. Dean approves training plan. | TNA report generated. Training calendar drafted. | Within 30 days of appraisal cycle close |
| 5.2 | Training Programme Planning | AI generates annual training calendar: internal programmes (workshops, guest lectures), external nominations (UGC-HRDC/ASC orientation and refresher courses), mandatory compliance training (POSH, fire safety, DPDP Act / data privacy). Checks leave and academic calendar for conflicts. | HR Officer + HOD finalise calendar. Dean approves. Finance Officer approves budget in FM-6. | Training calendar published. Employees nominated. | 15 days post-TNA approval |
| 5.3 | Nomination & Registration | For external: AI registers on UGC-HRDC portal or generates nomination letter. Tracks confirmation. Arranges travel advance via FM-4 if applicable. For internal: sends invites, tracks registrations, reserves venue via SS-6 (Student Clubs & Events room booking). | Employee confirms participation. HOD approves Duty Leave for training duration (HR-3 Stage 3.4). | Registration confirmed. Duty leave sanctioned. | Per programme schedule |
| 5.4 | Training Execution & Attendance | For internal: tracks attendance via QR code. Records pre/post assessments. For external: tracks employee return and submission of completion certificate. | Trainer / HOD confirms delivery for internal. | Attendance recorded. Assessment scores stored. | Programme duration |
| 5.5 | Completion & Certification | On completion: updates employee profile. Issues digital participation certificate (internal). For UGC mandatory programmes: records certificate — mandatory for CAS and NAAC. Updates API Category II score if applicable. Fires `training.completed` event. | HR Officer verifies external certificate. | Training completion in employee profile. API Category II updated. `training.completed` event → HR-4 Appraisal, Regulatory E14. | Within 5 days of programme end |
| 5.6 | Training Impact Assessment | 3 months post-training: AI sends impact assessment to employee and HOD. Computes ROI proxy score. Feeds into next TNA cycle. Generates annual training effectiveness report for management. | Dean reviews annual training effectiveness report. | Impact assessment stored. Training effectiveness data compiled for NAAC C6. | 3 months post-training |

**UGC Mandatory Programmes (tracked automatically):**

| Programme | Target | Frequency | Recorded In |
|---|---|---|---|
| Orientation Programme | New Assistant Professors | Once (within first year) | Employee file, NAAC, CAS dossier |
| Refresher Course | All Teaching Faculty | Every 3 years | Employee file, CAS dossier |
| Faculty Development Programme (FDP) | All Faculty | As nominated | Employee file, API Category II |
| POSH Awareness Training | All Staff | Annual | Compliance register |
| DPDP Act / Data Privacy | All Staff | Annual | Compliance register |
| Fire Safety & Emergency | All Staff | Annual | Compliance register |

**AI tracks every faculty member's UGC mandatory programme status automatically.**
90-day advance reminder sent before the 3-year Refresher Course deadline.
Non-completion flagged in the appraisal report and in the Regulatory E14 dashboard.

---

## HR-6: Separation & Exit Management

**Trigger:** Employee submits resignation, OR contract end date reached (auto-triggered
60 days before), OR superannuation age reached (auto-triggered 6 months before), OR
involuntary separation ordered by VC.

**Separation Types:**

| Type | Trigger | Notice Period | Gratuity Applicable |
|---|---|---|---|
| Voluntary Resignation | Employee submits resignation | 1–3 months (per contract / seniority) | Yes (if ≥ 5 years service) |
| Contract Expiry | Contract end date reached | 60-day advance notice | No (contract staff) |
| Retirement | Superannuation age (60 years; configurable) | 6-month advance notice auto-generated | Yes |
| Termination (Disciplinary) | VC order post-disciplinary process | Immediate (with pay in lieu if applicable) | No (misconduct case) |
| Voluntary Early Retirement (VER) | Employee applies, management approves | Per VER scheme | Yes + VER benefits |

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 6.1 | Separation Initiation | Receives resignation / expiry alert / retirement notice. Assigns Exit ID. Notifies HR Officer, HOD, Dean. Checks notice period obligation. Computes last working day. If notice buyout requested: computes amount and routes to Finance. **Also fires `separation.initiated` event to Academic module** — triggers EC-ACA-02 CourseHandoverWorkflow if mid-semester. | HOD acknowledges resignation. Dean / VC accepts (or rejects and initiates retention discussion). | `separation.initiated` event. Notice period clock starts. Last working day computed. | Same day |
| 6.2 | Knowledge Transfer Planning | AI generates knowledge transfer checklist: ongoing projects, student supervisions, exam duties, committee memberships, admin passwords/accesses. Schedules handover timeline. Assigns replacement/interim responsible person. | HOD manages execution. | Knowledge transfer plan distributed. Progress tracked weekly. | First week after initiation |
| 6.3 | No-Dues Process | Auto-initiates no-dues clearance from: Library (books, fines), Hostel (if applicable), Finance (pending advances, loans), IT (devices, software licenses), Academics (exam duties, student project submissions pending), HR (uniform/equipment if issued). Tracks status per department. | Each department head confirms clearance via system. | No-dues status tracked centrally. Employee notified of pending items. | 10 business days before last working day |
| 6.4 | Retirement / Gratuity Computation | For retirement / long-service separation (≥ 5 years): AI computes gratuity per Payment of Gratuity Act. Computes EL encashment. Computes any retirement benefits per institutional policy. | Finance Officer validates computation. VC approves gratuity payment order. | Amounts forwarded to FM-5 via `final_settlement.ready` event. | 30 days before last working day |
| 6.5 | Exit Interview | AI schedules exit interview. Sends structured questionnaire: reasons for leaving, institutional feedback, management experience, suggestions. Compiles exit analytics quarterly (attrition trends, department-wise, reason clustering). | HR Officer conducts interview. Records key themes. | Exit interview completed. Quarterly attrition analytics for Dean + VC. | Last week of service |
| 6.6 | Final Payroll Computation | On last working day: AI computes final payroll: salary for days worked + EL encashment + gratuity (if applicable) + pending allowances − loan recoveries − outstanding dues. Sends to FM-5 as `final_settlement.ready`. | Finance Officer approves full & final settlement. | Computation approved. FM-5 processes as special payroll run. | Last working day |
| 6.7 | Access Revocation | On last working day: auto-revokes all system access (email, LMS, finance portal, library, HR portal, attendance system). **Important sequencing:** Access revocation fires AFTER the Academic module confirms course handover package is generated (EC-ACA-02). Archives employee data per DPDP Act 7-year statutory retention policy. Transfers email to HOD (configurable). | IT Admin confirms access revocation. HR Officer verifies. | All accesses revoked. Data archived. `employee.separated` event. | Last working day (automated) |
| 6.8 | Experience & Relieving Letter | AI generates: Relieving Letter (last working day, designation, "no disciplinary action pending" certification). Experience Letter (period of service, designation). Service Certificate (for PF withdrawal / ESI claims / gratuity). | HR Officer signs (VC for senior positions). | All separation documents issued. `employee.separated` event closes record. | Within 3 business days of last working day |

**Statutory Formulas:**

```
Gratuity (Payment of Gratuity Act 1972):
  = (Last Drawn Basic Salary + DA) × 15/26 × Completed Years of Service
  Cap: ₹20,00,000 (current statutory limit — not configurable)

EL Encashment:
  = EL Balance Days × (Basic + DA) / 30
  Cap: 300 days (statutory — not configurable)
```

---

## EC-HR-03 — Shared Faculty Cross-Department Budget Split (P2 — Sprint 4)

**Trigger:** A senior professor teaches 60% in Engineering and 40% in MBA. The
employee data model has a single department field. HOD appraisal responsibility is
ambiguous. Payroll cannot be split across two budget heads.

**What breaks:** HOD doesn't know whether they're responsible for the appraisal.
Finance cannot split the salary cost correctly across department P&Ls. The Regulatory
module cannot correctly compute faculty-to-student ratio per program.

**Fix: `employee_department_assignments` table with weight_pct**

```sql
CREATE TABLE employee_department_assignments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    employee_id     UUID NOT NULL,
    department_id   UUID NOT NULL,
    assignment_type TEXT NOT NULL
        CHECK (assignment_type IN ('primary', 'secondary')),
    weight_pct      DECIMAL(5,2) NOT NULL,
    effective_from  DATE NOT NULL,
    effective_until DATE,                    -- NULL = active indefinitely
    appraisal_hod   UUID NOT NULL,           -- HOD who owns this department share
    budget_head     TEXT NOT NULL,
    CONSTRAINT weight_valid CHECK (weight_pct > 0 AND weight_pct <= 100)
);

-- System enforces: sum(weight_pct) for any employee = 100 at any point in time
-- Enforced via trigger, not just application logic

-- Payroll split view consumed by FM-5
CREATE VIEW employee_payroll_split AS
SELECT
    e.id AS employee_id,
    eda.department_id,
    eda.budget_head,
    eda.weight_pct,
    payroll.gross_salary * (eda.weight_pct / 100.0) AS allocated_amount
FROM employees e
JOIN employee_department_assignments eda ON eda.employee_id = e.id
JOIN payroll_runs payroll ON payroll.employee_id = e.id;
```

**Appraisal handling for shared faculty:**
The appraisal workflow runs once per department assignment. Each `appraisal_hod`
fills in their department-specific assessment independently. The final API score
is computed from both assessments, weighted by `weight_pct`. Neither HOD can see
the other's assessment until both have submitted.

**NAAC/NIRF compliance:** The Regulatory module's faculty count and
student-faculty ratio computations must use the `employee_department_assignments`
table — not the single department field on the employee master — to correctly
attribute faculty effort to each program.

---

## Complete System Flow

```
[FINANCE MODULE] ──► EVENT: budget.approved
                              │
          ┌───────────────────┴────────────────────┐
          │              HR MODULE                  │
          └───────────────────┬────────────────────┘
                              │
   HR-1: Recruitment  ────────►  VC approves vacancy + job ad
         EC-HR-03: Shared faculty uses
         employee_department_assignments
                              │
   HR-2: Employee Records ────►  HR Officer creates master record
         `employee.joined` event fires:
          → FM-5 (payroll creation)
          → Academics (timetable pool)
          → Library (staff membership)
          → Regulatory E14 (faculty count)
                              │
   ════ ONGOING OPERATIONS ═══════════════════════
                              │
   HR-3: Attendance & Leave ──►  HOD approves leave
         EC-HR-01: Visiting faculty
         OTP session confirmation
         `payroll.inputs_ready` → FM-5
                              │
   HR-4: Appraisal  ──────────►  HOD → Dean → VC
         EC-HR-02: API score draft
         + liability transfer
         ORCID/Scopus discovery (weekly)
         `employee.promoted` → FM-5, Academics
                              │
   HR-5: Training  ───────────►  Dean approves training plan
         `training.completed` → HR-4, Regulatory E14
                              │
   ════ SEPARATION ═══════════════════════════════
                              │
   HR-6: Separation  ─────────►  VC accepts resignation
         `separation.initiated` → Academic (EC-ACA-02
          CourseHandoverWorkflow fires BEFORE LMS revoked)
         No-dues → all departments confirm
         `final_settlement.ready` → FM-5
         Access revoked AFTER course handover confirmed
         `employee.separated` → all modules
```

---

## Cross-Module Integration Map

| Event | Fired By | Consumed By | Payload / Purpose |
|---|---|---|---|
| `vacancy.sanctioned` | HR-1 | FM-6 Budget | Budget hold placed for new position |
| `employee.joined` | HR-1 | FM-5 Payroll, Academics, Library, Regulatory E14 | Employee ID, designation, pay scale, department — initialises all downstream |
| `payroll.inputs_ready` | HR-3 Attendance | FM-5 Payroll | Working days, LOP, visiting faculty session totals, on-duty per employee |
| `pay_revision.ready` | HR-2 / HR-4 | FM-5 Payroll | Revised basic pay, effective date |
| `employee.confirmed` | HR-2 Probation | FM-5 Payroll | Probation over — confirmation increment applied |
| `employee.promoted` | HR-4 CAS | FM-5 Payroll, Academics | New designation, pay level — payroll and timetable updated |
| `training.completed` | HR-5 | HR-4 Appraisal, Regulatory E14 | Training record — feeds API Category II and NAAC compliance |
| `separation.initiated` | HR-6 | Academics (EC-ACA-02), Finance, Library, IT | Last working day, handover plan initiated |
| `final_settlement.ready` | HR-6 | FM-5 Payroll | EL encashment, gratuity, last month salary — special payroll run |
| `employee.separated` | HR-6 | FM-5, Academics, Library, all modules | Employee ID deactivated across all systems |
| `payslip.issued` | FM-5 | HR-2 Records | Stored in employee digital vault |
| `form16.issued` | FM-5 | HR-2 Records | Annual TDS certificate stored in employee vault |
| `budget.approved` | FM-6 Finance | HR-1 Recruitment | Unlocks manpower requisitions for the financial year |
| `academics.faculty_activity_summary` | Academics | HR-4 Appraisal | Category I data: lectures delivered, students mentored — pre-fills appraisal |

---

## SLA & Escalation Matrix

| Module | Approval Gate | Approver | SLA | Breach Escalation |
|---|---|---|---|---|
| Recruitment | Manpower requisition | VC | 5 business days | Board notified if VC unavailable |
| Recruitment | Job advertisement approval | VC | 2 business days | Registrar acts on VC behalf |
| Recruitment | Shortlist approval | HR Officer + HOD | 5 business days | Dean reviews if HOD delays |
| Recruitment | Merit list approval | VC | 3 business days | Board informed; process paused |
| Recruitment | Appointment letter | VC (digital sign) | 3 business days | Registrar signs on delegation |
| Employee Records | Probation confirmation | VC | 15 days before expiry | Auto-extended 3 months if VC unavailable |
| Employee Records | Annual increment | Finance Officer | April 1 | VC releases directly if FO unavailable |
| Attendance | Leave approval (faculty/staff) | HOD | 2 business days | Auto-approved with HOD flag if not acted on |
| Attendance | International duty leave | Dean | 3 business days | Escalates to VC |
| Attendance | Visiting faculty session dispute | HOD | 5 business days | HR Officer escalates to Dean |
| Appraisal | HOD assessment submission | HOD | 10 days | Dean reminded; HR Officer escalates |
| Appraisal | Dean review & sign-off | Dean | 7 days | VC reviews directly |
| Appraisal | CAS promotion order | VC | 90 days of eligibility | Registrar notified; UGC timeline monitored |
| Appraisal | API score dispute resolution | IQAC | 21 days | VC intervenes |
| Training | Training plan approval | Dean | 15 days post-TNA | HR Officer escalates to VC |
| Separation | Resignation acceptance | VC | 5 business days | HR Officer flags as pending |
| Separation | Course handover (if mid-semester) | HOD | 48 hours | Dean mandates; EC-ACA-02 EmergencySeperationOverride |
| Separation | No-dues clearance | Department Heads | 10 days before LWD | HR Officer escalates to Dean |
| Separation | Full & final approval | Finance Officer | LWD | VC authorises directly if FO unavailable |
| Separation | Relieving letter | HR Officer | 3 days post-LWD | Dean mandates issuance |

---

## What Actors Never Do (AI Handles Completely)

**Recruitment & Records:**
- Draft job advertisements per UGC format
- Screen applications for minimum eligibility (NET/PhD/publications check)
- Rank shortlisted candidates by qualification criteria
- Constitute and schedule Selection Committee meetings
- Draft appointment letters and service agreements
- Create employee master records and provision all system access on joining day
- Compute annual increments per pay scale rules
- Track and alert on document expiry dates

**Attendance & Leave:**
- Pull biometric data and mark daily attendance
- Check leave balance before approval (auto-flag if insufficient)
- Credit monthly EL accrual
- Flag absenteeism patterns and draft warning letter templates
- Generate payroll input file with LOP / OD data on cut-off date
- Send visiting faculty session OTPs and log confirmed sessions

**Appraisal & Training:**
- Pre-fill appraisal forms with Category I data from Academics module
- Pull student feedback scores and integrate into appraisal
- Compute provisional API scores per UGC formula
- Discover faculty publications via ORCID/Scopus and create draft entries
- Track CAS eligibility by years of service and minimum API thresholds
- Identify training gaps from appraisal reports and cluster them
- Register employees on UGC-HRDC portal for mandatory programmes
- Track UGC mandatory programme completion status per employee

**Separation:**
- Compute gratuity per Payment of Gratuity Act formula
- Compute EL encashment
- Initiate no-dues process across all departments simultaneously
- Schedule exit interview and distribute questionnaire
- Revoke all system access on last working day (with correct sequencing for course handover)
- Generate relieving letter, experience letter, and service certificate

---

## Notification Map

| Module | Trigger Event | Recipients | Channel |
|---|---|---|---|
| Recruitment | Vacancy advertised | Candidate applicants | Institutional website + job portals |
| Recruitment | Application received | Applicant | Email (auto-acknowledgement) |
| Recruitment | Shortlisted for interview | Candidate | Email + SMS |
| Recruitment | Appointment letter issued | Selected candidate | Email (PDF) |
| Records | Contract expiry warning (60 days) | Employee + HR Officer + HOD | Email |
| Records | Increment order issued | Employee | Email |
| Records | Probation review due | Employee + HOD | Email |
| Records | Document expiry alert | Employee + HR Officer | Email |
| Attendance | Leave approved / rejected | Employee | Email + SMS |
| Attendance | AWOL (absent without leave) | Employee + HOD | Email |
| Attendance | Visiting faculty: session OTP sent | Visiting faculty | SMS |
| Attendance | Visiting faculty: unconfirmed session | HOD | Email (next working day) |
| Attendance | Payroll input file sent to Finance | Finance Officer | Email + dashboard |
| Appraisal | Appraisal form distributed | All employees | Email |
| Appraisal | API score draft ready — please review | Faculty | Email + Portal |
| Appraisal | New publications found via ORCID/Scopus | Faculty | Email + Portal (weekly) |
| Appraisal | CAS eligibility reached | Employee + HR Officer + Dean | Email |
| Training | UGC mandatory programme due (90 days) | Employee + HR Officer | Email |
| Training | Training programme announced | Nominated employees | Email |
| Training | Completion certificate issued | Employee | Email (PDF) |
| Separation | Resignation acknowledged | Employee + HOD | Email |
| Separation | No-dues clearance pending | Relevant departments | Email |
| Separation | Full & final settlement approved | Employee | Email |
| Separation | Relieving letter issued | Employee | Email (PDF) |
| Separation | Retirement approaching (6 months / 3 months / 1 month) | Employee + HR Officer + Finance | Email |

---

## DPDP Act 2023 — Employee Data Compliance

Employee personal data is sensitive personal data under the DPDP Act. The following
controls are enforced at the system level:

| Data Element | Storage | Display | Retention After Separation |
|---|---|---|---|
| Bank account number | Encrypted at rest | Masked (`XXXX XXXX 1234`) in all views except Finance Officer | 7 years (statutory) |
| Aadhaar number | Encrypted at rest | Masked entirely in all UI views | 7 years (statutory) |
| Salary / compensation data | Encrypted at rest | Visible to: employee, HR Officer, Finance Officer only | 7 years (statutory) |
| Disciplinary records | Encrypted at rest | Visible to: HR Officer, Dean, VC only | 7 years (statutory) |
| Medical / health records | Encrypted at rest | Visible to: HR Officer only | 7 years (statutory) |
| Training & appraisal records | Standard encryption | Visible to: employee, HR Officer, HOD, Dean | 7 years (statutory) |
| Performance grades | Standard encryption | Visible to: employee, HR Officer, HOD, Dean | 7 years (statutory) |

**Right to access:** Employee can request a full data export via self-service portal.
HR Officer receives the request and approves the export within 5 business days.

**Erasure:** Employee cannot request erasure while the 7-year statutory retention
period is active (PF, ESI, TDS, Gratuity Act obligations). After 7 years, data is
anonymised — names and identifiers removed while statistical aggregates for
NAAC/NIRF historical reporting are preserved.

**Consent logging:** Employee onboarding (HR-1 Stage 1.9) must log a consent record
in the E21 `consent_records` table before writing any personal data to the employee
master. The `ConsentMiddleware` enforces this for the employee onboarding endpoint.

---

## Compliance Coverage

| Compliance Area | Domain | AI Automation Level |
|---|---|---|
| UGC Regulations 2018 (faculty qualification) | HR-1 Recruitment | Full — eligibility screened automatically |
| UGC CAS Promotion (PBAS/API) | HR-4 Appraisal | Full — API computed; CAS triggered on eligibility |
| UGC Mandatory Training (Orientation/Refresher) | HR-5 Training | Full — tracked, reminded, recorded; 90-day advance alert |
| Payment of Gratuity Act 1972 | HR-6 Separation | Full — computed automatically |
| EPF Act (PF computation + deposit) | FM-5 / HR-2 | Full — computed and scheduled |
| ESI Act (ESI computation + deposit) | FM-5 / HR-2 | Full — computed and scheduled |
| Maternity Benefit Act 1961 | HR-3 Leave | Full — entitlement enforced, pay protected |
| POSH Act (ICC register + training) | HR-5 Training | Partial — training tracked; ICC proceedings by committee |
| DPDP Act 2023 (employee data privacy) | All HR domains | Full — role-based masking, retention policy, access logs, consent logging |
| Income Tax Act Sec 192 (TDS on salary) | FM-5 | Full — computed, deposited, Form 16 issued |
| Reservation Roster (SC/ST/OBC/EWS) | HR-1 Recruitment | Full — roster maintained, shortfall alerted; consumed by Regulatory E14 |

---

## Configurable Parameters

| Module | Parameter | Default |
|---|---|---|
| Recruitment | Probation period (full-time faculty) | 2 years (configurable) |
| Recruitment | Application window duration | 30 days |
| Records | Annual increment rate (institutional scale) | 3% of basic |
| Records | Contract expiry advance notice | 60 days |
| Attendance | Working days per week (academic staff) | 6 days (Mon–Sat) |
| Attendance | Visiting faculty OTP confirmation window | 30 minutes from session start |
| Attendance | Absenteeism alert threshold | 3 unplanned absences in a month |
| Attendance | Mass leave alert (concurrent) | > 20% of department on same day |
| Leave | CL entitlement per year | 12 days |
| Leave | EL accrual rate | 2.5 days per month |
| Leave | Maternity leave (max 2 children) | 26 weeks |
| Appraisal | Appraisal cycle start date | March 1 |
| Appraisal | API discrepancy alert threshold | > 20% gap between self and HOD score |
| Appraisal | ORCID/Scopus publication discovery | Weekly (requires API key per institution) |
| Training | UGC Refresher Course reminder | 90 days before 3-year deadline |
| Separation | Retirement age | 60 years |
| Separation | Retirement advance notice | 6 months |
| Separation | Notice period — junior staff | 1 month |
| Separation | Notice period — senior faculty / HOD | 3 months |
| DPDP | Statutory data retention after separation | 7 years |

---

*Document version: 2.0 | March 2026*
*Connected to: admissions_workflow.md → academic_operations_workflow.md →*
*examination_workflow.md → student_services_workflow.md → finance_workflow.md →*
*hr_payroll_workflow.md → regulatory_accreditation_workflow.md*
*Full institutional lifecycle: Lead Captured → Graduated → Faculty Separated*
*QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential*
