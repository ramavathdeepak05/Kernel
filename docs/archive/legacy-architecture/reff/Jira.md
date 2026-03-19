
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

# ALIS Project Backlog (E00 - E07)\n\nThis document contains all epics and stories with their descriptions.\n\n## Epic: [AV-192] Epic E00 – Institutional Security & Governance Layer\n**Status:** To Do\n\n### Epic Description\n**Objective**  
Establish a non-bypassable, system-wide institutional security framework that governs identity, data protection, audit integrity, privilege control, AI boundaries, and regulatory compliance across all modules of the platform.

This epic defines the mandatory security primitives upon which every other epic depends.

**Context**  
ALIS is not a generic SaaS application. It operates in a regulated academic environment handling PII, financial records, biometric logs, transcripts, and institutional decisions.

Security is not implemented at feature level — it is enforced at the architectural layer.

This epic ensures:

* No silent privilege escalation
* No cross-tenant leakage
* No tampering of academic or financial records
* No AI policy bypass
* No unauthorized data mutation

**Authoritative Reference**

* ALIS Master Developer Document
* Institutional Data Protection Policy
* UGC & NAAC compliance standards
* IT Act (India) data protection provisions

**Hard Constraints**

* All state mutations must be audit logged
* No hard deletes of regulated records
* AI cannot bypass rule engines
* Tenant data must remain cryptographically isolated
* All irreversible operations require dual authorization

**Dependency Rule** All epics (E01–E08 and beyond) depend on E00. No domain module may go to production without E00 enforcement hooks.  
  
E00 is complete only when:

* All modules inherit audit middleware
* All write endpoints pass rule validation
* Tenant isolation verified
* AI gateway restricted to proposal-only mode
* Policy Governance Service operational
* Policy Resolver enforced in rule engine
* Security test suite passes (privilege, injection, tenant breach)

This epic is non-negotiable and must precede domain deployment.\n\n### Child Stories\n#### Story: [AV-193] E00-S01 — Data Classification & Sensitivity Model\n**Status:** Done\n\n> **Story**  
As the platform, I must classify all stored data by sensitivity level to enforce encryption and retention rules.

**Description**  
Define data categories: PUBLIC, INTERNAL, CONFIDENTIAL, REGULATED (PII, Finance, Biometric, Transcript). Each entity must carry a sensitivity flag. Encryption and masking policies applied automatically.

**Must Align With**

* Layer 1: Entity metadata extension
* Layer 4: Field-level masking
* Layer 6: Access log capture

**Acceptance Criteria**

* All models tagged with sensitivity level
* Encrypted-at-rest for CONFIDENTIAL and REGULATED
* Masking in logs and AI context\n\n#### Story: [AV-194] E00-S02 — Immutable Audit Ledger\n**Status:** Done\n\n> **Story**  
As an institution, I must have tamper-evident audit logs for every critical operation.

**Description**  
Create append-only audit ledger storing: actor, role, action, entity, timestamp, hash. Ledger entries chained via cryptographic hash to detect tampering.

**Must Align With**

* Layer 6: System logbook
* Layer 4: Lock after commit

**Acceptance Criteria**

* No update/delete on audit table
* Hash chain verification endpoint
* Admin export capability\n\n#### Story: [AV-195] E00-S03 — Tenant Isolation Enforcement\n**Status:** Done\n\n> **Story**  
As a multi-institution system, I must ensure complete logical and cryptographic isolation between tenants.

**Description**  
All queries scoped by tenant_id. Enforce row-level security. Optional tenant-specific encryption keys. AI context restricted per tenant.

**Must Align With**

* Layer 1: Tenant scoping
* Layer 2: AI isolation
* Layer 4: Query validation middleware

**Acceptance Criteria**

* No cross-tenant queries allowed
* Tenant context required in every API call
* Automated isolation tests\n\n#### Story: [AV-196] E00-S04 — Privilege Escalation & Dual Control\n**Status:** Done\n\n> **Story**  
As the system, I must prevent unauthorized privilege escalation and require dual approval for critical actions.

**Description**  
Define time-bound elevated access tokens. Critical operations (result publish, payroll release, transcript seal) require 2-authority confirmation.

**Must Align With**

* Layer 5: Authority enforcement
* Layer 4: Time-bound locks

**Acceptance Criteria**

* Elevated role expires automatically
* Dual approval required for flagged operations
* Escalation logged\n\n#### Story: [AV-197] E00-S05 — Incident Response & Lockdown Mode\n**Status:** Done\n\n> **Story**  
As system administrator, I must be able to trigger institutional lockdown during a security incident.

**Description**  
Lockdown mode disables non-essential writes, blocks AI invocation, and forces MFA reauthentication. Includes account freeze and mass token invalidation.

**Must Align With**

* Layer 4: System-wide write gate
* Layer 6: Incident log

**Acceptance Criteria**

* Global flag toggles system mode
* Non-admin writes blocked
* All sessions invalidated\n\n#### Story: [AV-198] E00-S06 — AI Boundary Enforcement\n**Status:** Done\n\n> **Story**  
As the platform, I must ensure AI cannot execute state mutations or bypass policies.

**Description**  
All AI outputs pass through validation middleware. AI responses tagged as PROPOSAL. No direct DB access. Prompt injection detection layer required.

**Must Align With**

* Layer 2: Agent execution policy
* Layer 4: Rule validation engine

**Acceptance Criteria**

* AI cannot call mutation endpoints
* Injection attempts flagged
* PII masked before AI context injection\n\n#### Story: [AV-199] E00-S07 — Data Retention & Deletion Policy Engine\n**Status:** Done\n\n> **Story**  
As the institution, I must define retention periods for different data classes.

**Description**  
Define retention matrix (e.g., attendance: 5 yrs, transcript: permanent, biometric logs: 2 yrs). Automatic archival jobs required. No deletion of REGULATED data without legal workflow.

**Must Align With**

* Layer 1: Retention metadata
* Layer 4: Archival locks

**Acceptance Criteria**

* Scheduled archival service
* Deletion requires superadmin + log
* Retention audit report\n\n#### Story: [AV-200] E00-S08 — Field-Level Change Tracking\n**Status:** Done\n\n> **Story**  
As compliance officer, I must know exactly which fields changed, by whom, and when.

**Description**  
Implement per-field diff tracking for critical entities (marks, payroll, fee, transcript). Previous values stored encrypted.

**Must Align With**

* Layer 6: Field-level audit
* Layer 4: No silent mutation

**Acceptance Criteria**

* Diff log per entity
* Viewable in admin console
* Tamper detection enabled\n\n#### Story: [AV-201] E00-S09 — Policy Governance & Registry Service\n**Status:** Done\n\n> **Story**  
As the institution, I must manage institutional policies through a structured, versioned, and approval-gated governance framework.

**Description**  
Implement a dedicated Policy Service positioned between UI and Rule Engine. Policies must never exist as free-text or embedded in AI weights. Each policy must be structured, parameterized, versioned, time-bound, and approval-controlled.

