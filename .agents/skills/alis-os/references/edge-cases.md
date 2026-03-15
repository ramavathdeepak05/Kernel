# ALIS OS — Edge Cases, Failure Modes & Architectural Fixes
## Engineering Reference Document v1.0
### QUAICU Pvt. Ltd. | Confidential

---

## How to Read This Document

Every edge case entry follows a consistent structure:

- **Trigger** — what causes this to happen in production
- **What breaks** — the exact system failure and downstream consequences
- **Architectural fix** — the code-level or schema-level solution
- **Implementation notes** — specific guidance for the ALIS Python/FastAPI stack

Severity ratings: **P0** (data loss / regulatory breach) | **P1** (user-facing failure) | **P2** (operational friction)

---

# Module E04 — Admissions

---

## EC-ADM-01 | Identity Mismatch Across Documents
**Severity: P1**

**Trigger:** A student's name appears differently across their 10th marksheet ("Sai Kumar Reddy"), Aadhaar ("K. Sai Kumar"), and JEE scorecard ("Sai K Reddy"). The automated eligibility rules engine flags the application as fraudulent or incomplete.

**What breaks:** The application stalls in `ELIGIBILITY_SCREENING` state. The student has no self-service resolution path. Admissions staff have no structured way to log the reconciliation decision. The audit trail is blank.

**Architectural fix:**

Add a `name_variants` JSONB column to the `applications` table and a `KYC_RECONCILIATION` sub-state to the state machine.

```sql
ALTER TABLE applications
  ADD COLUMN name_variants JSONB DEFAULT '[]',
  ADD COLUMN kyc_status TEXT DEFAULT 'PENDING'
    CHECK (kyc_status IN ('PENDING','RECONCILED','FLAGGED','REJECTED'));

-- name_variants stores each document's name independently
-- e.g. [{"source": "10th", "name": "Sai Kumar Reddy"}, ...]
```

The rules engine must compute a **fuzzy name similarity score** (Jaro-Winkler, threshold ≥ 0.85) across all document names before raising a hard flag. Only scores below threshold route to the KYC reconciliation HITL queue.

```python
from jellyfish import jaro_winkler_similarity

def evaluate_name_consistency(names: list[str]) -> tuple[bool, float]:
    scores = []
    for i, a in enumerate(names):
        for b in names[i+1:]:
            scores.append(jaro_winkler_similarity(a.lower(), b.lower()))
    min_score = min(scores) if scores else 1.0
    return (min_score >= 0.85), min_score
```

**Implementation notes:**
- Aadhaar eKYC API returns the canonical name — use this as the ground truth when available.
- The reconciliation HITL task must store the officer's resolution reason in `audit_ledger` with `policy_version`.
- After reconciliation, the `kyc_status` transitions to `RECONCILED` and normal eligibility evaluation resumes.

---

## EC-ADM-02 | State Counseling Late Joiners
**Severity: P1**

**Trigger:** State quota admissions (EAMCET, KCET, OJEE) complete 6–10 weeks after the management quota batch starts classes. Late joiners arrive mid-semester with no timetable, no LMS access, and no mentor.

**What breaks:** The Academic module has already generated and locked the timetable, attendance sessions, and course content for the main batch. A new `student.enrolled` event for a late joiner would trigger the full academic initialization pipeline, which cannot generate a working schedule for a partially-elapsed semester.

**Architectural fix:**

Add `PROVISIONAL` and `LATE_JOINER` enrollment states. The `student.enrolled` event payload must carry an `enrollment_type` field.

```python
class EnrollmentType(str, Enum):
    STANDARD = "standard"
    PROVISIONAL = "provisional"      # seat confirmed, KYC pending
    LATE_JOINER = "late_joiner"      # joining after semester start
    LATERAL_ENTRY = "lateral_entry"  # direct 2nd year admission

class StudentEnrolledPayload(BaseModel):
    # ... existing fields ...
    enrollment_type: EnrollmentType = EnrollmentType.STANDARD
    joining_date: date
    semester_start_date: date        # the date the main batch started
    catch_up_required: bool          # computed: joining_date > semester_start_date + 7 days
```

The Academic module's `handle_student_enrolled` handler checks `catch_up_required`. If true, it triggers the **Catch-Up Cohort** workflow instead of standard initialization:

```python
async def handle_student_enrolled(event: DomainEvent):
    payload = StudentEnrolledPayload(**event.payload)

    if payload.catch_up_required:
        await temporal_client.start_workflow(
            CatchUpCohortWorkflow,
            args=[payload, event.tenant_id],
            id=f"catchup-{payload.student_id}",
        )
        return

    # Standard initialization path
    await standard_academic_init(payload, event.tenant_id)
```

The `CatchUpCohortWorkflow` in Temporal:
1. Calculates elapsed teaching weeks from `semester_start_date` to `joining_date`.
2. Generates a compressed assignment schedule: all past-due assignments get a single consolidated deadline 2 weeks from joining.
3. Creates attendance sessions only from joining date onward. Past sessions are pre-marked `EXCUSED_LATE_JOINER` — not absent.
4. Assigns mentor and generates LMS access identically to the standard path.
5. Does NOT regenerate the timetable — inserts the student into existing sections.

**Implementation notes:**
- The `EXCUSED_LATE_JOINER` attendance status must be excluded from the eligibility percentage denominator.
- The NAAC evidence engine (E14) must handle late joiners correctly in enrollment count snapshots.

---

## EC-ADM-03 | Ghost Withdrawal — Seat Occupied by Absent Student
**Severity: P0**

**Trigger:** A student pays the confirmation fee, receives a roll number, LMS access, and hostel room, then silently joins another institution. They never respond to any communication. The seat shows as occupied; waitlisted students are never called.

**What breaks:** Seat counter is wrong. Waitlist is never activated. Revenue is potentially lost if the confirmation fee doesn't cover the seat cost. On Day 7, there is no automated mechanism to detect the no-show.

**Architectural fix:**

Implement a **Physical Reporting Gate** — the enrollment state machine has a mandatory `REPORTING_PENDING` state that blocks full `ENROLLED` status until biometric capture on campus.

```sql
-- New status in the enrollment state machine
-- SEAT_CONFIRMED → REPORTING_PENDING → ENROLLED
-- SEAT_CONFIRMED → REPORTING_PENDING → SEAT_FORFEITED (on SLA breach)

CREATE TABLE reporting_gate_log (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id     UUID NOT NULL,
    student_id    UUID NOT NULL,
    roll_number   TEXT NOT NULL,
    reporting_sla TIMESTAMPTZ NOT NULL,  -- seat_confirmed_at + 7 days
    reported_at   TIMESTAMPTZ,
    biometric_ref TEXT,                  -- fingerprint/face capture reference ID
    forfeited_at  TIMESTAMPTZ,
    forfeiture_reason TEXT
);
```

A Temporal workflow monitors the SLA:

```python
@workflow.defn
class ReportingGateWorkflow:
    @workflow.run
    async def run(self, student_id: str, tenant_id: str, sla: datetime):
        try:
            # Wait for biometric signal OR SLA expiry
            await workflow.wait_for_signal(
                "biometric_captured",
                timeout=sla - datetime.utcnow()
            )
            # Student reported — transition to ENROLLED
            await workflow.execute_activity(
                confirm_full_enrollment, args=[student_id, tenant_id]
            )
        except asyncio.TimeoutError:
            # SLA breached — send forfeiture warning
            await workflow.execute_activity(
                send_forfeiture_warning, args=[student_id, tenant_id]
            )
            # 48-hour grace period
            try:
                await workflow.wait_for_signal("biometric_captured", timeout=timedelta(hours=48))
                await workflow.execute_activity(confirm_full_enrollment, args=[student_id, tenant_id])
            except asyncio.TimeoutError:
                # Forfeit seat and release to waitlist
                await workflow.execute_activity(
                    forfeit_seat_and_activate_waitlist, args=[student_id, tenant_id]
                )
```

**Implementation notes:**
- Until `ENROLLED`, LMS access is read-only. Hostel room is reserved but not physically assignable.
- Roll number is generated at `SEAT_CONFIRMED` for operational reasons but marked `PROVISIONAL` in the student record header.
- Biometric capture can be replaced by a QR-scan at the admission desk if biometric hardware is unavailable — configurable per institution via feature flag `admissions.biometric_reporting_gate`.

---

## EC-ADM-04 | Forged Document — OCR Passes, Document is Fake
**Severity: P0**

**Trigger:** A high-quality forged 12th marksheet passes all automated format checks (correct DPI, correct layout, plausible percentage). The system auto-approves eligibility. The fraud is discovered at Stage 9 final verification.

**What breaks:** If discovered post-enrollment, the institution has a legal liability. The audit trail shows the system approved the document, creating ambiguity about institutional culpability.

**Architectural fix:**

Every document approval must log the verification method used. OCR-only approval is never sufficient for academic certificates. Implement a **three-tier verification hierarchy**:

