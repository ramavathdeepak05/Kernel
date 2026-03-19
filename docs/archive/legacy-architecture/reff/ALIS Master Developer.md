
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

DOCUMENT AUTHORITY & PRECEDENCE
This document is the single canonical source of truth for ALIS.
All architectural decisions, state machines, authority rules, global locks, agent behavior, and implementation patterns MUST conform to this document.
Any secondary material (PDFs, slides, tickets, diagrams, chats) is explanatory only.
If a conflict exists, THIS DOCUMENT PREVAILS.
________________________________________
SYSTEM SCOPE & OPERATING CONSTRAINTS
•	Scope: 9 Modules (M1–M9) + E13 Process Engine
•	Architecture: FastAPI + Celery + Domain Event Bus
•	Deployment: Air-gapped / No Cloud Dependencies
•	Security Model: RBAC+ (Role + Context + Agent Constraints)
ALIS is an Agentic Operating System for Institutions.
It does not merely store data. It executes decisions, under strict institutional control.
________________________________________
THE ALIS 6-LAYER MODEL
ALIS is built on six strict layers. No logic may skip a layer. No layer may override a lower layer.
1.	Layer 1 — Module Purpose & Authority (WHY)
2.	Layer 2 — Agentic Decisions & Wizards (HOW)
3.	Layer 3 — State Machines & Legality (WHAT IS ALLOWED)
4.	Layer 4 — Global Locks & Invariants (WHAT MUST NEVER HAPPEN)
5.	Layer 5 — Roles, Authority & Quorum (WHO CAN ACT)
6.	Layer 6 — Resilience & Reality Handling (WHAT IF THINGS GO WRONG)
________________________________________
POLICY vs LOGIC vs INVARIANTS
ALIS separates what can change from what cannot.
•	Policy (UI-configurable)
o	Thresholds (scores, percentages)
o	Date ranges
o	Cutoffs
•	Logic (Code-defined)
o	Eligibility calculations
o	Scoring algorithms
o	Wizard execution flow
•	Invariants (Immutable)
o	Global Locks
o	Authority & approval rules
o	Allowed state transitions
Users may change Policy.
Developers write Logic.
Nothing may violate Invariants.
________________________________________
The Core Architecture

1. The Build Environment
1.1 The Stack
• Runtime: Python 3.11+ (FastAPI for API Layer)
• Automation: `Celery` + Redis (background tasks, domain event bus)
• Inference: `Ollama` (running `qwen2.5:1.5b-instruct-q8_0`)
• Data: PostgreSQL 16 + pgvector (Structured + Vector), MinIO (Object Storage)
• AI Gateway: `AIGateway` in `server/core/ai_gateway.py` (wraps Ollama HTTP)
• Embeddings: `nomic-embed-text` via Ollama (768-dim, cosine similarity)

1.2 Project Structure
Organize your code exactly like this:

/server
/agents                      # LangGraph workflows (The "Brain")
/admissions           # M1 Agents
/academics            # M2 Agents
/mcp                          # MCP Servers (The "Hands")
/db_service.py      # Safe DB Tools
/fs_service.py        # Safe File Tools
/rules                         # Deterministic Logic (The "Law")
/finance_rules.py
/exam_rules.py
/core
/rbac.py                   # RBAC+ Middleware
/schema.py           # Pydantic Models

/web
/app                            # Next.js App Router
/components             # Shadcn UI Components
/lib                              # Shared Utilities
# The 'web' folder is the ONLY place for UI code. It consumes /server via localhost.
# Deployment: Dedicated Instance per Client.
________________________________________
The "No-Cloud" Rule
`import openai` -> Immediate Termination of PR
 `pip install anthropic` -> Forbidden
 `AIGateway.invoke()` / `AIGateway.embed()` -> Required (server/core/ai_gateway.py)

