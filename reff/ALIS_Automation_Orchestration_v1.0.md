
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

ALIS_Automation_Orchestration_v1.0.md


---

ALIS Automation & Orchestration Specification v1.0

(Cross-Module | Versioned | Bounded | Replayable)


---

1. Purpose

This document defines how automation operates within ALIS.

Automation in ALIS:

May orchestrate wizards across modules

Is versioned and replayable

Is bounded by core invariants

Cannot bypass locks, policy, or authority

Cannot mutate state outside wizard execution


Automation is governed.
It is not programmable freedom.


---

2. Architectural Position

Trigger (Event / Schedule / Condition)
        ↓
Automation Orchestrator
        ↓
Validation Engine
        ↓
Wizard Invocation (Atomic)
        ↓
Core Enforcement (Rules, Locks, Policy)
        ↓
Commit / Escalation
        ↓
Event Emission

Automation never bypasses Core.


---

3. Cross-Module Scope

Automation flows may:

Invoke wizards across modules

Chain admissions → academics → finance → HR

React to global events

Coordinate institutional lifecycle flows


Automation may not:

Directly write to DB

Skip wizard boundaries

Skip rule validation

Skip state transition validation

Modify registry

Modify policy

Override locks


All state change must occur through wizard execution.


---

4. Automation Registry

All automation flows must be registered in:

> AutomationRegistry



Each automation definition must include:

{
  "automation_id": "admission_full_lifecycle",
  "version": "1.0",
  "trigger": "AdmissionConfirmed",
  "steps": [
    {"wizard": "EnrollmentHandover"},
    {"wizard": "FeeStructureCheck"},
    {"wizard": "LMSActivation"}
  ],
  "approval_required": false,
  "effective_from": "2026-06-01",
  "approved_by": "registrar_id",
  "hash": "sha256:abc123"
}

Rules:

Edits create new version.

Activated versions are immutable.

Historical versions remain replayable.

No in-place mutation permitted.



---

5. Trigger Types

5.1 Event-Based

Triggered by system event.

Examples:

AdmissionConfirmed

PaymentPosted

GradeFinalized

PolicyActivated


Preferred trigger type.


---

5.2 Schedule-Based

Triggered by scheduler.

Examples:

Daily risk analysis

Monthly payroll

Weekly compliance scan


Must use centralized scheduler service.


---

5.3 Condition-Based

Triggered by rule evaluation.

Examples:

Attendance < threshold

Dues > 30 days

AI confidence < threshold


Condition evaluation must use PolicyResolver.

No hardcoded thresholds.


---

6. DAG Validation (Mandatory)

Before activation, automation must pass:

Directed Acyclic Graph validation

No circular wizard chains

No recursive event loop

No self-trigger loops

No mutual module recursion


Global DAG validation across modules required.

Failure → reject activation.


---

7. Lock & Authority Enforcement

Before each wizard invocation:

1. Evaluate Global Locks.


2. Validate state legality.


3. Validate required approval.


4. Validate authority role.



Automation may not downgrade approval requirement.

Automation may not bypass lock precedence.


---

8. Atomicity Rule

Each wizard invocation:

Executes in its own transaction.

Either fully commits or fully rolls back.

Cannot partially commit state.

Cannot carry transaction across steps.


Automation chains are sequential atomic steps.


---

9. Execution Logging & Replay Binding

Every automated invocation must log:

automation_id

automation_version

trigger_source

wizard_invoked

step_number

policy_version

logic_version

actor = SYSTEM_AUTOMATION

timestamp

execution_hash


Replay engine must reconstruct:

Trigger context

Automation version active at time

Policy version

Logic version


Replay must not use current automation version.


---

10. Simulation Mode (Pre-Activation)

Before activating new automation version:

System must support:

Dry-run execution

Impact preview

Conflict detection

Lock collision detection

Circular dependency detection

Event storm simulation


Activation requires approval after simulation.


---

11. Escalation & Failure Handling

If step fails:

Options (configurable per flow):

Retry (max 3 attempts)

Escalate to role

Mark provisional state

Abort chain


Failure must never partially mutate state.

Escalation must be logged.


---

12. Performance & Rate Control

Automation engine must:

Enforce concurrency limits

Enforce per-automation rate limit

Enforce depth limit

Prevent event storm loops

Execute in background worker


Automation must not block user transaction.


---

13. Emergency Controls

System must support:

Global automation pause

Per-flow pause

Read-only institutional mode

Emergency freeze during exam season


Emergency actions must be auditable.


---

14. Governance Dashboard Requirements

Admin must view:

Active automation flows

Version history

Upcoming activation

Execution frequency

Failure rate

Escalation frequency

Cross-module flow map

DAG visualization


Automation must never be invisible.


---

15. Prohibited Patterns

Automation must not:

Mutate policy

Upload logic modules

Override lock precedence

Directly emit system events bypassing wizard

Chain across more than configured max depth

Trigger itself indirectly



---

16. Automation Supremacy Boundary

If conflict occurs between:

Automation step

Policy rule

Global lock

State legality


Core invariants prevail.

Automation step must halt.


---

17. Legal & Audit Integrity Clause

Automation execution is equivalent to institutional action.

All automated decisions must be:

Traceable

Version-bound

Replayable

Non-retroactive

Non-mutable


Automation is a governed institutional actor.


---

Final Position

ALIS Automation is:

Cross-module

Versioned

Replayable

Bounded

Lock-aware

Authority-aware

Deterministic

Audit-safe


ALIS is not a workflow playground.

It is a governed institutional orchestration engine.