```python
class DocumentVerificationMethod(str, Enum):
    OCR_FORMAT_ONLY = "ocr_format"        # automated, low confidence
    DIGILOCKER_API = "digilocker_api"     # automated, high confidence
    BOARD_API = "board_api"               # automated, high confidence (CBSE/state board APIs)
    MANUAL_OFFICER = "manual_officer"     # human verification
    MANUAL_FORENSIC = "manual_forensic"  # flagged for deeper scrutiny

class DocumentVerificationRecord(BaseModel):
    document_id: UUID
    method: DocumentVerificationMethod
    confidence_score: float              # 0.0–1.0
    verified_by: UUID | None             # officer ID if manual
    api_reference: str | None            # DigiLocker/board API reference
    flags: list[str]                     # anomaly flags raised
    approved: bool
    approved_at: datetime
    policy_version: str                  # rules engine version at time of approval
```

**Hard rule:** `ACADEMIC_CERTIFICATE` category documents (10th, 12th, UG degree) MUST be verified by DigiLocker API or Board API. OCR-only approval sets `confidence_score < 0.5` and routes to `MANUAL_FORENSIC` regardless of format correctness. This is enforced in the rules engine policy, not in application code.

**Additional anomaly signals to flag automatically:**
- Document parses perfectly but DigiLocker API returns no matching record → `POTENTIAL_FORGERY`
- Percentage on document is suspiciously round (exactly 60.0%, 75.0%) → `STATISTICAL_ANOMALY`
- Document metadata (PDF creation date) is newer than the document's issue date → `METADATA_MISMATCH`
- Re-upload count exceeds 2 for the same document type → `EXCESSIVE_REUPLOAD`

---

## EC-ADM-05 | Razorpay Webhook Drop on Fee Payment
**Severity: P0**

**Trigger:** A student pays the semester/confirmation fee on the deadline day. The payment leaves their bank account, but the Razorpay webhook to ALIS fails (network timeout, server restart, queue overflow). The ALIS ledger shows `UNPAID`. The Exam module blocks the hall ticket.

**What breaks:** Student has paid but is marked defaulter. Exam access is blocked. Student has no self-service resolution. Finance staff have no structured tool to resolve without risk of double-posting.

**Architectural fix:**

Implement a **Payment Dispute / UTR Reconciliation Portal** with a 48-hour temporary restriction lift:

```python
class PaymentDisputeWorkflow:
    """
    Temporal workflow triggered when student submits UTR number.
    Runs a gateway reconciliation check independent of webhook.
    """
    @workflow.run
    async def run(self, dispute: PaymentDisputeRequest):
        # Step 1: Temporarily lift exam/portal restriction for 48h
        await workflow.execute_activity(
            lift_restriction_temporarily,
            args=[dispute.student_id, dispute.tenant_id, timedelta(hours=48)]
        )

        # Step 2: Query Razorpay API directly with UTR/order_id
        payment = await workflow.execute_activity(
            query_razorpay_by_utr,
            args=[dispute.utr_number, dispute.order_id]
        )

        if payment.status == "captured":
            # Payment confirmed — post to ledger, make permanent
            await workflow.execute_activity(
                post_payment_to_ledger,
                args=[payment, dispute.student_id, dispute.tenant_id]
            )
            await workflow.execute_activity(
                lift_restriction_permanently,
                args=[dispute.student_id, dispute.tenant_id]
            )
        else:
            # Payment not found — restore restriction after 48h, alert Finance
            await workflow.sleep(timedelta(hours=48))
            await workflow.execute_activity(
                restore_restriction_with_finance_alert,
                args=[dispute.student_id, dispute.tenant_id]
            )
```

**Additionally:** The Razorpay integration must implement **idempotent webhook processing** with a `payment_webhook_log` table. Before processing any webhook, the system checks if this `razorpay_payment_id` has already been processed. On startup, ALIS replays any unprocessed webhooks from the last 24 hours by polling the Razorpay API — this is the standard reconciliation safety net.

---

# Module E05 — Academic Operations

---

## EC-ACA-01 | Global Campus Disruption — Bandh / Flood / Power Failure
**Severity: P1**

**Trigger:** A state bandh, unexpected flooding, or 2-day power grid failure forces campus closure. The timetable has 40+ sessions across the next 2 days already created, attendance sessions are pre-generated, and assignment deadlines are imminent.

**What breaks:** Every pre-generated session becomes an unexcused absence for every student. Assignment auto-submission portals close. Deadline counters keep running. If manual intervention is needed for every session and deadline, the admin overhead is enormous.

**Architectural fix:**

Implement a **Global Recalibration Trigger** — a single Registrar-initiated command that cascades atomically.

```python
class RecalibrationScope(str, Enum):
    INSTITUTION_WIDE = "institution_wide"
    DEPARTMENT = "department"
    PROGRAM = "program"
    SECTION = "section"

class GlobalRecalibrationRequest(BaseModel):
    tenant_id: UUID
    scope: RecalibrationScope
    scope_ref: UUID | None          # department/program/section ID if scoped
    disruption_type: str            # 'bandh' | 'flood' | 'power' | 'other'
    disruption_start: date
    disruption_end: date
    shift_days: int                 # calendar days to push everything forward
    initiated_by: UUID              # must be Registrar role
    reason: str                     # mandatory reason log for audit

@workflow.defn
class GlobalRecalibrationWorkflow:
    @workflow.run
    async def run(self, req: GlobalRecalibrationRequest):
        # 1. Mark all sessions in disruption window as EXCUSED_DISRUPTION
        await workflow.execute_activity(mark_sessions_excused, args=[req])

        # 2. Shift all future deadlines forward by shift_days
        await workflow.execute_activity(shift_deadlines, args=[req])

        # 3. Re-run constraint solver on the shifted calendar
        await workflow.execute_activity(rerun_timetable_solver, args=[req])

        # 4. Notify all affected parties
        await workflow.execute_activity(notify_disruption, args=[req])

        # 5. Write immutable audit entry
        await workflow.execute_activity(audit_recalibration, args=[req])
```

The `EXCUSED_DISRUPTION` attendance status is excluded from the eligibility percentage denominator — identical treatment to `EXCUSED_LATE_JOINER`. This must be enforced in the rules engine policy `attendance_eligibility`, not in application code.

**Implementation notes:**
- The constraint solver re-run is computationally expensive. Run it as a background Celery task with `ai_tasks` queue priority.
- The Registrar confirmation screen must show a preview: "This will shift 847 sessions and 234 deadlines. 3 exam dates fall within a pre-locked window and will require manual resolution." The 3 conflicts are shown explicitly before the Registrar confirms.
- Pre-locked exam dates (CoE-approved exam schedule) are immovable by the recalibration trigger. The solver flags conflicts but does not override them.

---

## EC-ACA-02 | Faculty Attrition Mid-Semester
**Severity: P1**

**Trigger:** A faculty member resigns unexpectedly in week 6 of a 16-week semester. They own 3 courses. AI has already generated course outlines, PPTs, IA papers, rubrics, and mapped learning outcomes to their profile.

**What breaks:** 3 courses are suddenly `INSTRUCTOR_MISSING`. The timetable has their sessions for the next 10 weeks. The LMS course shells are owned by their account. IA papers approved by them are scheduled for auto-release.

**Architectural fix:**

Implement a **Course Handover Workflow** triggered by the `employee.separation_initiated` event.

```python
class CourseHandoverPackage(BaseModel):
    """Snapshot of course state at handover moment."""
    course_id: UUID
    outgoing_faculty_id: UUID
    incoming_faculty_id: UUID | None     # None if replacement not yet found
    handover_date: date
    # Syllabus state
    completed_units: list[str]           # units marked DELIVERED
    remaining_units: list[str]           # units not yet delivered
    weeks_remaining: int
    # Assessment state
    pending_ia_papers: list[UUID]        # approved but not yet auto-released
    pending_grading: list[UUID]          # submitted but not yet evaluated
    pending_assignments: list[UUID]      # student submissions pending feedback
    # Materials
    approved_ppts: list[UUID]            # slide decks approved by outgoing faculty
    question_bank_entries: list[UUID]    # questions added by this faculty
```

