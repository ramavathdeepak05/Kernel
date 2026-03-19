# Student Services Module Workflow
### Full Automation Reference — ALIS OS Module E09
#### Model: AI Executes Everything. Actors Approve.
#### QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential

---

## Document Map

This document covers the full Student Services module (E09) of ALIS OS.

**Connected documents:**
- `academic_operations_workflow.md` — Academic Risk Score (RED) triggers SS-7 counseling referral; attendance module receives `attendance.medical_leave` from SS-7; venue requests from SS-6 checked against timetable
- `examination_workflow.md` — `library.cleared` and `hostel.cleared` are hall ticket prerequisites; EC-SS-01 grievance blackout pauses invigilator complaints during exam window
- `finance_workflow.md` — `scholarship.awarded` adjusts fee account; `student.dues_cleared` gates alumni transition; hostel security deposit refund on `hostel.cleared`
- `admissions_workflow.md` — `student.enrolled` triggers SS-1, SS-2, SS-3, SS-4 and E16 Parent Portal provisioning
- `examination_workflow.md` — `exam.malpractice_flagged` enters SS-5 disciplinary pipeline
- `regulatory_accreditation_workflow.md` — `grievance.closed` feeds NAAC metric; placement outcome data feeds NIRF; scholarship data feeds NAAC C5; student activity feeds NAAC C7

**Cross-references to skill files:**
- Edge cases: `references/edge-cases.md` — EC-SS-01, EC-SS-02, EC-SS-03, EC-SS-04
- Parent Portal: `references/architecture.md` §21 — E16 go-live blocker
- Alumni saga: `references/architecture.md` §4 — `AlumniTransitionSaga`
- DPDP: `references/architecture.md` §22 — E21 consent and erasure apply to all student data collection
- WhatsApp primary channel: `references/architecture.md` §28
- Build sequence: `ALIS_BUILD_PLAN.md` — EC-SS-01/02 Sprint 2; EC-SS-03/04 Sprint 3

---

## Core Operating Principle

AI executes every task. Humans (Actors) only Approve, Reject, or Escalate at defined gates.

All eight service domains operate on this model:
- AI monitors, drafts, routes, schedules, and computes without staff initiation
- Every approval gate has a defined SLA with absolute `TIMESTAMPTZ` deadlines —
  never `sleep(timedelta)` (EC-CROSS-04)
- Student data flows from Admissions → Academics → Exams → Student Services
  with no manual handoff
- All service actions are logged, timestamped, and attached to the student master profile
- Students interact via a single self-service portal. Parents interact via the
  E16 Guardian Portal (OTP-only, read-only, separate domain)
- **Primary notification channel: WhatsApp** (>90% open rate for Indian university
  students and parents vs. <20% for email). Email is secondary and archival.
  SMS for time-critical events. In-app for confidential notifications
  (counseling, grievances)
- DPDP Act 2023 consent must be logged before writing student personal data at
  every new data collection point (placement profile, scholarship application,
  counseling record, alumni profile)

---

## Actors

| Actor | Scope of Authority | Escalation Path |
|---|---|---|
| Dean of Student Affairs | All 8 service domains — final authority on student welfare | Vice Chancellor |
| Hostel Warden | Room allotment, mess, leave, discipline within hostel | Dean of Student Affairs |
| Placement Officer (TPO) | Company registration, drive management, offer tracking | Dean of Student Affairs |
| Faculty Advisor / Mentor | Scholarship endorsement, club approval, counseling referrals | HOD → Dean |
| Administrative Staff | Library, health appointments, event logistics, scholarship docs | Dean of Student Affairs |
| Student | Self-service requests, applications, grievances | — |
| Guardian (E16) | Read-only: attendance, dues, exam schedule, results, risk traffic light | Cannot raise actions — read only |

---

## Module Overview

| # | Service Domain | Primary Trigger | Primary Actor | Stages |
|---|---|---|---|---|
| SS-1 | Hostel & Accommodation | `student.enrolled` with `hostel_opted = true` | Hostel Warden | 8 stages |
| SS-2 | Library & Learning Resources | `student.enrolled` → auto-registration | Administrative Staff | 6 stages |
| SS-3 | Placement & Career Services | Configurable semester milestone (default: Semester 5) | Placement Officer (TPO) | 10 stages |
| SS-4 | Scholarships & Financial Aid | Semester start / `student.financial_flag` | Admin Staff + Faculty Advisor | 7 stages |
| SS-5 | Grievance & Disciplinary | Student submits / incident flagged / malpractice event | Dean of Student Affairs | 7 stages |
| SS-6 | Student Clubs & Events | Student submits club/event proposal | Faculty Advisor + Dean | 7 stages |
| SS-7 | Health & Counseling | Self-booking / `risk.score_red` auto-referral / emergency | Administrative Staff | 5 stages |
| SS-8 | Alumni Relations | All three: `result.final_published` AND `student.dues_cleared` AND `graduation.verified` | Dean of Student Affairs | 6 stages |

**Also in scope:** E16 Parent / Guardian Portal — go-live blocker, provisioned on `student.enrolled`

---

## SS-1: Hostel & Accommodation

**Trigger:** `student.enrolled` with `hostel_opted = true`. AI auto-initiates
allotment workflow. No Warden action needed to begin.

**DPDP note:** Hostel application form collects room preference and any medical
conditions affecting room assignment. Consent record must be logged in
`consent_records` (E21) for hostel-specific personal data before writing to the
allotment record.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 1.1 | Allotment Eligibility Check | Reads: category, gender, program, fee payment status, `hostel_opted` flag. Validates eligibility per institutional policy. | No action — AI executes fully. | Eligibility: PASS / FAIL. Failed students notified with reason. | Instant |
| 1.2 | Room Assignment | Applies configurable rules: gender separation, floor preference, disability-friendly rooms, first-year isolation blocks, medical requirements. Assigns best-fit room from live inventory. Prevents double-booking at transaction level. | Warden reviews AI recommendation. Approves or re-assigns. | Room allocation record. Student and parent notified via WhatsApp. | 1 business day |
| 1.3 | Hostel Fee Invoice | Generates invoice (room rent + security deposit + mess charges) via Finance module. Dispatches Razorpay payment link. | No action unless manual waiver requested (waiver routes to Finance Officer). | Invoice dispatched. Payment deadline set. | Instant on allotment |
| 1.4 | Check-In & Onboarding | Marks student checked-in on payment confirmation. Issues digital room card / QR. Generates welcome kit (hostel rules, emergency contacts, mess timings). | Warden verifies physical check-in on system. | `hostel.checkin` event. Room status → OCCUPIED. | Day of arrival |
| 1.5 | Mess & Daily Operations | Tracks daily mess attendance via QR/biometric. Calculates monthly mess bill. Sends daily menu. Flags absent students for 2+ consecutive days (feeds Academics risk module). | Warden reviews weekly mess report. Approves adjustments. | Monthly mess bill auto-generated and attached to student fee dues in Finance. | Daily (auto) |
| 1.6 | Leave & Outpass Management | Receives leave/outpass request. Validates against hostel rules (max nights per month, exam blackout periods). On approval: sends departure + return notification to parent via WhatsApp. | Warden approves / rejects within SLA. Auto-approved with parent WhatsApp notification if Warden does not act within 4 hours. | Leave record updated. Parent WhatsApp sent on departure and return. | 4 hours SLA |
| 1.7 | Maintenance & Complaints | Receives complaint. Auto-classifies severity. Assigns to maintenance staff with deadline. Escalates if unresolved. | Warden reviews complaints past SLA. Approves contractor calls for major repairs. | Ticket created → resolved → closed. Student notified at each step. | Minor: 24 hrs \| Major: 72 hrs |
| 1.8 | Vacating & Clearance | Triggers on semester end, withdrawal, or graduation clearance. Generates vacating checklist. Checks: damage, dues, inventory. Releases security deposit on full clearance. | Warden conducts final room inspection. Records damage. Approves clearance. | `hostel.cleared` event. Security deposit refund routed to Finance. | 3 business days post-vacating |

