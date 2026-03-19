
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

ALIS Configuration Boundary Specification v1.0

(Single Codebase, Multi-Institution Model)


---

1. Foundational Principle

ALIS supports institutional variability through structured configuration only.

No institution-specific behavior may be implemented through code branching, schema divergence, or conditional logic based on institution identity.

All variability must be expressed through:

Policy Registry

Workflow Registry

Role & Permission Registry

Metadata Registry

Feature Flag Registry

Academic & Financial Calendar Registry


If a requirement cannot be implemented through configuration, it must be rejected or generalized.


---

2. Architectural Invariants (Non-Configurable)

The following components are permanently immutable and may never be altered via UI or configuration:

2.1 State Machine Legality

Entity states are fixed.

Backward transitions are prohibited.

Terminal states are immutable.

Transition rules cannot be edited by client.



---

2.2 Global Lock Mechanism

Lock evaluation order is fixed.

Lock precedence cannot be altered.

Locks cannot be disabled.

Lock enforcement cannot be bypassed.



---

2.3 Audit System

Audit logging is mandatory.

Logs are append-only.

Logs cannot be deleted.

Logs cannot be edited.

Audit structure cannot be modified.



---

2.4 Deterministic Core Engines

These engines are invariant:

Financial ledger model (double-entry)

Grade computation engine

Transcript generator integrity

Payroll calculation engine (deterministic core)

Rule Engine state legality validator


Clients may configure parameters but not alter logic.


---

2.5 AI Core Constraints

AI remains read-only.

AI cannot commit state.

AI cannot bypass PolicyResolver.

AI cannot emit Global Locks.

AI cannot modify audit.



---

2.6 Event Discipline

All cross-module interactions are event-driven.

Direct cross-module DB writes are prohibited.

Idempotency enforcement is mandatory.



---

2.7 Transaction Boundaries

One wizard = one transaction boundary.

Partial commits are forbidden.

Event emission happens after commit.



---

3. Configurable Domains (UI-Controlled)

The following areas are configurable through structured registries:


---

3.1 Policy Registry (Versioned)

Configurable:

Thresholds (attendance, marks, caps)

Percentage limits

Grace rules

Deadlines

Fee amounts

Scholarship caps

Credit requirements

Pass/fail cutoffs


Requirements:

Versioned

Effective date

Approval workflow

Immutable once activated

Diff viewer

Policy hash stored


Policies cannot modify structural invariants.


---

3.2 Workflow Registry

Configurable:

Approval chains

Quorum requirements

Escalation paths

SLA timers

Role sequence


Validation Engine must ensure:

No circular approval

No self-approval

No removal of final authority

No infinite escalation loop

No bypass of required quorum


Workflow definitions cannot:

Alter state machine legality

Disable audit

Disable lock enforcement



---

3.3 Role & Permission Registry

Configurable:

Custom roles

Permission assignment

Delegation rules

Scope constraints


Constraints:

Cannot create super-root bypass

Cannot disable audit visibility

Cannot grant structural mutation privileges

Cannot alter invariant components



---

3.4 Institutional Metadata Registry

Configurable:

Institution name

Branding

Logo

Email domain

Academic calendar

Semester structure

Program definitions

Grading scale mapping (parameterized)


Metadata cannot change structural engines.


---

3.5 Feature Flag Registry

Configurable:

Enable/disable optional modules

Toggle advisory features

Toggle experimental AI models

Toggle non-critical workflows


Feature flags cannot disable:

Audit

Global Locks

PolicyResolver

Authority checks



---

3.6 Calendar Registry

Configurable:

Academic year definition

Exam windows

Fee payment deadlines

Holiday schedule

Payroll cycles


Calendar changes must be versioned.


---

4. Forbidden Customization Patterns

The following are permanently prohibited:

if institution_name == "XYZ":

Client-specific schema:

Extra table for one institution

Extra column for one client

Custom migration for one deployment


Hardcoded client logic in:

Rule Engine

AI prompts

Workflow execution

Event routing


Per-client code forks.

Any violation invalidates production integrity.


---

5. Registry Architecture Model

All registries must:

Be first-class entities

Be versioned

Be auditable

Support effective dates

Emit configuration change events

Store actor_id

Store approval trail

Store hash for integrity


Configuration changes must not retroactively alter past decisions.

Decision replay must use historical configuration version.


---

6. Validation Engine Requirement

All configuration changes must pass validation before activation:

Policy Validation

Type safety

Range validation

Conflict detection

No invariant violation


Workflow Validation

Directed acyclic graph

Quorum consistency

Authority consistency

No self-approval

No deadlock path


Role Validation

Permission hierarchy consistency

No forbidden structural permission


Invalid configurations must be rejected.


---

7. Multi-Institution Codebase Rule

The ALIS codebase is single.

Institution variability is expressed exclusively via registries.

Upgrades apply uniformly to all deployments.

Schema is identical across institutions.

No deployment may alter schema independently.


---

8. Upgrade & Migration Discipline

When deploying new version:

Registry schema migrations must be backward-compatible.

Policy versions preserved.

Audit history preserved.

Model versions preserved.

No retroactive mutation allowed.

Data migration scripts must be deterministic.


Upgrade must not require institution-specific code change.


---

9. AI Isolation Rule (Per Deployment)

Each university deployment must maintain:

Separate model directory

Separate adapter storage

Separate embedding index

Separate RAG documents

Separate policy registry


No cross-university model contamination.


---

10. Governance Philosophy

ALIS allows institutions to configure everything operationally.

ALIS does not allow institutions to alter:

Structural invariants

Deterministic engines

Enforcement layers

Legal guarantees


Configurability ends at the boundary of institutional safety.


---

Summary

This document defines:

Where client control stops.
Where architectural law begins.

It allows: Full operational flexibility.

It prevents: Codebase entropy.