The handover workflow:
1. Creates the `CourseHandoverPackage` snapshot — point-in-time state of every course.
2. Transitions all 3 courses to `INSTRUCTOR_MISSING` state — visible to HOD dashboard.
3. Transfers LMS course shell ownership to HOD as temporary custodian.
4. Freezes all pending IA paper auto-releases until incoming faculty approves them.
5. Assigns a temporary substitute for the timetable (HOD's responsibility within 48h SLA).
6. When incoming faculty is assigned (`incoming_faculty_id` populated), sends them the handover package and queues a review task for pending materials.

**For the emergency notice period buyout scenario** (faculty wants to leave tomorrow):
- `EmergencySeperationOverride` flag bypasses the 90-day workflow.
- Triggers `CRITICAL_VACANCY` alert to HOD and Dean immediately.
- All timetable sessions for next 2 weeks are flagged `SUBSTITUTE_REQUIRED` in red.
- Temporal workflow compresses knowledge transfer checklist to 48 hours.
- Dean must acknowledge the override (dual authorization required for P0 severity).

---

## EC-ACA-03 | Mass Bunk Detection — False Positive Alerts
**Severity: P1**

**Trigger:** An entire section of 60 students collectively skips a class (festival protest, sports event, etc.). The AI immediately sends 60 SMS alerts to parents, triggering a wave of panicked calls to the Dean.

**What breaks:** Institutional reputation. Parent trust. Phone lines. The HOD is blindsided by 60 parent calls with no context.

**Architectural fix:**

Add a **Mass Anomaly Filter** to the attendance alert pipeline. Before sending any parent notifications, the system checks session-level attendance percentages:

```python
class AttendanceAlertPolicy:
    INDIVIDUAL_ALERT_THRESHOLD = 0.85    # < 85% triggers individual alert
    MASS_BUNK_THRESHOLD = 0.20           # < 20% attendance halts individual alerts
    MASS_BUNK_WINDOW_HOURS = 24          # check within 24h window

def should_send_parent_alert(session: AttendanceSession, student: Student) -> bool:
    session_attendance_pct = session.present_count / session.total_enrolled

    if session_attendance_pct < MASS_BUNK_THRESHOLD:
        # Mass bunk detected — halt individual alerts, queue HOD review
        domain_event_bus.publish(DomainEvent(
            event_type="attendance.mass_bunk_detected",
            payload={
                "session_id": str(session.id),
                "attendance_pct": session_attendance_pct,
                "absent_count": session.total_enrolled - session.present_count,
                "course_id": str(session.course_id),
                "faculty_id": str(session.faculty_id),
            }
        ))
        return False  # Halt all 60 parent alerts

    # Normal path — check individual student threshold
    student_pct = calculate_student_attendance_pct(student.id, session.course_id)
    return student_pct < INDIVIDUAL_ALERT_THRESHOLD
```

The `attendance.mass_bunk_detected` event sends a single HOD notification: "60 students absent in CS601 (10:00 AM session). Mass event suspected. No parent alerts sent. Please investigate and confirm."

The HOD can then:
1. Confirm as mass bunk → system logs reason, no alerts sent, session marked `MASS_EXCUSED` pending Registrar approval.
2. Deny → system sends all 60 individual parent alerts immediately.

---

## EC-ACA-04 | Adjunct / Industry Faculty Variable Scheduling
**Severity: P2**

**Trigger:** An industry expert hired to teach a fintech module can only teach on alternating Saturdays or specific evenings, and their availability changes week-to-week. The constraint solver fails repeatedly because it optimizes for standard weekly recurring patterns.

**What breaks:** The timetable solver either rejects the faculty member's assignment (constraint violation) or generates technically valid but practically useless slots that the faculty cannot attend.

**Architectural fix:**

Add an **Ad-Hoc Scheduling Zone** to the timetable solver — a separate constraint class for visiting/adjunct faculty that bypasses weekly recurring pattern requirements:

```python
class FacultySchedulingMode(str, Enum):
    STANDARD = "standard"          # Weekly recurring slots (normal faculty)
    ADHOC = "adhoc"                # Block hours, variable availability (visiting)
    HYBRID = "hybrid"              # Mix of recurring + ad-hoc sessions

class AdhocAvailabilitySlot(BaseModel):
    faculty_id: UUID
    date: date
    start_time: time
    end_time: time
    confirmed: bool                 # Faculty must confirm each slot via portal
    expires_at: datetime            # Slot offer expires if not confirmed in 48h

# Visiting faculty submit their availability week-by-week
# The solver treats these as hard constraints for ad-hoc faculty
# rather than trying to fit them into regular weekly patterns
```

Visiting faculty receive a weekly availability prompt (Monday morning) to confirm their slots for the coming week. If they don't confirm by Tuesday noon, the HOD gets an alert and the solver places a `SESSION_UNSCHEDULED` placeholder — the HOD manually resolves.

---

# Module E06 — Examinations

---

## EC-EXM-01 | Question Paper Dispatch Failure — Network Outage at T-30
**Severity: P0**

**Trigger:** The system is scheduled to decrypt and release question papers 30 minutes before the exam. A campus-wide internet outage hits exactly at that time. Invigilators cannot access the portal. The exam cannot start.

**What breaks:** Exam delayed or cancelled. Regulatory breach if exam must be rescheduled. Student anxiety. Potential malpractice window if papers are somehow accessed during the chaos.

**Architectural fix:**

Implement an **Offline Cryptographic Fallback** — a USB-key protocol using HashiCorp Vault's offline unsealing mechanism.

```
Protocol design:
1. 72 hours before each exam, the system pre-generates encrypted paper bundles
   and writes them to a Vault-sealed local cache on the campus server.

2. The campus server holds the encrypted bundle. It CANNOT decrypt without the
   Vault unseal key, which only the CoE holds on a physical USB device.

3. At T-30, normal flow: Vault unseals via network, decrypts, distributes.

4. Network failure flow:
   a. System detects Vault unreachable (3 failed pings, 90-second window).
   b. Triggers "Offline Exam Mode" alert to CoE's mobile (SMS, not internet).
   c. CoE inserts USB key into the offline terminal at the exam control room.
   d. USB key contains the session-specific unseal shard (Shamir's Secret Sharing).
   e. Terminal decrypts the pre-cached bundle locally.
   f. CoE prints papers OR distributes via LAN (campus local network, no internet needed).
   g. All offline actions are cryptographically signed and synced to Vault audit log
      when connectivity restores.
```

```python
class ExamPaperDispatchMode(str, Enum):
    ONLINE_VAULT = "online_vault"          # normal path
    OFFLINE_USB = "offline_usb"            # fallback path
    EMERGENCY_PRINT = "emergency_print"    # last resort

class OfflineDispatchRecord(BaseModel):
    exam_session_id: UUID
    dispatch_mode: ExamPaperDispatchMode
    initiated_by: UUID                     # CoE ID
    usb_key_serial: str                    # hardware token serial number
    offline_at: datetime
    synced_at: datetime | None
    audit_hash: str                        # cryptographic proof of integrity
```

**Implementation notes:**
- The USB key protocol requires a physical terminal at the exam control room — an air-gapped laptop with the ALIS offline client pre-installed.
- Feature flag: `examinations.offline_fallback_enabled` — must be `true` for any institution using this module.
- This is not optional for any institution running end-semester exams through ALIS.

---

## EC-EXM-02 | Damaged Answer Script Barcode
**Severity: P1**

**Trigger:** A physical answer script's barcode is damaged during handling. It cannot be scanned into the tracking system. Blind evaluation depends on barcode-based anonymization — a manual lookup would break blind evaluation and create bias.

**What breaks:** The script cannot be assigned to an evaluator. If assigned manually using the student's name, blind evaluation is compromised. If not assigned, the student has no result.

**Architectural fix:**

Implement a **Damaged Script Triage Queue** with dual-authorization override:

```python
class DamagedScriptStatus(str, Enum):
    REPORTED = "reported"
    UNDER_TRIAGE = "under_triage"
    RE_INDEXED = "re_indexed"
    DUAL_AUTH_APPROVED = "dual_auth_approved"
    ASSIGNED_TO_EVALUATOR = "assigned_to_evaluator"

class DamagedScriptRecord(BaseModel):
    script_id: UUID                    # system-generated on triage
    exam_session_id: UUID
    original_barcode: str | None       # partially readable barcode
    secondary_identifier: str          # roll number from cover page (pre-printed, not handwritten)
    reported_by: UUID                  # invigilator ID
    triage_officer: UUID | None        # CoE staff handling triage
    coe_authorization: UUID | None     # CoE approval
    registrar_authorization: UUID | None  # Registrar approval (dual auth)
    re_index_reason: str
    blind_evaluation_preserved: bool   # must be True before assignment
```

The "secondary visual identifier" is a pre-printed roll number on the cover page header — separate from the barcode — that exists specifically for this failure scenario. The evaluator is assigned by CoE using an anonymized script ID, not the roll number. The roll-number-to-script-ID mapping is stored in a sealed Vault key only the CoE and Registrar can access, opened only after evaluation is complete.

**Dual authorization rule:** Neither CoE alone nor Registrar alone can complete the re-indexing. Both must digitally approve the `DamagedScriptRecord` before the script enters the evaluator queue. This is enforced in the workflow, not just application logic.

---

## EC-EXM-03 | Revaluation vs. Supplementary Exam — Overlapping Timelines
**Severity: P1**

**Trigger:** A student fails a course and applies for revaluation (7–15 day window). However, the supplementary exam registration opens before the revaluation result is published. The system demands a re-appear fee. If the student pays and then passes revaluation, the system has two competing active workflows for the same course.

**What breaks:** Double-charging the student. Workflow conflict between `REVALUATION_PENDING` and `SUPPLEMENTARY_REGISTERED` states for the same course. If revaluation passes, the supplementary registration must be annulled and the fee refunded — but both refund and annulment are complex, multi-step processes.

**Architectural fix:**

Implement an **Overlapping Workflow Resolver** using an escrow state for the supplementary fee:

```python
class CourseAttemptStatus(str, Enum):
    ENROLLED = "enrolled"
    FAILED = "failed"
    REVALUATION_PENDING = "revaluation_pending"
    SUPPLEMENTARY_REGISTERED_CONDITIONAL = "supplementary_registered_conditional"
    SUPPLEMENTARY_REGISTERED_CONFIRMED = "supplementary_registered_confirmed"
    REVALUATION_PASSED = "revaluation_passed"
    SUPPLEMENTARY_APPEARED = "supplementary_appeared"

@workflow.defn
class RevaluationSupplementaryResolverWorkflow:
    @workflow.run
    async def run(self, student_id: str, course_id: str, tenant_id: str):
        # Student is in REVALUATION_PENDING and wants to register for supply exam
        # Allow registration but hold fee in escrow
        await workflow.execute_activity(
            register_supplementary_conditional,  # status = CONDITIONAL, fee in escrow
            args=[student_id, course_id, tenant_id]
        )

        # Wait for whichever comes first: revaluation result OR supply exam date
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

**Implementation notes:**
- The escrow ledger entry is tagged `SUPPLEMENTARY_FEE_ESCROW` and excluded from daily revenue reconciliation until released.
- The student portal shows clear status: "Your revaluation result will be published by [date]. Your supplementary registration is conditionally held. You will be notified immediately on revaluation result."

---

## EC-EXM-04 | Grace Mark Cascade — Merit List Contamination
**Severity: P1**

**Trigger:** The AI automatically applies a 2-mark grace to push a student from 38 to 40 (passing mark). This bumps their CGPA fractionally above another student who passed without grace, stealing the University Gold Medal from the non-grace student.

**What breaks:** A student who passed without assistance loses a merit award to one who needed a grace mark. Legally and ethically indefensible. Likely to be challenged.

**Architectural fix:**

Add a `grace_marks_applied` boolean and `grace_mark_count` integer to the `student_result_record`. Create a separate merit computation that has an explicit grace mark exclusion rule in the policy DSL:

```yaml
# In tenant_policies — merit_list_eligibility
policy_id: "merit_list_eligibility"
rules:
  - id: "grace_mark_exclusion"
    condition: "student.grace_marks_applied == true AND list_type IN ['gold_medal', 'top_rank', 'scholarship_merit']"
    on_match: "EXCLUDED"
    reason_code: "GRACE_MARK_RECIPIENT"
    note: "Students who received grace marks are excluded from top-1% merit calculations per UGC norms"

  - id: "backlog_exclusion"
    condition: "student.active_backlogs > 0"
    on_match: "EXCLUDED"
    reason_code: "ACTIVE_BACKLOG"
```

This rule is data-driven and configurable per institution, not hardcoded. The merit list computation explicitly passes `list_type` to the policy engine on every evaluation.

**The grace mark itself** is always computed by the rules engine, never the LLM. The policy specifies: "If final marks are within [grace_threshold] of passing mark AND student has appeared in minimum required exams AND no prior grace mark applied this semester, apply grace." The LLM's role is zero in this calculation.

---

## EC-EXM-05 | AI Evaluation Hallucination on Descriptive Scripts
**Severity: P0**

**Trigger:** The AI auto-grades a descriptive answer and produces a score that is factually wrong — either inflated (hallucinated quality) or deflated (missed a valid argument). Since this is automated and high-stakes, any systematic error affects hundreds of students.

**What breaks:** Incorrect marks at scale. If inflated, cheating is rewarded. If deflated, genuine students are failed. Both are regulatory and legal liabilities.

**Architectural fix:**

LLM scoring of descriptive answers is never final. It is always a `DRAFT_SCORE` that requires faculty confirmation:

```python
class AnswerEvaluationRecord(BaseModel):
    script_id: UUID
    question_id: UUID
    max_marks: int
    # AI scoring
    ai_draft_score: int | None
    ai_justification: str | None        # per-answer reasoning
    ai_confidence: float                # 0.0–1.0
    ai_model_used: str
    ai_evaluated_at: datetime | None
    # Faculty review
    faculty_final_score: int | None
    faculty_override_reason: str | None  # required if delta > 20%
    faculty_reviewed_at: datetime | None
    faculty_id: UUID | None
    # Status
    status: Literal["PENDING", "AI_DRAFT", "FACULTY_CONFIRMED", "DISPUTED"]
```

**Mandatory escalation rules:**
1. If `ai_confidence < 0.6` → route to faculty immediately without showing AI score (prevents anchoring bias).
2. If `faculty_final_score` deviates from `ai_draft_score` by more than 20% → require faculty to enter `faculty_override_reason`.
3. If a faculty member confirms >95% of AI scores without any override across a batch → flag for HOD audit (possible rubber-stamping).
4. Statistical distribution check: if final score distribution for a course deviates >2 standard deviations from the historical mean → flag to CoE before result publication.

---

# Module E07 — Finance

---

## EC-FIN-01 | Government DBT Scholarship Delay
**Severity: P1**

**Trigger:** A student relies on a state scholarship promised in August but disbursed in March. The system's daily batch job flags them as a "Defaulter" from September onward, restricting their portal access and blocking exam registration.

**What breaks:** A student who has done nothing wrong is treated as a fee defaulter for 7 months. Portal restrictions. Exam eligibility blocked. Hall ticket not generated. Severe distress, legitimate grievance.

**Architectural fix:**

Implement an **Awaiting Government Funds** ledger tag that explicitly pauses automated defaulter escalation:

```sql
CREATE TABLE student_fee_exemptions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL,
    student_id       UUID NOT NULL,
    exemption_type   TEXT NOT NULL
        CHECK (exemption_type IN (
            'AWAITING_GOVT_DBT',
            'AWAITING_BANK_LOAN',
            'AWAITING_NGO_GRANT',
            'PAYMENT_DISPUTE',
            'SCHOLARSHIP_ESCROW',
            'MANAGEMENT_WAIVER'
        )),
    expected_date    DATE,                -- when funds are expected
    amount_expected  DECIMAL(12,2),
    reference_number TEXT,               -- scholarship ID / loan sanction letter
    approved_by      UUID NOT NULL,      -- Finance Officer who approved the exemption
    valid_until      DATE NOT NULL,      -- exemption expires on this date
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT now()
);
```

The defaulter detection Celery Beat job checks this table before escalating:

```python
def is_student_exempted(student_id: UUID, tenant_id: UUID) -> bool:
    exemption = db.query(
        """SELECT id FROM student_fee_exemptions
           WHERE student_id = $1 AND tenant_id = $2
           AND valid_until >= CURRENT_DATE""",
        [student_id, tenant_id]
    )
    return len(exemption) > 0