**Cross-module integration:**
- Reads: `student.enrolled`, `academic_calendar` (exam blackout dates), `student.dues`
- Writes: `hostel.checkin` → Academics (risk baseline), Finance (fee ledger)
- Writes: `hostel.cleared` → Finance (deposit refund), Exams (hall ticket prerequisite), Graduation
- Mess absence (2+ days) → Academics Risk module (risk score input)

### EC-SS-04 — Hostel Room Swap at 100% Capacity (P2 — Sprint 3)

**Trigger:** Two roommates have a serious altercation. Hostel is at 100% occupancy.
Warden has no empty room to move either student to.

**What breaks:** Neither student can be moved. AI finds no logical path — deadlock.
Conflict escalates without institutional response.

**Fix: Peer Room Swap Exchange with SAFETY severity bypass**

```sql
CREATE TABLE hostel_swap_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    requester_id    UUID NOT NULL,
    requester_room  UUID NOT NULL,
    reason          TEXT NOT NULL,
    severity        TEXT DEFAULT 'ROUTINE'
        CHECK (severity IN ('ROUTINE', 'URGENT', 'SAFETY')),
    matched_with    UUID,
    matched_room    UUID,
    warden_approved BOOLEAN DEFAULT false,
    status          TEXT DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'MATCHED', 'APPROVED', 'COMPLETED', 'CANCELLED')),
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

**ROUTINE / URGENT flow:** Student posts swap request. AI shows it anonymously to
other students willing to swap. Mutually accepted pair → `MATCHED` → Warden approves
→ `APPROVED` → physical move executed.

**SAFETY flow (physical altercation, harassment):** Bypasses the swap exchange.
Warden receives immediate alert. Warden places one student in temporary overflow
space (guest room, conference room, faculty flat) for up to 72 hours. Dean of
Student Affairs notified directly. Permanent resolution required within 72 hours —
AI monitors and escalates to Dean if Warden has not resolved by the absolute
`TIMESTAMPTZ` deadline.

---

## SS-2: Library & Learning Resources

**Trigger:** `student.enrolled` fires auto-registration. No student action needed.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 2.1 | Auto-Membership Creation | Creates library member record on `student.enrolled`. Member ID = Roll Number. Sets borrowing quota by program (configurable: UG 3, PG 5, PhD 8). Issues digital library card. | No action required. | Library membership active. Digital card issued. | Instant |
| 2.2 | Catalogue & Discovery | Maintains digital catalogue. Auto-suggests resources based on enrolled courses. Sends personalised reading list via WhatsApp at semester start. | Librarian approves new acquisitions. Updates catalogue. | Personalised reading list sent. | Semester start (auto) |
| 2.3 | Issue & Return Management | Processes book issue/return via barcode or RFID. Updates real-time availability. Sends due-date reminders via WhatsApp (3 days before, day of). | No action unless override (lost/damaged book). | Issue/return records updated. Due-date alerts sent. | Real-time |
| 2.4 | Fine Calculation & Payment | Auto-calculates overdue fine per day (configurable rate and cap). Adds fine to student dues ledger in Finance. Blocks further issue if fine unpaid > 7 days. | Admin Staff resolves disputed fines. | Fine posted to Finance. `book.blocked` status if unpaid beyond threshold. | Daily (auto) |
| 2.5 | Resource Reservation & E-Access | Queue system for books on issue. Notifies student via WhatsApp when available. Manages e-resource access tokens (NPTEL, Shodhganga, subscription services). | Admin Staff manages vendor access credentials. | Reservation queue maintained. E-access links sent on schedule. | Real-time |
| 2.6 | No-Dues Clearance | At semester end / program completion: checks for unreturned books and unpaid fines. Generates no-dues certificate on full clearance. Blocks transcript if dues pending. | Admin Staff resolves exceptional cases. | `library.cleared` event. No-dues certificate issued. | 3 business days before results |

**Cross-module integration:**
- `library.cleared` → Exams (hall ticket prerequisite), Graduation (transcript release)
- Fine amounts pushed to Finance module student dues ledger

---

## SS-3: Placement & Career Services

**Trigger:** Configurable semester milestone (default: start of Semester 5 for
4-year programs). AI auto-activates placement profiles and computes eligibility.

**One-offer policy:** When enabled, student is auto-withheld from all active drives
once an offer is accepted. EC-SS-02 (employer revocation) and EC-SS-03 (verbal lock)
are the two structured exception paths.

**DPDP note:** Placement profile activation constitutes a new data collection point
(resume data shared with companies). Consent must be logged in `consent_records`
before the profile is activated and before resume data is shared with any company.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 3.1 | Student Profile Activation | Auto-creates placement profile from academic record (CGPA, backlogs, skills, projects). Sends profile completion nudge. DPDP: consent logged before activation. | Student completes resume and uploads documents. | `placement.profile_active` event. Profile visible in TPO dashboard. | Semester 5 start (auto) |
| 3.2 | Eligibility Configuration | TPO sets rules per drive (min CGPA, max backlogs, programs, graduation year). AI computes eligible student list and auto-notifies eligible students. | TPO sets rules. Reviews AI-generated eligible list. | Eligibility rules stored. Eligible students auto-notified via WhatsApp. | Before each drive |
| 3.3 | Company Registration & JD Management | Receives company registration via employer portal. Creates company profile, parses JD, extracts requirements. Maps JD skills to student profiles (preliminary match score). | TPO reviews company profile. Approves company for campus drive. | Company registered. JD published to eligible students. | 2 business days |
| 3.4 | Student Registration for Drive | Opens application window. Auto-displays drive to eligible students. Collects registrations. Generates student list with resume bundle for company. | TPO confirms registration window open and close. | Drive registration list generated. Resume pack sent to company. | Per drive schedule |
| 3.5 | Pre-Placement Training | Identifies skill gaps vs. JD requirements across registered students. Schedules targeted training (aptitude, GD, technical mock). Tracks completion. | Faculty Advisor / TPO approves training schedule. | Training completion tracked. Mock results stored in profile. | 2 weeks before drive |
| 3.6 | Drive Scheduling & Logistics | Schedules pre-placement talk, aptitude test, GD, interview rounds. Allocates rooms (cross-checks Academics timetable via `event.venue_request`). Sends calendar invites to all parties. | TPO confirms schedule. Dean approves use of facilities. | Drive calendar published. Venue allotted. | 1 week before drive |
| 3.7 | Drive Execution & Result Capture | Captures round-wise shortlist updates in real time. Maintains scoreboard. Auto-withholds students with accepted offers under one-offer policy. Checks for `PlacementOfferLock` (EC-SS-03) before allowing student into any round. | TPO enters / validates final results from company. | Round-wise status updated. Students notified via WhatsApp at each shortlist. | Same day as drive |
| 3.8 | Offer Letter Management | Receives offer letter (upload or email parse). Extracts role, CTC, joining date. Links to student profile. Enforces one-offer policy. Student has 3-day acceptance window. | TPO validates offer details. Student accepts / declines. | `offer.received` event. Offer letter stored in student profile. | 3 business days |
| 3.9 | Placement Statistics & Reporting | Continuously updates placement dashboard (% placed, avg CTC, median CTC, sector-wise, program-wise). Auto-generates weekly TPO summary. | TPO reviews and publishes placement report. | Analytics dashboard updated. Weekly report to Dean. | Continuous (auto) |
| 3.10 | Internship Management | Manages summer/winter internship applications. Tracks offers, PPO (Pre-Placement Offers), joining confirmations. For PPO: applies EC-SS-03 verbal lock pattern automatically. | TPO tracks PPO conversions. Faculty Advisor approves academic credit if applicable. | Internship records + PPO status stored in profile. | Per internship cycle |

### EC-SS-02 — Offer Revoked by Employer Post-Placement (P1 — Sprint 2)

**Trigger:** Student accepts an offer. They are locked out of all drives. 3 months
later, the company revokes the offer — often informally via email that bypasses
the TPO portal. The student has no valid offer and no path back into active drives.

**What breaks:** Student is blocked from drives with no valid offer. By the time the
revocation is communicated, several drives may have already closed. No structured
re-entry exists in the original flow.

**Fix: OfferRevocationWorkflow (Temporal) with mandatory TPO verification**

```python
class PlacementOfferStatus(str, Enum):
    RECEIVED             = "received"
    ACCEPTED             = "accepted"
    REJECTED             = "rejected"
    REVOKED_BY_EMPLOYER  = "revoked_by_employer"
    JOINED               = "joined"
    OFFER_LAPSED         = "offer_lapsed"