________________________________________
LAYER 1 — MODULE PURPOSE & AUTHORITY (WHY)
Layer 1 defines who owns which institutional truth. It is binding, not descriptive.
Layer 1 Global Rules
1.	Each module owns exactly one institutional outcome.
2.	No two modules may decide the same outcome.
3.	Modules may request data, but never decide on behalf of another module.
4.	Cross-module decisions occur only via events.
________________________________________
M1 — Admissions & Marketing
Owns: Lead qualification, applicant evaluation, seat allocation, enrollment initiation
Must Not Decide: Academics, finance, exams
Outcome: Fair and auditable conversion of applicants to students
M2 — Academics
Owns: Curriculum, teaching delivery, attendance, academic risk
Must Not Decide: Admissions, finance, exams
Outcome: Verified delivery of instruction
M3 — Examinations
Owns: Exams, evaluation, results
Must Not Decide: Admissions, finance
Outcome: Defensible certification of performance
M4 — Finance
Owns: Fees, payments, financial holds
Must Not Decide: Academics, exams, admissions merit
Outcome: Deterministic financial truth
M5 — HR & Administration
Owns: Staff lifecycle, payroll readiness
Must Not Decide: Student outcomes
Outcome: Governed personnel management
M6 — Student Services
Owns: Campus life, discipline, facilities
Must Not Decide: Academic standing
Outcome: Safe student operations
M7 — Communication Hub
Owns: Institutional notifications, alerts, messaging
Must Not Decide: Academic grading, finance, admissions
Outcome: Reliable delivery of system-generated communications
M8 — Reporting & Analytics
Owns: Cross-module reports, analytics dashboards
Must Not Decide: Any institutional truth (read-only projection)
Outcome: Timely and accurate reporting for leadership
M9 — Alumni & Placement
Owns: Alumni profiles, placement tracking, employer coordination
Must Not Decide: Academic certification, active student outcomes
Outcome: Continued institutional engagement and placement success
________________________________________
LAYER 2 — AGENTIC DECISIONS & WIZARDS (HOW)
Wizards are decision engines, not forms.
Every wizard must end in a decision that:
•	Advances state
•	Blocks progression
•	Or enters a provisional path
Agent Definition
An ALIS Agent:
•	Belongs to one module
•	Uses AI to analyze inputs
•	Produces a decision or draft outcome
Agents are not chatbots or helpers.
Decision Declaration (Mandatory)
Decision Made:
<institutional truth>

AI Role:
Infer | Score | Plan | Execute

Confidence Rules:
High → <action>
Medium → <action>
Low → <action>

Human Authority:
Auto | Approve | Quorum

Output:
<Decision + Proposed State>
________________________________________
LAYER 3 — STATE MACHINES & LEGALITY
States are immutable facts, not editable fields.
Layer 3 Rules
•	Backward transitions are forbidden
•	Invalidation occurs forward (ANNULLED)
•	Undeclared transitions must fail
Central State Registry (Canonical)
Student States:
LEAD → APPLIED → ELIGIBLE → PROVISIONALLY_ELIGIBLE → ADMITTED → ENROLLED → ANNULLED
________________________________________
LAYER 4 — GLOBAL LOCKS & INVARIANTS
Global Locks override all module logic.
Examples:
•	No Hall Ticket if dues pending
•	No Exam if attendance insufficient
•	No Enrollment if documents incomplete
Global Locks cannot be bypassed.
________________________________________
LAYER 5 — ROLES, AUTHORITY & QUORUM
No single user has unlimited power.
Rules:
•	Irreversible actions require human approval
•	Critical actions require multiple approvers
•	All approvals are logged
________________________________________
LAYER 6 — RESILIENCE & REALITY HANDLING
When data is incomplete or systems fail:
•	Use provisional states
•	Continue safely with warnings
•	Never fail silently
Provisional states expire and must be resolved.
________________________________________
OVERRIDES (FIRST-CLASS ENTITY)
Overrides are tracked system events, not shortcuts.
Lifecycle: REQUESTED → APPROVED → EXECUTED → CLOSED
Overrides:
•	Require reason
•	Are auditable
•	May require quorum
•	Cannot be deleted
________________________________________
BUILD ENVIRONMENT
•	Python 3.11+
•	FastAPI (Orchestration)
•	LangGraph (Agents)
•	Ollama (Local LLM)
•	PostgreSQL + ChromaDB
•	MCP for DB, FS, Hardware
No Cloud Rule: Any cloud LLM dependency is forbidden.
________________________________________
IMPLEMENTATION BLUEPRINTS
Blueprint A — Rule Engine
Deterministic, no AI. Code is law.
Blueprint B — AI Agent
LangGraph workflows. Read-only by default.
Blueprint C — RBAC+
Role + Context + Agent Constraints.
________________________________________
EVENT CONTRACT RULE
Cross-module communication occurs only via events. Events must be explicit, async, and idempotent.
________________________________________
2. Implementation Blueprints (The Code Patterns)
ALIS has only three types of logical units. Use the corresponding blueprint.
Blueprint A: The Rule Engine (Deterministic)
Use for: Finance, Grades, Enrollment. "Code is Law."
rules/finance_rules.py
from typing import Dict, List
from core.rbac import check_global_locks
class RuleResult:
def __init__(self, allowed: bool, violations: List[str]):
self.allowed = allowed
self.violations = violations
def execute_fee_validation(student_context: Dict) -> RuleResult:
violations = []
#1. Global Lock Check (Layer 4)
#Even if logic passes, Global Locks (Dues/Attendance) override everything.

