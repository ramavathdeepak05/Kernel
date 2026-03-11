
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

ALIS AI Governance – Legal & Audit Hardening Addendum v1.0
18. Non-Delegation Clause
AI systems within ALIS are explicitly non-authoritative.
No AI output shall:
Constitute a final institutional decision
Replace legally required human approval
Override rule engine enforcement
Substitute statutory compliance validation
All irreversible institutional decisions must pass through:
Rule validation
Authority verification
Audit logging
AI participation is advisory unless explicitly committed by Core.
19. Human Override Logging
If a human:
Accepts AI recommendation
Rejects AI recommendation
Modifies AI output
System must log:
AI output snapshot
Human decision
Reason code
Timestamp
Actor ID
Confidence tier at time of decision
This protects against:
Bias allegations
“Blind automation” accusations
Procedural unfairness claims
20. Appeal Replay Guarantee
For academic, financial, or disciplinary disputes:
System must support:
Replay of AI evaluation using historical:
model_version
prompt_version
policy_version
logic_version
Display of AI output at time of decision
Display of confidence score
Display of override history
Replay must not use current model.
Historical determinism is mandatory.
21. Model Change Governance
Model upgrades must:
Create new model_version
Undergo validation testing
Be approved by authorized role
Have effective_from date
Model changes cannot:
Retroactively affect historical decisions
Modify archived outputs
Recompute past grades automatically
22. Academic Integrity Protection
For grading or evaluation agents:
System must:
Log grading rubric used
Log policy thresholds applied
Log input scoring matrix
Prevent mid-cycle model drift
Mid-semester grading model updates are prohibited unless:
Explicitly approved
Logged
Notified
Effective from future cycle only
23. Bias & Fairness Monitoring
For evaluative agents:
Institution must be able to generate:
Distribution of AI scores
Override rates by role
Outlier detection reports
Confidence anomaly report
AI cannot silently introduce systemic bias.
If anomaly detected:
Agent must be review-flagged
Further automation may be suspended
24. Explainability Requirement
For evaluative agents:
AI output must include:
Structured reasoning fields
Feature basis explanation
Scoring breakdown
Black-box outputs are prohibited for:
Grading
Scholarship scoring
Risk classification
Disciplinary flagging
25. Data Minimization Rule
AI input context must:
Contain only necessary fields
Mask irrelevant PII
Avoid full transcript dumps
Avoid financial record exposure unless required
Violation of context contract must be treated as security incident.
26. Model Artifact Retention
Institution must retain:
Model binary hash
Adapter hash
Prompt version
Embedding model version
Evaluation dataset version (if applicable)
For minimum statutory period applicable to academic record retention.
27. AI Disablement Safeguard
System must support:
Per-agent disable toggle
Global AI pause mode
AI downgrade mode (Advisory only)
Emergency fallback to manual workflow
Institution must retain ability to revert to deterministic-only mode.
28. Liability Containment
AI outputs must include:
Confidence score
Advisory disclaimer flag (internal use)
Traceable provenance
System must not represent AI output as authoritative.
All externally issued documents must reflect institutional authority, not AI identity.
29. No Self-Modifying AI
ALIS AI agents may not:
Modify their own prompts
Update their own thresholds
Retrain automatically
Adjust policy interpretation dynamically
Self-evolution is prohibited in production.
30. Audit Supremacy Clause
If conflict arises between:
AI output
Human override
Policy rule
Lock condition
Core invariant logic prevails.
Audit records are final source of institutional truth.
Final Legal Positioning
AI in ALIS is:
Assistive computation layer
Governed intelligence
Non-authoritative actor
Deterministically bounded
Audit-constrained
Replayable
ALIS is not an autonomous decision system.
It is an institutionally governed operating environment.
..