The Policy Service must:

* Store policies in structured JSON format
* Support draft → approval → activation workflow
* Enforce effective_from and effective_to dates
* Generate immutable policy versions
* Emit PolicyActivated events
* Provide read-only API for rule engine consumption

Policies must not be editable once activated. Retroactive mutation is prohibited.

**Must Align With**

* Layer 1: Policy entity schema
* Layer 3: Legal activation event
* Layer 4: Immutable version locking
* Layer 6: Full policy audit log

**Acceptance Criteria**

* API: `POST /policy/draft`
* API: `POST /policy/submit`
* API: `POST /policy/approve`
* API: `GET /policy/:policyId?date=`
* Every policy version hash stored
* Diff viewer available in admin UI\n\n#### Story: [AV-202] E00-S10 — Policy Resolver Middleware\n**Status:** Done\n\n> **Story**  
As the rule engine, I must always resolve the correct active policy version before executing any institutional decision.

**Description**  
Implement a Policy Resolver middleware layer that:

* Retrieves correct version based on decision date
* Prevents execution if no active version exists
* Caches active policy safely
* Logs policy_version_used in every decision event

This middleware must be mandatory for all rule validations across modules.

**Must Align With**

* Layer 3: Deterministic decision binding
* Layer 4: Non-bypassable enforcement
* Layer 6: Decision audit linkage

**Acceptance Criteria**

* All rule executions include policy_version reference
* No module can access raw policy DB directly
* Resolver required in CI tests\n\n---\n\n## Epic: [AV-113] EPIC E01 — PLATFORM CORE & SECURITY\n**Status:** Done\n\n### Epic Description\n**Objective**  
Build the foundational execution substrate for the ALIS system. This epic establishes identity, authority, state legality enforcement, global locks, and auditability. No downstream module, wizard, or AI agent may execute outside the constraints defined here.

**Context**  
ALIS is an Agentic Operating System, not a passive ERP. The platform must actively prevent illegal institutional states rather than merely recording actions. This epic implements Layers 3–6 of the ALIS Master Architecture and provides the enforcement mechanisms that all modules depend on.

**Authoritative Reference**  
All implementation MUST strictly follow the _ALIS Master Developer Document_. In case of ambiguity, the Master Document prevails.

**Out of Scope**

* Domain logic (Admissions, Academics, Exams, etc.)
* Wizard UI flows
* AI reasoning logic (handled in E03)

**Blocking Rule**  
No other epic may progress beyond scaffolding until E01 core invariants are operational.

**E01 is complete only when:**

* All API calls are RBAC+ guarded
* State transitions are enforced centrally
* Global Locks override all modules
* Overrides are auditable and controlled
* Multi-tenant isolation is proven\n\n### Child Stories\n#### Story: [AV-114] E01-S01 — Core Identity Model\n**Status:** Done\n\n> **Story**  
As the platform, I need a canonical identity model to represent all actors and system agents.

**Description**  
Implement the base identity entities used across ALIS, independent of domain context. This includes human users, AI agents, and system actors.

**Must Align With**

* Layer 5 (Roles, Authority & Quorum)

**Acceptance Criteria**

* Canonical `User` entity with immutable ID
* Supports human + AI agent identities
* Status lifecycle: ACTIVE, SUSPENDED, ARCHIVED
* No domain-specific fields
* Soft-delete only\n\n#### Story: [AV-115] E01-S02 — Authentication & Session Control\n**Status:** Done\n\n> **Story**  
As a user or system actor, I must authenticate securely before performing any action.

**Description**  
Implement authentication primitives and session control. This includes login, token issuance, session expiry, and device awareness.

**Must Align With**

* Security Model: RBAC+

**Acceptance Criteria**

* Password hashing (no plaintext ever)
* Token-based authentication
* Session expiry & revocation
* Failed login protection
* No module-level bypass\n\n#### Story: [AV-116] E01-S03 — Role-Based Access Control (RBAC)\n**Status:** Done\n\n> **Story**  
As the platform, I must restrict access based on role.

**Description**  
Implement role-based permission checks as the first security gate. Roles must be declarative and not hard-coded into business logic.

**Must Align With**

* Blueprint C — RBAC+

**Acceptance Criteria**

* Role definitions (Student, Faculty, Admin, Agent, etc.)
* Permission mapping
* Middleware-level enforcement
* No controller-level shortcuts\n\n#### Story: [AV-117] E01-S04 — Context & Attribute-Based Access (ABAC)\n**Status:** Done\n\n> **Story**  
As the platform, I must enforce permissions based on context, not just role.

**Description**  
Extend RBAC to RBAC+ by introducing contextual checks such as course ownership, exam state, evaluation windows, etc.

**Must Align With**

* Layer 5 (Authority & Quorum)

**Acceptance Criteria**

* Context-aware permission evaluation
* Works alongside RBAC (not replacing)
* Default deny
* Explicit failure reasons\n\n#### Story: [AV-118] E01-S05 — Organization & Tenant Isolation\n**Status:** Done\n\n> **Story**  
As the platform, I must guarantee institutional data isolation.

**Description**  
Implement multi-tenant architecture ensuring that no data or action crosses institutional boundaries unless explicitly authorized.

**Must Align With**

* Layer 1 (Module Authority)
* Layer 4 (Global Locks)

**Acceptance Criteria**

* Organization entity
* Department / unit hierarchy
* Mandatory `org_id` scoping
* Super-admin access fully audited\n\n#### Story: [AV-119] E01-S06 — Central State Registry\n**Status:** Done\n\n> **Story**  
As the platform, I must enforce legal state transitions.

**Description**  
Implement the canonical state registry and state machine enforcement defined in Layer 3. All state transitions must be declared and validated.

**Must Align With**

* Layer 3 (State Machines & Legality)

**Acceptance Criteria**

* Explicit state definitions
* Allowed transition matrix
* Runtime rejection of illegal transitions
* Forward-only invalidation via ANNULLED\n\n#### Story: [AV-120] E01-S07 — Global Locks & Invariants Engine\n**Status:** Done\n\n> **Story**  
As the platform, I must prevent globally illegal actions regardless of module logic.

**Description**  
Implement the Global Lock engine that overrides all module and wizard decisions.

**Examples**

* No exam if attendance < threshold
* No hall ticket if dues pending

**Must Align With**

* Layer 4 (Global Locks & Invariants)

**Acceptance Criteria**

* Central lock evaluation
* Evaluated before any decision
* Non-bypassable
* Explicit violation reasons\n\n#### Story: [AV-121] E01-S08 — Override Framework (First-Class Entity)\n**Status:** Done\n\n> **Story**  
As the platform, I must allow controlled overrides with full auditability.

**Description**  
Implement override lifecycle management as a first-class system entity.

**Lifecycle**  
REQUESTED → APPROVED → EXECUTED → CLOSED

**Must Align With**

* Layer 6 (Resilience & Reality Handling)

**Acceptance Criteria**

