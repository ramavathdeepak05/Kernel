# Examination Module Workflow
### Full Automation Reference — ALIS OS Module E06
#### Model: AI Executes Everything. Actors Approve.
#### QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential

---

## Document Map

This document covers the full Examinations module (E06) of ALIS OS.

**Connected documents:**
- `admissions_workflow.md` — student identity, photo, program, category data
- `academic_operations_workflow.md` — upstream source of IA marks, attendance, question papers
- `student_services_workflow.md` — grievance blackout during exams (EC-SS-01), dues clearance
- `finance_workflow.md` — dues clearance gate for hall tickets (read model, not event-only)
- `regulatory_accreditation_workflow.md` — consumes result statistics, SGPA data, graduation counts

**Cross-references to skill files:**
- Edge cases: `references/edge-cases.md` — EC-EXM-01 through EC-EXM-05
- Vault architecture: `references/architecture.md` §14 (P0 — HashiCorp Vault)
- Dues read model: `references/architecture.md` §14 (P1 — Finance Dues Race Condition)
- Load testing targets: `references/gaps.md` — Load Testing Baseline section
- Build sequence: `ALIS_BUILD_PLAN.md` — Sprint 1 (EC-EXM-01, EC-EXM-05), Sprint 2 (EC-EXM-02, EC-EXM-03, EC-EXM-04)

---

## How Examinations Fit Into the Larger System

The Examination module is a downstream consumer. It never collects data independently —
everything it needs is already in the system.

```
ADMISSIONS MODULE            ACADEMIC MODULE              EXAMINATION MODULE
─────────────────            ───────────────              ──────────────────
Student ID + Roll No.  ───►  Internal marks (IA1–3) ───► Eligibility check
Program + Batch        ───►  Attendance %            ───► Hall ticket generation
Photo + personal data  ───►  Question papers (M4)    ───► Paper dispatch (Vault-gated)
Finance clearance      ───►  Course registrations    ───► Result computation
                             Faculty assignments      ───► Grade cards + transcripts
```

**Events the Examination module listens to:**

| Event | Source | Triggers |
|-------|--------|---------|
| `exam_block.start` | Academic Calendar | Eligibility run, hall ticket generation |
| `internal_marks.locked` | Academic Module (M8) | Combined result computation ready |
| `attendance.semester_final` | Academic Module (M6) | Eligibility confirmation |
| `student.dues_cleared` | Finance Module | Eligibility gate signal (supplemented by read model) |
| `result.published` | This module | Revaluation window opens |
| `revaluation.result_ready` | This module | Revised grade card triggered |
| `grievance.invigilator_complaint` | Student Services | Blackout check during exam period |

**Critical: The dues clearance gate must query the `student_dues_status` read model
at hall-ticket generation time — not rely solely on the `student.dues_cleared` event.**
Reason: a library fine posted after the event fires invalidates clearance. The event
alone creates a race condition. See §14 P1 in `references/architecture.md` and the
Dues Gate section in Stage 1 below.

---

## Pipeline Overview

| # | Stage | AI Does | Approver |
|---|-------|---------|----------|
| 1 | Exam Registration & Eligibility | Runs eligibility checks, generates exam form | Registrar / CoE |
| 2 | Exam Schedule Generation | Drafts timetable, resolves conflicts | Controller of Examinations (CoE) |
| 3 | Question Paper Management | Stores, encrypts (AES-256, Vault-gated), dispatches | CoE (paper receipt confirmation only) |
| 4 | Hall Ticket Generation | Generates and delivers hall tickets | CoE (batch approval) |
| 5 | Seating & Invigilation Arrangement | Allocates rooms, seats, invigilators | CoE |
| 6 | Exam Conduct & Attendance | Creates sessions, logs malpractice | Invigilator (marks attendance) |
| 7 | Answer Script Management | Tracks chain of custody, assigns evaluators | CoE |
| 8 | Evaluation & Marks Entry | Auto-grades objectives, assists descriptive | Faculty Evaluator |
| 9 | Result Computation & Publication | Computes SGPA/CGPA, generates grade cards | Registrar |
| 10 | Revaluation & Rechecking | Manages requests, assigns re-evaluators | CoE + Registrar |
| 11 | Supplementary / Re-appear Examination | Identifies eligible students, full repeat cycle | Registrar |
| 12 | Transcript & Score Card Generation | Assembles all official documents | Registrar |

---

## Key Actors