```

**Implementation notes:**
- The exemption does not waive the fee — it pauses escalation only.
- When the DBT credit arrives, Finance confirms receipt and the exemption is closed.
- The Exam module's eligibility check (`student.dues_cleared`) must check exemptions too: `dues_cleared OR is_exempted`.
- Feature flag: `finance.government_dbt_exemption` — always enabled for Indian institutions.

---

## EC-FIN-02 | Fragmented Multi-Source Fee Payment
**Severity: P1**

**Trigger:** A student's ₹2,00,000 annual fee is paid via: ₹10,000 UPI, ₹50,000 Demand Draft from parent, and ₹1,40,000 bank education loan disbursed directly to the institution in tranches. The reconciliation engine sees partial payments and flags a defaulter.

**What breaks:** The student is compliant. The bank loan tranche schedule doesn't match the institution's fee deadline calendar. The DD is in transit. The partial UPI payment looks like a defaulter pattern.

**Architectural fix:**

Implement a **Promissory / Escrow Ledger** with explicit third-party fund tracking:

```python
class FeePaymentComponent(BaseModel):
    invoice_id: UUID
    component_type: str  # 'direct_payment' | 'dd' | 'loan_tranche' | 'scholarship' | 'promissory'
    amount: Decimal
    payment_reference: str | None
    expected_date: date | None    # for promissory components
    received: bool
    received_at: datetime | None
    posted_by: UUID | None        # Finance staff who confirmed receipt