* Overrides require reason
* Quorum support
* Immutable audit trail
* Time-bound validity\n\n#### Story: [AV-122] E01-S10 — System Configuration Registry\n**Status:** Done\n\n> **Story**  
As the platform, I must manage configurable policy parameters centrally.

**Description**  
Implement a configuration registry for policy (not logic, not invariants).

**Must Align With**

* Policy vs Logic vs Invariant separation

**Acceptance Criteria**

* Versioned configs
* Change history
* Read-only to non-admins
* No runtime mutation of invariants\n\n#### Story: [AV-123] E01-S11 — Security Guardrails & Hardening\n**Status:** Done\n\n> **Story**  
As the platform, I must fail safely and securely.

**Description**  
Implement baseline security protections.

**Acceptance Criteria**

* Rate limiting
* Input validation
* Permission guardrails
* No sensitive error leakage
* Default deny posture\n\n#### Story: [AV-124] E01-S09 — Global Audit Log\n**Status:** Done\n\n> **Story**  
As the institution, I need an immutable record of all critical actions.

**Description**  
Implement a system-wide append-only audit log.

**Must Align With**

* Regulatory defensibility

**Acceptance Criteria**

* Actor, action, entity, timestamp
* Immutable storage
* Queryable by authorized roles
* No silent writes\n\n---\n\n## Epic: [AV-126] EPIC E02 — SHARED SERVICES\n**Status:** Done\n\n### Epic Description\n**Objective**  
Build the shared, reusable infrastructure services required by all ALIS modules and wizards. This epic provides standardized mechanisms for workflows, approvals, notifications, documents, files, and search that prevent duplication and ensure consistent behavior across the platform.

**Context**  
ALIS is a rule-driven institutional operating system. Shared capabilities such as approvals, notifications, file handling, and workflows must be centralized so that domain modules focus only on domain intent, not plumbing.

**Authoritative Reference**  
All implementations MUST conform to the _ALIS Master Developer Document_. Shared Services may not embed domain logic or violate policy, invariant, or authority layers defined therein.

**Out of Scope**

* Business rules of specific modules
* AI reasoning or generation (handled in E03)
* UI styling and presentation concerns

**Dependency Rule**  
E02 depends on E01 (Platform Core & Security).  
No domain epic may implement its own workflow, notification, or document logic.

**E02 is complete only when:**

* All workflows run through the shared engine
* All approvals use the quorum framework
* All notifications are centrally dispatched
* No module implements its own file, doc, or workflow logic
* Shared services are reusable and policy-safe\n\n### Child Stories\n#### Story: [AV-127] E02-S01 — Workflow Engine\n**Status:** Done\n\n> **Story**  
As the platform, I need a generic workflow engine to orchestrate multi-step institutional processes.

**Description**  
Implement a reusable workflow engine that supports step-based execution, approvals, rejections, escalations, and completion. Domain modules define workflows declaratively; execution is handled centrally.

**Must Align With**

* Layer 3 (State Machines & Legality)
* E01 State Registry

**Acceptance Criteria**

* Define workflow templates declaratively
* Support states: CREATED, IN_PROGRESS, APPROVED, REJECTED, COMPLETED
* Workflow instances are auditable
* No domain logic inside engine
* Illegal transitions rejected\n\n#### Story: [AV-128] E02-S02 — Approval & Quorum Framework\n**Status:** Done\n\n> **Story**  
As the platform, I must support approval chains and quorum-based decisions.

**Description**  
Implement a generic approval framework supporting single-approver, multi-approver, and quorum-based approvals.

**Must Align With**

* Layer 5 (Roles, Authority & Quorum)

**Acceptance Criteria**

* Approval rules configurable per workflow
* Role-based approvers
* Quorum thresholds supported
* Approval actions audited
* No hard-coded approver logic\n\n#### Story: [AV-129] E02-S03 — Notification Dispatcher\n**Status:** Done\n\n> **Story**  
As the platform, I must notify users of important events.

**Description**  
Implement a centralized notification service used by all modules.

**Channels**

* Email
* SMS
* WhatsApp (pluggable)

**Must Align With**

* Shared Services only (no domain logic)

**Acceptance Criteria**

* Template-based notifications
* Channel abstraction
* Retry & failure handling
* Delivery status tracking
* No direct notifications from modules\n\n#### Story: [AV-130] E02-S04 — Template & Document Generation Service\n**Status:** Done\n\n> **Story**  
As the platform, I must generate official documents from system data.

**Description**  
Implement a document generation service for PDFs and official communications.

**Examples**

* Offer letters
* Hall tickets
* Receipts
* Certificates

**Acceptance Criteria**

* Template-driven generation
* Dynamic data binding
* Versioned templates
* Immutable generated documents
* Audit log on generation\n\n#### Story: [AV-131] E02-S05 — File Storage & Versioning Service\n**Status:** Done\n\n> **Story**  
As the platform, I must securely store and version files.

**Description**  
Implement centralized file storage with version control.

**Examples**

* Student documents
* Exam scripts
* Research papers

**Must Align With**

* Tenant isolation
* Audit requirements

**Acceptance Criteria**

* Versioned uploads
* Immutable previous versions
* Access controlled via RBAC+
* Secure storage abstraction
* No direct filesystem access by modules\n\n#### Story: [AV-132] E02-S06 — Global Search & Indexing\n**Status:** Done\n\n> **Story**  
As the platform, I must support fast, secure search across entities.

**Description**  
Implement a shared search and indexing layer.

**Acceptance Criteria**

* Index core entities (users, courses, documents, workflows)
* Permission-aware search results
* Extensible index schema
* No raw DB search from modules\n\n#### Story: [AV-133] E02-S07 — Commenting & Activity Feed\n**Status:** Done\n\n> **Story**  
As the platform, I must support contextual comments and activity logs.

**Description**  
Implement a generic commenting and activity feed system attachable to any entity.

**Acceptance Criteria**

* Entity-agnostic comments
* Role-based visibility
* Timestamped entries
* Immutable history
* No business logic inside comments\n\n#### Story: [AV-134] E02-S08 — Task & Reminder Engine\n**Status:** Done\n\n> **Story**  
As the platform, I must create system-driven tasks and reminders.

**Description**  
Implement a task/reminder engine triggered by workflows, deadlines, and policies.

**Examples**

* “Upload documents”
* “Approve request”
* “Submit feedback”

**Acceptance Criteria**

* Task assignment by role or user
* Due dates and escalation
* Completion tracking
* Reminder notifications
* No UI-only tasks\n\n#### Story: [AV-135] E02-S09 — Event Bus / Internal Messaging\n**Status:** Done\n\n> **Story**  
As the platform, I must emit and consume system events.

**Description**  
Implement an internal event bus for cross-module signaling.

**Examples**

* Enrollment completed
* Fees cleared
* Exam published

**Acceptance Criteria**

* Publish/subscribe model
* Event schema versioning
* No direct module-to-module calls
* Auditable event emission\n\n#### Story: [AV-136] E02-S10 — Shared Validation & Error Framework\n**Status:** Done\n\n> **Story**  
As the platform, I must return consistent, explainable errors.

