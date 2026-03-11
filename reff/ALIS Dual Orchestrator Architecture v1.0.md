
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

🏗 ALIS Dual Orchestrator Architecture v1.0


---

1️⃣ High-Level Structure

GLOBAL ORCHESTRATOR
        ↓
Module Orchestrator (Admissions)
Module Orchestrator (Academics)
Module Orchestrator (Exams)
Module Orchestrator (Finance)
Module Orchestrator (HR)
Module Orchestrator (Student Services)
Module Orchestrator (Regulatory)

Each module owns:

Its automation

Its AI agents

Its internal workflow


The Global Orchestrator:

Coordinates modules

Handles cross-module flows

Enforces global DAG validation



---

2️⃣ Role of Module Orchestrator

Each module orchestrator:

Executes module automation flows

Triggers module-scoped AI agents

Validates module-level state

Ensures local lock compliance

Handles module-level escalation


It may not:

Trigger another module directly

Write to other module’s DB

Invoke foreign AI agent


If cross-module action needed:

→ Emit event
→ Global Orchestrator handles it


---

3️⃣ Role of Global Orchestrator

The Global Orchestrator:

Listens to system-wide events

Executes cross-module automation chains

Ensures global DAG validation

Prevents circular loops

Enforces cross-module lock precedence

Coordinates lifecycle transitions


It does NOT:

Execute AI directly

Mutate state directly

Bypass module orchestrator


Instead:

Global → invokes module orchestrator
Module orchestrator → invokes wizard/AI
Wizard → Core → Commit

This keeps AI module-scoped.


---

4️⃣ Why This Is Architecturally Strong

You now get:

✅ Local containment
✅ Cross-module coordination
✅ Clear authority layers
✅ No AI cross-contamination
✅ Easier debugging
✅ Clear failure isolation

This mirrors enterprise architecture patterns.


---

5️⃣ Critical Safeguards (Must Implement)

If you do dual orchestration, you must enforce:

🔒 No Recursive Invocation

Global → Module
Module may not → Global again.

Otherwise: Infinite loop risk.


---

🔒 Execution Depth Cap

Max automation depth:

Recommended: 5 steps

Hard limit: 10


Prevents runaway chains.


---

🔒 AI Invocation Boundary

AI may only be invoked by:

Module Orchestrator


Never by:

Global Orchestrator


This preserves your module-scoped AI decision.


---

🔒 Global Lock Precedence

Global Orchestrator must check:

1. Financial lock


2. Academic eligibility


3. Disciplinary hold


4. Regulatory hold



Before delegating to module.


---

🔒 Failure Isolation

If Module Orchestrator fails:

Global Orchestrator:

Must stop chain

Must log failure

Must not attempt silent retry beyond limit



---

6️⃣ Clean Responsibility Split

Layer	Responsibility

Core	Law & Enforcement
Module Orchestrator	Local automation + AI
Global Orchestrator	Cross-module lifecycle
AI	Advisory/Evaluative only


This is extremely clean.


---

7️⃣ Example Flow (Full Lifecycle)

AdmissionConfirmed (Event) → Global Orchestrator → Admissions Orchestrator → Enrollment Wizard → Finance Orchestrator → Fee Structure Wizard → Academics Orchestrator → LMS Activation Wizard

AI agents, if needed, are triggered inside module orchestrator only.


---

8️⃣ Why This Is Better Than Single Global Engine

If you used only a global orchestrator:

Modules become passive

AI scoping gets messy

Harder debugging

Higher coupling


If you used only module orchestrators:

Cross-module lifecycle becomes fragmented


Dual model balances both.