class OfferRevocationRecord(BaseModel):
    offer_id: UUID
    student_id: UUID
    company_id: UUID
    revocation_reason: str
    revocation_date: date
    evidence_document_url: str    # email screenshot or formal letter
    tpo_verified: bool            # TPO must verify; students cannot self-revoke
    student_reactivated_at: datetime | None

@workflow.defn
class OfferRevocationWorkflow:
    @workflow.run
    async def run(self, revocation: OfferRevocationRecord):
        # Step 1: Wait for TPO verification signal (absolute deadline: 3 days)
        signal = await workflow.wait_for_signal(
            "tpo_verification",
            timeout=timedelta(days=3)
        )

        if not signal.verified:
            await notify_student_revocation_rejected(revocation.student_id)
            return

        # Step 2: Unlock student placement profile immediately
        await workflow.execute_activity(
            unlock_student_placement_profile,
            args=[revocation.student_id, revocation.tenant_id]
        )

        # Step 3: Auto-insert into all currently active eligible drives
        await workflow.execute_activity(
            reinsert_into_active_drives,
            args=[revocation.student_id, revocation.tenant_id]
        )

        # Step 4: Notify student via WhatsApp with active drive list
        await workflow.execute_activity(
            notify_student_reactivation,
            args=[revocation.student_id, revocation.tenant_id]
        )
```

**Anti-gaming safeguard:** TPO must verify using evidence (email from company HR,
formal letter). Students cannot self-initiate a revocation claim without TPO
verification. If TPO does not act within 3 days, the claim is auto-rejected and
the student is directed to the Dean. `PlacementOfferStatus.REVOKED_BY_EMPLOYER`
is logged permanently — revoked offers are not counted as placed in Regulatory
E14 NIRF reporting.

---

### EC-SS-03 — Verbal Offer Lock (P2 — Sprint 3)

**Trigger:** Student receives a verbal job offer. They ask the company to delay
the formal PDF. They remain active in the system and interview for better companies,
bypassing the one-offer policy.

**What breaks:** Unfair advantage. Company trust damaged. TPO cannot enforce
policy without a formal letter in hand.

**Fix: TPO-initiated Verbal Lock with auto-expiry**

```python
class PlacementOfferLockType(str, Enum):
    FORMAL_OFFER = "formal_offer"   # PDF offer letter received
    VERBAL_LOCK  = "verbal_lock"    # TPO manually locks on company confirmation

class PlacementOfferLock(BaseModel):
    student_id: UUID
    company_id: UUID
    lock_type: PlacementOfferLockType
    lock_initiated_by: UUID          # TPO only — students cannot initiate
    company_contact_name: str
    company_contact_email: str
    formal_offer_due_by: date        # deadline for formal PDF
    locked_at: datetime
    formal_offer_received_at: datetime | None
    auto_unlock_if_no_formal: bool = True