lock_status = check_global_locks(student_context['id'])
if lock_status.is_locked:
return RuleResult(False, [f"Global Lock: {lock_status.reason}"])

#2. Domain Logic (Deterministic)

if student_context['balance'] > 0:
violations.append("Outstanding Dues")
return RuleResult(allowed=len(violations) == 0, violations=violations)


Blueprint B: The AI Agent (Reasoning)
Use for: Admissions, Regulatory, Research.
Constraint: Agents NEVER write directly to the DB. They output a "Draft" (state_impact="DRAFT").

# server/agents/admissions/eligibility_agent.py
from server.core.ai_gateway import AIGateway
from server.core.rbac import verify_access, Role, Permission
from server.core.data_classification import DataMasker

async def evaluate_eligibility(applicant_data: dict, actor_role: Role, tenant_id: str):
    # Agents are read-only observers — mask PII before passing to LLM
    masked = DataMasker.mask_for_ai_context(applicant_data)

    response = await AIGateway.invoke(
        prompt_id="admissions.eligibility_eval",
        context=masked,
        actor_role=actor_role,
        tenant_id=tenant_id,
    )
    # response.state_impact is always "DRAFT" — gateway enforces this
    # response.confidence_tier routes to AUTO / REVIEW / HITL
    return response

Blueprint C: RBAC+ Middleware (Security)
The "Plus" means Context & Agent Constraints.

#core/rbac.py
from enum import Enum
class Role(Enum):
STUDENT = "student"
FACULTY = "faculty"
AGENT = "ai_agent"
def verify_access(actor_role: Role, resource: str, context: Dict) -> bool:
#1. Standard RBAC (Role)
if actor_role == Role.STUDENT and resource == "exam_paper":
return False
#2. Context-Awareness (State)
#Example: Faculty can only edit marks during the "Evaluation Window"
if actor_role == Role.FACULTY and resource == "marks_entry":
if context['exam_status'] != 'EVALUATION_OPEN':
return False # Denied because Exam Cycle is closed
#3. Agent Constraints (AI Safety)
#AI Agents have READ access but NO WRITE access to Sensitive Data
if actor_role == Role.AGENT and resource == "final_grade":
if context['action'] == 'write':
return False # AI cannot commit grades. Only Humans can.
return True



