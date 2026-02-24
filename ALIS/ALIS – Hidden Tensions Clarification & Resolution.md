ALIS – Hidden Tensions Clarification & Resolution

Version 1.0

Status: Authoritative Clarification Layer


---

0️⃣ Purpose

This document clarifies potential architectural tensions within ALIS and defines authoritative resolution rules.

It exists to:

Prevent accidental autonomy creep

Prevent implementation drift

Clarify cross-layer responsibilities

Protect replay integrity

Protect governance-first posture

Guide Antigravity-driven builds


This document overrides ambiguity.


---

1️⃣ Automation vs Strict-By-Default Posture

Tension

Automation implies efficiency.
Strict-by-default implies friction.

Clarification

Automation may execute freely, but:

High-impact state transitions require validation.

Lifecycle blocks require manual re-trigger.

Override requires quorum.

AI cannot auto-commit unless explicitly relaxed.


Automation coordinates. Core enforces. Humans authorize.

No contradiction exists.


---

2️⃣ Dual Orchestrator Recursion Risk

Tension

Global Orchestrator → Module Orchestrator → Event → Global Orchestrator.

Potential infinite loops.

Clarification

The system must enforce:

Execution Chain ID tracking.

Event depth counter.

Global DAG validation across modules.

Hard max execution depth (recommended: 5).

No Module → Global re-entry within same execution chain.


Recursion must be programmatically blocked.


---

3️⃣ Module-Scoped AI vs Cross-Module Automation

Tension

AI agents are module-scoped. Automation is cross-module.

Risk of implicit cross-module trust.

Clarification

Inter-module communication must occur only via:

Wizard execution

Event bus

Validated payload contracts


Receiving module must validate:

Policy

Lock state

Authority

Schema integrity


No module may trust another module’s AI output blindly.


---

4️⃣ AI Replay vs Model Upgrade

Tension

Replay requires historical AI determinism. Models may be upgraded.

Clarification

For every AI invocation, system must persist:

model_hash

model_binary_version

adapter_hash

prompt_version

embedding_version (if applicable)


Model artifacts must be archived.

Replay must bind to historical model version. If model binary unavailable → replay must fail loudly.

No silent substitution.


---

5️⃣ Scoped Provisional vs Lock Engine

Tension

Provisional state exists at entity level. Global locks also exist.

Risk of lock precedence confusion.

Clarification

Lock precedence order remains:

1. Financial Lock


2. Academic Lock


3. Disciplinary Lock


4. Regulatory Lock



Provisional is NOT a lock. It is a state modifier.

Provisional cannot override financial or regulatory locks.

Lock evaluation always precedes provisional logic.


---

6️⃣ Override vs Lifecycle Continuity

Tension

Override allows forced progression. System remains safe-by-default.

Clarification

Override triggers:

Scoped provisional state on affected entities.

Downstream irreversible operations blocked per entity.

No global freeze.

No silent resolution.


Override must log:

Blockers

Reason

Quorum

Policy snapshot

Execution hash


Override never deletes inconsistencies.


---

7️⃣ Automation Versioning vs Manual Re-Trigger

Tension

Automation may be updated between failure and re-trigger.

Clarification

Manual re-trigger uses:

Automation version active at re-trigger time.

Policy version resolved at re-trigger time.

Logic version resolved at re-trigger time.


Original failed attempt remains historically bound.

No replay mutation occurs.


---

8️⃣ Institutional Logic Layer vs Lifecycle Timing

Tension

Custom grading logic may change mid-semester.

Clarification

All execution resolves logic version at time of execution.

Historical results remain bound to original logic version.

Effective date must be strictly enforced.

No retroactive logic mutation permitted.


---

9️⃣ Global Scheduler Authority Boundary

Tension

Global Orchestrator schedules lifecycle tasks. Cannot mutate state directly.

Clarification

Global Orchestrator may:

Trigger module wizards.

Schedule lifecycle events.

Pause system.


Global Orchestrator may NOT:

Write to DB.

Modify policy.

Invoke AI directly.

Bypass module orchestrators.


State mutation must occur inside wizard context only.


---

🔟 Cross-Module Data Contracts

Tension

Cross-module flows may rely on shared assumptions.

Clarification

All cross-module communication must use:

Typed event schemas.

Versioned payload definitions.

Backward compatibility enforcement.

Strict schema validation.


No implicit contract allowed.


---

11️⃣ Execution Depth & Storm Control

Tension

Automation chains may cascade.

Clarification

System must enforce:

Max chain depth.

Max AI invocation per chain.

Rate limiting per automation.

Event storm detection.

Execution timeout limits.


Automation must never create runaway execution.


---

12️⃣ Governance Relaxation Drift

Tension

Strict-by-default can be relaxed.

Risk of creeping flexibility.

Clarification

All relaxations must be:

Versioned

Approved

Effective-date bound

Visible on Governance Dashboard


Dashboard must display:

Active relaxations

AI auto-commit flags

Reduced quorum policies

Override frequency

Provisional counts


Governance drift must be visible.


---

13️⃣ Provisional State Resolution Integrity

Tension

Provisional may be forgotten.

Clarification

Provisional may only be cleared via:

Wizard execution

Validation pass

Audit log entry


Provisional must never auto-expire. Provisional must never be cleared by config change.


---

14️⃣ AI Invocation Depth Control

Tension

AI may trigger workflows indirectly.

Clarification

Rules:

AI may only be invoked by Module Orchestrator.

AI may not trigger other AI.

AI invocation depth per execution chain = 1 (recommended).

AI cannot alter automation configuration.


No recursive intelligence loops allowed.


---

15️⃣ Replay Integrity Clause

Every institutional decision must be reproducible by:

Binding:

policy_version

logic_version

automation_version

lifecycle_version

model_version

lock_state

authorization_snapshot


If any missing → system integrity considered compromised.


---

16️⃣ Final Governance Position

ALIS is:

Deterministic at its core.

Probabilistic only at advisory layer.

Versioned everywhere.

Replayable always.

Strict by default.

Relaxed explicitly.

Bounded by law.

Orchestrated, not autonomous.


There are no architectural contradictions.

There are only boundaries that must be implemented precisely.


---

17️⃣ Implementation Mandate

All Antigravity-generated code must conform to:

Wizard-bound state mutation

Version binding at execution time

Lock precedence enforcement

No direct DB writes outside wizard

No AI outside module orchestrator

No lifecycle mutation outside wizard

Explicit schema validation

Execution chain ID propagation


Violation of any above is architectural breach.


---

This clarification document should now be:

Added to handbook references

Included in Antigravity context

Attached to Jira root epic

Locked as architectural constraint layer