```

A `VERBAL_LOCK` has the same drive-blocking effect as a `FORMAL_OFFER`. If formal
PDF is not received by `formal_offer_due_by`, the lock auto-expires and the student
is reinstated in active drives. Company contact receives automated reminder 3 days
before the deadline. Only a TPO can initiate a `VERBAL_LOCK`.

---

## SS-4: Scholarships & Financial Aid

**Trigger:** Semester start (merit) or `student.financial_flag` from Finance (need-based).
External scholarship portals (NSP, state portals) also trigger inbound tracking.

**DPDP note:** Scholarship application collects sensitive category data (caste
certificate, income certificate, bank details). Consent must be logged before
writing any scholarship application data.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 4.1 | Scholarship Catalogue Management | Maintains all scholarship data (institutional, government, private). Tracks eligibility criteria, deadlines, application portals. Sends targeted WhatsApp notifications to eligible students. | Admin Staff updates catalogue each semester. | Scholarship list published. Eligible students auto-notified. | Before semester start |
| 4.2 | Eligibility Screening | Computes eligibility per student per scholarship: CGPA threshold, income slab, category (SC/ST/OBC/EWS/General), first-gen status, hostel residency, program type. Tags each student ELIGIBLE / NOT_ELIGIBLE. | No action — batch computation. | Eligibility report generated. Students pre-tagged. | Instant (batch) |
| 4.3 | Application Assistance | Pre-fills application form from student master profile. Flags missing documents. Logs consent record (DPDP) before any data submission. Submits to external portals via API (NSP integration) or generates PDF. | Student reviews and authorises final submission. | Application submitted. Reference number stored. | Per scholarship deadline |
| 4.4 | Document Verification | Receives uploaded documents (income certificate, caste certificate, bank details). Runs format and completeness check. Flags discrepancies. | Admin Staff verifies originals for institutional scholarships. Faculty Advisor endorses merit nominations. | Document status: VERIFIED / PENDING / REJECTED. Student notified via WhatsApp. | 3 business days |
| 4.5 | Selection & Award | Ranks eligible applicants. Merit: CGPA rank order. Need-based: composite score. Generates provisional selection list. | Dean / Scholarship Committee approves final award list. | `scholarship.awarded` event → Finance adjusts fee account. | Per scholarship cycle |
| 4.6 | Disbursement & Fee Adjustment | Institutional scholarships: credits student fee account via Finance. Government scholarships: tracks DBT credit confirmation. Auto-reconciles. | Finance Officer approves disbursement order. | `scholarship.disbursed` event. Fee account updated. Confirmation to student via WhatsApp. | 5 business days post-award |
| 4.7 | Renewal & Compliance Tracking | Monitors CGPA of scholarship holders each semester. Flags students below retention threshold. Auto-generates renewal applications. Manages suspension / reinstatement. | Admin Staff + Faculty Advisor review flagged cases. | Renewal status updated. Suspension/reinstatement letters auto-generated. | Each semester end |

**Regulatory feed:** `scholarship.awarded` and `scholarship.disbursed` → Regulatory
E14 (NAAC C5 Student Support & Progression, government scholarship compliance).

---

## SS-5: Grievance & Disciplinary

**Trigger:** Student submits grievance via portal (anonymous option available), OR
incident flagged by faculty/staff, OR `exam.malpractice_flagged` event received
from Examinations module.

**Grievance Categories (AI auto-classifies on intake):**
- **Academic:** Marks dispute, attendance wrongly marked, faculty misconduct, unfair evaluation
- **Administrative:** Fee dispute, document delay, infrastructure complaint, hostel/library issue
- **Disciplinary:** Ragging, harassment, POSH violation, misconduct by student or staff
- **Financial:** Scholarship non-receipt, fee overcharge, refund delay
- **Exam/Malpractice:** From `exam.malpractice_flagged` — special handling, full confidentiality
- **Other:** General complaints

**UGC (Redressal of Grievances of Students) Regulations 2023 mandates:**
- Acknowledgement within 3 working days (ALIS OS: 1 hour auto-ack)
- Resolution within 30 days from intake (hard limit — not configurable)
- Appeal to Ombudsperson if unresolved at institutional level
- Annual compliance report submitted to UGC

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 5.1 | Intake, Classification & Anomaly Check | Receives grievance. Runs `GrievanceAnomalyDetector` (EC-SS-01) before routing. Auto-classifies category + sub-category. Assigns Grievance ID. Assesses severity (ROUTINE / SERIOUS / CRITICAL). Routes to appropriate committee. Sends auto-acknowledgement. | No action at intake — AI routes automatically. | Grievance ID issued. Acknowledgement via in-app + WhatsApp within 1 hour. | 1 hour (auto-ack) |
| 5.2 | Investigation Initiation | Compiles case file: student profile, academic record, previous grievances (pattern check), involved parties. Drafts preliminary notice to respondent. Schedules hearing date within statutory window. | Dean / SGRC Chairperson reviews case file. Confirms hearing schedule. | Case file assembled. Respondent notified. Hearing scheduled. | Within 15 days of intake |
| 5.3 | Hearing & Evidence Management | Maintains digital hearing records. Collects written statements from both parties via secure portal. Organises supporting documents. Generates hearing summary. | SGRC Committee conducts hearing. Records verdict / findings. | Hearing notes stored. Verdict entered. | Per hearing schedule |
| 5.4 | Resolution & Action | Drafts resolution order based on committee verdict. Generates action letters. For disciplinary cases: computes penalty per category (warning → suspension → expulsion). Triggers connected workflows: hostel eviction, academic suspension, access revocation. | Dean / VC approves final resolution order for SERIOUS and CRITICAL cases. | Resolution order issued. Connected workflows triggered. Both parties notified via WhatsApp. | Within 30 days of intake (UGC — not configurable) |
| 5.5 | Appeal & Ombudsperson Routing | If student unsatisfied within 7 days of resolution: auto-routes appeal to Ombudsperson. Tracks proceedings. For POSH: escalates to ICC automatically and independently. | Ombudsperson / ICC handles independently — ALIS OS tracks, does not manage. | Appeal reference number issued. Process tracked. | Per appeal timeline |
| 5.6 | UGC Portal Compliance Reporting | Monitors 30-day resolution deadline per case. If breached: auto-logs breach event and notifies Dean. On case closure: flags for annual UGC compliance report. | Dean reviews monthly grievance report. Approves annual UGC report. | UGC compliance data compiled. Annual report generated. | On resolution + annual batch |
| 5.7 | Closure & Analytics | On resolution confirmation: marks grievance CLOSED. Stores full case history. Generates monthly analytics for Dean: volume by category, resolution time, repeat respondents, closure rate. | Dean reviews monthly analytics. | Grievance CLOSED. `grievance.closed` event → Regulatory E14. | On resolution |

**Confidentiality rules (hard-coded — not configurable):**
- POSH / ICC cases: accessible only to ICC members and VC
- Anonymous grievances: max severity `SERIOUS` — never `CRITICAL`
- `exam.malpractice_flagged` cases: accessible only to CoE and Dean, not to faculty in the student's department

### EC-SS-01 — Weaponized Grievance Spike (P1 — Sprint 2)

**Trigger:** During exam week, a coordinated group submits dozens of anonymous
CRITICAL-severity complaints against an invigilator in 24 hours. AI's
auto-escalation routes all to CRITICAL, derailing the exam cell and potentially
removing the invigilator mid-examination.

**What breaks:** Legitimate invigilator wrongly escalated. Exam disrupted. Dean
flooded with manufactured alerts. No accountability for anonymous complaints.

**Fix: GrievanceAnomalyDetector in the intake pipeline**

```python
class GrievanceAnomalyDetector:
    SPIKE_THRESHOLD_MULTIPLIER = 3.0    # 300% above rolling average
    SPIKE_WINDOW_HOURS = 24
    MIN_SPIKE_COUNT = 5

    async def detect_coordinated_spike(
        self,
        respondent_id: UUID,
        respondent_type: str,           # 'faculty' | 'staff' | 'student'
        tenant_id: UUID,
    ) -> bool:
        recent_count = await count_grievances_against(
            respondent_id, hours=self.SPIKE_WINDOW_HOURS, tenant_id=tenant_id
        )
        rolling_avg = await rolling_average_grievances(
            respondent_id, days=30, tenant_id=tenant_id
        )
        expected = rolling_avg * (self.SPIKE_WINDOW_HOURS / 24)

        return (
            recent_count >= self.MIN_SPIKE_COUNT
            and recent_count >= expected * self.SPIKE_THRESHOLD_MULTIPLIER
        )