| Actor | Role |
|-------|------|
| **Controller of Examinations (CoE)** | Central authority for all exam operations. Final approver on schedule, hall tickets, question paper dispatch, and malpractice cases |
| **Registrar** | Signs off on results, transcripts, score cards, and degree-related documents |
| **Faculty Evaluator** | Evaluates answer scripts; assigned by CoE (not the student's own faculty where possible) |
| **Invigilator** | Faculty on duty in the exam hall; marks attendance, raises malpractice flags |
| **Student** | Registers for exam, receives hall ticket, views results, applies for revaluation |
| **Unfair Means Committee (UFM Committee)** | Constituted by CoE; hears malpractice cases and recommends punishment |
| **Finance** | Clears student dues — feeds `student_dues_status` read model consumed by this module |

---

## Production Hardening Requirements

### HashiCorp Vault — P0 Prerequisite

**Question paper encryption requires HashiCorp Vault before any exam module goes live.**
MinIO server-side encryption alone is insufficient — it does not provide CoE-only
decrypt access or a per-operation audit trail.

Every question paper must:
1. Be encrypted with AES-256 using a paper-specific key stored in Vault
2. Be decryptable only by the CoE role (RBAC enforced at the Vault policy level)
3. Produce a Vault audit log entry on every decrypt operation
4. Trigger an immediate alert to CoE + Registrar on any unauthorized access attempt

**Docker Compose addition (if not already present):**
```yaml
vault:
  image: hashicorp/vault:latest
  environment:
    VAULT_DEV_ROOT_TOKEN_ID: ${VAULT_ROOT_TOKEN}
  ports: ["8200:8200"]
  cap_add: ["IPC_LOCK"]
```

**Feature flag:** `examinations.question_paper_vault` — must be `true` before the
Examination module processes any paper. Claude Code must verify this flag is set
and Vault is reachable before executing any paper management workflow.

### Dues Gate — Read Model (Not Event-Only)

The hall ticket eligibility check for dues must query the `student_dues_status`
read model at generation time:

```python
class StudentDuesStatus(BaseModel):
    student_id: UUID
    tenant_id: UUID
    total_outstanding: Decimal
    last_updated_at: datetime
    pending_library_fines: Decimal
    pending_hostel_dues: Decimal
    pending_exam_fees: Decimal
    dues_cleared: bool = Field(
        default_factory=lambda self: self.total_outstanding == 0
    )
```

The `student.dues_cleared` event is still published by Finance, but the Examination
module must re-query this read model at the moment of hall ticket generation to
catch any dues added after the event fired.

### Result Day Load — Pre-generation Required

On result publication day, a 5,000-student university generates 15,000+ simultaneous
portal hits (students + parents + faculty) within 30 minutes.

**Grade cards must be pre-generated as PDFs before the Registrar approves publication.**
The approval step releases pre-built PDFs — it does not trigger real-time generation.

```python
# Pre-generation runs as a Celery task after all marks are locked
# and before the Registrar approval gate opens

@celery_app.task(queue="results", bind=True)
async def pre_generate_grade_cards(self, batch_id: str, semester: int, tenant_id: str):
    students = await get_batch_students(batch_id, tenant_id)
    for student in students:
        pdf_bytes = await generate_grade_card_pdf(student.id, semester, tenant_id)
        await minio.put_object(
            bucket="grade-cards",
            object_name=f"{tenant_id}/{student.roll_number}/{semester}.pdf",
            data=pdf_bytes,
        )
    await mark_grade_cards_ready(batch_id, semester, tenant_id)
```

**Load test targets for exam-related endpoints** (from `references/gaps.md`):

| Scenario | Concurrent users | p95 latency target | Error rate target |
|---|---|---|---|
| Result publication day | 2,000 | < 2s | < 1% |
| Exam hall ticket release | 1,000 | < 1s | < 0.5% |
| Normal exam operations | 200 | < 500ms | < 0.1% |

These must pass on staging before any institution go-live. Run with Locust against
production-equivalent data (minimum 5,000 student records, 2 years of historical data).

---

## Stage 1 — Exam Registration & Eligibility Check

**Purpose:** Determine which students are eligible to appear for each course.
Generate the official eligible / ineligible list. Handle exceptions.

### AI Does

**Exam Registration Form (auto-generated):**
AI generates a pre-filled exam registration form per student: all enrolled courses
for the semester, credit value, carry-forward backlog courses, fee payable.
Student confirmation is one click — no manual data entry.
Registration window is time-bound (configurable: typically 2–3 weeks before exam block).

**Eligibility Engine (fully automated):**
AI checks all of the following simultaneously for every student × every course:

| Check | Source | Pass Condition |
|-------|--------|----------------|
| Minimum attendance | Academic Module (M6) | ≥ 75% (configurable) |
| Condonation eligibility | Attendance module | 65–74% with valid reason (medical, sports, university event) |
| All IA assessments attempted | Academic Module (M8) | Appeared in minimum prescribed IAs |
| Internal marks submitted | Academic Module (M8) | Faculty has locked marks |
| No active disciplinary hold | Student Affairs | No pending suspension |
| Dues cleared | `student_dues_status` read model | `total_outstanding == 0` |
| Exam registration completed | This module | Form confirmed + fee paid |

**Dues Gate — Critical Implementation Note:**

```python
async def check_dues_clearance(student_id: UUID, tenant_id: UUID) -> bool:
    # NEVER rely solely on student.dues_cleared event — it can be stale
    # Always query the read model at eligibility check time
    dues_status = await get_student_dues_status(student_id, tenant_id)
    return dues_status.dues_cleared  # computed from total_outstanding == 0
```

The `student.dues_cleared` event is a signal to start the check — not the result
of the check. The read model is the authoritative source.

**Result per student per course:**
- `ELIGIBLE` — clears all checks
- `INELIGIBLE: ATTENDANCE` — below 75%, no condonation basis
- `INELIGIBLE: DUES` — outstanding balance (from read model)
- `INELIGIBLE: DISCIPLINARY_HOLD` — active case
- `CONDONATION_PENDING` — attendance 65–74%; requires CoE approval
- `REGISTRATION_INCOMPLETE` — student has not confirmed or paid

**Exception handling:**
- Condonation requests: AI generates draft condonation letter pre-filled with
  attendance data and reason codes. Student submits reason + supporting documents.
  CoE reviews and approves / rejects.
- Medical certificates: uploaded by student; AI flags for CoE review.
- Retrospective dues clearance: Finance posts to read model → AI re-runs
  eligibility check automatically. No manual re-trigger required.

### Approver — Registrar / CoE

- Reviews ineligible list and condonation requests
- Approves condonations → status updated to ELIGIBLE
- Rejects condonations → ineligibility letter auto-dispatched to student + parent
- Signs off on final eligibility list → locks the list and triggers Stage 4
  (hall ticket generation). **Once locked, eligibility list is immutable.**

### Notifications (auto)

- Exam registration window opens → all students notified (Email + Portal + WhatsApp)
- Registration deadline T-3, T-1 → reminders
- Student found ineligible → notified with reason and condonation process link
- Condonation approved / rejected → student notified immediately
- Final eligibility confirmed → student notified

---

## Stage 2 — Exam Schedule Generation

**Purpose:** Generate the end-semester exam timetable with no student schedule conflicts.

### AI Does

**Hard Constraints (cannot be violated):**
- No student can have two exams in the same session (FN or AN) on the same day
- Common/shared courses across multiple programs appear on the same date and time
- Practical exams scheduled in lab rooms only; theory in lecture halls
- Gap of at least one calendar day between theory exams in the same program
- No exam scheduled on declared holidays or Sundays

**Soft Constraints (optimized):**
- High-credit / high-difficulty courses scheduled earlier in the exam block
- Core courses not scheduled on the same day as their prerequisite courses
- Exam load spread evenly across the block (avoid 5 exams in 3 days)
- Lab exams in the second half of the exam block (more prep time)

**Solver note:** The exam schedule is generated by a constraint solver (Google OR-Tools),
not an LLM. The LLM's role is only to explain the timetable in plain English and
draft the student notification. Task class: `EXTRACTION` for parsing any input
constraints, `DRAFTING` for communication. Never `REASONING` for the solve itself.

**Output:**
- Draft timetable: date × session × course × duration × room block
- Conflict report: any student with overlapping exams (should be zero)
- Room requirement summary: total room-hours needed vs. available

### Approver — CoE

- Reviews draft timetable; adjusts if needed (AI re-checks constraints on any change)
- Approves → timetable published to student portal, faculty portal, and notice board
- Students and faculty notified immediately on publish

---

## Stage 3 — Question Paper Management

**Purpose:** Receive question papers, store them encrypted in Vault, and dispatch at
the correct time on exam day. Maintain full chain of custody. Provide offline fallback
if network fails at T-30.

### AI Does

**Paper receipt and storage:**
- Question papers submitted by faculty through Academic Module M4 (approved by
  faculty → HOD)
- On receipt by Exam Cell: AI assigns a paper ID, timestamps submission,
  encrypts file using AES-256 with a paper-specific key stored in HashiCorp Vault
- Encrypted paper stored in MinIO (encrypted blob). Key stored in Vault only.
- AI generates receipt confirmation sent to faculty + HOD
- AI checks paper against prescribed format (marks total, section structure,
  unit coverage) — flags deviations for CoE review

**Paper security protocol:**
- No one can view or download the paper after CoE encryption lock.
  Only the CoE can decrypt (enforced at Vault policy level, not application level).
- System logs every Vault access attempt with timestamp, user ID, and outcome.
- Any unauthorized access attempt triggers immediate alert to CoE + Registrar
  (SMS, not reliant on internet).

**Exam day dispatch (fully automated, time-locked):**
- 30 minutes before exam start: system requests decrypt from Vault and makes
  paper available to the designated printing station or online exam portal
- Paper released only if:
  1. Exam session is active on the calendar
  2. At least one invigilator has checked in for the hall
  3. No security hold placed by CoE
- For online exams: paper delivered directly to students' exam portal at start time
- Invigilators receive "paper received" confirmation in their portal

**If faculty has not submitted paper by deadline:**
- AI escalates to HOD at T-21 days
- AI escalates to CoE at T-7 days (SLA breach)
- CoE may activate the question bank (Academic Module M4) to auto-generate
  a replacement paper — CoE approves before encryption

### EC-EXM-01 — Offline Cryptographic Fallback (P0 — Sprint 1)

**Trigger:** Campus-wide internet outage hits exactly at T-30 when the system
attempts to decrypt and release question papers. Invigilators cannot access the portal.

**Fix: USB-Key Protocol using HashiCorp Vault offline unsealing**

```
Protocol design:
1. 72 hours before each exam: system pre-generates encrypted paper bundles
   and writes them to a Vault-sealed local cache on the campus server.

2. Campus server holds the encrypted bundle. Cannot decrypt without the
   Vault unseal key, which only the CoE holds on a physical USB device.

3. Normal flow (T-30): Vault unseals via network → decrypts → distributes.

4. Network failure flow:
   a. System detects Vault unreachable: 3 failed pings within 90-second window.
   b. Triggers "Offline Exam Mode" alert to CoE mobile via SMS (not internet).
   c. CoE inserts USB key into the offline terminal at the exam control room.
   d. USB key contains the session-specific unseal shard (Shamir's Secret Sharing).
   e. Terminal decrypts the pre-cached bundle locally.
   f. CoE prints papers OR distributes via LAN (campus local network, no internet).
   g. All offline actions are cryptographically signed and synced to Vault audit log
      when connectivity restores.
```

```python
class ExamPaperDispatchMode(str, Enum):
    ONLINE_VAULT   = "online_vault"       # normal path
    OFFLINE_USB    = "offline_usb"        # fallback path
    EMERGENCY_PRINT = "emergency_print"   # last resort

class OfflineDispatchRecord(BaseModel):
    exam_session_id: UUID
    dispatch_mode: ExamPaperDispatchMode
    initiated_by: UUID                    # CoE user ID
    usb_key_serial: str                   # hardware token serial number
    offline_at: datetime
    synced_at: datetime | None            # populated when connectivity restores
    audit_hash: str                       # cryptographic proof of integrity
```

**Feature flag:** `examinations.offline_fallback_enabled` — must be `true` for any
institution running end-semester exams through ALIS. This is not optional.

**Physical prerequisite:** An air-gapped laptop with the ALIS offline client
pre-installed must be present at the exam control room before every exam season.

### Approver — CoE

- Reviews format compliance flags before encrypting
- Approves encryption lock (irreversible after this point)
- Approves day-of dispatch (or pre-authorizes the timetable for auto-dispatch)

---

## Stage 4 — Hall Ticket Generation

**Purpose:** Generate a unique hall ticket for every eligible student for every
exam they are appearing in.

### AI Does

**Hall ticket contents (auto-assembled from system data):**
- University name + logo + watermark + security serial number
- Student full name (as on 10th certificate — from Admissions module)
- Roll number + Enrollment number
- Photograph (from Admissions module)
- Program, semester, academic year
- Exam schedule: course code, course name, date, session (FN/AN), reporting time,
  exam hall, seat number (populated after Stage 5)
- Important instructions (general + institution-specific)
- Unique QR code (encodes student ID + exam session — used for digital verification)
- Digital signature of CoE

**Generation trigger:**
Both conditions must be true before hall tickets are released:
1. Eligibility list finalized and approved by CoE (Stage 1)
2. Seating arrangement completed (Stage 5)

**Dues re-check at generation time:**
Even if the eligibility list was approved earlier, the system re-queries
`student_dues_status` at the moment each hall ticket is generated. If a fine
has been added since eligibility was confirmed (e.g., a library fine posted
that morning), the hall ticket is withheld and the student is notified.

**Delivery:**
- Hall ticket PDF auto-generated per student
- Delivered via Email + downloadable from student portal + WhatsApp notification
- Available from T-7 days before first exam

**QR verification at hall entry:**
- Invigilator scans QR code → system confirms: hall ticket valid, student eligible,
  correct hall
- If status has changed since issue (rare edge case): system flags for manual check
  by invigilator; CoE notified

### Approver — CoE (batch approval)

- Reviews a sample of generated hall tickets for accuracy
- Approves batch release → all hall tickets made available simultaneously
- Individual corrections: AI re-generates specific hall ticket after data fix

### Edge cases

- **Student registered late:** AI generates hall ticket individually on
  eligibility confirmation
- **Lost / corrupted hall ticket:** Student requests re-print from portal;
  AI generates duplicate with "DUPLICATE" watermark; CoE auto-notified

---

## Stage 5 — Seating & Invigilation Arrangement

**Purpose:** Allocate every eligible student to a specific room and seat. Assign
faculty to invigilation duty. Enforce exam integrity through seating rules.

### AI Does

**Seating algorithm — Hard rules:**
- No two students from the same section or same course in adjacent seats
  (column separation enforced)
- If multiple courses share a hall: students of the same course are not in
  adjacent columns — alternating course columns
- Room capacity strictly not exceeded (capacity − 10% buffer, configurable)
- Students with disabilities or special needs: seated in accessible locations
  (flagged from Admissions data at enrollment)

**Seating algorithm — Soft rules:**
- Alphabetical or roll-number ordering within each room (for attendance marking)
- Students with backlogs from previous semesters mixed with current semester
  students in the same hall (reduces section clustering)

**Output per exam session:**
- Room-wise seating chart (printable PDF): Room → Row → Seat → Student name +
  roll number + course
- Student view: each student sees only their own room + seat (on hall ticket)
- Hall display list (posted outside each room): students in that room

**Invigilation assignment — AI assigns based on:**
- Faculty availability (not already assigned to another hall in the same session)
- Faculty NOT from the same department as the students in that hall
  (cross-departmental invigilation — standard practice)
- Seniority-based lead invigilator (1 senior + 1 junior per hall, configurable)
- Flying squads: 2–3 senior faculty assigned as roving invigilators across all halls

**Output:**
- Invigilation duty chart: session × hall × faculty assigned
- Faculty notified of their duty via Email + portal
- Faculty can raise a conflict (travel, medical) — AI finds an alternative

### Approver — CoE

- Reviews seating chart and invigilation duty chart
- Approves both → seating details pushed to hall tickets (triggering final delivery),
  duty chart dispatched to faculty

---

## Stage 6 — Exam Conduct & Attendance

**Purpose:** Manage the actual conduct of each exam session. Record attendance.
Handle malpractice in a structured, auditable way.

### AI Does

**Pre-session (automated):**
- Creates an attendance session for every scheduled exam at the configured time
- Sends report-time reminder to students 24 hours and 2 hours before
- Sends duty reminder to invigilators 24 hours before session

**During session — invigilator actions:**

| Action | Actor | System Response |
|--------|-------|----------------|
| Mark student present / absent | Invigilator | Attendance recorded, timestamp logged |
| Student arrives late (within window) | Invigilator | Marked "late — allowed" with timestamp |
| Student not allowed (outside window) | Invigilator | Marked "absent — late arrival" |
| Student leaves early (after allowed time) | Invigilator | Exit time recorded |
| Malpractice detected | Invigilator | UFM workflow triggered (see below) |

**Malpractice / Unfair Means (UFM) Workflow:**

When an invigilator flags a malpractice incident, AI immediately:
1. Opens a UFM case with a unique UFM case ID
2. Records: student roll number, exam, session, date, time, hall, invigilator,
   offence type (from categorized dropdown)
3. Invigilator uploads photo of confiscated material (if physical) or describes it
4. Student statement recorded (or refusal noted)
5. Student issued a new answer booklet if they choose to continue
6. Both answer booklets linked to the UFM case
7. Student's result for that paper → `WITHHELD` status immediately
8. CoE and Registrar notified immediately (SMS — does not require internet)
9. UFM Committee hearing scheduled automatically (7–14 days, configurable)

**UFM Offence Categories:**

| Category | Examples | Typical Outcome |
|----------|----------|----------------|
| A — Possession only | Material in possession, not used | Paper cancelled; F grade |
| B — Active copying | Copying from another student or material | Paper cancelled + 1 semester debarment |
| C — Impersonation | Someone else writing exam | Full semester cancelled + 2 year debarment |
| D — Disruption / assault | Destroying question paper, assaulting invigilator | Full semester cancelled + possible expulsion |

**UFM Committee Hearing (AI-managed):**
- AI schedules hearing; sends notices to student, invigilator, and committee
- AI assembles case file: incident report, confiscated material records, student
  statement, answer booklets, CCTV request (if applicable)
- Committee records verdict and recommended punishment
- CoE approves recommendation → student notified
- If debarred: status updated across all modules; future exam registrations blocked

**Grievance blackout during exam period (from EC-SS-01):**
During the 48 hours before and during any exam, severity auto-escalation for
invigilator-related complaints is paused. Complaints are received and queued, but no
automatic action is taken until the exam concludes. This prevents a coordinated
grievance attack from removing an invigilator mid-examination.
See `references/edge-cases.md` EC-SS-01.

**Post-session:**
- Attendance reconciliation: AI compares signed attendance sheet (uploaded by
  invigilator) against system records; flags discrepancies
- Script count: invigilator records total scripts collected; AI verifies against
  attendance count

---

## Stage 7 — Answer Script Management

**Purpose:** Maintain a complete, auditable chain of custody for every answer script
from exam hall to evaluation to archival.

### AI Does

**Script tracking system:**
- Each answer booklet has a pre-printed unique barcode generated before exam day
- Barcode links to: student roll number, course, session, hall — all masked at
  evaluation stage for blind evaluation
- After the exam: invigilator scans all collected scripts (or enters count);
  system confirms receipt

**Anonymization for blind evaluation:**
- Student identity masked on the script for end-semester exams
- Evaluators see only: script barcode, course name, answer content
- Student identity revealed only after marks are entered and locked

**Evaluator assignment:**
- AI assigns scripts based on: course expertise (faculty tags from Academic M2),
  faculty NOT from the same department as students (where possible),
  maximum scripts per evaluator (25–40 per course, configurable)
- Evaluators notified of assignment with start date and deadline

**Double evaluation trigger (configurable):**
- All courses above a credit threshold (e.g., all 4+ credit core courses)
- Any script where AI detects high-variance answer pattern
- Any script where two evaluators' marks differ by > 15% of max marks

**Script custody log (auto — no human input):**
- Every scan, assignment, and movement time-stamped and logged
- Lost script: immediate alert to CoE; investigation workflow triggered

### EC-EXM-02 — Damaged Answer Script Barcode (P1 — Sprint 2)

**Trigger:** A physical answer script's barcode is torn or smudged during handling.
Blind evaluation depends on barcode-based anonymization — a manual roll number lookup
would break it and create bias.

**Fix: Damaged Script Triage Queue with dual-authorization override**

```python
class DamagedScriptRecord(BaseModel):
    script_id: UUID                       # system-generated on triage
    exam_session_id: UUID
    original_barcode: str | None          # partially readable barcode if any
    secondary_identifier: str             # pre-printed roll number from cover page header
    reported_by: UUID                     # invigilator ID
    triage_officer: UUID | None           # CoE staff
    coe_authorization: UUID | None        # CoE digital approval
    registrar_authorization: UUID | None  # Registrar digital approval (dual auth)
    re_index_reason: str
    blind_evaluation_preserved: bool      # must be True before assignment
```

**The secondary visual identifier** is a pre-printed roll number on the cover page
header — physically separate from the barcode — that exists specifically for this
scenario. The evaluator receives an anonymized script ID, not the roll number. The
roll-number-to-script-ID mapping is sealed in Vault, accessible only to CoE and
Registrar, revealed only after evaluation is complete.

**Dual authorization rule:** Neither CoE alone nor Registrar alone can complete
re-indexing. Both must digitally approve the `DamagedScriptRecord` before the script
enters the evaluator queue. This is enforced in the Temporal workflow, not just
in application logic.

---

## Stage 8 — Evaluation & Marks Entry

**Purpose:** Evaluate answer scripts, compute scores, and prepare for result
computation. AI assists but never produces final marks.

### AI Does

**Objective / MCQ sections:**
- Auto-graded against the answer key immediately on scan / digital submission
- Score breakdown shown per question
- Anomalies flagged: questions with > 90% wrong answers across all students
  (possible poor question or syllabus mismatch) → notified to CoE for moderation

**Descriptive / essay sections (EC-EXM-05 rules apply — P0):**
- AI scores each answer against the model answer (uploaded by faculty at paper setting)
  and the rubric generated in Academic Module M4
- Per-answer AI output: `ai_draft_score` + `ai_confidence` + justification

**Mandatory rules for AI-assisted descriptive evaluation:**

```python
class AnswerEvaluationRecord(BaseModel):
    script_id: UUID
    question_id: UUID
    max_marks: int
    # AI output — always DRAFT, never final
    ai_draft_score: int | None
    ai_justification: str | None
    ai_confidence: float               # 0.0–1.0
    ai_model_used: str
    ai_evaluated_at: datetime | None
    # Faculty review — this is the only value that flows to result computation
    faculty_final_score: int | None
    faculty_override_reason: str | None  # required if |delta| > 20% of max marks
    faculty_reviewed_at: datetime | None
    faculty_id: UUID | None
    status: Literal["PENDING", "AI_DRAFT", "FACULTY_CONFIRMED", "DISPUTED"]
```

**Four mandatory rules (from EC-EXM-05):**
1. If `ai_confidence < 0.6`: route to faculty **without showing the AI score** —
   prevents anchoring bias. Faculty grades independently first.
2. If `|faculty_final_score - ai_draft_score| > 0.20 × max_marks`:
   `faculty_override_reason` is required (structured dropdown, not free text).
3. If a faculty member confirms > 95% of AI scores without any override across
   a batch: pattern flagged for HOD audit (rubber-stamping signal).
4. Statistical distribution check: if final score distribution for a course
   deviates > 2 standard deviations from the historical mean → flag to CoE
   before result publication.

**`faculty_final_score` is the only value that flows to result computation.**
`ai_draft_score` is never promoted to final without explicit faculty confirmation.

**Marks entry and validation:**
- Marks entered per question (or per section, configurable)
- AI validates: total within maximum, no blank entries, internal total correct
- Auto-totals computed and displayed before submission
- Evaluator submits marks → locked for that script

**Moderation (auto-triggered):**

| Condition | Trigger |
|-----------|---------|
| > 80% of students below 50% in a course | CoE + HOD notified; moderation triggered |
| Mean marks below configured threshold (e.g., 35%) | CoE + HOD notified |
| Double evaluation: marks differ by > 15% | Third evaluator assigned |
| Any student's marks revised post-initial entry | Full audit trail logged; CoE notified |

**Grace marks (configurable by institution policy):**
- AI applies grace marks per the university's configured policy DSL
  (e.g., student within 1–5 marks of passing in ≤ N courses → grace applied)
- Grace is applied by the rules engine — never by the LLM
- `grace_marks_applied = true` and `grace_mark_count` recorded on every affected result
- Grace recipients are excluded from merit computations (see EC-EXM-04 below)

### EC-EXM-05 — AI Evaluation Hallucination (P0 — Sprint 1)

Full implementation spec already embedded above. Key invariant:

> `AnswerEvaluationRecord.ai_draft_score` is DRAFT status only — it is never
> promoted to final without `faculty_final_score` being set.
> This is enforced at the database level via a CHECK constraint:
> `CHECK (status = 'FACULTY_CONFIRMED' IMPLIES faculty_final_score IS NOT NULL)`

### EC-EXM-04 — Grace Mark Merit Contamination (P1 — Sprint 2)

**Trigger:** AI applies a 2-mark grace to push a student past the passing mark.
This fractionally increases their CGPA, displacing another student from the
University Gold Medal who passed without assistance.

**Fix: Policy DSL exclusion rule**

```yaml
# In tenant_policies — merit_list_eligibility
policy_id: "merit_list_eligibility"
rules:
  - id: "grace_mark_exclusion"
    condition: >
      student.grace_marks_applied == true
      AND list_type IN ['gold_medal', 'top_rank', 'scholarship_merit']
    on_match: "EXCLUDED"
    reason_code: "GRACE_MARK_RECIPIENT"
    note: "UGC norms — grace mark recipients excluded from top-1% merit calculations"

  - id: "backlog_exclusion"
    condition: "student.active_backlogs > 0"
    on_match: "EXCLUDED"
    reason_code: "ACTIVE_BACKLOG"
```

This rule is **data-driven and configurable per institution** — it lives in
`tenant_policies`, not in application code. The merit list computation explicitly
passes `list_type` to the policy engine on every evaluation so the exclusion
applies only where appropriate.

### Approver — Faculty Evaluator

- Reviews AI-suggested marks for descriptive sections
- Accepts or overrides; submits final marks for each script

### Approver — CoE (moderation)

- Reviews moderation cases; approves mark revision or scaling

---

## Stage 9 — Result Computation & Publication

**Purpose:** Combine internal marks and end-semester marks, compute grades, compute
SGPA and CGPA, generate grade cards, and publish results.

### AI Does

**Result computation (fully automated once marks are locked):**

**Step 1 — Final marks per course:**
```
Final Marks = Internal Marks (from Academic M8, locked by HOD)
            + End-Semester Marks (from Stage 8, locked by CoE)
```

**Step 2 — Grade assignment (standard UGC 10-point scale, configurable):**

| Marks Range | Letter Grade | Grade Points |
|------------|--------------|--------------|
| 90–100 | O (Outstanding) | 10 |
| 80–89 | A+ (Excellent) | 9 |
| 70–79 | A (Very Good) | 8 |
| 60–69 | B+ (Good) | 7 |
| 50–59 | B (Above Average) | 6 |
| 45–49 | C (Average) | 5 |
| 40–44 | P (Pass) | 4 |
| Below 40 | F (Fail) | 0 |

**Step 3 — SGPA computation:**

```
SGPA = Σ (Grade Points × Credit Hours for each course)
       ─────────────────────────────────────────────────
              Σ (Credit Hours for all courses)

Example:
  Data Structures  (4 credits, Grade A  = 8 pts): 4 × 8  = 32
  DBMS             (3 credits, Grade B+ = 7 pts): 3 × 7  = 21
  Maths            (4 credits, Grade O  = 10 pts): 4 × 10 = 40
  Total grade points = 93 | Total credits = 11
  SGPA = 93 / 11 = 8.45
```

**Step 4 — CGPA computation (cumulative, updated every semester):**

```
CGPA = Σ (SGPA × Total Credits for that semester, across all semesters)
       ───────────────────────────────────────────────────────────────────
                     Σ (Total Credits across all semesters)
```

**Step 5 — Pass / fail / backlog determination:**
- Pass: marks ≥ passing threshold in both internal and external components
- Fail in internal + pass in external = overall fail (configurable)
- Grace marks applied per rules engine policy before this determination

**Step 6 — Grade card pre-generation:**
Grade card PDFs are generated and stored in MinIO **before** the Registrar
approval gate. The approval step releases pre-built PDFs, not real-time renders.
This is mandatory for result day load handling (2,000 concurrent users target).

**Grade card PDF contents:**
- University header + security features (watermark, serial number, QR code)
- Student details (name, roll no., program, semester, academic year)
- Table: Course code | Course name | Credits | Internal marks | External marks |
  Total | Grade | Grade Points
- SGPA for this semester
- CGPA to date (updated)
- Result status: PASS / PASS WITH BACKLOG / FAIL
- Grace mark notation: "G" next to any grade where grace was applied
- Digital signature of CoE + Registrar (applied at approval time)

### Result Publication Embargo

Results are computed and grade cards pre-generated before the Registrar approves.
No student can see results before the Registrar approves, even if computation is
complete. The approval action:
1. Signs the pre-generated PDFs with CoE + Registrar digital signatures
2. Updates the publication timestamp in the database
3. Makes PDFs accessible to students (served from MinIO pre-signed URLs)
4. Fires the `result.published` domain event to all downstream consumers

**Domain event:** `result.published` → consumed by Student Services (progression),
Academics, Regulatory E14 (pass %, SGPA distribution), Alumni E12 (transition).

### Approver — Registrar

- Reviews auto-generated results summary (statistics: pass %, distinction %,
  mean CGPA per batch)
- Reviews exception list: withheld results (UFM pending), moderation flags, outliers
- Approves → grade cards signed, results published to student portal,
  parents notified via WhatsApp + Email

---

## Stage 10 — Revaluation & Rechecking

**Purpose:** Structured process for students to challenge end-semester marks.
Three tiers: rechecking, revaluation, photocopy request.

### The Three Tiers

| Tier | What It Is | Who Does It | Outcome |
|------|-----------|-------------|---------|
| **Rechecking** | Verify totaling only — no re-reading of content | Exam Cell staff | Marks correction if totaling error found |
| **Revaluation** | Full re-evaluation by a second examiner | Different faculty evaluator | Marks may go up or down |
| **Photocopy / Scanned Copy** | Student receives copy of evaluated script | System (automated) | Student uses to decide on revaluation |

### AI-Managed Workflow

```
Result published
      │
      ▼
Revaluation window opens (configurable: 7–15 days after result)
      │
Student applies via portal:
  ├── Selects tier (Rechecking / Revaluation / Photocopy)
  ├── Selects subjects (max 2 for revaluation, all for rechecking — configurable)
  └── Pays fee (Razorpay; fee per subject, configurable)
      │
      ├── PHOTOCOPY REQUEST
      │     AI retrieves digitized script → masks evaluator identity
      │     → delivers to student portal within 24 hours
      │     Student has 5 days to review and decide on revaluation
      │
      ├── RECHECKING
      │     Exam Cell reviews: all questions evaluated? totaling correct?
      │     If error: marks corrected, grade card updated, student notified
      │     If no error: original marks stand, student notified
      │
      └── REVALUATION (EC-EXM-03 governs if supplementary is also open)
            AI assigns to second evaluator (not original; not from student's department)
            Evaluator re-evaluates the full script fresh
            AI compares original vs. revaluation marks:
              ├── Difference ≤ 15% of max marks → original stands
              ├── Difference > 15% of max marks → average of original + revaluation
              └── Result changes (pass ↔ fail) → new marks always applied
            Updated grade card generated (original archived, not deleted)
            If result improves to PASS: backlog cleared, SGPA/CGPA updated
```

**Important rules enforced by system:**
- Revaluation not allowed for: practical exams, viva-voce, project reports, IA
- Revaluation window is hard-closed; no extensions except CoE approval
- Merit list and gold medal rankings not affected by revaluation
- Student accepts risk of adverse result at application time (disclosed in portal)

### EC-EXM-03 — Revaluation vs. Supplementary Overlap (P1 — Sprint 2)

**Trigger:** Student fails a course and applies for revaluation. The supplementary
registration window opens before the revaluation result is published. System demands
a re-appear fee. If revaluation passes, the system now has two competing active
workflows for the same course.

**What breaks:** Double-charging. Workflow conflict between `REVALUATION_PENDING`
and `SUPPLEMENTARY_REGISTERED`. If revaluation passes, both refund and annulment are
needed — complex multi-step processes with no clean resolution in the naive design.

**Fix: Escrow state for supplementary fee**

```python
class CourseAttemptStatus(str, Enum):
    ENROLLED                          = "enrolled"
    FAILED                            = "failed"
    REVALUATION_PENDING               = "revaluation_pending"
    SUPPLEMENTARY_REGISTERED_CONDITIONAL = "supplementary_registered_conditional"
    SUPPLEMENTARY_REGISTERED_CONFIRMED   = "supplementary_registered_confirmed"
    REVALUATION_PASSED                = "revaluation_passed"
    SUPPLEMENTARY_APPEARED            = "supplementary_appeared"

@workflow.defn
class RevaluationSupplementaryResolverWorkflow:
    @workflow.run
    async def run(self, student_id: str, course_id: str, tenant_id: str):
        # Allow conditional registration — fee held in escrow, not posted to revenue
        await workflow.execute_activity(
            register_supplementary_conditional,
            args=[student_id, course_id, tenant_id]
        )

        # Wait for revaluation result OR supplementary exam date — whichever first
        result_signal = await workflow.wait_for_signal(
            "revaluation_result_published",
            timeout=timedelta(days=30)
        )

        if result_signal.passed:
            # Revaluation passed — annul supply registration, refund escrow fee
            await workflow.execute_activity(
                annul_supplementary_and_refund,
                args=[student_id, course_id, tenant_id]
            )
        else:
            # Revaluation failed — confirm supply registration, release escrow to college
            await workflow.execute_activity(
                confirm_supplementary_registration,
                args=[student_id, course_id, tenant_id]
            )
```

The escrow ledger entry is tagged `SUPPLEMENTARY_FEE_ESCROW` and excluded from
daily revenue reconciliation until released. Student portal shows clear status:
"Your revaluation result will be published by [date]. Your supplementary registration
is conditionally held."

---

## Stage 11 — Supplementary / Re-appear Examination

**Purpose:** Students who fail one or more courses are given the opportunity to
clear them in a supplementary exam.

### AI Does

**Eligibility identification (auto, on main result publication):**
- Scans all results; generates supplementary eligible list: students with F grade
- Per student: courses to clear, internal marks carried forward, fee payable
- Eligible students notified immediately on main result day with registration window

**Supplementary registration:**
- Pre-filled by AI; student confirms. Internal marks carried forward automatically.
- Student only appears for end-semester component (internal marks locked from main exam)

**All subsequent stages repeat identically:** Stages 2 through 9 apply, with
two differences:
1. Question paper drawn from question bank for supplementary (original paper may
   have been circulated), not from the original encrypted paper
2. Grade card notation: `P*` or `SB` or `PASS(S)` to indicate cleared via
   supplementary (configurable notation per institution)

**Backlog tracking (continuous):**
- AI maintains a live backlog register per student: courses with F grade,
  attempts taken, attempts remaining (max attempts configurable)
- If student exhausts maximum attempts in a course: AI flags for academic committee
  review; detention or program exit policy applied per institution rules

### Approver — Registrar

- Approves supplementary exam schedule
- Approves supplementary results before publication

---

## Stage 12 — Transcript & Score Card Generation

**Purpose:** Generate all official academic records: semester grade cards,
consolidated transcripts, score cards for placement, and final degree transcripts.

### Document Types, Triggers, and AI Assembly

**1. Semester Grade Card**
- Trigger: Result published (Stage 9) — pre-generated at that time
- Auto-released, no approval for initial download
- Digital signature: CoE + Registrar (applied at publication)

**2. Consolidated Marksheet (unofficial)**
- Trigger: Student request from portal
- AI compiles all semester grade cards into one document
- Available within 24 hours of request. No approval required.

**3. Official Transcript**
- Trigger: Student request (higher studies, employment, transfer)
- AI assembles: all semesters, all courses, all grades, SGPA per semester, final CGPA,
  program details, medium of instruction, certification statement
- Format: Association of Indian Universities (AIU) standard format
- Security: AI-generated unique document ID, QR code for online verification,
  university seal embedded
- Approval: Registrar (reviews and digitally signs)
- SLA: 3–5 working days (configurable)
- Delivery: sealed PDF (tamper-evident) + physical copy on request

**4. Score Card / Provisional Certificate**
- Trigger: Student request (placement, competitive exams)
- Contents: name, roll number, program, current CGPA, total credits, expected
  graduation date
- Available immediately; no manual approval required

**5. Degree Transcript (Final)**
- Trigger: Degree audit cleared (all credits, no pending backlogs, all dues cleared,
  disciplinary clearance, OBE graduation requirements where applicable)
- AI sends clearance requests to: Library, Hostel, Finance, Exam Cell, Student Affairs
- On all clearances received: degree transcript generated
- Approval: Registrar + Vice-Chancellor (digital signatures)
- Issued once; replacement requires "DUPLICATE" notation and Registrar approval

**6. Verified Grade Card (for competitive exam use)**
- Trigger: Student request with specific exam name
- Enhanced security features + covering letter
- Approved and dispatched by Registrar

**Online verification (built-in):**
- Every official document has a unique QR code + verification URL
- Third parties scan QR → system confirms: authenticity, key data, graduation year
- No personal data exposed in the verification response — only confirmation + document ID

### Approver — Registrar

- Official transcripts: reviews, digitally signs, approves dispatch
- Degree transcript: reviews, digitally signs, forwards to VC for countersignature
- All other documents: auto-approved and dispatched on request

---

## Complete Examination Module Flow

```
[ACADEMIC MODULE] ──► internal marks locked + attendance final
[ADMISSIONS MODULE] ──► student photo, personal data
[FINANCE MODULE] ──► student_dues_status read model (queried at hall ticket time)
                              │
          ┌───────────────────┴─────────────────────┐
          │           EXAMINATION MODULE             │
          └───────────────────┬─────────────────────┘
                              │
   Stage 1: Eligibility  ─────►  CoE approves eligible list
            └── Dues gate: read model query (not event-only)
                              │
   Stage 2: Exam Schedule ────►  CoE approves timetable
                              │
   Stage 3: Question Papers ──►  CoE locks + encrypts (Vault)
            EC-EXM-01: Offline USB fallback if network fails
                              │
   Stage 4: Hall Tickets  ────►  CoE approves batch release
            └── Re-queries dues read model at generation
                              │
   Stage 5: Seating + Invig. ─►  CoE approves arrangement
                              │
   ══════════ EXAM DAY ═══════════════════════════════
                              │
   Stage 6: Conduct + Attend.  ─►  Invigilator marks attendance
            └── UFM → CoE + Committee
            └── Grievance blackout for invigilator complaints (EC-SS-01)
                              │
   Stage 7: Script Management ─►  CoE tracks custody
            EC-EXM-02: Damaged barcode → dual-auth triage
                              │
   Stage 8: Evaluation  ──────►  Faculty evaluator reviews AI DRAFT scores
            EC-EXM-05: Confidence < 0.6 → AI score hidden
            EC-EXM-04: Grace marks → merit exclusion policy
            └── CoE approves moderation
   Stage 9: Results (pre-generated) ──► Registrar approves + signs
            └── WhatsApp + Email + Portal notification
            └── result.published event → downstream consumers
                              │
   ══════════ POST-RESULT ════════════════════════════
                              │
   Stage 10: Revaluation  ────►  CoE approves processing
            EC-EXM-03: Reval + Supply overlap → escrow workflow
            └── Registrar approves revised cards
   Stage 11: Supplementary ───►  Full cycle repeats
                              │
   Stage 12: Transcripts  ────►  Registrar signs + dispatches
            └── QR-verifiable documents
```

---

## Status States (Per Student, Per Course)

| Status | Meaning |
|--------|---------|
| `EXAM_NOT_REGISTERED` | Registration window open; student has not registered |
| `REGISTRATION_PENDING_PAYMENT` | Registered; exam fee not paid |
| `INELIGIBLE: ATTENDANCE` | Attendance below threshold |
| `INELIGIBLE: DUES` | Outstanding balance per read model |
| `INELIGIBLE: DISCIPLINARY_HOLD` | Active case |
| `CONDONATION_PENDING` | Attendance 65–74%; awaiting CoE decision |
| `ELIGIBLE` | Cleared all checks |
| `HALL_TICKET_GENERATED` | Hall ticket available for download |
| `APPEARED` | Present in exam session |
| `ABSENT` | Did not appear |
| `RESULT_WITHHELD: UFM` | Malpractice case pending |
| `RESULT_WITHHELD: MODERATION` | Marks under moderation |
| `PASS` | Cleared the course |
| `FAIL` | Below threshold; backlog registered |
| `PASS (GRACE)` | Passed after grace mark application; excluded from merit lists |
| `REVALUATION_APPLIED` | Student applied for revaluation |
| `REVALUATION_COMPLETE` | Revaluation done; marks updated or unchanged |
| `SUPPLEMENTARY_ELIGIBLE` | Eligible for supplementary exam |
| `SUPPLEMENTARY_REGISTERED_CONDITIONAL` | Registered while revaluation pending; fee in escrow |
| `SUPPLEMENTARY_REGISTERED_CONFIRMED` | Revaluation failed; supply confirmed |
| `PASS_SUPPLEMENTARY` | Cleared via supplementary |
| `MAX_ATTEMPTS_EXHAUSTED` | Reached maximum allowed attempts |
| `DEBARRED: UFM` | Debarred for specified period |

---

## Domain Events — Fired and Consumed

**Fired by Examination module:**

| Event | Consumed By | Payload |
|-------|-------------|---------|
| `exam.eligibility_confirmed` | Student portal, Academic module | student_id, eligible_courses, ineligible_courses |
| `hall_ticket.generated` | Student portal | student_id, semester, download_url |
| `result.published` | Student Services, Academics, Alumni E12, Regulatory E14 | batch_id, semester, pass_pct, mean_sgpa |
| `result.final_published` | Alumni transition saga | student_id, final_cgpa, graduation_verified |
| `result.withheld: UFM` | Student portal, CoE dashboard | student_id, course_id, ufm_case_id |
| `revaluation.result_ready` | RevaluationSupplementaryResolverWorkflow | student_id, course_id, new_marks, status_change |
| `supplementary.eligible` | Student portal | student_id, courses, registration_window |

**Consumed by Examination module:**

| Event | Source | Action |
|-------|--------|--------|
| `exam_block.start` | Academic Calendar | Initiate eligibility run |
| `internal_marks.locked` | Academic M8 | Enable combined result computation |
| `attendance.semester_final` | Academic M6 | Finalize attendance eligibility |
| `student.dues_cleared` | Finance | Trigger dues read model re-query |
| `grievance.invigilator_complaint` | Student Services | Activate exam period blackout check |

---

## Notification Map

| Event | Student | Faculty / Invigilator | CoE / Registrar | Parent |
|-------|---------|----------------------|-----------------|--------|
| Exam registration window opens | Email + SMS + WhatsApp | — | — | — |
| Registration deadline T-3, T-1 | SMS | — | — | — |
| Ineligible determination | Email + Portal | — | Summary report | Email |
| Condonation approved / rejected | Email + Portal | — | — | Email |
| Hall ticket available | Email + SMS + WhatsApp + Portal | — | — | — |
| Exam schedule published | Email + Portal | Email (duty chart) | — | — |
| UFM case filed | Email + Portal | Email (invigilator) | Immediate SMS alert | Email + SMS |
| UFM verdict | Email + Portal | — | — | Email |
| Results published | Email + SMS + WhatsApp + Portal | — | — | Email |
| Revaluation window opens | Email + Portal | — | — | — |
| Revaluation complete | Email + Portal | — | Email (if marks change) | — |
| Supplementary eligibility | Email + SMS + WhatsApp + Portal | — | — | Email |
| Supplementary results | Email + Portal | — | — | Email |
| Backlog cleared | Email + Portal | Email (mentor) | — | Email |
| Transcript / document ready | Email + Portal | — | — | — |
| Degree audit cleared | Email + Portal | — | Email | Email |

---

## SLA Defaults

| Process | SLA | If Breached |
|---------|-----|-------------|
| Question paper submission by faculty | 21 days before exam | Escalates to HOD → CoE |
| Eligibility list approval (CoE) | 10 days before exam | Escalates to Registrar |
| Hall ticket release to students | 7 days before first exam | CoE notified |
| Script assignment to evaluators | 3 days after exam session | CoE notified |
| Marks entry by evaluator | 10 days after exam | CoE escalates to HOD |
| Result computation after marks locked | Same day (automated) | — |
| Result publication | Per academic calendar | Registrar accountability |
| Revaluation processing window | 21–30 days | CoE accountability |
| Transcript (official) delivery | 3–5 working days | Student notified of delay |
| Degree audit completion | 15 days before convocation | Registrar accountability |
| UFM Committee hearing | 7–14 days after incident | CoE escalates to Dean |

**All SLA timers use absolute deadline timestamps stored at task creation.**
Never compute `sleep(timedelta)` in Temporal workflows.
See EC-CROSS-04 in `references/edge-cases.md`.

---

## What Actors Never Do (AI Handles Completely)

- Run eligibility checks or compute attendance thresholds
- Generate exam registration forms
- Build the exam timetable or check for student schedule conflicts
- Encrypt or decrypt question papers (system + Vault managed)
- Generate, populate, or deliver hall tickets
- Compute seating arrangements or assign seats
- Build the invigilation duty chart
- Auto-grade objective sections
- Compute SGPA or CGPA
- Generate grade cards, transcripts, or score cards
- Open or close the revaluation window
- Identify supplementary-eligible students
- Send any routine notification, reminder, or deadline alert
- Track script chain of custody
- Assemble clearance requests for degree audit
- Pre-generate grade card PDFs before result publication

---

## Configuration Parameters

| Parameter | Common Values | Configurable |
|-----------|--------------|-------------|
| Minimum attendance for eligibility | 75% (AICTE default) | Yes |
| Condonation range | 65–74% with valid reason | Yes |
| Internal vs. external marks split | 40:60, 50:50, 30:70 | Yes |
| Exam duration by credit | 2h (3-credit), 2.5h (4-credit), 3h (5-credit) | Yes |
| Grading scale | UGC 10-point or 7-point | Yes |
| Grace marks rule | 1–5 marks, ≤ 2 courses | Yes |
| Grace mark merit exclusion | Always applied to gold_medal, top_rank, scholarship_merit | Not configurable |
| Revaluation fee | ₹300–₹500 per subject | Yes |
| Revaluation marks rule | <15% diff → original; >15% → average | Yes |
| Maximum supplementary attempts | 2–4 per course | Yes |
| Revaluation window | 7–15 days after result | Yes |
| Double evaluation threshold | >15% difference between two evaluators | Yes |
| Scripts per evaluator | 25–40 per course | Yes |
| Supplementary grade notation | P* / SB / PASS(S) | Yes |
| AI confidence threshold (hide from evaluator) | 0.60 | Yes |
| AI override reason required (deviation) | > 20% of max marks | Yes |
| Rubber-stamping audit flag threshold | > 95% AI confirmation rate | Yes |
| Offline Vault fallback | `examinations.offline_fallback_enabled` | Yes (must be true for live) |
| Grievance blackout during exam | 48 hours before + during each exam | Yes |

---

*Document version: 2.0 | March 2026*
*Connected to: admissions_workflow.md → academic_operations_workflow.md →*
*examination_workflow.md → student_services_workflow.md → finance_workflow.md →*
*hr_payroll_workflow.md → regulatory_accreditation_workflow.md*
*Full student lifecycle: Lead Captured → Graduated*
*QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential*
