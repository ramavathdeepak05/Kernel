ALIS Runtime & Operational Contract v1.0
(Single-University Production Deployment Model)
1. Purpose
This document defines the runtime execution laws governing ALIS in production.
It specifies:
Transaction model
Database conventions
Event bus behavior
Concurrency control
Audit guarantees
Deployment topology
Backup & disaster recovery
Observability
Security operations
Upgrade discipline
This contract is binding.
If runtime behavior violates this contract, the implementation is invalid.
2. Deployment Topology (Single University)
Each university deployment must consist of:
Application Service (FastAPI)
PostgreSQL Database (isolated)
Event Worker Service
Institutional Logic Sandbox Runtime
Local LLM Inference Server (Ollama)
Backup Service
Log Aggregation Service
Each university deployment is physically isolated.
No shared DB. No shared runtime. No shared inference server. No shared policy store.
Codebase is shared. Runtime is isolated.
3. Transaction Model
3.1 Wizard Execution Boundary
One Wizard = One Database Transaction
Rules:
All state mutation occurs inside a single atomic transaction.
AI calls occur outside transaction.
ILL execution occurs outside transaction.
Core commit occurs inside transaction.
Event emission occurs only after commit.
No partial commits allowed.
3.2 Transaction Integrity
Use optimistic locking (version column).
Use row-level locking for critical entities.
Prevent concurrent seat allocation.
Prevent double payment reconciliation.
Prevent duplicate enrollment.
Failed transaction must roll back fully.
4. Database Conventions
All stateful tables must include:
id (UUID)
institution_id
state
version (integer)
created_at
updated_at
Financial tables must include:
immutable flag
voucher_id
ledger_reference
audit_hash
Hard deletes are prohibited.
Corrections must use forward state transitions.
5. State Machine Enforcement
State transitions validated centrally.
Backward transitions rejected.
Illegal transitions rejected at runtime.
State mutation cannot occur via UI.
State legality precedes business logic.
6. Global Lock Enforcement
Before any state mutation:
Check global locks.
If locked → fail immediately.
No advisory override allowed.
Lock evaluation precedes ILL execution.
Global Locks are evaluated in fixed order:
Financial
Academic eligibility
Disciplinary
Regulatory hold
Order is invariant.
7. Event Bus Model
7.1 Event Discipline
All cross-module interaction must use events.
Events must be:
Stored in DB
Idempotent
Versioned
Retry-safe
Direct cross-module writes are forbidden.
7.2 Event Processing
Consumers must check idempotency key.
Duplicate processing must not mutate state twice.
Events processed asynchronously.
Failed events logged and retried.
Event handlers must re-check state legality.
8. Institutional Logic Execution
ILL execution rules:
Executed outside DB transaction.
Executed in sandbox.
Execution timeout enforced.
Determinism verified.
Output validated before commit.
Execution hash logged.
If ILL fails:
Abort wizard.
No state commit.
Log failure.
9. AI Execution Rules
AI executed via LangGraph + Ollama.
No cloud inference.
AI read-only.
AI returns structured draft only.
AI confidence threshold enforced.
AI cannot commit state.
All AI prompts must log:
model_version
prompt_version
embedding_version
10. Audit Model
Every state-changing action must log:
entity_id
previous_state
next_state
actor_id
actor_role
policy_version
logic_version
execution_hash
timestamp
override_id (if any)
Audit log is append-only.
Audit log cannot be deleted.
Audit log must support replay.
11. Backup & Disaster Recovery
11.1 Backup Frequency
DB backup daily.
Incremental backup hourly.
Policy registry backup daily.
Logic registry backup daily.
Model artifacts backup weekly.
11.2 Retention
Daily backups retained 30 days.
Monthly backups retained 12 months.
Audit retained minimum 7 years.
11.3 RPO / RTO
RPO: ≤ 1 hour
RTO: ≤ 4 hours
Restore testing must occur quarterly.
12. Observability
System must expose:
Structured logs
Error logs
State transition logs
Lock activation logs
ILL execution metrics
AI latency metrics
Event queue lag
DB connection pool metrics
Alerts must trigger on:
Lock frequency anomaly
Failed ILL execution spike
AI timeout spike
Event retry exhaustion
Policy resolution failure
13. Security Operations
JWT-based authentication.
Token expiry enforced.
Session invalidation supported.
MFA for administrative roles.
Password hashed via bcrypt.
Rate limiting enforced.
Brute-force detection active.
Role changes audited.
Admin cannot disable:
Audit
Lock
PolicyResolver
Authority enforcement
14. Data Sensitivity & PII
Data classification levels:
PUBLIC
INTERNAL
CONFIDENTIAL
REGULATED
AI context must exclude REGULATED data unless explicitly permitted.
Logs must redact:
Aadhaar
Bank account
PAN
Password
Tokens
15. Upgrade Discipline
Upgrades must:
Preserve schema compatibility.
Preserve registry integrity.
Preserve logic versions.
Preserve policy versions.
Preserve audit chain.
Schema migration must be deterministic.
No per-client schema changes allowed.
16. Performance Constraints
Define:
Max concurrent users: configurable per deployment.
AI timeout: 10 seconds max.
ILL timeout: 200 ms max.
DB transaction timeout: 5 seconds.
Event retry backoff exponential.
Max 3 retry attempts before manual flag.
17. Replay & Dispute Resolution
System must support:
Decision replay.
Policy version retrieval.
Logic version retrieval.
Audit diff viewer.
Lock reason visibility.
Override trace view.
Replay must use historical versions.
18. Governance Dashboard
Admin must be able to view:
Active policy versions
Active logic versions
Lock status
Override history
Event queue health
AI confidence anomaly report
No governance blind spots allowed.
19. Failure Hierarchy
Failures classified as:
Retryable
Provisional
Terminal
Human-intervention-required
System must never silently fail.
20. Final Runtime Law
If runtime behavior violates:
State legality
Lock enforcement
Policy resolution
Authority model
Audit immutability
The operation must halt.
Working behavior is not acceptable if it violates invariants.
Correctness overrides availability.