**Description**  
Implement a shared validation and error handling framework.

**Acceptance Criteria**

* Standard error formats
* User-safe messages
* Machine-readable error codes
* No raw exception leaks
* Policy violations clearly surfaced\n\n---\n\n## Epic: [AV-137] Epic E03 – AI Gateway & Agents\n**Status:** To Do\n\n### Epic Description\n**Objective**  
Build the centralized AI execution layer of the platform. This epic defines how all AI models, agents, prompts, tools, and retrieval mechanisms operate within ALIS under strict legal, policy, and authority constraints.

**Context**  
ALIS is not an “AI feature platform.”  
AI in ALIS is a **constrained institutional actor** that may propose decisions, generate artifacts, and analyze data — but **never execute authority, mutate state, or bypass policy**.

This epic implements Layer 2 (Agentic Decisions) and integrates tightly with Layers 3–5 to ensure all AI output is advisory unless explicitly ratified by rules and authority.

**Authoritative Reference**  
All implementations MUST strictly conform to the _ALIS Master Developer Document_, including:

* “Agents draft, rules decide”
* “AI is read-only with respect to state”
* “No cloud LLM usage”

**Hard Constraints**

* Local / self-hosted LLMs only (e.g., LLaMA family)
* No OpenAI, Anthropic, or external cloud inference
* No direct database writes by AI agents
* No autonomous execution of irreversible actions

**Out of Scope**

* Domain business logic
* UI presentation
* Wizard-specific workflows (defined in domain epics)

**Dependency Rule**  
E03 depends on:

* E01 – Platform Core & Security
* E02 – Shared Services

No domain epic may invoke AI directly outside this gateway.

‌

**E03 is complete only when:**

* All AI calls go through the Gateway
* No agent can mutate system state
* Prompts and agents are versioned and auditable
* Local LLMs operate without cloud dependency
* AI output is always constrained, reviewable, and accountable\n\n### Child Stories\n#### Story: [AV-138] E03-S01 — AI Gateway Core\n**Status:** Ready For Review\n\n> **Story**  
As the platform, I need a single, controlled gateway through which all AI interactions occur.

**Description**  
Implement a centralized AI Gateway service that all modules and wizards must use to invoke AI capabilities.

**Must Align With**

* Blueprint B — AI Agent Architecture

**Acceptance Criteria**

* Single API surface for AI calls
* No direct model invocation elsewhere in codebase
* Request/response fully logged (metadata only)
* RBAC-protected access
* Tenant-aware invocation\n\n#### Story: [AV-139] E03-S02 — Local LLM Runtime Integration\n**Status:** Ready For Review\n\n> **Story**  
As the platform, I must run AI inference using locally hosted models.

**Description**  
Integrate locally hosted LLM runtimes (e.g., LLaMA via Ollama or equivalent) under air-gapped constraints.

**Hard Rules**

* No external network calls
* No telemetry leaks

**Acceptance Criteria**

* Model registry (model name, version, capability)
* Hot-swap support (model upgrades without refactor)
* Deterministic configuration
* Resource limits enforced\n\n#### Story: [AV-140] E03-S03 — Prompt Registry & Versioning\n**Status:** Ready For Review\n\n> **Story**  
As the platform, I must manage prompts as versioned, auditable assets.

**Description**  
Implement a centralized prompt registry used by all agents and wizards.

**Examples**

* UGC syllabus prompt
* Question paper generation prompt
* Feedback summarization prompt

**Acceptance Criteria**

* Prompt templates stored centrally
* Versioned prompts
* Prompt metadata (purpose, scope)
* No inline prompts inside modules
* Audit trail on prompt changes\n\n#### Story: [AV-141] E03-S04 — Agent Definition & Lifecycle\n**Status:** In Progress\n\n> **Story**  
As the platform, I must define AI agents as constrained, named actors.

**Description**  
Implement agent abstractions with explicit roles and scopes.

**Agent Examples**

* CourseBuilderAgent
* QuestionPaperAgent
* FeedbackSynthesizerAgent

**Acceptance Criteria**

* Agents have identity
* Agents declare allowed tools
* Agents cannot write to DB
* Agents produce structured outputs
* Agent execution logged\n\n#### Story: [AV-142] E03-S05 — Tool Invocation Framework\n**Status:** To Do\n\n> **Story**

As the platform, I must allow AI agents to invoke approved deterministic tools without granting authority or state mutation rights.

**Description**

Implement a controlled Tool Invocation Framework inside the AI Gateway.  
Tools must be pre-registered, versioned, and declared in the Agent DSL.  
No dynamic tool selection or autonomous chaining allowed.

‌

**Tool Examples**

RAGRetrieverTool

RubricValidatorTool

StructuredScoringTool

PolicyLookupTool

‌

**Acceptance Criteria**

Tools are registered in Tool Registry

Agents declare allowed tools in DSL

Undeclared tools are rejected

Tool output must match schema

Tool invocation is logged

Tools cannot write to DB

No tool chaining allowed

RAG implemented via this framework\n\n#### Story: [AV-145] E03-S06 — Retrieval & Knowledge Context (RAG)\n**Status:** To Do\n\n> **Story**  
As the platform, AI must ground outputs in institutional data.

**Description**  
Implement retrieval mechanisms to provide agents with contextual knowledge.

**Sources**

* Documents
* Policies
* Course data
* Research papers

**Acceptance Criteria**

* Embedding-based retrieval
* Tenant-isolated indexes
* Context size limits
* Source attribution preserved\n\n#### Story: [AV-146] E03-S07 — Output Structuring & Confidence Scoring\n**Status:** To Do\n\n> **Story**  
As the platform, AI outputs must be structured and assessable.

**Description**  
Enforce structured outputs (JSON / schemas) and confidence indicators.

**Acceptance Criteria**

* Schema-validated outputs
* Confidence or certainty scores
* Failure modes explicit
* No free-text-only outputs for decisions\n\n#### Story: [AV-147] E03-S08 — Guardrails & Safety Filters\n**Status:** To Do\n\n> **Story**  
As the platform, AI must not violate institutional or legal boundaries.

**Description**  
Implement guardrails on AI outputs.

**Guardrails Include**

* Toxicity filtering
* Hallucination detection
* Policy contradiction detection
* Unsafe suggestion blocking

**Acceptance Criteria**

* Guardrails applied pre- and post-generation
* Blocked outputs logged
* Safe fallback responses
* No silent failures\n\n#### Story: [AV-148] E03-S09 — Human-in-the-Loop Enforcement\n**Status:** To Do\n\n> **Story**  
As the platform, AI decisions must require human or rule ratification where mandated.

**Description**  
Implement mechanisms to route AI outputs through approval or policy checks before execution.

**Examples**

* Scholarship approval
* Revaluation grading
* Disciplinary summaries

**Acceptance Criteria**