async def intake_grievance(grievance: GrievanceSubmission) -> GrievanceRecord:
    is_spike = await anomaly_detector.detect_coordinated_spike(
        respondent_id=grievance.respondent_id,
        respondent_type=grievance.respondent_type,
        tenant_id=grievance.tenant_id,
    )

    if is_spike:
        severity_override = "ANOMALY_REVIEW"
        await notify_dean_of_spike(grievance.respondent_id, spike_count=recent_count)
        # Individual complaints are held — NOT sent to respondent yet
    else:
        severity_override = None

    return create_grievance_record(grievance, severity_override=severity_override)
```

**Additional safeguards:**
- Anonymous complaints are hard-capped at `SERIOUS` — never `CRITICAL`
- Complaints submitted within 30 minutes of each other with near-identical text
  trigger a `COORDINATED_COMPLAINT_FLAG` for manual Dean review
- **Exam period blackout** (cross-ref: `examination_workflow.md` Stage 2.4):
  During the 48 hours before and during an exam, severity auto-escalation for
  invigilator-related complaints is paused. Complaints are received and queued;
  no automatic action until the exam concludes.
  ```yaml
  # Policy DSL
  grievance_escalation:
    exam_period_blackout: true
    blackout_scope: "respondent_type = 'invigilator'"
    blackout_hours_before_exam: 48
  ```

**Feature flag:** `grievance.anomaly_detection` — enabled by default; parameters
configurable per institution.

---

## SS-6: Student Clubs & Events

**Trigger:** Student submits club registration request or event proposal via the student portal.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 6.1 | Club Registration & Charter | Receives registration form. Checks for duplicate/overlapping clubs. Validates minimum membership (configurable, typically 15+). Assigns Faculty Advisor from eligible pool. | Faculty Advisor confirms willingness. Dean approves new club charter. | Club registered. Charter issued. Club page created on student portal. | 5 business days |
| 6.2 | Event Proposal Submission | Student/club submits structured proposal. AI pre-validates: budget ceiling, venue availability, blackout dates (exams, public holidays), required external permissions. | Faculty Advisor reviews and endorses. | Endorsed proposal routed to Dean for final approval. | 2 business days |
| 6.3 | Resource & Venue Allotment | Checks venue availability in real time (cross-references Academics timetable via `event.venue_request`). Allots venue, equipment, IT resources. Confirms. | Dean approves event and resource allotment. | Venue booked. Resources confirmed. Hostel event notice sent if applicable. | 3 business days |
| 6.4 | Budget & Finance Integration | Receives event budget request. Checks club's allocated annual budget balance. Routes to Finance for PO creation if external vendors involved. | Dean approves budget. Finance Officer approves PO. | Budget sanctioned. Finance module updated. | 3 business days |
| 6.5 | Event Execution & Attendance | Generates event QR for attendance. Tracks registrations. Sends WhatsApp reminders (24 hours and 1 hour before). Manages participant list. | Faculty Advisor present at event. Confirms execution. | Attendance captured. Participation certificates auto-generated post-event. | Day of event |
| 6.6 | External Participation & NOC | Processes requests for inter-college participation. Validates eligibility (attendance ≥ 75%, no dues, no active disciplinary case). Generates NOC/permission letter. | Dean signs NOC for external competitions. | NOC issued. Absence pre-approved in Attendance module. | 2 business days |
| 6.7 | Post-Event Report & Compliance | Prompts club president to submit post-event report (photos, expenditure, feedback) within 7 days. Validates expenditure vs. sanctioned budget. Flags overspend. Compiles annual student activity report. | Faculty Advisor verifies report. Dean approves expenditure. | Report stored. Budget reconciliation complete. Annual activity data → Regulatory E14 (NAAC C7). | 7 days post-event |

---

## SS-7: Health & Counseling

**Trigger:** Student self-books via portal, OR `risk.score_red` sustained 7 days
triggers auto-counseling referral, OR medical emergency reported on campus.

**Confidentiality rules (hard-coded — not configurable):**
- Counseling session notes: not accessible to faculty, HOD, TPO, or Placement Officer
- Dean of Student Affairs can access counseling records only when there is a risk
  to the safety of the student or others
- Health records: accessible only to Health Staff, student, and Dean
- E16 Parent Portal shows only risk traffic light (Green / Amber / Red) —
  no clinical detail, no diagnosis, no counseling summary

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 7.1 | Appointment Booking | Displays available slots (doctor, nurse, counselor). Auto-confirms booking. Sends WhatsApp reminder 1 hour before. Tracks no-shows. Sends rescheduling nudge. | Health staff confirms daily schedule. | Appointment confirmed. Calendar invite sent. | Immediate (self-service) |
| 7.2 | Consultation & Record | Creates digital health record for each visit: diagnosis, prescription, follow-up flag. If student admitted: fires `attendance.medical_leave` event to Academics. | Doctor / Counselor enters notes. Approves sick leave. | Health record created. `attendance.medical_leave` if admitted. | Same day |
| 7.3 | Counseling & Mental Health Referrals | AUTO-TRIGGER: `risk.score_red` sustained 7 days → auto-schedules counseling session. Notifies student via in-app only (not WhatsApp — confidentiality). Tracks attendance. If student declines twice: alerts Dean without case details. | Counselor conducts session. Records confidential notes. Recommends follow-up or external referral. | Session logged. Follow-up scheduled if needed. Risk traffic light updated in E16 portal (Red/Amber/Green — no clinical detail). | Within 48 hours of trigger |
| 7.4 | Medical Emergency Management | Receives emergency alert. Simultaneously alerts: campus doctor, nearest hospital, parent (WhatsApp + SMS), Dean. Tracks incident response. | Doctor / Dean manages emergency. Logs response. | Emergency response record. Parent notified immediately. Incident report filed. | Immediate |
| 7.5 | Health Clearance & Reports | At program completion: generates medical clearance certificate. Compiles anonymised campus health analytics (no individual identifiers). | Health Officer signs certificate. | `health.cleared` event for graduation workflow. Anonymised report for Dean. | On graduation trigger |

---

## SS-8: Alumni Relations

**Trigger:** ALL THREE of the following must be true:
1. `result.final_published` from Examinations module
2. `student.dues_cleared` from Finance module
3. `graduation.verified` from Registrar

The `AlumniTransitionSaga` Temporal workflow waits for all three signals.
No partial states. No shortcuts.

**DPDP note:** Alumni profile creation and annual career update collection are
new data collection contexts. Consent for alumni data use (employment updates,
mentorship matching, donation campaigns) must be separately logged before the
alumni profile is published. Alumni can withdraw consent at any time. Erasure
requests are eligible 7 years post-graduation.

```python
class AlumniTransitionSaga:
    @workflow.run
    async def run(self, student_id: UUID):
        results_done = False
        dues_cleared = False
        graduation_verified = False

        while not (results_done and dues_cleared and graduation_verified):
            signal = await workflow.wait_for_signal(
                ["result.final_published",
                 "student.dues_cleared",
                 "graduation.verified"],
                timeout=timedelta(days=365)   # cancels if not completed in current cycle
            )
            if signal.type == "result.final_published":
                results_done = True
            elif signal.type == "student.dues_cleared":
                dues_cleared = True
            elif signal.type == "graduation.verified":
                graduation_verified = True

        await execute_activity(transition_student_to_alumni, args=[student_id])
