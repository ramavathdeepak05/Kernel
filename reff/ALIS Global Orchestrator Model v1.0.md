
> [!IMPORTANT]
> **GLOBAL ARCHITECTURE UPDATE: Event-Driven Autonomy**
> 
> ALIS has shifted to an Event-Driven Autonomy model, altering the Staff role and standardizing module structure.
> 
> **The New Standard Module Contract (5 Elements):**
> 1. `module_policies` table — configurable rules.
> 2. `automation_pipeline.py` — Celery task chain for 24/7 autonomous execution.
> 3. `event_publisher.py` — Domain events this module fires.
> 4. `event_handlers.py` — Domain events this module reacts to.
> 5. `review_queue` integration — Exceptions surfaced to staff routing.
> 
> **Staff Role Paradigm Shift:**
> Staff activity is vastly reduced compared to traditional ERPs:
> - **Rare**: Set policies once per academic year (marks threshold, fee amounts, seat capacity), Handle escalations.
> - **Daily**: Review exceptions flagged by the system (borderline marks, uncertain docs, capacity conflicts).
> - **Occasional**: Override specific decisions when human judgment is indispensable.
> - **Periodic**: Monitor dashboard metrics (Reporting) for system performance.
> *Everything else (offer letters, invoices, enrollments, hall tickets, results, notifications) is handled by the system 24/7.*
> 
> **Revised Full Build Order:**
> - **Phase 0 (Infrastructure)**: Domain Event Bus, Academic Calendar, Celery Beat.
> - **E04 Ext (Admissions Autonomous)**: First fully automated module establishing the pattern.
> - **E05 (Academics)**: Subscribes: StudentEnrolled. Publishes: SemesterStarted/Ended.
> - **E06 (Examinations)**: Subscribes: AttendanceFinalized. Publishes: ResultsDeclared.
> - **E07 (Finance)**: Subscribes: StudentEnrolled + events. Publishes: FeePaymentReceived.
> - **E08 (HR & Staff)**: Publishes: FacultyOnLeave.
> - **E09 (Student Services)**: Subscribes: StudentEnrolled. Publishes: HostelAllotted.
> - **E10 (Communication)**: Subscribes to EVERYTHING. Publishes: nothing.
> - **E11 (Reporting)**: Subscribes to EVERYTHING. Read-only projection.
> - **E12 (Alumni)**: Subscribes: StudentGraduated.
> - **Hardening**: Load test the full automated pipeline end-to-end.

---

ALIS Global Orchestrator Model v1.0

(Lifecycle-Aware | Cross-Module | Scheduled | Bounded)


---

1️⃣ Role of Global Orchestrator

The Global Orchestrator is responsible for:

Cross-module automation chains

Institutional lifecycle scheduling

System-wide state coordination

Event-driven orchestration

Institutional calendar transitions


It is not allowed to:

Invoke AI directly

Mutate state directly

Bypass module orchestrators

Override policy

Override locks


It delegates execution to Module Orchestrators only.


---

2️⃣ Two Modes of Operation

Global Orchestrator operates in:

Mode A — Reactive (Event-Driven)

Triggered by system events:

AdmissionConfirmed

TermClosed

PolicyActivated

PaymentPosted


This is normal automation behavior.


---

Mode B — Proactive (Lifecycle Scheduling)

Triggered by time or institutional calendar.

Examples:

Semester start

Semester end

Annual rollover

Accreditation reporting window

Payroll cycle close

Admission cycle open/close

Graduation cycle

Fee due reminder cycles


This is lifecycle governance.


---

3️⃣ Lifecycle Scheduler Architecture

Global Orchestrator must include:

🔹 Institutional Calendar Registry

Example:

{
  "calendar_id": "academic_year_2026",
  "semester_start": "2026-07-01",
  "semester_end": "2026-11-30",
  "exam_period_start": "2026-12-05",
  "graduation_date": "2027-02-15"
}

All lifecycle triggers must reference calendar registry.

No hardcoded dates.


---

🔹 Lifecycle Task Registry

Example:

{
  "task_id": "semester_closure_v1",
  "trigger_type": "scheduled",
  "trigger_date": "semester_end + 2 days",
  "steps": [
    "FinalizeGrades",
    "LockAttendance",
    "GenerateResults"
  ]
}

Lifecycle tasks must be versioned and replayable.


---

4️⃣ Governance Boundaries

Global Orchestrator may:

Trigger module orchestrators

Enforce order of lifecycle tasks

Pause institution-wide processes

Activate freeze modes

Initiate archival processes


Global Orchestrator may not:

Generate grades

Generate documents

Invoke AI directly

Modify policy

Change registry

Commit state



---

5️⃣ Lifecycle Freeze Controls

Global Orchestrator must support:

Exam freeze mode

Financial freeze mode

Admission freeze mode

Full institutional read-only mode


These are time-bound lifecycle states.

Example: During result publication: → Freeze grade modification.


---

6️⃣ Versioning Model

Lifecycle definitions must be:

Versioned

Effective-date bound

Approved

Immutable after activation

Replayable


Historical lifecycle execution must bind to version active at that time.


---

7️⃣ Execution Safety Model

When executing scheduled lifecycle tasks:

1. Validate global locks.


2. Validate policy context.


3. Validate module readiness.


4. Execute sequentially.


5. Stop on failure.


6. Log every step.



No blind execution.


---

8️⃣ Replay & Audit

Lifecycle execution must log:

lifecycle_task_id

lifecycle_version

execution_time

modules invoked

state changes

policy versions

automation versions

failures/escalations


Lifecycle events must be replayable like automation flows.


---

9️⃣ Failure Containment

If lifecycle execution fails:

Stop chain.

Do not partially advance lifecycle state.

Escalate to institutional admin.

Allow retry.


Never auto-force forward.


---

🔟 Calendar Integrity Rule

Time in ALIS must be:

Institutional time (timezone-fixed)

Non-mutable per execution

Policy-bound

Logged with timestamp precision


No timezone drift allowed.


---

11️⃣ Why This Is Powerful

You now have:

Reactive automation

Proactive institutional governance

Cross-module lifecycle coordination

Freeze control

Time-aware orchestration

Versioned lifecycle logic


This is enterprise-grade architecture.