* AI outputs never auto-commit
* Explicit approval states
* Clear handoff points
* Audit trail preserved\n\n#### Story: [AV-149] E03-S10 — AI Observability & Cost Controls\n**Status:** To Do\n\n> **Story**  
As the platform, I must monitor AI usage and performance.

**Description**  
Implement observability for AI execution.

**Acceptance Criteria**

* Invocation counts
* Latency tracking
* Failure rates
* Model usage metrics
* No user-visible telemetry leakage\n\n---\n\n## Epic: [AV-150] Epic E04 – Admissions\n**Status:** To Do\n\n### Epic Description\n**Objective**  
Automate the end-to-end university admissions lifecycle — from lead capture to enrolled student — by building policy-compliant workflows, AI-assisted evaluations, offer issuance, and state-locked enrollment handoff. This epic enforces strict forward-only state transitions across 9 wizards, with full auditability and RBAC governance.

**Context**  
ALIS treats admissions not as a form-processing pipeline but as a state machine where legality, eligibility, and authority are enforced at every step. Each wizard is designed to transform institutional state (e.g., LEAD → APPLIED, ELIGIBLE → ADMITTED) and must obey policy locks, AI advisory patterns, and audit trails.

Admissions logic spans all 6 layers of the ALIS architecture:

* Layer 1: Entity definitions (Applicant, Document, Lead)
* Layer 2: Agents (Eligibility Scoring, Counsellor Matching)
* Layer 3: Legal transitions
* Layer 4: Global policy locks
* Layer 5: RBAC-based override control
* Layer 6: Observability and audit

**Authoritative Reference**  
All logic must conform to:

* ALIS Master Developer Document
* Forward-only transitions
* “AI proposes, rules enforce”
* All overrides require justification + signature
* No UI-side policy

**Hard Constraints**

* No direct database writes from agents
* No backward state mutation (e.g., ADMITTED → ELIGIBLE)
* No offer letters without eligibility check
* No enrollment without document verification

**Out of Scope**

* Post-enrollment academic flows (see E05)
* Financial transactions (handled in E07)

**Dependency Rule** Depends on:

* E01 – Platform Core & Security
* E02 – Shared Services
* E03 – AI Gateway & Agents\n\n### Child Stories\n#### Story: [AV-151] E04-S01 — Applicant Wizard\n**Status:** To Do\n\n> **Story**  
As an applicant, I must submit my details and generate an application record.

**Description**  
Define the `Applicant` model with fields: name, email, phone, intended_program, source_channel, and status (LEAD → APPLIED). Enforce uniqueness on email/phone. Application form must validate input on backend and trigger the legal state transition to `APPLIED`.

**Must Align With**

* Layer 1: Entity definition
* Layer 3: Legal transition
* Layer 4: Lock if duplicate exists

**Acceptance Criteria**

* API: `POST /applicants`
* UI: Form submission → APPLIED
* Duplicate detection enforced
* Transition logged\n\n#### Story: [AV-152] E04-S02 — Lead De-duplication Wizard\n**Status:** To Do\n\n> **Story**  
As the system, I must identify and merge duplicate leads safely.

**Description**  
Implement fuzzy match (e.g., cosine, Jaro-Winkler) across leads. Store results in `LeadMergeLog`. If confidence > 0.9 → auto-merge. Otherwise, admin must approve merge via UI. All merges must preserve original lead IDs for audit.

**Must Align With**

* Layer 4: Lock if applicant already advanced
* Layer 6: Merge audit trail

**Acceptance Criteria**

* API: `POST /leads/merge`
* Merge log recorded
* Admin override with justification\n\n#### Story: [AV-153] E04-S03 — Eligibility Evaluation Wizard\n**Status:** To Do\n\n> **Story**  
As admissions staff, I must evaluate academic eligibility from uploaded documents.

**Description**  
Run LLM agent on uploaded marksheets to extract grades. Score against program threshold. Result: ELIGIBLE, NOT_ELIGIBLE, or PROVISIONAL. Store confidence and rationale. State transitions must be backend-only.

**Must Align With**

* Layer 2: Agent inference
* Layer 3: Transition legality
* Layer 4: Lock if missing docs

**Acceptance Criteria**

* API: `POST /eligibility/evaluate`
* AI agent must not mutate state directly
* Transition executed by orchestrator\n\n#### Story: [AV-154] E04-S04 — Document Verification Wizard\n**Status:** To Do\n\n> **Story**  
As an admissions officer, I must verify the authenticity of submitted documents.

**Description**  
Define `ApplicationDocument` entity. Each file must pass OCR, LLM stamp/seal detection, and date validity check. Docs must be verified before offer generation is allowed.

**Must Align With**

* Layer 2: AI for verification
* Layer 4: Locks on invalid/missing docs

**Acceptance Criteria**

* API: `POST /documents/upload`
* is_verified = true/false
* Admin override with log\n\n#### Story: [AV-155] E04-S05 — Counsellor Allocation Wizard\n**Status:** To Do\n\n> **Story**  
As the system, I must assign the best-fit counsellor to each applicant.

**Description**  
Run vector search between applicant profile and counsellor embeddings. Score top matches. Assign counsellor with lowest load, unless policy lock or override required.

**Must Align With**

* Layer 2: Embedding agent
* Layer 4: Lock if capacity exceeded

**Acceptance Criteria**

* API: `POST /counsellors/assign`
* Manual reassignment with reason\n\n#### Story: [AV-156] E04-S06 — Offer Letter Generation Wizard\n**Status:** To Do\n\n> **Story**  
As an eligible applicant, I should receive a signed offer letter.

**Description**  
Generate templated PDF offer letters only if eligibility and documents are verified. Templates are versioned. Letters are immutable post-issue.

**Must Align With**

* Layer 3: Only ELIGIBLE applicants
* Layer 4: No offer if seats full

**Acceptance Criteria**

* PDF must be generated server-side
* No offer if block present
* Link emailed and visible on UI\n\n#### Story: [AV-157] E04-S07 — Admission Confirmation Wizard\n**Status:** To Do\n\n> **Story**  
As an applicant, I must confirm my seat by paying fees and locking my admission.

**Description**  
Confirm payment reconciliation, freeze seat, and transition to `ADMITTED`. Generate institutional reg. number and log admission event.

**Must Align With**

* Layer 3: Legal transition
* Layer 4: Block if fee unpaid

**Acceptance Criteria**

* Payment required flag
* Reg. number format enforced
* State moved to ADMITTED\n\n#### Story: [AV-158] E04-S08 — Intake Quality Scoring Wizard\n**Status:** To Do\n\n> **Story**  
As the admissions dean, I want to assess batch quality.

**Description**  
Run a regression model across applicant scores, profiles, and yield metrics. Output a `quality_score` per intake. Low score should raise alerts for leadership.

**Must Align With**

* Layer 2: Analytical agent
* Layer 6: Observability

**Acceptance Criteria**

* Batch score stored and timestamped
* Alert if below threshold\n\n#### Story: [AV-159] E04-S09 — Enrollment Handover Wizard\n**Status:** To Do\n\n> **Story**  
As the registrar, I want to transition ADMITTED applicants into ENROLLED students.

