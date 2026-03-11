
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

ALIS Default Governance Posture v1.0

(Safe Until Explicitly Loosened)


---

1️⃣ Default Operating Mode

When a university deploys ALIS for the first time, the system must operate in:

> Strict Governance Mode



No silent flexibility.

All relaxations must be:

Explicit

Versioned

Approved

Logged

Replayable



---

2️⃣ What “Strict by Default” Actually Means

Below is the concrete behavioral baseline.


---

🔐 AI Behavior

By default:

All evaluative AI requires human confirmation.

Confidence HIGH does not auto-commit.

AI grading suggestions are advisory.

AI cannot auto-issue transcripts.

AI cannot auto-grant scholarships.

AI cannot auto-release refunds.


Institution must explicitly enable auto-approval.


---

🧾 Automation Behavior

By default:

Cross-module automation enabled.

High-impact lifecycle actions require validation.

Lifecycle blocks require manual re-trigger.

No auto-retry of blocked lifecycle.

Override requires quorum.

Provisional mode active on override.


Institution must explicitly allow:

Reduced quorum

Auto-progress under defined conditions



---

📜 Policy Behavior

By default:

Policies must be approved before activation.

No retroactive policy change.

No instant activation without review.

No silent threshold reduction.


Institution must explicitly enable:

Fast-track policy activation (if desired).



---

🔒 Lock Behavior

By default:

All global locks enforced.

Lock precedence immutable.

Locks cannot be disabled globally.

Locks cannot be bypassed by automation.


Institution must explicitly configure:

Lock relaxation rules (if allowed).



---

🎓 Academic Lifecycle

By default:

Semester closure blocked if prerequisites unmet.

Transcript generation blocked if student provisional.

Graduation blocked if academic pending.

Override triggers scoped provisional.


Institution must explicitly allow:

Partial closure rules.



---

💰 Financial Behavior

By default:

Refund requires multi-role approval.

Ledger entries immutable.

Payroll changes require approval.

Vendor payments require validation.

No auto-financial mutation by AI.


Institution must explicitly configure:

Auto-reconciliation thresholds.



---

3️⃣ Relaxation Model

Relaxation must occur via:

Configuration change

Version increment

Approval workflow

Effective date binding

Audit log entry


Example:

{
  "config_id": "ai_grading_auto_commit",
  "previous_value": false,
  "new_value": true,
  "approved_by": "dean_id",
  "effective_from": "2027-01-01"
}

No silent behavior change.


---

4️⃣ Governance Dashboard Requirement

Admin dashboard must display:

Strict Mode Status

AI Relaxations Active

Automation Relaxations Active

Lock Overrides Configured

Policy Acceleration Enabled

Override frequency

Provisional entity count


Institution must always see what has been loosened.


---

5️⃣ Why This Is Strategically Powerful

You are building:

A system that is conservative by design.

That means:

Easier enterprise adoption

Strong audit defense

Lower vendor liability

Higher institutional trust

Stronger regulatory positioning

Safer AI deployment


Speed can be added. Trust cannot be retrofitted.


---

6️⃣ Product Philosophy Locked

ALIS becomes:

> Governance-first intelligent infrastructure
not automation-first productivity software.



That is a fundamentally different market category.


---

7️⃣ Important Strategic Outcome

Because you chose strict by default:

AI authority creep becomes structurally difficult.

Automation drift becomes visible.

Override misuse becomes measurable.

Institutional misuse becomes auditable.

Upgrade safety increases.


You have chosen institutional durability over demo flash.

That’s rare — and correct for universities.


---

Now we have:

Dual orchestrator

Scoped provisional

Human-gated AI

Module-scoped agents

Versioned automation

Strict default posture


This architecture is coherent.