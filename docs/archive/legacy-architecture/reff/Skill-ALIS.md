
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

skill_alis_enforcement_v2.md

ALIS Constitutional Enforcement Layer (Expanded + Hardened)



0. Constitutional Position

This skill sits above Jira and below Antigravity.

It does not generate features.
It canonicalizes intent.

It converts imperfect Jira stories into Layer-compliant build instructions.

If architectural certainty cannot be established → STOP.


1. Operating Doctrine

ALIS is:

A state machine system

A governance engine

A policy-bound institutional OS

An event-driven architecture

An AI-assisted but not AI-controlled system


This skill enforces:

Determinism over intelligence

Structure over convenience

Authority over automation

Auditability over speed




2. Invocation Scope (Mandatory Use Cases)

This skill MUST be invoked for:

New wizard implementation

Modifying existing wizard logic

Adding state transitions

Adding AI agent

Adding cross-module communication

Changing policy usage

Adding workflow

Adding override path

Refactoring rule engine

Adding background job

Adding event emitter

Changing authority rules


If a developer attempts to bypass this → generation invalid.



3. Canonicalization Pipeline

When Jira story is received:

Step 1 — Authority Validation

Identify module.

Validate module owns institutional truth (Layer 1).

If story crosses boundary → enforce event contract.


Step 2 — Wizard Classification

STATE_ENGINE

ADVISORY_ENGINE

HYBRID_ENGINE

INFRASTRUCTURE_ENGINE (for core services)


If unclear → STOP.

Step 3 — Decision Isolation

Enforce:

Exactly ONE institutional decision.


If story implies multiple decisions → split required → STOP.

Step 4 — Layer Mapping

Map story to affected layers: 1–6.

If any required layer missing → inject.

Step 5 — State Legality Check

Validate:

All input states declared.

All output states legal.

No backward transition.

Provisional states used where uncertainty exists.


If illegal → STOP.

Step 6 — Policy Separation

Extract:

All thresholds

All percentages

All date windows

All caps

All limits


Replace with:

policy = PolicyResolver.get(policy_id, decision_date)

Hardcoded constants are prohibited.

Step 7 — Global Lock Hook

Inject:

lock_status = check_global_locks(entity_context)
if lock_status.is_locked:
    return FAIL

No wizard may bypass.

Step 8 — Authority Enforcement

Determine:

Auto

Human Approval

Quorum Required


If irreversible and no authority specified → require human.

Step 9 — AI Constraint Enforcement

If AI used:

Must be read-only

Must return draft only

Must declare confidence tiers

Must never commit state

Must never modify financial or grade truth


Step 10 — Event Contract Injection

If cross-module:

EVENT CONTRACT:
Name:
Producer:
Consumer:
Idempotency Rule:
Retry Strategy:
Failure Handling:



4. Expanded Mandatory Structural Template

Every wizard must expand into:


---

MODULE:

<M# + Name>

WIZARD NAME:

<Name>WIZARD TYPE:

STATE_ENGINE | ADVISORY_ENGINE | HYBRID_ENGINE | INFRASTRUCTURE_ENGINE

LAYERS IMPACTED:

[List 1–6]

PRIMARY ENTITY:

<Entity Name>DECISION:

<One institutional truth only>INSTITUTIONAL OUTCOME OWNED:

<Must match Layer 1 authority>

STATE INPUT:

[Allowed states only]

STATE OUTPUT:

[Allowed states only]

POLICY PARAMETERS USED:

[List policy_id references]

GLOBAL LOCKS CHECKED:

[List lock names]

AUTHORITY MODEL:

Auto | Human | Quorum

OVERRIDE PATH:

Required? Yes/No
Lifecycle: REQUESTED → APPROVED → EXECUTED → CLOSED

EVENT CONTRACT:

Name: Producer: Consumer: Idempotent: Yes/No Async: Yes/No

AI ROLE:

Infer | Score | Plan | Execute | None

CONFIDENCE TIERS:

High → Medium → Low →

DATA SENSITIVITY LEVEL:

PUBLIC | INTERNAL | CONFIDENTIAL | REGULATED

FAILURE MODES:

Lock → Policy Missing → State Illegal → Low Confidence → Missing Data → Unauthorized Actor → System Failure →



If any block is missing → STOP.



5. Advanced Enforcement Rules



A. Deterministic Core Protection

Any wizard touching:

Grades

Financial amounts

Transcript

Certification

Payroll

Fee clearance


Must be:

Rule Engine final authority.

AI may assist but not commit.


If violated → STOP.



B. Advisory Isolation

If wizard classified ADVISORY_ENGINE:

Must explicitly declare:

NO STATE IMPACT

NO DB WRITE

NO LOCK EMISSION


Must return artifact only.




C. Hybrid Discipline

HYBRID_ENGINE must implement:

AI Draft → Human Review (if required) → Rule Commit → Audit Log

No direct commit.



D. Audit Logging Injection

All state-changing engines must append:

audit_log(
    actor=,
    decision=,
    state_from=,
    state_to=,
    policy_version=,
    authority=,
    hash=
)

Audit immutability required.




E. Invariant Protection Layer

These may NEVER be altered:

State legality

Global locks

Authority quorum

Override lifecycle

Policy version immutability

Tenant isolation


If Jira suggests bypass → STOP.



F. Cross-Module Firebreak

Direct module-to-module DB access is forbidden.

Only allowed via:

Event emission → Event consumer → Rule evaluation

If code attempts direct call → STOP.



G. Provisional Discipline

If AI confidence LOW:

Must transition to provisional state.

Must emit warning event.

Must block irreversible actions.





H. Tenant Isolation Enforcement

All data access must include:

tenant_id

If omitted → STOP.



I. No-Cloud Hard Stop

If any import:

openai

anthropic

google.generativeai

external inference


→ Immediate STOP.

Only:

from langchain_community.llms import Ollama

allowed.




6. Structural Compliance Scoring (Optional Mode)

Before code generation:

Score story 0–100:

Authority Alignment State Legality Policy Separation Lock Enforcement AI Constraint Event Discipline Override Safety Audit Completeness Resilience Handling

If < 85 → require clarification.




7. Developer-Proofing Measures

Because developers are average:

Never assume they understand Layer boundaries.

Never assume they remember Policy separation.

Never assume they remember event discipline.

Never assume they enforce global locks.


This skill must enforce everything explicitly.




8. Output Mode

Before Antigravity writes code, output:




Compliance Summary

Layer 1 Authority: PASS / FAIL
Layer 2 Decision Discipline: PASS / FAIL
Layer 3 State Legality: PASS / FAIL
Layer 4 Lock Enforcement: PASS / FAIL
Layer 5 Authority Model: PASS / FAIL
Layer 6 Resilience: PASS / FAIL
Policy Separation: PASS / FAIL
AI Constraint: PASS / FAIL
Event Contract: PASS / FAIL
Override Handling: PASS / FAIL

If any FAIL → STOP.




9. Emergency Stop Conditions

Immediate halt if:

Wizard implies backward state transition.

AI commits state.

Global lock bypassed.

Policy constant hardcoded.

Cross-module direct mutation.

Single user irreversible action without approval.

Audit disabled.

Tenant ID missing.




10. Final Directive

Antigravity is an accelerator.

This skill is the constitution.

Acceleration without constitution = entropy.

Structure without enforcement = drift.

This skill must prevent drift.

