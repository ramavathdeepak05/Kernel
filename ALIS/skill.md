skill.md 
Skill Name
Build ALIS (Agentic Institutional OS)

Skill Purpose
This skill instructs Antigravity to generate, modify, and review code strictly according to the ALIS Master Developer Handbook (Canonical v1.0).

The goal is speed without architectural decay.

Antigravity is used as an execution accelerator, not as a system designer.

Canonical Authority
The following sources are the only allowed inputs for building ALIS:

ALIS Master Developer Handbook (Canonical) — primary source of truth
Jira Epics & Stories (TEXT ONLY) — implementation intent and scope
No other sources may be used.

Rules:

Code MUST be derived strictly from the Master Handbook and Jira descriptions
Jira stories may clarify what to build, but never redefine how it works
If Jira text conflicts with the Handbook, the Handbook prevails
If Jira text is ambiguous, Antigravity MUST stop and ask for clarification
Any secondary material (PDFs, slides, chats, diagrams) is explanatory only.

If a conflict exists, THE MASTER HANDBOOK PREVAILS.

Prime Directives (Non‑Negotiable)
Do not invent architecture
Do not blur module boundaries
Do not bypass layers
Do not weaken governance to simplify code
Do not convert agents into helpers
If a requirement is unclear, STOP and ask for clarification.

ALIS Layer Awareness (Mandatory)
All generated code MUST explicitly respect these layers:

Layer 1 — Module Authority
Layer 2 — Agentic Decisions & Wizards
Layer 3 — State Machines
Layer 4 — Global Locks
Layer 5 — Roles & Authority (RBAC+)
Layer 6 — Resilience (Provisional, Async)
No code may skip or override a layer.

Allowed Logical Units (Only These)
Antigravity may generate only the following unit types:

1. Rule Engine (Deterministic)
Pure Python functions
No AI usage
Enforces Layer 3 + Layer 4 rules
Returns explicit allow/deny results
Example intent:

Validate fee clearance before enrollment

2. AI Agent (LangGraph)
Read‑only by default
Uses local LLMs via Ollama
Produces decisions or draft outputs
Never commits irreversible state
Agents MUST:

Declare decision intent
Respect confidence tiers
Defer authority when required
3. RBAC+ Middleware
Role‑based checks
Context‑aware checks (state, window, scope)
Agent constraints (AI read/write limits)
RBAC+ is enforced before business logic.

Mandatory Prompt Template
All Antigravity prompts MUST use this structure:

MODULE:
<Module ID and Name>

LAYER:
<Layer(s) affected>

ENTITY:
<Primary entity>

DECISION:
<What institutional decision is being made?>

STATE INPUT:
<Current state(s)>

STATE OUTPUT:
<Proposed next state(s)>

AUTHORITY:
<Auto | Human | Quorum>

LOCKS:
<Relevant Global Locks>

EVENTS:
<Events emitted or consumed>

FAILURE MODE:
<What happens if data is missing or lock fails?>
If any field is missing, generation MUST stop.

Decision Discipline (Layer 2)
Every wizard or agent MUST:

Declare exactly ONE decision
End with a state change, block, or provisional path
Never produce data without consequence
If no decision exists, the feature is incomplete.

State Machine Discipline (Layer 3)
States are immutable facts
Backward transitions are forbidden
Corrections occur only via ANNULLED or equivalent
Undeclared transitions must raise runtime errors
Antigravity MUST reject any code that mutates state illegally.

Global Locks (Layer 4)
Checked before all decisions
Override module logic
Cannot be disabled or bypassed
If a Global Lock exists, the correct output is FAIL.

Authority & Overrides (Layer 5)
Sensitive actions require human approval
Critical actions require multi‑signature quorum
Overrides are explicit entities
Override lifecycle: REQUESTED → APPROVED → EXECUTED → CLOSED

No silent overrides are allowed.

Resilience Rules (Layer 6)
When certainty is low:

Use provisional states
Emit warnings
Allow non‑terminal actions to proceed
Terminal actions remain blocked until resolved.

Event Contract Rules
Cross‑module communication is event‑based only
Events must be explicit and idempotent
No direct cross‑module writes
Antigravity must never generate tight coupling.

Forbidden Actions
Antigravity MUST NOT:

Introduce cloud LLMs
Add hidden admin bypasses
Write business rules in UI code
Create generic workflow engines
Collapse multiple decisions into one
Violations invalidate the output.

Quality Gate (PR Acceptance)
Generated code is accepted ONLY if:

Layer(s) are explicitly referenced
Decision is declared
State transitions are legal
Locks are enforced
Authority is respected
Failure modes are handled
If any condition fails, the PR is rejected.

Final Instruction to Antigravity
Optimize for correctness first, speed second.

ALIS is an institutional operating system. Mistakes do not fail silently — they become incidents.