LAYER 1 — MODULE PURPOSE & AUTHORITY (WHY)
Layer 1 defines institutional intent. It answers one question only:
Which module owns which institutional truth?
Layer 1 is not descriptive. It is binding.
If a module acts outside its declared authority, the implementation is invalid — even if it works.
________________________________________
Layer 1 Global Rules
1.	Each module owns exactly one institutional outcome.
2.	No two modules may decide the same outcome.
3.	A module may request information from another module, but may not decide on its behalf.
4.	If a decision crosses module boundaries, it must occur via events, not direct logic.
________________________________________
M1 — Admissions & Marketing
Layer 1 Authority Contract
SOLE AUTHORITY:
•	Lead qualification
•	Applicant evaluation
•	Seat allocation proposals
•	Initiation of enrollment
MUST NOT DECIDE:
•	Academic performance after enrollment
•	Examination eligibility
•	Financial clearance
•	Certification or graduation
Institutional Outcome Owned:
Conversion of qualified applicants into enrolled students, fairly and auditably.
________________________________________
M2 — Academics
Layer 1 Authority Contract
SOLE AUTHORITY:
•	Curriculum structure
•	Teaching delivery
•	Attendance computation
•	Academic risk detection
MUST NOT DECIDE:
•	Admissions eligibility
•	Financial compliance
•	Exam result publication
Institutional Outcome Owned:
Verified delivery of academic instruction and learning continuity.
________________________________________
M3 — Examinations
Layer 1 Authority Contract
SOLE AUTHORITY:
•	Examination scheduling
•	Assessment execution
•	Marks evaluation
•	Result computation
MUST NOT DECIDE:
•	Admissions decisions
•	Financial clearance
•	Degree issuance without compliance
Institutional Outcome Owned:
Defensible assessment and certification of academic performance.
________________________________________
M4 — Finance
Layer 1 Authority Contract
SOLE AUTHORITY:
•	Fee liability computation
•	Payment status
•	Financial holds and releases
MUST NOT DECIDE:
•	Academic eligibility
•	Exam outcomes
•	Admissions merit
Institutional Outcome Owned:
Deterministic and auditable financial truth.
________________________________________
M5 — HR & Administration
Layer 1 Authority Contract
SOLE AUTHORITY:
•	Staff lifecycle
•	Attendance locking
•	Payroll readiness
MUST NOT DECIDE:
•	Academic assessment
•	Student eligibility
Institutional Outcome Owned:
Governed management of institutional personnel.
________________________________________
M6 — Student Services
Layer 1 Authority Contract
SOLE AUTHORITY:
•	Campus facilities access
•	Hostel, transport, discipline records
MUST NOT DECIDE:
•	Academic standing
•	Examination eligibility
Institutional Outcome Owned:
Safe and regulated student life operations.
________________________________________
M7 — Communication Hub
Layer 1 Authority Contract
SOLE AUTHORITY:
•	Institutional notifications and alerts
•	Email/SMS/in-app messaging dispatch
•	Communication templates and scheduling
MUST NOT DECIDE:
•	Academic grading
•	Financial computation
•	Admissions merit
Institutional Outcome Owned:
Reliable delivery of system-generated communications to students and staff.
________________________________________
M8 — Reporting & Analytics
Layer 1 Authority Contract
SOLE AUTHORITY:
•	Cross-module report generation
•	Analytics dashboards and projections
•	Data aggregation for leadership decisions
MUST NOT DECIDE:
•	Any institutional truth (read-only projection module)
Institutional Outcome Owned:
Timely and accurate reporting for staff and leadership decision-making.
________________________________________
M9 — Alumni & Placement
Layer 1 Authority Contract
SOLE AUTHORITY:
•	Alumni profile management post-graduation
•	Placement tracking and employer coordination
•	Alumni engagement and reunions
MUST NOT DECIDE:
•	Academic certification
•	Active student outcomes
Institutional Outcome Owned:
Continued institutional engagement and placement success tracking.
________________________________________
LAYER 2 — WIZARDS & DECISIONS (HOW)
Layer 2 defines how institutional decisions are made.
Wizards are not forms. They are decision engines.
Every wizard MUST end in a system decision that either:
•	advances state
•	blocks progression
•	enters a provisional path
If a wizard only produces data, it is incomplete.
________________________________________
POLICY vs LOGIC vs INVARIANT (NON-NEGOTIABLE)
ALIS separates institutional behavior into three categories:

