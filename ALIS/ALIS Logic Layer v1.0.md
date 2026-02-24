ALIS Institutional Logic Layer (ILL) Specification v1.0
1. Purpose
The Institutional Logic Layer (ILL) enables per-university custom deterministic algorithms without modifying ALIS Core.
ILL allows deep institutional customization while preserving:
State legality
Lock enforcement
Audit immutability
Policy governance
Event discipline
Transaction integrity
Upgrade compatibility
The ILL computes outcomes.
The Core decides and commits.
2. Architectural Position
Copy code

ALIS Core (Invariant)
    - State Machine
    - Lock Engine
    - Audit Engine
    - Policy Resolver
    - Event Bus
    - RBAC
    - Transaction Manager

        ↓ invokes

Institutional Logic Layer (Custom)

        ↓ returns

Core Validation → Commit → Audit → Event
ILL never owns authority.
3. Design Principles
Core invariants are untouchable.
Custom logic must be deterministic.
Custom logic must be sandboxed.
Custom logic must be versioned.
Custom logic must be auditable.
Custom logic must not mutate state directly.
Custom logic must not access external systems.
4. Allowed Custom Decision Surfaces
ILL is allowed only at predefined decision surfaces.
Allowed Examples
Grade computation
Relative grading distribution
Scholarship scoring
Fee calculation
Installment schedule calculation
Payroll formula
Custom academic scoring logic
Explicitly Forbidden
State machine transitions
Lock definitions
Audit engine modification
Event emission
Ledger posting
Authority rules
Transaction boundaries
PolicyResolver override
Global lock override
5. Registration Model
Each logic module must be registered in the Logic Registry.
Example:
JSON
Copy code
{
  "logic_id": "grading_relative_v3",
  "module": "Examinations",
  "decision_surface": "grade_computation",
  "version": "3.0",
  "effective_from": "2026-06-01",
  "approved_by": "dean_id",
  "hash": "sha256:abc123..."
}
Requirements:
Unique logic_id
Version number
Effective date
Approval record
Execution hash
Audit trail
No logic may execute without registration.
6. Interface Contract
Each custom module must implement a strict interface.
Example (Grading):
Python
Copy code
class GradingStrategy:
    def compute(self, input_payload: dict, policy_context: dict) -> dict:
        pass
Rules:
Must be pure function.
Must return structured result.
Must not write to DB.
Must not call network.
Must not access filesystem.
Must not import arbitrary modules.
Must not mutate global state.
Must not emit events.
Must not log audit.
Return example:
JSON
Copy code
{
  "result": "A",
  "numeric_score": 8.7,
  "metadata": {},
  "confidence": 1.0
}
7. Sandboxing Requirements
ILL execution must occur inside a restricted runtime:
No network access
No file access
No subprocess
No OS calls
Memory limits enforced
CPU time limit enforced (e.g., 200ms)
No dynamic import
No reflection
No access to application internals
Execution must be isolated from main app process.
8. Determinism Requirement
Logic must be:
Deterministic
Same input → same output
No random unless seeded and logged
No time-dependent logic except via provided context
No side effects
Non-deterministic modules must be rejected.
9. Policy Binding
Before invoking ILL:
Core resolves policies:
Python
Copy code
policy_context = PolicyResolver.get(policy_id, decision_date)
ILL receives policy_context as read-only input.
ILL may not hardcode thresholds.
All thresholds must come from policy_context.
10. Execution Flow
Core validates state legality.
Core checks Global Locks.
Core resolves policy.
Core invokes ILL.
ILL computes and returns result.
Core validates output format.
Core applies deterministic checks.
Core commits state change.
Core writes audit record.
Core emits events.
ILL never commits state.
11. Version Binding & Replay
Each decision must log:
logic_id
logic_version
policy_version
execution_hash
input_snapshot_hash
Replay engine must:
Load historical logic version.
Load historical policy version.
Recompute decision deterministically.
Retroactive logic mutation is forbidden.
12. Execution Hashing
Before activation:
Logic module content must be hashed.
Hash stored in registry.
Hash stored in audit per execution.
Silent logic change invalidates version.
13. Upgrade & Migration
When new logic version is uploaded:
Old version remains immutable.
Effective date controls activation.
Historical decisions remain bound to old version.
No retroactive modification allowed.
14. Validation Engine
Before activation, each logic module must pass:
Syntax validation
Interface compliance validation
Determinism validation
Resource limit test
Policy usage validation
Security sandbox validation
Performance test
Non-side-effect verification
Invalid modules cannot be activated.
15. Governance & Approval
Logic activation requires:
Authorized role
Approval workflow
Audit entry
Effective date
Rollback path
No immediate activation without governance.
16. Multi-Institution Isolation
Each university deployment must maintain:
Separate Logic Registry
Separate module storage
Separate execution environment
Separate model artifacts
Separate policy store
No cross-university sharing of custom logic.
17. Failure Handling
If ILL execution fails:
Core must not commit state.
Failure logged.
Decision enters provisional or failed state.
Human intervention required if necessary.
ILL failure must never corrupt state.
18. Security Model
ILL must:
Run in isolated environment.
Have no database credentials.
Have no environment variable access.
Have no internal service tokens.
Have no filesystem write permission.
Have no external connectivity.
19. Enforcement Priority
If conflict occurs between:
ILL logic
Policy
Lock
State legality
Core invariant rules prevail.
ILL output may be rejected by Core.
20. Summary
ILL enables:
Deep institutional flexibility
Custom algorithms
Unique grading systems
Unique financial computations
Without:
Code forks
Core mutation
Architectural drift
Upgrade collapse
Core governs. ILL computes. Audit records everything.