**Description**  
Finalize enrollment by migrating data into the student registry. Create `Student` record, assign roll number, and mark state ENROLLED.

**Must Align With**

* Layer 3: Legal transition
* Layer 4: Must pass all locks

**Acceptance Criteria**

* ETL to student registry
* Roll number format enforced
* Enrollment audit event triggered\n\n---\n\n## Epic: [AV-160] Epic E05 – Academics\n**Status:** To Do\n\n### Epic Description\n**Objective**  
Build the academic core of ALIS, covering curriculum design, course allocation, timetabling, attendance, and instructional delivery. This epic implements the Learning Engine from Curriculum → Delivery.

**Context**  
ALIS Academics engine formalizes course structure and session planning with intelligent assistants and programmatic enforcement of attendance, syllabus completion, and faculty responsibilities. All academic interactions must comply with UGC/AICTE regulations and institutional standards defined in policy layers.

State transitions (e.g., course assigned, timetable published, attendance locked) must be legal, auditable, and authority-bound. AI may suggest content or optimize timetables but cannot autonomously execute without rule-based ratification.

**Authoritative Reference** Must align with:

* ALIS Master Developer Document
* UGC/NAAC compliance standards
* No unauthorized attendance backfill or grading

**Constraints**

* Only verified faculty may create lesson plans or mark attendance
* Students cannot view unpublished course material
* Course builds must be derived from official syllabus unless flagged

**Dependency Rule** Depends on:

* E01: Platform Core & Security
* E02: Shared Services
* E03: AI Gateway & Agents\n\n### Child Stories\n#### Story: [AV-161] E05-S01 — Course Builder Wizard\n**Status:** To Do\n\n> **Story**  
As an academic admin, I must be able to generate program-aligned courses using AI based on UGC guidelines.

**Description**  
Course Builder must extract topics, modules, and credit weight from official syllabi using LLMs. Courses must be versioned and flagged as "derived" or "manual." No state transitions allowed without admin signature.

**Must Align With**

* Layer 1: Entity definition
* Layer 2: AI-generated suggestions
* Layer 3: Admin-locked creation

**Acceptance Criteria**

* API: `POST /courses`
* Flag derived vs manual
* Require approval signature before publish\n\n#### Story: [AV-162] E05-S02 — Faculty Mapping Wizard\n**Status:** To Do\n\n> **Story**  
As a department head, I need to assign verified faculty to the approved courses.

**Description**  
Faculty can be mapped only to courses where their program expertise aligns. Must respect teaching load caps. Assignment triggers downstream provisioning (LMS, attendance rights).

**Must Align With**

* Layer 1: Entity → FacultyCourseMap
* Layer 4: Load constraint lock
* Layer 5: Role-bound permissions

**Acceptance Criteria**

* Mapping must validate expertise field
* API logs assignment reason
* UI disables overload mappings\n\n#### Story: [AV-163] E05-S03 — Timetable Wizard\n**Status:** To Do\n\n> **Story**  
As an academic planner, I want to generate class schedules while avoiding faculty/time clashes.

**Description**  
Timetable creation is semi-automated. Agents can suggest optimal scheduling, but final approval is manual. All timetables must pass clash validation. Once published, it locks session dates.

**Must Align With**

* Layer 2: AI timetabling suggestions
* Layer 3: Publish transition is final
* Layer 6: Versioned timetable logs

**Acceptance Criteria**

* No room/time/faculty clash
* Suggestions can be overridden
* Timetable is read-only after publish\n\n#### Story: [AV-164] E05-S04 — Enrollment Wizard\n**Status:** To Do\n\n> **Story**  
As a student, I want to enroll in my semester courses according to eligibility and curriculum path.

**Description**  
Enrollment must follow credit and prerequisite policies. Once a student is enrolled, course visibility and attendance eligibility are activated.

**Must Align With**

* Layer 1: StudentCourse table
* Layer 3: Legal transition → enrolled
* Layer 4: Credit lock enforcement

**Acceptance Criteria**

* Must validate prerequisites
* Total credit load within policy
* Enrollment triggers LMS access\n\n#### Story: [AV-165] E05-S05 — Attendance Wizard\n**Status:** To Do\n\n> **Story**  
As a faculty, I must be able to mark session-level attendance and trigger shortage alerts.

**Description**  
Attendance must be session-specific. Once marked, it is locked unless override is approved. Alerts for low attendance must sync to disciplinary and exam eligibility modules.

**Must Align With**

* Layer 1: Attendance model with session FK
* Layer 4: Lock attendance after 48h
* Layer 6: Audit and alert generation

**Acceptance Criteria**

* Only mapped faculty may mark
* Late edit requires approval
* Alert if < 75% threshold reached\n\n#### Story: [AV-166] E05-S06 — Lesson Plan Wizard\n**Status:** To Do\n\n> **Story**  
As faculty, I must log my topic coverage and teaching plan per session.

**Description**  
Each course must have a session plan submitted in advance. Faculty may edit only until first session. AI may suggest plans based on syllabus.

**Must Align With**

* Layer 1: LessonPlan model
* Layer 2: AI suggestions allowed
* Layer 5: Edit rights limited to faculty role

**Acceptance Criteria**

* Submission required before class
* Locked after session start
* AI logs must be separate from final plan\n\n#### Story: [AV-167] E05-S07 — LMS Upload Wizard\n**Status:** To Do\n\n> **Story**  
As faculty, I want to upload lecture materials, notes, and readings to the course portal.

**Description**  
Content must be associated with the right session. Students may only access published content. Unpublished material is invisible to learners.

**Must Align With**

* Layer 1: MaterialSessionLink model
* Layer 4: Content visibility lock
* Layer 6: Content versioning

**Acceptance Criteria**

* Upload must specify session ID
* Only published content visible to students
* File audit trail enforced\n\n#### Story: [AV-168] E05-S08 — Assignment Grader Wizard\n**Status:** To Do\n\n> **Story**  
As a faculty, I must evaluate and grade submitted student assignments.

**Description**  
Submissions are timestamped. Grading must comply with rubric if uploaded. AI assistance allowed for similarity and rubric validation, but not final scoring.

**Must Align With**

* Layer 1: AssignmentSubmission entity
* Layer 2: Agentic grading aid
* Layer 5: Final grade input must be manual

**Acceptance Criteria**

* Rubric is optional but enforced if uploaded
* Similarity score advisory only
* Faculty-only scoring rights\n\n#### Story: [AV-169] E05-S09 — Feedback Wizard\n**Status:** To Do\n\n> **Story**  
As a student, I must be able to provide course and faculty feedback.

**Description**  
Feedback must be anonymous and time-locked per semester. Faculty may view summaries only after grade submission.

**Must Align With**

* Layer 1: Feedback model (anonymous FK)
* Layer 4: Time lock enforcement
* Layer 6: Report access policy

**Acceptance Criteria**