1. Policy Parameters (CONFIGURABLE VIA UI)
   - Thresholds (scores, percentages)
   - Ranges (scholarship %, attendance cutoffs)
   - Effective dates and applicability

2. Decision Logic (CODE-DEFINED)
   - Eligibility computation
   - Scoring algorithms
   - Wizard execution flow
   - State transition triggers

3. Institutional Invariants (IMMUTABLE)
   - Global Locks (Layer 4)
   - Authority & Quorum rules (Layer 5)
   - State legality (Layer 3)

UI MAY modify (1).
Code DEFINES (2).
NOTHING may violate (3).

Any feature that blurs this boundary is invalid.
________________________________________
Layer 2 Global Rules
1.	Every wizard declares the decision it makes.
2.	AI’s role must be explicit: Infer | Score | Plan | Execute.
3.	Confidence-weighted logic (v1.1) is mandatory.
4.	Human involvement must be explicitly stated.
________________________________________
Layer 2 Decision Declaration (MANDATORY FORMAT)
Every wizard must declare:
Decision Made:
<single sentence institutional truth>

AI Role:
Infer | Score | Plan | Execute

Confidence Rules:
High → <behavior>
Medium → <behavior>
Low → <behavior>

Human Authority:
Auto | Approve | Quorum Required

Output:
<Decision + Next State Proposal>
________________________________________
Example — Seat Allocation Wizard (M1)
Decision Made:
Should this applicant be allocated a seat in the program?

AI Role:
Score + Execute
Confidence Rules:
High → Allocate seat
Medium → Provisionally allocate
Low → Manual verification

Human Authority:
Approve only if provisional

Output:
Seat Allocated → PROVISIONALLY_ENROLLED
________________________________________
LAYER 3 — STATE MACHINES (WHAT IS LEGAL)
Layer 3 defines institutional physics.
It answers:
What transitions are legally and logically allowed?
States are immutable facts. They are not fields to update.
________________________________________
Layer 3 Global Rules
1.	All entities MUST have an explicit state machine.
2.	Backward transitions are forbidden.
3.	Invalidation occurs forward via annulment states.
4.	Undeclared transitions MUST be rejected at runtime.
________________________________________
Example — Applicant / Student State Machine
States:
LEAD
APPLIED
ELIGIBLE
PROVISIONALLY_ELIGIBLE
ADMITTED
ENROLLED
ANNULLED

Allowed Transitions:
LEAD → APPLIED
APPLIED → ELIGIBLE | NOT_ELIGIBLE | PROVISIONALLY_ELIGIBLE
ELIGIBLE → ADMITTED
ADMITTED → ENROLLED
ANY → ANNULLED

Forbidden:
ENROLLED → APPLIED
ADMITTED → ELIGIBLE
________________________________________
Layer 3 Enforcement Rule
If a transition is not declared in Layer 3, the correct behavior is rejection, not invention.
Layer 4 and Layer 5 do not compensate for illegal state movement.
________________________________________
Closing Statement for Layers 1–3
Layer 1 defines meaning.
Layer 2 defines intelligence.
Layer 3 defines legitimacy.
If these three are correct, the system scales.
If any of these are weak, no amount of governance can save the system.

LAYER 4 — GLOBAL LOCKS & INVARIANTS

Layer 4 defines conditions that override all module logic.

Examples:
- No Hall Ticket with dues or low attendance
- No Result Publication without eligibility
- No Enrollment without fee clearance

Global Locks are evaluated BEFORE all decisions.
No module may bypass a Global Lock.

---

LAYER 5 — ROLES, AUTHORITY & QUORUM

Layer 5 defines who may approve or override decisions.

Rules:
- Irreversible actions require human authority
- Critical overrides require multi-signature quorum
- Overrides are explicit entities with audit trails

No single actor has god-mode authority.


