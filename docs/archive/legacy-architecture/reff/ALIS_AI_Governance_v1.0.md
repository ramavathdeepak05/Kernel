
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

ALIS AI Governance Specification v1.0
1. Purpose
This document defines the operational, architectural, and governance rules for all AI components within ALIS.
AI in ALIS is:
Assistive
Constrained
Non-authoritative
Deterministic-bound
Auditable
Version-controlled
AI may propose, score, analyze, generate, or optimize.
AI may never:
Commit state
Bypass rules
Override locks
Modify policy
Mutate registry
Escalate authority
This specification is binding.
2. Foundational Principle
Agents draft. Rules decide.
AI outputs are advisory unless validated and committed by the Core.
Core invariants always prevail over AI output.
3. AI Execution Environment
3.1 Local-Only Inference
Only self-hosted LLMs permitted.
No cloud inference (OpenAI, Anthropic, etc.).
Model server must run inside institutional deployment boundary.
No external API calls from AI runtime.
3.2 Isolation Requirements
AI runtime must:
Have no database write access.
Have no direct database read access (only scoped inputs).
Have no filesystem write access.
Have no network access.
Run with execution timeout.
Run with memory limits.
Be tenant-isolated per university deployment.
4. AI Agent Taxonomy
All AI agents must be classified into one of the following categories.
Type A — Advisory Agents
Examples:
Academic Risk Analyzer
Compliance Gap Detector
Research Summarizer
Characteristics:
Informational only
No state impact
No lock emission
Must declare STATE_IMPACT = NONE
Type B — Evaluative Agents
Examples:
Document Verification
Scholarship Scoring
Script Assessment
Answer Grading Suggestion
Characteristics:
Produce structured recommendation
Must include confidence score
Must never finalize outcome
Must pass through Rule Engine validation
May require human approval
Type C — Optimization Agents
Examples:
Timetable Optimization
Seating Plan Allocation
Faculty Assignment
Characteristics:
Produce planning artifact
Deterministic seed required
Output must be validated before commit
Type D — Generation Agents
Examples:
Question Paper Draft
Lesson Plan Draft
Offer Letter Draft
Characteristics:
Content generation only
Must log model version
Must log prompt version
Cannot auto-publish critical artifacts without approval
5. Authority Model
Every agent must declare:
AI_ROLE (Infer | Score | Plan | Generate)
STATE_IMPACT (None | Draft | ProvisionalOnly)
Allowed values:
None
Draft
ProvisionalOnly
Forbidden:
Final
Commit
Override
If detected → reject configuration.
6. Confidence Governance
All non-advisory agents must return:
JSON
Copy code
{
  "confidence_score": 0.0–1.0,
  "confidence_tier": "HIGH | MEDIUM | LOW"
}
Current implemented thresholds (server/core/ai_gateway.py):
  HIGH   ≥ 0.85 → PolicyResolver auto-applies within policy bounds
  MEDIUM 0.60–0.84 → Staff review queue (SLA: 24 hours)
  LOW    < 0.60 → Mandatory HITL escalation (SLA: 4 hours)
Governance goal: thresholds should be policy-configurable via PolicyResolver.
Current status: hardcoded in ai_gateway.py — migration to ConfigRegistry is pending.
7. Prompt Governance
All prompts must be stored in:
PromptRegistry
Each invocation must log:
model_version
prompt_version
temperature
top_p
inference_time
Inline prompts in code are prohibited.
Prompt changes must create new version.
8. Output Schema Enforcement
AI must return structured JSON.
Free-text may not be used directly for decision.
Schema must be validated before any downstream logic executes.
Invalid schema → reject output.
9. Model Governance
Each deployment must pin:
Base model version
Adapter version (if LoRA used)
Embedding model version
No silent model update permitted.
Model upgrades require:
Version increment
Evaluation validation
Approval workflow
Effective date scheduling
10. Replay & Audit Requirements
For any AI-influenced decision, system must log:
input_snapshot_hash
output_json
model_version
prompt_version
policy_version
logic_version (if hybrid)
confidence_score
timestamp
Replay engine must reconstruct historical context exactly.
11. AI Context Contract
AI must receive:
Sanitized input only
Scoped entity context
No unrestricted database access
No full-record dumps
No unrelated tenant data
Sensitive data must be masked unless explicitly required.
PII exposure must be minimal and auditable.
12. Drift & Bias Monitoring
For evaluative agents:
System must track:
Confidence distribution
Override rate
Approval rejection rate
Performance anomaly
Latency spikes
Periodic review required.
AI must not silently degrade.
13. Failure Handling
If AI:
Times out → provisional or escalate
Returns invalid schema → reject
Returns low confidence → route to human
Crashes → abort wizard
No silent fallback logic allowed.
14. Semester Freeze Policy (Recommended)
For academic-critical agents:
Model and prompt versions may be frozen per academic cycle.
Changes allowed only during controlled window.
Prevents mid-semester grading inconsistency.
15. Prohibited Practices
Embedding policy inside model weights.
Hardcoding thresholds in prompts.
Allowing AI to directly write to database.
Allowing AI to emit system events.
Using AI output without schema validation.
Allowing dynamic prompt mutation without versioning.
16. Enforcement Priority
If conflict occurs between:
AI output
Policy
Lock
State legality
Core invariant rules prevail.
AI output may be discarded.
17. Summary
AI in ALIS is:
Controlled
Versioned
Auditable
Constrained
Deterministic-bound
Non-authoritative
AI augments institutional intelligence.
AI does not govern institutional authority.