* No editable feedback
* Lockout if grades not submitted
* Admin-only export rights\n\n#### Story: [AV-170] E05-S10 — Mentorship Wizard\n**Status:** To Do\n\n> **Story**  
As a faculty mentor, I must log and track meetings with my assigned mentees.

**Description**  
Every session must include date, discussion topic, and outcomes. Logs must be accessible to the Dean but not editable post-lock.

**Must Align With**

* Layer 1: MentorshipLog table
* Layer 4: Post-lock immutability
* Layer 6: Visibility = Dean only

**Acceptance Criteria**

* Date/topic mandatory
* Lock after 24h of submission
* Read-only access to Deans\n\n---\n\n## Epic: [AV-171] Epic E06 – Examinations\n**Status:** To Do\n\n### Epic Description\n**Objective**  
Establish a secure, auditable, and policy-driven examination lifecycle—from exam form registration through transcript issuance. This epic implements the ALIS Certification Engine.

**Context**  
ALIS treats assessments as regulated state transitions involving high-integrity operations (hall ticket generation, paper setting, evaluation, and result declaration). All critical stages require immutable logs, policy locks, and dual-layer approvals. AI may assist but cannot execute core academic authority actions.

Exam workflows must be mapped to academic calendar, program structures, invigilator responsibilities, and revaluation processes. All output—grades, scorecards, seating plans—must be versioned, retrievable, and locked post-issue.

**Authoritative Reference**

* ALIS Master Developer Document
* University ordinances on exams and revaluation
* UGC/NAAC guidelines for assessment

**Constraints**

* AI cannot generate final grades or results
* Hall tickets require verified enrollment and fee clearance
* No backdated evaluation or result overrides

**Dependency Rule** Depends on:

* E01 – Platform Core & Security
* E02 – Shared Services
* E05 – Academics (session data, attendance, grading rights)\n\n### Child Stories\n#### Story: [AV-172] E06-S01 — Exam Calendar Wizard\n**Status:** To Do\n\n> **Story**  
As the controller of exams, I must publish the semester-wise exam calendar and freeze it after release.

**Description**  
Define calendar entities: exam_type, semester, date_range, linked_courses. Must allow pre-release editing but become immutable after publication. Syncs downstream to forms and seating.

**Must Align With**

* Layer 1: Calendar entity schema
* Layer 3: Legal publish event
* Layer 4: Lock after release

**Acceptance Criteria**

* Only COE may publish
* API: `POST /exam-calendar`
* Calendar versioning enforced\n\n#### Story: [AV-173] E06-S02 — Exam Form Wizard\n**Status:** To Do\n\n> **Story**  
As a student, I must fill and submit my exam form to become eligible for appearing.

**Description**  
Forms must validate course enrollment, attendance %, fee clearance. Must track submission timestamp. No retroactive submissions allowed.

**Must Align With**

* Layer 4: Gate if attendance < 75%
* Layer 1: ExamForm table with FK to semester
* Layer 6: Immutable submission log

**Acceptance Criteria**

* Blocked if fee unpaid or short attendance
* Timestamp stored
* API: `POST /exam-form/submit`\n\n#### Story: [AV-174] E06-S03 — Hall Ticket Wizard\n**Status:** To Do\n\n> **Story**  
As a verified student, I must download my system-generated hall ticket.

**Description**  
Hall tickets must pull seating plan, course code, exam slot, and student photo. Tickets locked after generation. Barcode and QR code required.

**Must Align With**

* Layer 1: HallTicket schema
* Layer 4: Generate only after form + approval
* Layer 6: Ticket version log

**Acceptance Criteria**

* Generated only if exam form submitted
* QR embedded for validation
* API: `GET /hall-ticket/:studentId`\n\n#### Story: [AV-175] E06-S04 — Question Paper Wizard\n**Status:** To Do\n\n> **Story**  
As a faculty-in-charge, I must generate AI-assisted question papers under exam cell supervision.

**Description**  
LLM suggests draft papers with 3-part structure (MCQ, LA, case). Final paper must be approved and digitally sealed. Paper release is logged.

**Must Align With**

* Layer 2: AI paper drafts
* Layer 4: Lock after approval
* Layer 5: Dual-sign control (Faculty + COE)

**Acceptance Criteria**

* API logs approver identity
* Paper is auto-archived after print
* Generated under secure session\n\n#### Story: [AV-176] E06-S05 — Invigilator Roster Wizard\n**Status:** To Do\n\n> **Story**  
As exam staff, I must schedule and notify invigilators for each exam session.

**Description**  
Each room must have mapped invigilators. Avoid same-day double shifts. Notify faculty 48h in advance. Emergency override allowed with log.

**Must Align With**

* Layer 1: Roster entity
* Layer 4: Clash detection and lock
* Layer 6: Email/SMS logs

**Acceptance Criteria**

* Each slot must have 2 invigilators minimum
* Conflicts auto-flagged
* Notifications logged\n\n#### Story: [AV-177] E06-S06 — Seating Plan Wizard\n**Status:** To Do\n\n> **Story**  
As the COE cell, I must generate room-wise seating plans with roll number mappings.

**Description**  
Seating plans must randomize rows, prevent friends in same row. Plans versioned per session. Audit trail required.

**Must Align With**

* Layer 1: SeatingPlan schema
* Layer 4: Lock before exam starts
* Layer 6: Version + revision history

**Acceptance Criteria**

* Must validate no repeat roll numbers per room
* Downloadable PDF export
* Locked 12h before session\n\n#### Story: [AV-178] E06-S07 — Script Barcode Wizard\n**Status:** To Do\n\n> **Story**  
As the controller, I must generate barcode identifiers to anonymize answer sheets.

**Description**  
Each barcode must encode course, session, and anonymized roll. Barcode mapping stored in secured vault.

**Must Align With**

* Layer 1: ScriptBarcode table
* Layer 4: Tamper-evident lock
* Layer 6: Vault mapping

**Acceptance Criteria**

* Barcode printable on secure template
* Mapping encrypted
* API: `GET /barcode/:examId`\n\n#### Story: [AV-179] E06-S08 — Marks Entry Wizard\n**Status:** To Do\n\n> **Story**  
As an evaluator, I must enter student marks using hybrid AI assist (MCQ autograde + manual score).

**Description**  
MCQ score is computed by AI, but long answers scored manually. Partial scores allowed. Lock after submission.

**Must Align With**

* Layer 1: Marks entity
* Layer 2: MCQ grading AI
* Layer 5: Evaluator signature required

**Acceptance Criteria**

* Total = MCQ + manual
* Only assigned evaluator may enter
* Audit record per entry\n\n#### Story: [AV-180] E06-S09 — Revaluation Wizard\n**Status:** To Do\n\n> **Story**  
As a student, I may request revaluation of my exam scripts with payment.

**Description**  
Allow reval only if declared grade is within reval band. New marks override only if deviation exceeds ±5%. Reval status must be visible.

**Must Align With**

* Layer 1: RevalRequest model
* Layer 4: Rule enforcement engine
* Layer 6: Visibility tracker

