
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

ALIS AI Invocation Authorization Model v1.0

(Automation-Triggered, Human-Gated AI)

This extends both:

AI Governance Spec

Automation Orchestration Spec



---

1️⃣ Core Principle

AI may be triggered directly by Automation
but may not execute without required human authorization
when:

Output affects institutional record

Output affects financial state

Output affects academic evaluation

Output affects compliance state


AI execution may be automated.
AI impact must remain governed.


---

2️⃣ Two-Stage AI Invocation Model

Automation must follow this pattern:

Trigger
   ↓
Authorization Check
   ↓
AI Invocation
   ↓
AI Output (Draft / Score / Plan)
   ↓
Rule Validation
   ↓
Commit / Escalate

AI may not be executed if:

Authorization not satisfied

Lock active

Required quorum not met



---

3️⃣ AI Invocation Categories

We define three invocation classes.


---

Class 1 — Safe Advisory Invocation (No Authorization Required)

Examples:

Risk report

Analytics summary

Compliance scan

Research digest


These:

Have STATE_IMPACT = NONE

Cannot alter state

May auto-run


No human gate required.


---

Class 2 — Evaluative Invocation (Pre-Authorized Automation)

Examples:

Script grading suggestion

Scholarship scoring

Document verification scoring

Academic risk scoring


These require:

Role-based authorization policy

Pre-configured approval binding


Example rule:

"grading_ai_may_run_if": 
  role in ["ExamController", "Dean"]

Once authorized:

Automation may invoke AI

Output must still pass Rule Engine

Human may override



---

Class 3 — High Impact Generation (Explicit Approval Required Before Invocation)

Examples:

Question paper generation

Official transcript drafting

Regulatory submission drafting

Offer letter generation


Automation must:

1. Request authorization


2. Log approval


3. Then invoke AI



AI cannot pre-generate without approval.


---

4️⃣ Authorization Binding Model

AI invocation must reference:

{
  "agent_id": "grading_agent_v2",
  "authorization_policy": "exam_controller_required",
  "invocation_class": "EVALUATIVE"
}

Invocation is denied if authorization missing.


---

5️⃣ Approval Logging Requirements

Before AI invocation requiring authorization:

System must log:

requesting_actor

approving_actor

role

timestamp

agent_id

automation_id

reason


This becomes part of audit chain.


---

6️⃣ AI Invocation Logging

Every invocation must log:

agent_id

model_version

prompt_version

input_hash

output_hash

confidence_score

authorization_id

automation_version


Replay must bind invocation to authorization.


---

7️⃣ Anti-Autonomy Safeguard

Automation may trigger AI.

Automation may not:

Auto-approve AI invocation

Lower confidence threshold

Skip required authorization

Modify authorization policy


Authorization rules are immutable unless versioned.


---

8️⃣ Confidence Override Rules

Even if authorization exists:

If AI returns:

LOW confidence → human review mandatory

Schema invalid → reject

Timeout → escalate


Authorization does not override quality gate.


---

9️⃣ Replay Model Extension

Replay must include:

Whether AI was invoked

Whether invocation was authorized

Who authorized

Confidence score at time

Whether override occurred


No AI invocation is legally invisible.


---

🔟 Risk Mitigation

This model prevents:

Silent AI auto-grading

Silent AI financial decision

Automation creeping into authority

Human displacement without trace


It allows:

Efficient workflow

Controlled intelligence

Institutional oversight

Legal defensibility



---

🧠 Important Structural Safeguard

AI invocation must remain:

Inside Orchestrator boundary
but outside Core commit boundary.

AI must never directly trigger another AI in recursive chain.

Max AI depth per automation chain = 1 (recommended).