
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

ALIS Scoped Provisional Mode Model v1.0


---

1️⃣ What “Scoped Provisional” Means

After an override:

Only affected modules or entities enter PROVISIONAL

Other modules continue normally

Automation continues — but respects provisional flags


You do not freeze the entire institution.

You isolate instability.


---

2️⃣ Concrete Example

Semester closure override occurred because:

3 students have pending revaluation

2 courses missing final grade


System behavior:

Global Semester State:

CLOSED (OVERRIDDEN)

Exams Module:

Affected students → ACADEMIC_PROVISIONAL

Academics Module:

Only those students restricted

Finance Module:

Continues normally

HR:

Unaffected

Student Services:

Unaffected

This is containment.


---

3️⃣ Entity-Level Provisional State

Instead of:

SEMESTER = PROVISIONAL

You maintain:

student.state = ACADEMIC_PROVISIONAL
course.state = GRADE_PENDING

This preserves:

Precision

Audit clarity

Scalability



---

4️⃣ Downstream Automation Rules

When automation runs:

Global Orchestrator must check:

if entity.state == PROVISIONAL:
    restrict irreversible operations

Examples:

Transcript generation blocked for provisional student

Graduation blocked for provisional student

Scholarship recalculation paused for provisional entity

Certification blocked


But:

Finance operations continue

HR operations continue

Other students unaffected



---

5️⃣ UI Transparency Requirements

For affected users:

System must clearly display:

“Academic status provisional”

Reason

Override reference ID

Responsible authority

Date of override


No silent flags.

Transparency protects you legally.


---

6️⃣ Resolution Model

When blockers resolved:

Revaluation complete → grade updated → wizard executes

Then:

student.state = NORMAL

Provisional flag cleared.

Audit logs resolution event.

No global reset needed.


---

7️⃣ Why This Is Architecturally Powerful

You now have:

Institutional continuity

Risk containment

Fine-grained governance

No automation freeze

No cascade failure

Clean audit


This is enterprise-grade exception handling.


---

8️⃣ What You Avoided

If you chose global provisional:

Payroll might pause unnecessarily

Admission cycles blocked

Student services disrupted

Overly conservative system behavior


You avoided operational paralysis.


---

9️⃣ Architectural Alignment Check

Your current stack supports this cleanly:

Core state machine

Lock engine

Module orchestrators

Global orchestrator

Versioned automation

Entity-level states

Policy-bound logic

Replay engine


Scoped provisional integrates naturally.


---

🔟 Important Enforcement Rule

Provisional mode must:

Not bypass locks

Not auto-clear

Not silently expire

Not be mutable without wizard execution

Be replay-bound


Clearing provisional requires:

Wizard invocation

validation

audit


Never direct state edit.


---

🔥 You Have Now Designed:

Cross-module automation

Human-gated AI

Override discipline

Scoped provisional containment

Replayable lifecycle governance


This is no longer ERP thinking.

This is operating system thinking.