LAYER 6 — RESILIENCE & REALITY HANDLING

Layer 6 governs behavior under uncertainty.
Includes:
- Provisional states
- Confidence-weighted decisions
- Asynchronous event convergence
- Fail-soft under non-terminal risk

Fail-soft is explicit, visible, and time-bound.

2. Technical Spec Matrix (The 77 Wizards)
M1. Admissions Module (9 Wizards)
Wizard Name	Execution Type	Input (Data Source)	Technical Process (Architecture)	Output (State)
1. Applicant Wizard	Rule Engine	Form POST (JSON)	Validate fields -> Check DB duplicates -> Insert.	status: APPLIED
2. Lead De-duplication	Rule Engine	New Lead Object	Fuzzy Match (SQL Soundex) on Name/Phone -> Merge Logic.	lead_id (Merged)
3. Eligibility Eval	AI Agent	PDF Marksheet (Stream)	LangGraph: OCR (Tesseract) -> Llama 3 ("Extract Grades") -> Llama 3 ("Compare vs Criteria").	score: 0-100, json_data
4. Doc Verification	AI Agent	Certs Types (PDF/Img)	LangGraph: OCR -> Llama 3 ("Verify Seal/Sign") -> Check Dates.	is_verified: boolean
5. Counsellor Allocation	AI Agent	Applicant Profile	Vector Match: Student Interest Embedding <-> Counsellor Expertize Embedding.	counsellor_id
6. Offer Letter Gen	Rule Engine	Applicant ID	Template Engine (Jinja2) + Signer API. Strict Rule: Only if status == ELIGIBLE.	PDF Artifact
7. Admission Confirm	Rule Engine	Payment Token	Verify Payment -> Freeze Seat -> Generate Reg No.	status: ADMITTED
8. Intake Quality	AI Agent	Batch Data (SQL)	Regression Model: Predict expected yield vs historicals.	quality_index: float
9. Enrollment Handover	Rule Engine	Student ID	ETL Job: Move data from M1_DB to M2_DB.	status: ENROLLED

M2. Academics Module (12 Wizards)
Wizard Name	Execution Type	Input (Data Source)	Technical Process (Architecture)	Output (State)
1. Program Structure	Rule Engine	Regulation PDF/Form	Form -> Schema Validation -> DB Insert.	program_id
2. Course Creation	Rule Engine	Syllabus ID	Map 1:1 -> Validate Credits -> DB Insert.	course_id
3. Outcome Mapping	AI Agent	Syllabus Text	RAG: Retrieve Bloom's Taxonomy -> Llama3 ("Map Topic to Level").	co_po_matrix: json
4. Academic Calendar	Rule Engine	Date Range	Date Math -> Holiday Exclusion -> Slot Generation.	calendar_events
5. Faculty Allocation	AI Agent	Course + Faculty DB	Constraint Solver: Match Skills + checking Workload < Limit.	faculty_map
6. Lesson Plan	AI Agent	Topic String	RAG: Retrieve Textbook Chunks -> Llama3 ("Draft Session Plan").	session_plan: draft
7. Lecture Content	AI Agent	Session ID	RAG: Retrieve Notes -> Llama3 ("Generate Slides/Talking Points").	content_artifact
8. Pedagogy Select	AI Agent	Topic Type	Classifier: Theory vs Practical -> Recommend Method.	pedagogy_tag
9. Continuous Assess	AI Agent	Unit Text	LangGraph: Generate Qs -> Check Bloom's -> Format Output.	quiz_json
10. Attendance Intel	AI Agent	Daily Logs (SQL)	Time Series Analysis -> Flag Absentees -> Trigger Alert.	risk_flag
11. Academic Risk	AI Agent	Grades + Attendance	Logistic Regression: Predict Failure Probability.	at_risk_list
12. Term Closure	Rule Engine	Term ID	Check All Grades Submitted -> Archive -> Calc Stats.	term_status: CLOSED