```

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 8.1 | Graduation Clearance & Profile Transition | Waits for all three saga signals. Checks all module clearances (Finance, Library, Hostel, Exams). Transitions student profile to ALUMNI status. Archives and seals academic record. | Registrar confirms graduation list. Dean approves transition batch. | `alumni.created` event. Student email → alumni email. Academic transcript sealed permanently. | Post-result publication |
| 8.2 | Alumni Portal Onboarding | Auto-creates alumni portal account. Pre-fills with academic history, program, batch, placement data (DPDP consent required). Sends welcome message via WhatsApp. | No approval needed. DPDP consent logged before profile published. | Alumni portal active. Physical alumni card request auto-generated. | Within 24 hours of transition |
| 8.3 | Alumni Network Engagement | Maintains batch-wise and program-wise alumni groups. Sends quarterly AI-generated newsletter via WhatsApp + email. Invites alumni to campus events, guest lectures, mentorship programs. | Dean manages strategic engagement. Alumni Cell curates content. | Newsletter sent quarterly. Event participation recorded. | Quarterly (auto) |
| 8.4 | Career & Professional Updates | Collects career updates via annual survey (job changes, achievements, promotions). DPDP: consent re-confirmed before each annual survey dispatch. Updates alumni profile. Feeds NIRF/NAAC placement outcome data. | No approval — AI collects and updates. Dean can view aggregate dashboard. | Alumni career data updated. NIRF placement outcome compiled for Regulatory E14. | Annual (auto) |
| 8.5 | Mentorship & Referral Program | Matches alumni mentors with current students by program, career path, interests. Manages sessions via in-app scheduling. Tracks mentorship hours. | Alumni mentor accepts / declines. Faculty Advisor oversees program. | Sessions scheduled. Hours recorded. Mentorship data → NAAC C2. | Per match request |
| 8.6 | Alumni Giving & Endowment | Manages alumni donation campaigns (scholarship funds, infrastructure, research). Auto-generates 80G tax-exemption receipts. Annual giving report. | Dean approves campaign. Finance Officer manages fund allocation. | Donation records stored. 80G receipts auto-issued. Giving report generated. | Per campaign |

---

## E16: Parent / Guardian Portal (Go-Live Blocker)

**Status:** ❌ Not built. Required before institutional go-live.

**Why this is a go-live blocker:** Every parent wants attendance, dues, and results
visibility. Without it, parents call the Dean directly — breaking the AI-first model
at the highest-impact touchpoint.

**RBAC:** `guardian` role — scoped to a single `student_id`. Read-only everywhere.
No edit access. No ability to raise grievances or requests.

**Provisioning:** Auto-created on `student.enrolled` using `parent_phone` from
enrollment payload. No admin action required.

```python
class GuardianPortalEventHandler:
    async def handle_student_enrolled(self, event: DomainEvent):
        payload = StudentEnrolledPayload(**event.payload)
        if not payload.parent_phone:
            return
        await execute_transaction([(
            """INSERT INTO guardian_accounts
               (id, tenant_id, student_id, phone, otp_verified, created_at)
               VALUES ($1, $2, $3, $4, false, now())
               ON CONFLICT (tenant_id, phone, student_id) DO NOTHING""",
            [str(uuid4()), payload.tenant_id,
             payload.student_id, payload.parent_phone]
        )])
        await send_whatsapp(
            payload.parent_phone,
            template="guardian_portal_welcome",
            params={
                "student_name": payload.full_name,
                "portal_url": portal_url
            }
        )
```

```sql
CREATE TABLE guardian_accounts (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL,
    student_id   UUID NOT NULL,
    phone        TEXT NOT NULL,
    otp_verified BOOLEAN DEFAULT false,
    last_login   TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, phone, student_id)
);
CREATE INDEX idx_guardian_phone ON guardian_accounts(tenant_id, phone);
```

**Authentication:** OTP-only via registered mobile. 6-digit OTP. 30-minute session.
No permanent tokens for guardians.

**What guardians CAN see:**

| Data | Source Module | Update Frequency |
|---|---|---|
| Attendance % per course | Academics | Real-time |
| Attendance trend (last 30 days) | Academics | Daily |
| Current semester dues and payment history | Finance | Real-time |
| Upcoming exam schedule | Examinations | On publication |
| Results when published | Examinations | On `result.published` |
| Communications sent to student | All modules | Real-time |
| Risk traffic light (Green / Amber / Red) | Academics Risk module | Daily |

**What guardians can NEVER see (hard-coded):**
- Counseling session notes or any health records
- Grievance details or disciplinary case information
- Placement negotiation data, CTC, company details
- The underlying risk factors behind the Red/Amber classification
- Other students' data (multi-student parent view supported — each child is a separate scoped view with its own OTP flow)

**Feature flag:** `portal.guardian_access` — off by default, enabled per institution.

---

## Complete System Flow

```
[ADMISSIONS]
`student.enrolled` fires
         │
         ├──► SS-1 Hostel (if hostel_opted) → Warden approves room
         ├──► SS-2 Library → Auto-membership, no action required
         ├──► SS-4 Scholarships → Eligibility screened immediately
         └──► E16 Parent Portal → Auto-provisioned, WhatsApp welcome sent to parent
                                   │
[ACADEMICS] ──────────────────────┤
`risk.score_red` (sustained 7 days)│
         └──► SS-7 Counseling      │
              Auto-referral 48 hrs │
                                   │