# A single invoice can have multiple payment components
# The invoice is considered PAID when sum(received components) >= invoice_amount
# Automated defaulter escalation is paused if sum(all components) >= invoice_amount
# (even if some components are not yet received — they are 'promised')
```

Finance staff create the promissory components by logging the bank loan sanction letter number, expected disbursement schedule, and amount. This pauses defaulter escalation until `expected_date + grace_days` (configurable, default: 15 days after expected tranche date).

---

## EC-FIN-03 | Retroactive Scholarship Revocation
**Severity: P1**

**Trigger:** A student received a merit scholarship in Semester 1. In Semester 3, they are caught in a major disciplinary violation. Management revokes the scholarship retroactively back to Semester 1. The system must instantly recalculate past ledgers, generate a new large due amount, and manage the dispute.

**What breaks:** The retroactive ledger recalculation involves modifying posted (closed) accounting periods — a major accounting control violation if done naively. The student will dispute the amount. The audit trail is critical.

**Architectural fix:**

Never mutate closed ledger entries. Use a **Reversal Ledger Entry** pattern:

```python
class LedgerEntryType(str, Enum):
    FEE_CHARGE = "fee_charge"
    PAYMENT_RECEIVED = "payment_received"
    SCHOLARSHIP_CREDIT = "scholarship_credit"
    SCHOLARSHIP_REVERSAL = "scholarship_reversal"    # never edits original
    LATE_FEE_CHARGE = "late_fee_charge"
    WAIVER_CREDIT = "waiver_credit"
    WAIVER_REVERSAL = "waiver_reversal"

# To revoke Semester 1 scholarship:
# DO NOT: UPDATE ledger SET amount = 0 WHERE type = 'SCHOLARSHIP_CREDIT'
# DO: INSERT new entry with type = 'SCHOLARSHIP_REVERSAL', amount = original_amount
#     with dual authorization and reason code

class ScholarshipRevocationRecord(BaseModel):
    original_scholarship_credit_id: UUID    # the entry being reversed
    reversal_entry_id: UUID                 # the new reversal entry
    revocation_reason: str
    effective_from: date                    # which semester it applies from
    total_amount_reversed: Decimal
    approved_by_dean: UUID
    approved_by_finance_officer: UUID
    dispute_window_closes_at: datetime      # 30 days from revocation
    disputed: bool = False
```

The student receives an itemized statement showing the original credits and the reversals as separate line items — transparent and auditable. A 30-day dispute window is created automatically where the student can challenge the revocation.

---

# Module E08 — HR & Payroll

---

## EC-HR-01 | Visiting Faculty Session Billing Discrepancy
**Severity: P1**

**Trigger:** Guest lecturers are paid per lecture. The AI schedules them for 10 lectures, but 3 are cancelled due to campus events, and they take 2 extra unplanned tutorial sessions. The automated payroll run generates incorrect payment.

**What breaks:** Over- or under-payment to visiting faculty. Contractual dispute. If not caught before disbursement, a reversal in the next payroll cycle creates resentment and trust issues.

**Architectural fix:**

Implement a **Timesheet-to-Payroll Bridge** where visiting faculty digitally validate each session before it enters the payroll multiplier:

```sql
CREATE TABLE visiting_faculty_session_log (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL,
    faculty_id        UUID NOT NULL,
    timetable_slot_id UUID,              -- NULL for unscheduled sessions
    session_date      DATE NOT NULL,
    start_time        TIME NOT NULL,
    end_time          TIME NOT NULL,
    session_type      TEXT NOT NULL,     -- 'lecture' | 'tutorial' | 'lab' | 'other'
    status            TEXT NOT NULL,     -- 'SCHEDULED' | 'DELIVERED' | 'CANCELLED' | 'UNSCHEDULED_ADDED'
    faculty_confirmed BOOLEAN DEFAULT false,
    faculty_otp_used  TEXT,              -- OTP used to confirm attendance
    confirmed_at      TIMESTAMPTZ,
    hod_verified      BOOLEAN DEFAULT false,
    hod_verified_at   TIMESTAMPTZ,
    rate_per_session  DECIMAL(10,2),     -- from contract
    payable           BOOLEAN GENERATED ALWAYS AS (
                        faculty_confirmed AND status = 'DELIVERED'
                      ) STORED
);

-- Payroll computation for visiting faculty:
-- SELECT SUM(rate_per_session) FROM visiting_faculty_session_log
-- WHERE faculty_id = $1 AND payroll_month = $2 AND payable = true
```

Faculty receive an OTP via SMS at the start of each scheduled session. Confirming the OTP marks the session as `DELIVERED`. Unscheduled sessions added by the faculty require HOD verification before becoming `payable`.

---

## EC-HR-02 | CAS Promotion — API Score Disputes
**Severity: P1**

**Trigger:** The AI computes a faculty member's API (Academic Performance Indicator) score for Career Advancement Scheme (CAS) promotion and it falls slightly below the threshold. The faculty member disputes it, claiming a publication in an obscure journal was not recognized.

**What breaks:** If the AI's score is treated as final, the faculty member misses a promotion they may be entitled to. If every disputed score requires manual recomputation from scratch, the process is unmanageable.

**Architectural fix:**

The AI's API score computation is always a **Draft Computation** that the faculty member must explicitly accept. The liability transfer is the key mechanism:

```python
class APIScoreDraftStatus(str, Enum):
    AI_COMPUTED = "ai_computed"          # AI's initial calculation
    FACULTY_REVIEWING = "faculty_reviewing"
    FACULTY_DISPUTED = "faculty_disputed"  # faculty raises specific dispute
    DISPUTE_RESOLVED = "dispute_resolved"
    FACULTY_ACCEPTED = "faculty_accepted"  # faculty clicks Accept — liability transfers
    HOD_VERIFIED = "hod_verified"
    SUBMITTED_FOR_CAS = "submitted_for_cas"

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

**ORCID/Scopus integration** for autonomous publication discovery:

```python
class PublicationDiscoveryService:
    """Runs weekly per faculty member, autonomously discovers publications."""

    async def discover_publications(self, faculty: Employee) -> list[PublicationDraft]:
        results = []

        # Search by faculty name + institution affiliation
        scopus_pubs = await scopus_api.search(
            author=faculty.full_name,
            affiliation=faculty.institution_name,
        )

        # Search by ORCID if registered
        if faculty.orcid_id:
            orcid_pubs = await orcid_api.get_works(faculty.orcid_id)
            results.extend(orcid_pubs)

        results.extend(scopus_pubs)

        # Draft API entries — faculty only needs to click Verify
        return [
            PublicationDraft(
                faculty_id=faculty.id,
                title=pub.title,
                journal=pub.journal,
                issn=pub.issn,
                doi=pub.doi,
                year=pub.year,
                indexed_in=pub.indexes,   # Scopus / SCI / UGC
                suggested_api_points=compute_api_points(pub),
                status="AWAITING_FACULTY_VERIFICATION",
            )
            for pub in deduplicate(results)
        ]
```

---

## EC-HR-03 | Shared Faculty Cross-Department Budget Split
**Severity: P2**

**Trigger:** A senior professor teaches 60% in Engineering and 40% in MBA. The HR data model doesn't support split departmental attribution. HOD appraisal responsibility is ambiguous. Payroll cannot be correctly split across two budget heads.

**Architectural fix:**

The employee data model must natively support primary/secondary department assignment with percentage weights:

```sql
CREATE TABLE employee_department_assignments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    employee_id     UUID NOT NULL,
    department_id   UUID NOT NULL,
    assignment_type TEXT NOT NULL CHECK (assignment_type IN ('primary', 'secondary')),
    weight_pct      DECIMAL(5,2) NOT NULL,   -- must sum to 100 across employee
    effective_from  DATE NOT NULL,
    effective_until DATE,
    appraisal_hod   UUID NOT NULL,           -- which HOD conducts appraisal for this dept share
    budget_head     TEXT NOT NULL,
    CONSTRAINT weight_valid CHECK (weight_pct > 0 AND weight_pct <= 100)
);

-- Payroll split view used by FM-5
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

The appraisal workflow for shared faculty runs twice — once per department, with each HOD filling in their department-specific assessment. The final API score is computed from both assessments, weighted accordingly.

---

# Module E09 — Student Services

---

## EC-SS-01 | Weaponized Grievance Spike
**Severity: P1**

**Trigger:** During exam week, a coordinated group of students submits dozens of anonymous, severe complaints against a strict invigilator within a 24-hour window. The AI's auto-escalation routes all complaints to "Critical Severity," derailing the exam cell and potentially removing the invigilator mid-examination.

**What breaks:** A legitimate invigilator is wrongly escalated. The exam is disrupted. The Dean is flooded with critical alerts from a manufactured crisis. Anonymous complaints have no accountability.

**Architectural fix:**

Implement an **Anomaly Detection Triage** in the grievance intake pipeline:

```python
class GrievanceAnomalyDetector:
    SPIKE_THRESHOLD_MULTIPLIER = 3.0    # 300% above rolling average
    SPIKE_WINDOW_HOURS = 24
    MIN_SPIKE_COUNT = 5                 # at least 5 complaints to trigger

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
    # Check for coordinated spike before routing
    is_spike = await anomaly_detector.detect_coordinated_spike(
        respondent_id=grievance.respondent_id,
        respondent_type=grievance.respondent_type,
        tenant_id=grievance.tenant_id,
    )

    if is_spike:
        # Halt automated routing — queue for manual Dean review
        severity_override = "ANOMALY_REVIEW"
        await notify_dean_of_spike(grievance.respondent_id, spike_count=recent_count)
        # Individual complaints are held — NOT sent to respondent yet
    else:
        severity_override = None

    return create_grievance_record(grievance, severity_override=severity_override)