**Acceptance Criteria**

* API: `POST /reval/apply`
* Only one request per paper
* Reval result override rule enforced\n\n#### Story: [AV-181] E06-S10 — Result Declaration Wizard\n**Status:** To Do\n\n> **Story**  
As the COE, I must declare official semester results with SGPA computation.

**Description**  
Results must include subject-wise marks, SGPA, pass/fail status. Only published once signed by controller. Freeze all dependent modules.

**Must Align With**

* Layer 3: Legal declaration event
* Layer 5: COE-only signature
* Layer 6: Result log

**Acceptance Criteria**

* SGPA auto-calculated
* Final status stored and locked
* Publish event required\n\n#### Story: [AV-182] E06-S11 — Transcript Wizard\n**Status:** To Do\n\n> **Story**  
As an enrolled student, I should be able to download my digitally signed transcript.

**Description**  
Transcript must be auto-compiled from result logs, with GPA, course credits, and signature block. PDF version is institutionally sealed.

**Must Align With**

* Layer 1: Transcript entity
* Layer 4: No download before result lock
* Layer 6: Signature ledger

**Acceptance Criteria**

* GPA = sum(weighted grade points)
* Digital signature mandatory
* API: `GET /transcript/:studentId`\n\n---\n\n## Epic: [AV-183] Epic E07 – HR & Administration\n**Status:** To Do\n\n### Epic Description\n**Objective**  
Build the administrative backbone of ALIS to manage the full lifecycle of academic and non-academic staff—from job posting and onboarding to performance tracking and recordkeeping. This epic provides the human infrastructure for Payroll, Attendance, Appraisal, and Service Book operations.

**Context**  
This module governs who can access what within the ALIS ecosystem by provisioning users, roles, and institutional hierarchy. It feeds upstream into Payroll (Finance) and downstream into Academic ownership, access control, and eligibility flows. All actions must be governed by policy rules and leave an audit trail.

**Authoritative Reference**

* ALIS Master Developer Document
* HR Manual + Organization Chart
* Leave, Appraisal & Biometric Policy

**Constraints**

* Only authorized staff can trigger lifecycle transitions (hire, appraise, offboard)
* All biometric and leave records must match institutional policy windows
* No retroactive attendance or appraisal changes without dual approval

**Dependency Rule** Depends on:

* E01 – Platform Core & Security
* E02 – Shared Services\n\n### Child Stories\n#### Story: [AV-184] E07-S01 — Job Posting Wizard\n**Status:** To Do\n\n> **Story**  
As an HR manager, I must post open staff roles with metadata and application tracking.

**Description**  
Roles must include department, designation, level, and application deadlines. Auto-expiry and role-level permissioning apply.

**Must Align With**

* Layer 1: JobPost schema
* Layer 4: Deadline enforcement
* Layer 6: Posting audit + auto-expiry

**Acceptance Criteria**

* API: `POST /hr/jobs`
* Deadline must be future
* Expired jobs hidden from applicants\n\n#### Story: [AV-185] E07-S02 — Onboarding Wizard\n**Status:** To Do\n\n> **Story**  
As HR, I must onboard newly hired employees and provision them across systems.

**Description**  
Captures biodata, joining date, and documents. Triggers institutional email, LMS access, and role assignment. Flags duplication if Aadhar/PAN exist.

**Must Align With**

* Layer 1: Staff entity
* Layer 3: Legal onboarding event
* Layer 6: Staff activity log

**Acceptance Criteria**

* All fields validated
* LMS + Email provisioning triggered
* PDF employee file generated\n\n#### Story: [AV-186] E07-S03 — Leave Wizard\n**Status:** To Do\n\n> **Story**  
As a staff member, I must apply for leave and receive approval or rejection via workflow.

**Description**  
Leave types (CL, EL, ML, LOP) must map to policy. Auto-balance tracking. Role-based approvers. Attendance integration required.

**Must Align With**

* Layer 1: LeaveRequest model
* Layer 4: Block conflicting attendance
* Layer 6: Approval trail

**Acceptance Criteria**

* Leave overlaps auto-flagged
* API: `POST /leave/apply`
* Leave balance updated on approval\n\n#### Story: [AV-187] E07-S04 — Biometric Sync Wizard\n**Status:** To Do\n\n> **Story**  
As HR, I must sync biometric attendance logs with the central system daily.

**Description**  
Biometric logs are pulled, hashed, and cross-mapped to staff IDs. Late/absent flags generated automatically.

**Must Align With**

* Layer 1: AttendanceLog schema
* Layer 4: Hash + lock logs post-ingestion
* Layer 6: Daily sync record

**Acceptance Criteria**

* Auto-flag missing punches
* Lock logs post 48 hours
* API: `POST /biometric/sync`\n\n#### Story: [AV-188] E07-S05 — Appraisal Wizard\n**Status:** To Do\n\n> **Story**  
As a supervisor, I must evaluate staff annually based on defined KPIs.

**Description**  
Appraisal forms must include self-rating, supervisor rating, and committee override. Visibility time-locked until publish.

**Must Align With**

* Layer 1: Appraisal schema
* Layer 4: Freeze window after review
* Layer 5: Role-gated visibility

**Acceptance Criteria**

* PDF output stored
* Committee score overrides lower score only
* API: `POST /appraisal/submit`\n\n#### Story: [AV-189] E07-S06 — Service Book Wizard\n**Status:** To Do\n\n> **Story**  
As HR, I must maintain a service record for each employee across events (promotion, leave, awards).

**Description**  
Each entry must be timestamped, source-linked, and signed. No deletions allowed. Required for payroll and retirement calculations.

**Must Align With**

* Layer 1: ServiceBookEntry schema
* Layer 4: Entry immutability
* Layer 6: System logbook

**Acceptance Criteria**

* API: `POST /service-book/add`
* Signature + file attachment
* Only superadmin edit rights\n\n#### Story: [AV-190] E07-S07 — File Tracking Wizard\n**Status:** To Do\n\n> **Story**  
As admin staff, I must track movement and status of institutional files (physical + digital).

**Description**  
Each file has status, assigned holder, origin, and movement history. Escalation on overdue holding.

**Must Align With**

* Layer 1: FileTracker schema
* Layer 4: Auto-escalate on delay
* Layer 6: Movement log

**Acceptance Criteria**

* API: `POST /files/track`
* Delay >7 days triggers alert
* Status: with, moved, returned\n\n#### Story: [AV-191] E07-S08 — Circular Wizard\n**Status:** To Do\n\n> **Story**  
As HR/Admin, I must issue internal circulars to roles, departments, or staff groups.

**Description**  
Circulars may be textual or file-based. Target audience required. Must log dispatch receipt by user.

**Must Align With**

* Layer 1: Circular schema
* Layer 4: Read lock if acknowledgment required
* Layer 6: Dispatch + read log

**Acceptance Criteria**

* API: `POST /circular/issue`
* Departmental target required
* Acknowledgment flag logs user read\n\n---\n\n