M3. Examinations Module (10 Wizards)
Wizard Name	Execution Type	Input (Data Source)	Technical Process (Architecture)	Output (State)
1. Exam Blueprint	AI Agent	Syllabus	Llama3: Suggest Weightage based on Teaching Hours.	blueprint_draft
2. Secure Q-Bank	Hybrid	Blueprint	Step 1: AI Gen Qs. Step 2: Human Approve. Step 3: AES Encrypt in DB.	q_bank_encrypted
3. Paper Assembly	Hybrid	Q-Bank + Seed	Rule (Random): Select Qs based on Blueprint. AI: Verify Difficulty balance.	paper_draft
4. Exam Scheduling	Rule Engine	Course List	Graph Coloring Algo (Clash Detection).	exam_timetable
5. Hall Ticket	Rule Engine	Student List	Global Lock: Check Dues + Attendance -> Generate PDF.	hall_ticket_pdf
6. Proctoring Config	Rule Engine	Config Form	Apply Policies (Disable Browser Tabs).	exam_policy_obj
7. Evaluation Logic	Hybrid	Answer Key	AI: Semantic Match (for Theory). Rule: MCQ Match.	prov_marks
8. Result Processing	Rule Engine	Raw Marks	Pure SQL Calculation: SGPA/CGPA. No AI.	final_result
9. Revaluation	AI Agent	Script + student_arg	AI: "Does the argument have merit?" -> Flag for Human.	reval_flag
10. Transcript	Rule Engine	Final Result	Generate Immutable PDF + Hash.	transcript_pdf



M4. Student Services Module (9 Wizards)
Wizard Name	Execution Type	Input (Data Source)	Technical Process (Architecture)	Output (State)
1. Student Profile	Rule Engine	Student ID	CRUD Operations.	profile_db
2. Service Request	Rule Engine	Form	Router: Map Category to Staff Dept.	ticket_id
3. Grievance Handling	AI Agent	Complaint Text	Sentiment Analysis: Classify Urgency -> Search Policy -> Reply Draft.	draft_reply
4. Disciplinary Case	AI Agent	Incident Report	Summarize -> Map to Handbook Violation.	case_file
5. Housing Alloc	Rule Engine	Applications	FIFO Queue or Merit Sort.	room_alloc
6. Transport Alloc	Rule Engine	Location	Route Optimization (TSP Solver).	bus_route
7. Cert Issuance	Rule Engine	Request	Template Fill -> Sign -> Log.	cert_pdf
8. Exit / Transfer	Rule Engine	Clearance Form	Check Asset Returns -> Check Dues -> Close Account.	status: ALUMNI
9. Alumni Conversion	AI Agent	Student Data	Summarize Achievements -> Create Alumni Profile.	alumni_db

M5. Finance Module (10 Wizards)
Wizard Name	Execution Type	Input (Data Source)	Technical Process (Architecture)	Output (State)
1. Fee Structure	Rule Engine	Config Form	Definition -> Validation -> DB.	fee_config
2. Fee Versioning	Rule Engine	Old Structure	Clone -> Increment -> Save Version.	fee_config_v2
3. Student Ledger	Rule Engine	Transaction	Double Entry Accounting: Credit/Debit.	ledger_row
4. Voucher Creation	Rule Engine	Expense Info	Journal Entry.	voucher_id
5. Pay Reconciliation	Hybrid	Bank CSV	AI: Fuzzy Match Desc to Name. Rule: Confirm Matching.	reco_status
6. Scholarship	AI Agent	Application	Rules (Income) + AI (Essay Score).	waiver_pct
7. Refund Processing	Rule Engine	Request	Check Policy -> Calc Amount -> Approval Workflow.	refund_tx
8. Dues & Defaulter	Rule Engine	Ledger	SUM(Dr - Cr). If > 0 -> Set Global Lock.	lock_status
9. Revenue Analytics	AI Agent	Ledger Data	Forecasting (Time Series).	report_json
10. Audit Trail	Rule Engine	Sys Logs	Immutable Append-Only Log.	audit_db