[EXAMINATIONS]                     │
`exam.malpractice_flagged` ────────►  SS-5 Disciplinary (confidential)
`exam.backlog_cleared` ─────────────► SS-3 Placement re-evaluation
`result.final_published` ───────────► SS-8 AlumniTransitionSaga (signal 1 of 3)
                                   │
[FINANCE]                          │
`student.dues_cleared` ────────────► SS-8 AlumniTransitionSaga (signal 2 of 3)
`scholarship.disbursed` ───────────► SS-4 status update
                                   │
[REGISTRAR]                        │
`graduation.verified` ─────────────► SS-8 AlumniTransitionSaga (signal 3 of 3)
         │
         └──► All three received → transition_student_to_alumni()
              `alumni.created` → transcript sealed permanently

[SS-5 GRIEVANCE]
`grievance.closed` → Regulatory E14 (NAAC metric)

[SS-3 PLACEMENT]
`offer.received` → one-offer lock
`offer.revoked` → OfferRevocationWorkflow → TPO verifies → student reactivated
```

---

## Cross-Module Integration Map

| Event | Fired By | Consumed By | Payload / Purpose |
|---|---|---|---|
| `student.enrolled` | Admissions | SS-1, SS-2, SS-3, SS-4, E16 | Student ID, Roll No., program, batch, hostel_opted, parent_phone |
| `hostel.checkin` | SS-1 | Academics (risk baseline), Finance | Room no., check-in date |
| `hostel.cleared` | SS-1 | Finance (deposit refund), Exams (hall ticket), Graduation | Clearance status |
| `library.cleared` | SS-2 | Exams (hall ticket), Graduation (transcript) | Clearance status |
| `attendance.medical_leave` | SS-7 | Academics (Attendance) | Student ID, dates, doctor note |
| `risk.score_red` | Academics | SS-7 Health | Student ID, risk factors |
| `scholarship.awarded` | SS-4 | Finance | Student ID, amount, scholarship type |
| `scholarship.disbursed` | Finance | SS-4 | Confirms payment / DBT credit |
| `placement.profile_active` | SS-3 | SS-3 drives | Profile live for TPO dashboard |
| `offer.received` | SS-3 | SS-3 one-offer lock | Student ID, company, CTC |
| `exam.malpractice_flagged` | Examinations | SS-5 Disciplinary | Student ID, exam ID |
| `exam.backlog_cleared` | Examinations | SS-3 Placement | Student ID — re-evaluate zero-backlog eligibility |
| `grievance.closed` | SS-5 | Regulatory E14 | Grievance ID, category, resolution time |
| `result.final_published` | Examinations | SS-8 Alumni Saga | Signal 1 of 3 |
| `student.dues_cleared` | Finance | SS-8 Alumni Saga, Exams | Signal 2 of 3 |
| `graduation.verified` | Registrar | SS-8 Alumni Saga | Signal 3 of 3 |
| `alumni.created` | SS-8 | Exams (transcript seal) | Alumni ID, graduation date |
| `event.venue_request` | SS-6 Clubs | Academics (Timetable) | Date, time, venue — conflict check |
| `health.cleared` | SS-7 | Graduation workflow | Medical clearance status |

---

## SLA & Escalation Matrix

| Module | Approval Gate | Approver | SLA | Breach Escalation |
|---|---|---|---|---|
| Hostel | Room allotment | Warden | 1 business day | Auto-assigned; Dean notified |
| Hostel | Leave / outpass | Warden | 4 hours | Auto-approved with parent WhatsApp |
| Hostel | Maintenance (major) | Warden | 72 hours | Escalates to Dean |
| Hostel | SAFETY swap resolution | Warden | 72 hours (absolute) | Dean mandates; overflow space provided |
| Library | Catalogue update / acquisition | Librarian | 3 business days | Dean review flag |
| Placement | Company registration | TPO | 2 business days | Escalates to Dean |
| Placement | Drive result validation | TPO | Same day | Dean notified |
| Placement | Offer acceptance window | Student | 3 business days | Offer lapses; company notified |
| Placement | Revocation TPO verification | TPO | 3 business days | Auto-rejected; student directed to Dean |
| Scholarship | Document verification | Admin Staff | 3 business days | Escalates to Dean |
| Scholarship | Award list approval | Dean / Committee | 5 business days | Escalates to VC |
| Grievance | Acknowledgement (auto) | AI | 1 hour | — |
| Grievance | Case file & hearing schedule | SGRC Chairperson | 15 days | Statutory breach — Ombudsperson auto-notified (UGC Reg 2023) |
| Grievance | Final resolution order | Dean | 30 days from intake | Statutory breach — reported to UGC Grievance Portal |
| Clubs & Events | Event proposal | Faculty Advisor → Dean | 5 days | Escalates to Dean if Faculty Advisor delays > 2 days |
| Clubs & Events | Budget sanction | Dean + Finance | 3 business days | Auto-escalates to VC |
| Health | Medical leave approval | Doctor | Same day | Auto-approved with flag |
| Health | Counseling referral (RED risk) | Counselor | 48 hours | Dean notified (no case detail) |
| Health | Medical emergency | Doctor | Immediate | Hospital / police — not an ALIS OS gate |
| Alumni | Graduation clearance | Registrar | 3 days post-result | VC notified if bottleneck affects convocation |

---

## What Actors Never Do (AI Handles Completely)

**Hostel & Library:**
- Check room availability or assign rooms
- Calculate monthly mess bills or library fines
- Send leave/outpass approval notifications
- Create library memberships for new students
- Send due-date reminders

**Placement & Scholarships:**
- Build student placement profiles from academic records
- Match student profiles to JD requirements
- Send drive registration reminders
- Calculate scholarship eligibility
- Send scholarship award notifications
- Lock or unlock profiles for one-offer policy

**Grievance & Disciplinary:**
- Log, classify, or route grievance submissions
- Assign Grievance IDs or send acknowledgements
- Detect coordinated complaint spikes
- Apply exam-period blackouts
- Generate UGC/NAAC compliance reports

**Clubs, Health & Alumni:**
- Check venue availability against class timetable
- Calculate and track event budgets
- Book counseling appointments on risk triggers
- Send mental health referral alerts (with confidentiality controls)
- Wait for all three alumni saga signals and execute the transition
- Provision parent portal accounts and send WhatsApp welcome on enrollment
- Send quarterly alumni newsletters

---

## DPDP Act 2023 — Student Services Compliance

Every data collection point must log a consent record in the E21 `consent_records`
table before writing personal data. The `ConsentMiddleware` enforces this.

| Data Collection Point | Consent Required | Module Stage |
|---|---|---|
| Hostel application (medical conditions for room assignment) | Yes | SS-1.1 |
| Placement profile activation (data shared with companies) | Yes | SS-3.1 |
| Scholarship application (income, caste, bank details) | Yes | SS-4.3 |
| Counseling session (mental health data — separate consent) | Yes | SS-7.2 |
| Alumni profile creation (post-graduation data use) | Yes | SS-8.2 |
| Annual alumni career survey (re-consent each year) | Yes | SS-8.4 |

**Erasure rules:**
- Active students: erasure of academic records blocked (statutory retention)
- Alumni: PII erasure eligible 7 years post-graduation
- Anonymised statistical aggregates (batch-level placement %, scholarship %) retained permanently for NAAC/NIRF

---

## Notification Map

| Module | Trigger | Recipients | Channel |
|---|---|---|---|
| Hostel | Room allotment confirmed | Student + Parent | WhatsApp + Email |
| Hostel | Leave approved / rejected | Student | WhatsApp |
| Hostel | Student departs / returns hostel | Parent | WhatsApp (real-time) |
| Hostel | Maintenance ticket resolved | Student | In-app + Email |
| Hostel | SAFETY swap escalation | Warden + Dean | In-app + Email (staff) |
| Library | Book due in 3 days / overdue | Student | WhatsApp |
| Library | Fine added to account | Student | WhatsApp |
| Library | Book reservation available | Student | WhatsApp |
| Placement | New drive open | Eligible students | WhatsApp |
| Placement | Round-wise shortlist published | Registered students | WhatsApp |
| Placement | Offer letter received | Student + TPO + Dean | WhatsApp + Email |
| Placement | Offer revocation verified — reactivated | Student | WhatsApp |
| Placement | Verbal lock placed | Student | WhatsApp + In-app |
| Scholarships | Scholarship window open | Eligible students | WhatsApp |
| Scholarships | Documents verified / rejected | Student | WhatsApp |
| Scholarships | Scholarship awarded | Student + Parent + Finance | WhatsApp + Email |
| Grievance | Acknowledgement (auto) | Complainant | In-app + WhatsApp |
| Grievance | Hearing scheduled | Both parties | Email + SMS |
| Grievance | Anomaly spike detected | Dean | Email + In-app (staff) |
| Grievance | 30-day deadline breach imminent | Dean + SGRC Chair | Email + In-app |
| Grievance | Resolution issued | Both parties + Dean | Email |
| Clubs & Events | Event approved / rejected | Club President + Faculty Advisor | Email |
| Clubs & Events | Reminder (24 hours before) | Registered participants | WhatsApp |
| Health | Appointment confirmed | Student | WhatsApp |
| Health | Counseling referral triggered | Student (confidential) | In-app only |
| Health | Medical emergency alert | Parent + Dean + Doctor | WhatsApp + SMS (immediate) |
| Health | Risk level changes to RED | Parent (via E16 portal) | E16 portal update only |
| Alumni | Alumni profile activated | New alumni | WhatsApp + Email |
| Alumni | Newsletter / quarterly update | All alumni | WhatsApp + Email |
| Alumni | Mentorship match available | Student + Alumni mentor | Email + In-app |
| E16 Parent Portal | First-time provisioning | Parent | WhatsApp (guardian_portal_welcome template) |
| E16 Parent Portal | Risk level changes to RED | Parent | WhatsApp (no clinical detail) |
| E16 Parent Portal | Result published | Parent | WhatsApp |

---

## Configurable Parameters

| Module | Parameter | Default |
|---|---|---|
| Hostel | Room allotment priority rules | Category → Disability → Floor preference → Random |
| Hostel | Leave blackout periods | 10 days before and during exam blocks |
| Hostel | Security deposit amount | ₹5,000 (per room type) |
| Hostel | SAFETY swap overflow duration | 72 hours |
| Library | Books per student by program | UG: 3 \| PG: 5 \| PhD: 8 |
| Library | Fine per overdue day | ₹2/day |
| Library | Fine cap per book | ₹100 |
| Placement | Semester to activate placement profile | Semester 5 (4-year programs) |
| Placement | One-offer policy enforcement | Enabled by default |
| Placement | Dream Company drive attempts post-offer | 1 attempt |
| Placement | Verbal lock formal offer deadline | 14 days from lock initiation |
| Placement | Revocation TPO verification deadline | 3 business days |
| Scholarships | Merit scholarship CGPA threshold | ≥ 8.0 CGPA |
| Scholarships | Scholarship retention CGPA | ≥ 7.5 CGPA each semester |
| Grievance | Auto-acknowledgement window | 1 hour (UGC minimum: 3 working days) |
| Grievance | Resolution deadline | 30 days from intake (UGC mandated — not configurable) |
| Grievance | Anomaly spike multiplier threshold | 3.0× rolling average |
| Grievance | Anomaly minimum complaint count | 5 in 24 hours |
| Grievance | Exam blackout window | 48 hours before + during exam |
| Clubs & Events | Minimum members for club | 15 students |
| Clubs & Events | Annual club budget ceiling | ₹50,000 per club |
| Health | Auto-counseling trigger | RED sustained for 7 days |
| Health | Counseling confidentiality scope | Health Staff + Dean only (not modifiable) |
| Alumni | Alumni email domain suffix | @alumni.institution.edu.in |
| Alumni | Annual career survey month | March |
| Alumni | Career data erasure eligibility | 7 years post-graduation |
| E16 Parent Portal | Session duration | 30 minutes |
| E16 Parent Portal | Feature flag | `portal.guardian_access` — off by default |

---

## Regulatory Feeds from Student Services (E14 Integration)

| Data | Source | Framework / Report | Cadence |
|---|---|---|---|
| Grievance volume, closure rate, UGC compliance | SS-5.7 `grievance.closed` | NAAC B2 (Governance) | Annual |
| Scholarship disbursements, student category coverage | SS-4.6 `scholarship.disbursed` | NAAC C5 (Student Support) | Annual |
| Placement % placed, average CTC, sector distribution | SS-3.9 statistics | NIRF GO (Graduate Outcomes) | Annual (January window) |
| Alumni employment rate, career outcomes | SS-8.4 career updates | NIRF GO | Annual |
| Student activity events, participation hours | SS-6.7 post-event report | NAAC C7 (Student Activities) | Annual |
| Hostel occupancy, facilities utilisation | SS-1 operations data | NAAC B4 (Infrastructure) | Annual |
| Mentorship hours, alumni-student ratio | SS-8.5 mentorship records | NAAC C4 (Alumni Engagement) | Annual |

---

*Document version: 2.0 | March 2026*
*Connected to: admissions_workflow.md → academic_operations_workflow.md →*
*examination_workflow.md → student_services_workflow.md → finance_workflow.md →*
*hr_payroll_workflow.md → regulatory_accreditation_workflow.md*
*Full institutional lifecycle: Lead Captured → Graduated → Alumni Engaged*
*QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential*