```

**Additional safeguards:**
- Anonymous complaints can only be `ROUTINE` or `SERIOUS` severity — never `CRITICAL`. Critical severity requires identity verification.
- Complaints submitted within 30 minutes of each other with near-identical text trigger a `COORDINATED_COMPLAINT_FLAG` for manual review.
- The exam period blackout: during the 48 hours before and during an exam, severity auto-escalation for invigilator-related complaints is paused. The complaint is received and queued, but no automatic action is taken until the exam concludes.

---

## EC-SS-02 | Offer Revoked by Employer Post-Placement
**Severity: P1**

**Trigger:** A student accepts a placement offer, is locked out of the placement system (one-offer policy), and 3 months later the company revokes the offer due to market conditions or hiring freeze.

**What breaks:** The student is blocked from active drives. The company's revocation may arrive via informal email, not through the TPO portal. The system has no structured path to re-activate the student.

**Architectural fix:**

Implement an **Offer Revocation Workflow** with automatic re-insertion into active drives:

```python
class PlacementOfferStatus(str, Enum):
    RECEIVED = "received"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVOKED_BY_EMPLOYER = "revoked_by_employer"   # new status
    JOINED = "joined"
    OFFER_LAPSED = "offer_lapsed"                  # student didn't join

class OfferRevocationRecord(BaseModel):
    offer_id: UUID
    student_id: UUID
    company_id: UUID
    revocation_reason: str
    revocation_date: date
    evidence_document_url: str    # email screenshot or formal letter upload
    tpo_verified: bool            # TPO must verify the revocation is genuine
    student_reactivated_at: datetime | None

@workflow.defn
class OfferRevocationWorkflow:
    @workflow.run
    async def run(self, revocation: OfferRevocationRecord):
        # Step 1: TPO verifies revocation (anti-gaming: student cannot self-revoke)
        signal = await workflow.wait_for_signal("tpo_verification", timeout=timedelta(days=3))

        if not signal.verified:
            # Unverified revocation — reject request
            await notify_student_revocation_rejected(revocation.student_id)
            return

        # Step 2: Unlock student profile immediately
        await workflow.execute_activity(
            unlock_student_placement_profile,
            args=[revocation.student_id, revocation.tenant_id]
        )

        # Step 3: Auto-insert into all currently active eligible drives
        await workflow.execute_activity(
            reinsert_into_active_drives,
            args=[revocation.student_id, revocation.tenant_id]
        )

        # Step 4: Notify student with active drive list
        await workflow.execute_activity(
            notify_student_reactivation,
            args=[revocation.student_id, revocation.tenant_id]
        )
```

**Anti-gaming safeguard:** The TPO must verify the revocation using evidence (email from company HR, formal letter). Students cannot self-initiate an offer revocation without TPO verification. The `tpo_verified` flag is the gate — the workflow pauses until it receives the TPO signal.

---

## EC-SS-03 | Verbal Offer Lock — Bypassing the One-Offer Policy
**Severity: P2**

**Trigger:** A student receives a verbal job offer. They convince the company HR to delay sending the formal offer letter to the college. The student remains active in the system, interviewing for better companies, bypassing the one-offer policy.

**What breaks:** Unfair advantage over other students. Companies lose trust in the placement process. TPO cannot enforce policy.

**Architectural fix:**

Add a **Verbal Offer Lock** button to the TPO's placement management UI:

```python
class PlacementOfferLockType(str, Enum):
    FORMAL_OFFER = "formal_offer"      # PDF offer letter received
    VERBAL_LOCK = "verbal_lock"        # TPO manually locks based on company confirmation

class PlacementOfferLock(BaseModel):
    student_id: UUID
    company_id: UUID
    lock_type: PlacementOfferLockType
    lock_initiated_by: UUID            # TPO only — not student
    company_contact_name: str         # who confirmed verbally
    company_contact_email: str
    formal_offer_due_by: date         # deadline for formal PDF
    locked_at: datetime
    formal_offer_received_at: datetime | None
    auto_unlock_if_no_formal: bool = True  # unlock if PDF not received by due date
```

A verbal lock has the same behavioral effect as a formal offer: the student is blocked from further drives. If the formal offer PDF is not received by `formal_offer_due_by`, the lock auto-expires and the student is reinstated. The company contact receives an automated reminder 3 days before the formal offer deadline.

---

## EC-SS-04 | Hostel Room Swap at 100% Capacity
**Severity: P2**

**Trigger:** Two roommates have a serious altercation. The hostel is at 100% occupancy. The warden cannot find an empty room. The AI has no logical path to resolve a conflict without a free slot.

**Architectural fix:**

Implement a **Peer Room Swap Exchange** — students post swap requests, mutually accept, and the Warden approves the exchange:

```sql
CREATE TABLE hostel_swap_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    requester_id    UUID NOT NULL,       -- student posting the swap
    requester_room  UUID NOT NULL,
    reason          TEXT NOT NULL,
    severity        TEXT DEFAULT 'ROUTINE'  -- 'ROUTINE' | 'URGENT' | 'SAFETY'
        CHECK (severity IN ('ROUTINE', 'URGENT', 'SAFETY')),
    matched_with    UUID,               -- student who accepted the swap
    matched_room    UUID,
    warden_approved BOOLEAN DEFAULT false,
    status          TEXT DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'MATCHED', 'APPROVED', 'COMPLETED', 'CANCELLED')),
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

For `SAFETY` severity (physical altercation, harassment), the Warden gets an immediate alert and is empowered to place one student in a temporary overflow space (conference room, guest room, faculty flat) for up to 72 hours while a permanent swap is arranged. The `SAFETY` flag bypasses the standard swap exchange and triggers the Dean of Student Affairs directly.

---

# Module E14 — Regulatory & Accreditation

---

## EC-REG-01 | Legacy Physical Data — Pre-ALIS Records
**Severity: P1**

**Trigger:** NAAC requires a 5-year lookback. ALIS was installed 18 months ago. The previous 3.5 years of data exists only in physical files and unstructured Excel sheets. The AI's live dashboard shows "Red" for historical metrics — not because performance was poor, but because data doesn't exist in the system.

**What breaks:** The NAAC dashboard gives a misleading negative signal. Evidence compilation is impossible without manual intervention. The 5-year SSR quantitative section has gaps that NAAC will query.

**Architectural fix:**

Design the evidence engine with **Data Imputation Flags** and a structured legacy data import pipeline:

```sql
CREATE TABLE regulatory_metrics (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL,
    metric_key     TEXT NOT NULL,        -- 'student_enrollment_count', 'pass_percentage', etc.
    academic_year  TEXT NOT NULL,        -- '2021-22', '2022-23', etc.
    value          DECIMAL(15,4),
    data_source    TEXT NOT NULL,        -- 'live_module' | 'legacy_import' | 'manual_entry' | 'estimated'
    confidence     TEXT DEFAULT 'HIGH'
        CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW', 'MISSING')),
    evidence_docs  JSONB DEFAULT '[]',   -- attached scanned proofs
    imported_by    UUID,                 -- staff who imported legacy data
    verified_by    UUID,                 -- IQAC coordinator who verified
    notes          TEXT,
    created_at     TIMESTAMPTZ DEFAULT now()
);

-- Missing data detection view
CREATE VIEW regulatory_metrics_gap_report AS
SELECT
    metric_key,
    academic_year,
    CASE
        WHEN data_source = 'live_module' THEN 'VERIFIED'
        WHEN data_source = 'legacy_import' AND verified_by IS NOT NULL THEN 'IMPORTED_VERIFIED'
        WHEN data_source = 'legacy_import' AND verified_by IS NULL THEN 'IMPORTED_UNVERIFIED'
        WHEN data_source = 'manual_entry' THEN 'MANUAL_ENTRY'
        WHEN confidence = 'MISSING' THEN 'MISSING'
        ELSE 'UNKNOWN'
    END AS data_quality,
    evidence_docs
FROM regulatory_metrics;
```

The NAAC dashboard renders missing data points in red with an inline upload button — the IQAC coordinator can attach scanned legacy documents directly to the metric cell. The SSR auto-compilation flags every non-`live_module` data point with a footnote indicating the data source and confidence level.

---

## EC-REG-02 | Regulatory Format Changes — OTA Schema Updates
**Severity: P1**