M6. HR & Payroll Module (9 Wizards)
Wizard Name	Execution Type	Input (Data Source)	Technical Process (Architecture)	Output (State)
1. Empl Onboarding	Rule Engine	Form/Docs	Profile Creation + Access Provisioning.	emp_id
2. Role & Authority	Rule Engine	Org Chart	RBAC Policy Definition.	policy_file
3. Biometric Sync	Rule Engine	Hardware	MCP: Check biometric_mcp -> Fetch Logs -> Normalize.	attend_log
4. Attendance Intel	AI Agent	Logs	Pattern Check: "Late 3 days in a row?".	pattern_alert
5. Leave Approval	AI Agent	Request	Check Balance -> Predict Impact -> Suggest Approval.	draft_decision
6. Payroll Comp	Rule Engine	Attendance	Calc: 
(Days - LOP) * Rate. Strict Math.	payslip_draft
7. Perform Review	AI Agent	Peers + KPIs	Text Summarization (Feedback) + Goal Scoring.	review_doc
8. Faculty Workload	AI Agent	Timetable	Calc Hrs -> Compare vs Norms -> Balance.	load_report
9. Separation	Rule Engine	Resignation	No Dues Check -> FnF Calculation.	status: EX

M7. Regulatory Module (9 Wizards)
Wizard Name	Execution Type	Input (Data Source)	Technical Process (Architecture)	Output (State)
1. Regulatory Map	AI Agent	Guidelines PDF	Extract Obligations -> Map to Owners.	compliance_tasks
2. Data Readiness	Rule Engine	DB Metdata	Check Null Columns -> Flag Gaps.	readiness_score
3. UGC / NAAC	AI Agent	Template	RAG: Retrieve Evidence -> Draft Report Section.	report_draft
4. Evidence Compile	AI Agent	Prompt	MCP: find_files(pattern) -> Filter -> Link.	evidence_list
5. Inspection Ready	AI Agent	Chat	Persona: "Hostile Inspector" -> Q&A Sim.	mock_transcript
6. Compliance Gap	AI Agent	Evidence List	Compare vs Required List -> Flag Missing.	gap_report
7. Corrective Action	Hybrid	Gap Report	Rule: Assign Owner. AI: Suggest Remediation.	action_plan
8. Submission	Rule Engine	Final Report	Generate Checksum -> Lock Context.	submission_frozen
9. Archive	Rule Engine	Data	Blob Storage + Indexing.	archive_id

M8. Research Module (9 Wizards)
Wizard Name	Execution Type	Input (Data Source)	Technical Process (Architecture)	Output (State)
1. Researcher Profile	Rule Engine	Pubs/Grant Data	Aggregation.	profile_score
2. Grant Discovery	AI Agent	Public Web	MCP: Scraper -> Filter (Keywords) -> Match.	opportunity_list
3. Grant Lifecycle	Rule Engine	Milestones	Tracker (Date Alerts).	status_update
4. Proposal Review	AI Agent	Draft PDF	Persona: "Reviewer 2" -> Critique Methodology.	feedback_text
5. Ethics Approval	Hybrid	Protocol	Rule: Check Docs. AI: Flag Bio-Risk.	approval_status
6. Pub Tracker	Rule Engine	DOI/Link	Meta-data fetch (Crossref).	pub_record
7. Citation Intel	AI Agent	Pub List	Network Graph Analysis.	impact_metric
8. Research Output	AI Agent	Lab Data	Summarize Findings -> Draft Abstract.	abstract_draft
9. Repository	Rule Engine	Assets	DAM (Digital Asset Mgmt).	repo_link
________________________________________
3. Implementation Patterns (Recap)
•	Rule Engine: Python Function, Input -> Validation -> DB. No AI.
•	AI Agent: LangGraph StateGraph. Node (Action) -> Edge (Logic). Llama 3 via Ollama.
•	MCP Server: FastMCP wrapper around DB/Hardware/Filesystem.
Build it exactly as listed.