**Trigger:** UGC or AICTE changes the column headers or required metrics for their annual return 2 weeks before the deadline. The hardcoded report generator produces a non-compliant output.

**What breaks:** The submission is rejected or requires emergency manual reformatting. Compliance deadline is missed.

**Architectural fix:**

The regulatory template generator must be fully decoupled from the core codebase using a **versioned template schema** stored in the database:

```sql
CREATE TABLE regulatory_report_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    body            TEXT NOT NULL,
    regulatory_body TEXT NOT NULL,  -- 'NAAC' | 'NIRF' | 'UGC' | 'AICTE' | 'AISHE' | 'NBA'
    report_type     TEXT NOT NULL,  -- 'SSR' | 'AQAR' | 'annual_return' | 'nirf_data'
    version         TEXT NOT NULL,  -- '2024-25' | '2025-26'
    effective_from  DATE NOT NULL,
    effective_until DATE,
    column_mapping  JSONB NOT NULL, -- maps ALIS metric keys to regulatory column names
    required_fields JSONB NOT NULL, -- list of mandatory fields for this version
    validation_rules JSONB,         -- field-level validation
    template_url    TEXT,           -- downloadable blank template
    is_active       BOOLEAN DEFAULT true,
    published_by    TEXT,           -- 'quaicu_ota' | 'admin'
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

The `column_mapping` JSONB is the key. When NIRF renames "Number of faculty" to "Total sanctioned teaching posts," QUAICU pushes an OTA update to this table — no code deployment required. The report generator reads the active template at runtime:

```python
async def generate_regulatory_report(
    regulatory_body: str,
    report_type: str,
    tenant_id: str,
    academic_year: str,
) -> ReportOutput:
    # Always fetch the active template — never cache this
    template = await get_active_template(regulatory_body, report_type)

    # Map ALIS metrics to regulatory column names using template.column_mapping
    mapped_data = {}
    for alis_key, regulatory_col in template.column_mapping.items():
        metric = await get_metric(alis_key, tenant_id, academic_year)
        mapped_data[regulatory_col] = metric.value

    # Validate against required fields
    missing = [f for f in template.required_fields if f not in mapped_data or mapped_data[f] is None]
    if missing:
        return ReportOutput(status="INCOMPLETE", missing_fields=missing, data=mapped_data)

    return ReportOutput(status="READY", data=mapped_data)
```

QUAICU pushes template updates via a secure OTA channel (signed JSON payload) that institutions pull on a configurable schedule — no system downtime, no emergency deployments.

---

## EC-REG-03 | Faculty API Score Ghosting — Publications Not Logged
**Severity: P1**

**Trigger:** Faculty publish papers but don't bother logging them into the HR module. The NAAC live dashboard drops to "Red" for research output — not because research is poor, but because data is missing.

**What breaks:** Misleading NAAC readiness score. Decision-makers think the institution has a research problem when the reality is a data hygiene problem. NIRF ranking suffers.

**Architectural fix:**

Active publication discovery via external APIs (ORCID, Scopus, Google Scholar):

```python
class PublicationDiscoveryScheduler:
    """Celery Beat task — runs weekly per faculty member."""

    async def discover_and_draft(self, faculty_id: UUID, tenant_id: UUID):
        faculty = await get_employee(faculty_id, tenant_id)

        # Query external sources in parallel
        scopus_task = scopus_api.search(
            author=faculty.full_name,
            affiliation=faculty.institution_domain,
        )
        orcid_task = (
            orcid_api.get_works(faculty.orcid_id)
            if faculty.orcid_id else asyncio.sleep(0)
        )
        scholar_task = google_scholar.search(faculty.full_name, faculty.email_domain)

        scopus_pubs, orcid_pubs, scholar_pubs = await asyncio.gather(
            scopus_task, orcid_task, scholar_task, return_exceptions=True
        )

        # Deduplicate by DOI
        all_pubs = deduplicate_by_doi([
            *safe_result(scopus_pubs),
            *safe_result(orcid_pubs),
            *safe_result(scholar_pubs),
        ])

        # Find publications not yet in HR module
        known_dois = await get_logged_publication_dois(faculty_id, tenant_id)
        new_pubs = [p for p in all_pubs if p.doi not in known_dois]

        if new_pubs:
            # Create draft entries — faculty gets a single "Verify your publications" notification
            await create_publication_drafts(faculty_id, tenant_id, new_pubs)
            await notify_faculty_pending_verification(faculty_id, len(new_pubs))
```

The faculty member receives a consolidated weekly notification: "We found 3 publications that may be yours. Click to verify." Each draft shows the paper title, journal, year, and suggested API points. One click confirms — the burden of manual data entry is eliminated.

---

## EC-REG-04 | Ambiguous Graduate Employment Categorization
**Severity: P1**

**Trigger:** A student graduates and joins their family business. NIRF requires specific proof for placements. The system doesn't know whether to categorize this as: placement, entrepreneurship, higher studies, or unemployed. Wrong categorization fails the external audit.

**What breaks:** NIRF placement rate is incorrect. External audit finds discrepancies. Regulatory penalty or ranking deduction.

**Architectural fix:**

Force students into a **mandatory decision tree on graduation** before the Alumni profile is created. The graduation clearance workflow includes this as a required step:

```python
class GraduationEmploymentStatus(str, Enum):
    PLACED_EMPLOYED = "placed_employed"           # joining a company
    HIGHER_STUDIES = "higher_studies"             # continuing education
    ENTREPRENEURSHIP_OWN = "entrepreneurship_own" # own startup
    ENTREPRENEURSHIP_FAMILY = "entrepreneurship_family"  # family business
    GOVERNMENT_EXAM_PREP = "government_exam_prep" # UPSC/SSC/banking
    NOT_SEEKING_YET = "not_seeking_yet"           # gap year / personal reasons
    SEEKING_EMPLOYMENT = "seeking_employment"     # actively looking

class GraduationEmploymentDeclaration(BaseModel):
    student_id: UUID
    status: GraduationEmploymentStatus
    # Conditional required fields based on status:
    employer_name: str | None           # if PLACED_EMPLOYED
    employer_cin: str | None            # if PLACED_EMPLOYED (company registration)
    offer_letter_url: str | None        # if PLACED_EMPLOYED
    ctc_lpa: Decimal | None             # if PLACED_EMPLOYED
    institution_name: str | None        # if HIGHER_STUDIES
    program: str | None                 # if HIGHER_STUDIES
    startup_name: str | None            # if ENTREPRENEURSHIP_OWN
    startup_cin_or_gstin: str | None    # if ENTREPRENEURSHIP_OWN
    family_business_gstin: str | None   # if ENTREPRENEURSHIP_FAMILY
    # Mandatory for all
    declaration_date: date
    student_digital_signature: str
```

The NIRF/NAAC categorization mapping is then deterministic:

```python
NIRF_CATEGORY_MAP = {
    GraduationEmploymentStatus.PLACED_EMPLOYED: "placed",
    GraduationEmploymentStatus.HIGHER_STUDIES: "higher_studies",
    GraduationEmploymentStatus.ENTREPRENEURSHIP_OWN: "entrepreneurship",
    GraduationEmploymentStatus.ENTREPRENEURSHIP_FAMILY: "entrepreneurship",
    GraduationEmploymentStatus.GOVERNMENT_EXAM_PREP: "other",
    GraduationEmploymentStatus.NOT_SEEKING_YET: "not_placed",
    GraduationEmploymentStatus.SEEKING_EMPLOYMENT: "not_placed",
}
```

The declaration cannot be bypassed — the Alumni portal account is not created and the degree certificate is not downloadable until the declaration is submitted.

---

# Cross-Cutting Edge Cases

---

## EC-CROSS-01 | Celery Worker Crash During Multi-Step Domain Event
**Severity: P0**

**Trigger:** A Celery worker begins processing a `student.enrolled` event (which triggers 6+ downstream handlers), and the worker crashes after handlers 1–3 complete but before 4–6. The event is marked `PROCESSING` but never reaches `PROCESSED`. The 5-minute Beat retry re-runs ALL handlers, including 1–3 which have already executed — duplicate LMS accounts, duplicate library memberships, duplicate ledger entries.

**What breaks:** Duplicate system provisioning. Double-charging in Finance. Inconsistent state across modules.

**Architectural fix:**

Every domain event handler must be **idempotent**. Before executing, check if the specific side effect for this event has already been applied:

```python
class DomainEventHandler:
    async def handle(self, event: DomainEvent) -> None:
        handler_key = f"{event.id}:{self.__class__.__name__}"

        # Idempotency check — has this specific handler already run for this event?
        if await self.idempotency_store.exists(handler_key):
            logger.info(f"Handler {handler_key} already executed — skipping")
            return

        # Execute the handler
        await self._execute(event)

        # Mark as executed (with TTL of 7 days — event IDs are UUIDs, collision is impossible)
        await self.idempotency_store.set(handler_key, ttl=timedelta(days=7))
```

The `idempotency_store` is Redis with the `alis:idempotency:*` namespace. Every event handler has a unique key combining the event UUID and handler class name. Re-execution is a no-op.

**Additionally:** Individual handler progress within a `student.enrolled` event must be tracked:

```sql
CREATE TABLE domain_event_handler_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL,
    handler_class   TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('PENDING','PROCESSING','COMPLETED','FAILED')),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    error_message   TEXT,
    UNIQUE(event_id, handler_class)
);
```

---

## EC-CROSS-02 | Audit Ledger Hash Chain Corruption
**Severity: P0**

**Trigger:** A database administrator (or a bug) writes directly to the `audit_ledger` table, bypassing the application layer. The hash chain is broken. Future audits cannot verify the integrity of past records.

**What breaks:** The entire audit trail is untrustworthy. Regulatory audits (NAAC, AICTE, UGC) may reject evidence compiled from a compromised ledger.

**Architectural fix:**

The `audit_ledger` table must be insert-only, enforced at the PostgreSQL level — not just application level:

```sql
-- Row-level security: only the application service account can INSERT
-- No UPDATE, no DELETE — ever
ALTER TABLE audit_ledger ENABLE ROW LEVEL SECURITY;

CREATE POLICY audit_ledger_insert_only ON audit_ledger
    FOR INSERT TO alis_app_role
    WITH CHECK (true);

-- Revoke all other permissions
REVOKE UPDATE, DELETE ON audit_ledger FROM alis_app_role;
REVOKE UPDATE, DELETE ON audit_ledger FROM alis_admin_role;

-- The hash chain integrity check runs as a daily Celery Beat job
-- and on every regulatory submission
async def verify_audit_chain_integrity(tenant_id: UUID) -> ChainVerificationResult:
    records = await fetch_audit_records_ordered(tenant_id)
    for i, record in enumerate(records[1:], 1):
        expected_hash = sha256(records[i-1].entry_hash + record.payload_json)
        if record.entry_hash != expected_hash:
            return ChainVerificationResult(
                intact=False,
                first_corruption_at=record.id,
                corruption_index=i,
            )
    return ChainVerificationResult(intact=True)
```

---

## EC-CROSS-03 | Multi-Tenant Data Leakage via Async Context
**Severity: P0**

**Trigger:** In an async FastAPI application, a request from `tenant_woxsen` sets `SET LOCAL alis.current_tenant = 'woxsen'` on a database connection. Due to connection pool reuse, that connection is returned to the pool and subsequently used by a `tenant_gitam` request — but the session variable still says `woxsen`. Data from GITAM's request is scoped to Woxsen's tenant.

**What breaks:** Cross-tenant data exposure. DPDP Act violation. Catastrophic trust failure.

**Architectural fix:**

The `asyncpg` pool must set the tenant session variable on **every** connection checkout, not assumed to persist:

```python
async def execute_query(sql: str, params: list, tenant_id: str) -> list[dict]:
    async with pool.acquire() as conn:
        # ALWAYS set tenant context on checkout — never assume it persists
        async with conn.transaction():
            await conn.execute(
                f"SET LOCAL alis.current_tenant = '{tenant_id}'"
            )
            rows = await conn.fetch(sql, *params)
            return [dict(row) for row in rows]

# PostgreSQL-level enforcement — Row Level Security on all tenant tables
-- Every table has: tenant_id UUID NOT NULL
-- Every table has RLS policy that enforces current_tenant matches tenant_id

CREATE POLICY tenant_isolation ON students
    USING (tenant_id::text = current_setting('alis.current_tenant'));
```

The combination of application-layer session variable setting AND PostgreSQL Row Level Security provides defense in depth. Even if the application layer makes a mistake, RLS catches it at the database layer.

---

## EC-CROSS-04 | SLA Timer Drift in Temporal Workflows
**Severity: P1**

**Trigger:** Temporal workflows use `workflow.sleep(timedelta(hours=X))` for SLA timers. Under high load, Temporal's task queue backlog means the wake-up fires late. A 4-hour SLA approval gate actually wakes up after 6 hours, auto-approving an item that should have been escalated.

**What breaks:** SLA enforcement is unreliable. Escalations fire late or not at all. High-stakes items auto-approve when they should have escalated.

**Architectural fix:**

For SLA-critical timers (exam dispatch, financial escalation, document approval), use **absolute deadline timestamps** rather than relative durations:

```python
@workflow.defn
class ApprovalGateWorkflow:
    @workflow.run
    async def run(self, gate: ApprovalGate):
        # Use absolute timestamp, not relative sleep
        deadline = gate.created_at + timedelta(hours=gate.sla_hours)

        try:
            signal = await workflow.wait_for_signal(
                "approval_decision",
                # wait_until fires at the absolute time, not relative to when it's picked up
                timeout=deadline - workflow.now()
            )
            await process_approval(signal)

        except asyncio.TimeoutError:
            # Log the actual elapsed time for monitoring
            actual_elapsed = workflow.now() - gate.created_at
            await audit_log.record_sla_breach(
                gate_id=gate.id,
                expected_deadline=deadline,
                actual_fire_time=workflow.now(),
                drift_seconds=(workflow.now() - deadline).total_seconds(),
            )

            if gate.auto_approve_on_breach and gate.priority != "HIGH_STAKES":
                await auto_approve(gate)
            else:
                await escalate(gate)
```

All SLA breaches are logged with drift measurement. A weekly report flags workflows with systematic drift > 15 minutes — indicating Temporal queue saturation that needs infrastructure scaling.

---

# Implementation Priority Matrix

| Edge Case | Module | Severity | Effort | Priority |
|---|---|---|---|---|
| EC-ADM-03 Ghost Withdrawal | E04 | P0 | High | Sprint 1 |
| EC-ADM-04 Forged Document | E04 | P0 | Medium | Sprint 1 |
| EC-ADM-05 Webhook Drop | E04 | P0 | Low | Sprint 1 |
| EC-EXM-01 Paper Dispatch Failure | E06 | P0 | High | Sprint 1 |
| EC-EXM-05 AI Evaluation Hallucination | E06 | P0 | Low | Sprint 1 |
| EC-CROSS-01 Celery Idempotency | All | P0 | Medium | Sprint 1 |
| EC-CROSS-02 Audit Chain Corruption | All | P0 | Low | Sprint 1 |
| EC-CROSS-03 Multi-Tenant Leakage | All | P0 | Medium | Sprint 1 |
| EC-ADM-01 Identity Mismatch | E04 | P1 | Medium | Sprint 2 |
| EC-ADM-02 Late Joiners | E04 | P1 | High | Sprint 2 |
| EC-ACA-01 Global Recalibration | E05 | P1 | High | Sprint 2 |
| EC-ACA-02 Faculty Attrition | E05 | P1 | Medium | Sprint 2 |
| EC-ACA-03 Mass Bunk Filter | E05 | P1 | Low | Sprint 2 |
| EC-EXM-02 Damaged Script Triage | E06 | P1 | Medium | Sprint 2 |
| EC-EXM-03 Reval vs Supply | E06 | P1 | High | Sprint 2 |
| EC-EXM-04 Grace Mark Merit | E06 | P1 | Low | Sprint 2 |
| EC-FIN-01 DBT Scholarship Delay | E07 | P1 | Low | Sprint 2 |
| EC-FIN-02 Fragmented Payment | E07 | P1 | Medium | Sprint 2 |
| EC-FIN-03 Retroactive Revocation | E07 | P1 | Medium | Sprint 2 |
| EC-HR-01 Visiting Faculty Billing | E08 | P1 | Medium | Sprint 3 |
| EC-HR-02 CAS API Score Disputes | E08 | P1 | Medium | Sprint 3 |
| EC-SS-01 Weaponized Grievances | E09 | P1 | Medium | Sprint 2 |
| EC-SS-02 Offer Revocation | E09 | P1 | Low | Sprint 2 |
| EC-REG-01 Legacy Data Import | E14 | P1 | High | Sprint 3 |
| EC-REG-02 OTA Template Updates | E14 | P1 | Medium | Sprint 3 |
| EC-REG-03 Publication Ghosting | E14 | P1 | Medium | Sprint 3 |
| EC-REG-04 Graduate Categorization | E14 | P1 | Low | Sprint 3 |
| EC-CROSS-04 SLA Timer Drift | All | P1 | Medium | Sprint 2 |
| EC-HR-03 Shared Faculty Split | E08 | P2 | Medium | Sprint 4 |
| EC-ACA-04 Adjunct Scheduling | E05 | P2 | Medium | Sprint 3 |
| EC-SS-03 Verbal Offer Lock | E09 | P2 | Low | Sprint 3 |
| EC-SS-04 Hostel Room Swap | E09 | P2 | Low | Sprint 3 |

---

*Document version: 1.0 | March 2026*
*Authors: QUAICU Engineering*
*Classification: Internal — Confidential*
