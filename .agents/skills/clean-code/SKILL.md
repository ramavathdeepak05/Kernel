---
name: clean-code
description: "This skill embodies the principles of \"Clean Code\" by Robert C. Martin (Uncle Bob). Use it to transform \"code that works\" into \"code that is clean.\" QUAICU kernel — applies the kernel glossary (Proposal vs Action vs GovernedAction), core/ export boundaries, frozen dataclasses, the six separate lifecycle steps, CEL-in-YAML (never assembled in Python), and guard-clause-first typed errors. Triggers — QUAICU, core boundaries, frozen dataclass, lifecycle steps, naming, Port suffix, Adapter suffix."
risk: safe
source: "ClawForge (https://github.com/jackjin1997/ClawForge)"
date_added: "2026-02-27"
---

# Clean Code Skill

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific clean-code choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.**

### Invariants — never violated
- Use the kernel glossary precisely: `Proposal` (submitted, not yet evaluated) vs `Action`/`GovernedAction` (in/through the lifecycle). Ports end in `*Port`; adapters end in `*Adapter`. Don't invent synonyms.
- `core/` exports only its domain vocabulary (Action, Policy, Evaluation, LedgerEntry, …). `core/` NEVER imports or re-exports concrete types from adapters/delivery.
- Domain models (`Action`, `Policy`, `LedgerEntry`) are immutable: `@dataclass(frozen=True)`. State changes produce a new value / explicit transition, never in-place mutation.
- The six lifecycle steps stay SEPARATE functions; never merge propose/evaluate/gate/execute/seal/emit "for brevity".
- Conditions are CEL in the policy envelope YAML; never assembled as a string in Python.

### Limits & guard style
| Item | Rule |
|---|---|
| Lifecycle orchestrator fn | ≤ ~40 lines |
| Single lifecycle step fn | ≤ ~30 lines |
| Error handling | guard clauses first (fail-closed), happy path last, no `else` to reach it |
| Exceptions | typed `QUAICUError` subtypes; never bare `Exception`; never catch-and-continue |
| Mutable default args | never (especially in policy definitions) |

### Tie-break rules
- Merge two steps to reduce boilerplate? → no; the six steps are a public contract.
- Mutate an Action in place to save an allocation? → no; frozen + transition.

### Self-check
- [ ] Glossary terms used exactly; `*Port`/`*Adapter` suffixes correct.
- [ ] Domain models frozen; no in-place mutation.
- [ ] Six steps separate; conditions are CEL in YAML, not Python strings.
- [ ] Guard-clause-first; typed errors; no catch-and-continue.

---

This skill embodies the principles of "Clean Code" by Robert C. Martin (Uncle Bob). Use it to transform "code that works" into "code that is clean."

## Core Philosophy
> "Code is clean if it can be read, and enhanced by a developer other than its original author." — Grady Booch

## When to Use
Use this skill when:
- **Writing new code**: To ensure high quality from the start.
- **Reviewing Pull Requests**: To provide constructive, principle-based feedback.
- **Refactoring legacy code**: To identify and remove code smells.
- **Improving team standards**: To align on industry-standard best practices.

## 1. Meaningful Names
- **Use Intention-Revealing Names**: `elapsedTimeInDays` instead of `d`.
- **Avoid Disinformation**: Don't use `accountList` if it's actually a `Map`.
- **Make Meaningful Distinctions**: Avoid `ProductData` vs `ProductInfo`.
- **Use Pronounceable/Searchable Names**: Avoid `genymdhms`.
- **Class Names**: Use nouns (`Customer`, `WikiPage`). Avoid `Manager`, `Data`.
- **Method Names**: Use verbs (`postPayment`, `deletePage`).

## 2. Functions
- **Small!**: Functions should be shorter than you think.
- **Do One Thing**: A function should do only one thing, and do it well.
- **One Level of Abstraction**: Don't mix high-level business logic with low-level details (like regex).
- **Descriptive Names**: `isPasswordValid` is better than `check`.
- **Arguments**: 0 is ideal, 1-2 is okay, 3+ requires a very strong justification.
- **No Side Effects**: Functions shouldn't secretly change global state.

## 3. Comments
- **Don't Comment Bad Code—Rewrite It**: Most comments are a sign of failure to express ourselves in code.
- **Explain Yourself in Code**: 
  ```python
  # Check if employee is eligible for full benefits
  if employee.flags & HOURLY and employee.age > 65:
  ```
  vs
  ```python
  if employee.isEligibleForFullBenefits():
  ```
- **Good Comments**: Legal, Informative (regex intent), Clarification (external libraries), TODOs.
- **Bad Comments**: Mumbling, Redundant, Misleading, Mandated, Noise, Position Markers.

## 4. Formatting
- **The Newspaper Metaphor**: High-level concepts at the top, details at the bottom.
- **Vertical Density**: Related lines should be close to each other.
- **Distance**: Variables should be declared near their usage.
- **Indentation**: Essential for structural readability.

## 5. Objects and Data Structures
- **Data Abstraction**: Hide the implementation behind interfaces.
- **The Law of Demeter**: A module should not know about the innards of the objects it manipulates. Avoid `a.getB().getC().doSomething()`.
- **Data Transfer Objects (DTO)**: Classes with public variables and no functions.

## 6. Error Handling
- **Use Exceptions instead of Return Codes**: Keeps logic clean.
- **Write Try-Catch-Finally First**: Defines the scope of the operation.
- **Don't Return Null**: It forces the caller to check for null every time.
- **Don't Pass Null**: Leads to `NullPointerException`.

## 7. Unit Tests
- **The Three Laws of TDD**:
  1. Don't write production code until you have a failing unit test.
  2. Don't write more of a unit test than is sufficient to fail.
  3. Don't write more production code than is sufficient to pass the failing test.
- **F.I.R.S.T. Principles**: Fast, Independent, Repeatable, Self-Validating, Timely.

## 8. Classes
- **Small!**: Classes should have a single responsibility (SRP).
- **The Stepdown Rule**: We want the code to read like a top-down narrative.

## 9. Smells and Heuristics
- **Rigidity**: Hard to change.
- **Fragility**: Breaks in many places.
- **Immobility**: Hard to reuse.
- **Viscosity**: Hard to do the right thing.
- **Needless Complexity/Repetition**.

## Implementation Checklist
- [ ] Is this function smaller than 20 lines?
- [ ] Does this function do exactly one thing?
- [ ] Are all names searchable and intention-revealing?
- [ ] Have I avoided comments by making the code clearer?
- [ ] Am I passing too many arguments?
- [ ] Is there a failing test for this change?

## Limitations
- Use this skill only when the task clearly matches the scope described above.
- Do not treat the output as a substitute for environment-specific validation, testing, or expert review.
- Stop and ask for clarification if required inputs, permissions, safety boundaries, or success criteria are missing.

---

## QUAICU-Specific Application

This section extends clean code principles to the specific naming, module boundaries, function-length rules, and extraction decisions that apply to the QUAICU governance kernel codebase. These rules are derived directly from the spec (Glossary, §4, §7, Frozen Architecture Decisions). They exist because the kernel is a **governance product** — ambiguity in naming or leaky module boundaries is not just untidy code, it is a correctness and auditability risk.

### Naming Conventions — Use the Exact Glossary Terms

The spec establishes a glossary. Every name in every file in `core/` must come from that glossary. Using synonyms or abbreviations — even intuitive ones — creates drift between code and spec, which means code reviews and audits become translation exercises.

**The three most commonly confused terms and how to tell them apart:**

| Term | What it is | What it is NOT |
|------|-----------|----------------|
| `Action` | The proposed change to institutional state — the thing being governed. Has `type`, `payload`, `actor`, `tenant`. | Not the Python `typing.Protocol`. Not a Celery task. Not an HTTP request. |
| `GovernedAction` | An `Action` that has completed the **full lifecycle** — evaluate → gate → execute → seal → emit. It is sealed in the TrustLedger. | Not just any approved action. Not an action mid-lifecycle. |
| `Proposal` | The **act** of submitting an action. A proposal enters the lifecycle but never executes directly. | Not a `GovernedAction`. Not a draft policy. |

**Port vs Adapter vs Delivery — three architecture layers that must not bleed into each other's names:**

| Term | Where it lives | Naming rule |
|------|---------------|-------------|
| `Port` | `core/ports/*.py` | `InferencePort`, `HITLPort`, `WorkflowPort` — always `*Port` suffix, always a `typing.Protocol` or ABC |
| `Adapter` | `adapters/**/*.py` | `OllamaInferenceAdapter`, `TemporalWorkflowAdapter` — always `*Adapter` suffix, always implements exactly one Port |
| `Delivery` | `delivery/sdk/`, `delivery/api/`, `delivery/docker/` | Thin wrappers: `KernelSDK`, `KernelFastAPIApp` — never contains governance logic |

**Concrete naming rules:**

```python
# CORRECT — names match the glossary exactly
class Action:           ...   # the proposed change
class GovernedAction:   ...   # completed the full lifecycle
class Proposal:         ...   # the act of submission
class Policy:           ...   # a rule stored as data
class EvaluationResult: ...   # output of the Policy Engine step
class Gate:             ...   # HITL checkpoint
class LedgerEntry:      ...   # a sealed entry in the TrustLedger
class TrustLedger:      ...   # the ledger itself

# WRONG — do not use these, even if they feel natural
class ActionRecord:     ...   # "Record" adds nothing; use LedgerEntry
class ApprovalRequest:  ...   # should be Proposal or Gate depending on context
class PolicyRule:       ...   # "Rule" is not in the glossary; Policy is
class WorkflowStep:     ...   # the kernel calls these lifecycle steps, not workflow steps
class GovernanceAction: ...   # "Governance" is redundant; Action is already the governed concept
```

**Lifecycle step functions must use the verb from the spec lifecycle contract:**

```python
# core/lifecycle/engine.py
# The lifecycle contract is: propose → evaluate → gate → execute → seal → emit
# Every function name maps directly to one step. No synonyms.

async def propose(action: Action, *, tenant: TenantId) -> Proposal: ...
async def evaluate(proposal: Proposal) -> EvaluationResult: ...
async def gate(result: EvaluationResult) -> GateOutcome: ...
async def execute(outcome: GateOutcome) -> ExecutionResult: ...
async def seal(result: ExecutionResult) -> LedgerEntry: ...
async def emit(entry: LedgerEntry) -> None: ...

# WRONG — do not rename lifecycle steps even for brevity
async def check(...)    ...   # evaluate
async def approve(...)  ...   # gate
async def run(...)      ...   # execute
async def record(...)   ...   # seal
async def publish(...)  ...   # emit
```

### Module Boundary Rules — What `core/` Exports vs What `adapters/` Exports

The single most important structural rule is stated in ADR F-08: **core depends only on `core/ports/` interfaces — never on a concrete adapter or model SDK.** Clean code enforces this with module boundary discipline, not just willpower.

**What `core/` may export (public surface):**

- Domain types: `Action`, `GovernedAction`, `Proposal`, `Policy`, `LedgerEntry`, etc.
- Port interfaces: `InferencePort`, `HITLPort`, `StoragePort`, `WorkflowPort`, `IdentityPort`
- Lifecycle functions: `propose`, `evaluate`, `gate`, `execute`, `seal`, `emit`
- Exceptions: `GovernanceError`, `PolicyDeniedError`, `TenantIsolationError`, `FailClosedError`
- Layer public APIs: `PolicyEngine.evaluate()`, `TrustLedger.append()`, `TrustLedger.verify()`

**What `core/` must NEVER export or import:**

- Any concrete database driver, ORM model class, or SQL query
- Any HTTP client, model SDK (`openai`, `anthropic`, `boto3`)
- Any specific queue client (ARQ, Dramatiq, Temporal SDK)
- Any secrets-manager client (OpenBao SDK)
- Any domain-specific concept from the host application (student, loan, patient, invoice, etc.)

**`core/` never re-exports concrete types.** Even if a concrete type (e.g. a SQLAlchemy model) is imported deep inside an adapter, it must never surface through a `core/` `__init__.py` or public import path. The rule is not just "don't import in core" — it is "never allow a concrete type to be reachable by traversing `core/` imports." Any `from core import X` must resolve to an abstract type, a Protocol, a frozen dataclass, or a pure function. If `X` is backed by SQLAlchemy, asyncpg, or any external library, the import boundary is violated regardless of where the concrete class is defined.

**What `adapters/` exports (and the rule on imports):**

- Concrete adapter classes that implement one Port each
- `adapters/` MAY import from `core/ports/` (to implement the interface) and from `core/` types (to use domain types)
- `adapters/` must NEVER import from `delivery/` — adapters do not know about HTTP or SDK surfaces

**What `delivery/` exports:**

- HTTP route handlers (`delivery/api/`) that call core lifecycle functions
- The `@governed` decorator (`delivery/sdk/`) that wraps a function with the full lifecycle
- Delivery must NEVER contain governance logic — if you find a `CEL.eval()` call in `delivery/`, that is a boundary violation

**CI enforcement — add these checks:**

```python
# tests/architecture/test_module_boundaries.py
import ast, pathlib, pytest

FORBIDDEN_IN_CORE = [
    "openai", "anthropic", "boto3", "httpx", "sqlalchemy",
    "asyncpg", "dramatiq", "arq", "temporalio", "openbao",
    # Domain concepts — expand this list with your specific domain terms
    "student", "loan", "patient", "invoice", "user_account",
]

def _imports_in_file(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text())
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module.split(".")[0])
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    modules.append(alias.name.split(".")[0])
    return modules

@pytest.mark.parametrize("py_file", pathlib.Path("core").rglob("*.py"))
def test_no_forbidden_imports_in_core(py_file):
    imports = _imports_in_file(py_file)
    violations = [i for i in imports if i in FORBIDDEN_IN_CORE]
    assert not violations, (
        f"{py_file} imports forbidden modules: {violations}\n"
        "core/ must depend only on core/ports/ interfaces — ADR F-08."
    )
```

### Function Length Rules for Lifecycle Steps

The lifecycle spine (`propose → evaluate → gate → execute → seal → emit`) is the most safety-critical code in the kernel. Every arrow in the chain is a point where fail-closed applies. Function length rules here are stricter than standard clean code because long lifecycle functions obscure the fail-closed guarantee.

**Rules:**

- **Lifecycle orchestrator** (`core/lifecycle/engine.py` top-level function that calls all six steps): max 40 lines. It must read as a sequential narrative — call step one, handle error, call step two, handle error. No inline logic.
- **Each lifecycle step function** (`evaluate`, `gate`, `execute`, `seal`, `emit`): max 30 lines. If it exceeds 30 lines, extract the sub-logic into a clearly named helper.
- **Policy evaluation** (`core/policy/engine.py` `evaluate` method): max 25 lines for the core decision logic. CEL evaluation, conflict resolution, and result construction are three distinct concerns — extract each.
- **Ledger append** (`core/ledger/ledger.py` `append` method): max 20 lines. Compute hash, build Merkle node, write to storage, return entry. One line per clear step.
- **Port interface methods**: single responsibility — if an adapter method exceeds 25 lines, it is probably doing two things.

**The steps must never be merged.** The spec lifecycle contract has six named steps for a reason — each is a distinct governance checkpoint. Do not combine `evaluate` and `gate` into a single `evaluate_and_gate` function, or `seal` and `emit` into a single `seal_and_emit` function. Merging steps hides the point at which fail-closed applies and makes it impossible to test each checkpoint independently. If you find yourself wanting to merge two lifecycle steps, you are solving the wrong problem — the problem is likely that the individual step functions are too long, not that there are too many of them.

**The extraction rule for lifecycle steps:**

Extract when the name of the extracted function reveals a distinct governance concept. Inline when the logic is purely mechanical and the extraction would require a comment to explain what the helper does.

```python
# EXTRACT — "resolve_applicable_policies" reveals a distinct governance concept
async def evaluate(proposal: Proposal) -> EvaluationResult:
    applicable = await self._resolve_applicable_policies(proposal)
    cel_results = await self._run_cel_evaluation(proposal, applicable)
    return self._resolve_conflicts(cel_results)   # deny overrides allow — ADR spec §1

async def _resolve_applicable_policies(self, proposal: Proposal) -> list[Policy]:
    # Finds all ACTIVATED policies whose `governs` matches the action type
    # and whose `scope` covers the proposal's tenant
    ...

# INLINE — this is mechanical construction, not a governance concept
async def seal(result: ExecutionResult) -> LedgerEntry:
    leaf_hash = sha256(result.canonical_bytes()).digest()
    node = self._ledger.append_leaf(leaf_hash)    # <-- inline: "append a Merkle leaf"
    return LedgerEntry(
        action_id=result.action_id,
        leaf_index=node.index,
        inclusion_proof=node.proof,
        sealed_at=utc_now(),
    )
```

### When to Extract vs Inline in Policy Evaluation

Policy evaluation (`core/policy/engine.py`) is the step where the three most important clean code decisions arise for this codebase. The rules below prevent both over-extraction (tiny helper functions that obscure the algorithm) and under-extraction (one giant function that mixes CEL evaluation with conflict resolution with tenant scoping).

**Extract into a named method when:**

1. The block is a distinct, named step in the spec's policy evaluation pipeline (scope resolution, CEL evaluation, conflict resolution, result construction).
2. The block has a clear postcondition that can be stated in one sentence and tested independently.
3. The block is reused — policy pre-flight (`POST /policy/evaluate`) uses the same evaluation logic as the live lifecycle.

**Inline when:**

1. The code is a single conditional that enforces a Core Invariant — inlining the invariant check keeps it visible in the function where it must hold.
2. Extracting would require a docstring to explain what the helper does, because the logic has no name beyond "the next few lines."

**CEL conditions belong in the policy envelope YAML, not scattered in Python.** The spec (§3.9) is explicit: conditions live in the declarative envelope (`condition: |` field) and are evaluated by the CEL engine. Do not let CEL expressions drift into Python — not as string constants in `core/policy/`, not as f-strings assembled in adapters, not as hardcoded strings in tests that happen to be valid CEL. The policy envelope YAML is the single source of truth for conditions. Python code calls `cel_env.compile(policy.condition)` and evaluates it; it never constructs CEL expressions itself.

```python
# WRONG — CEL condition assembled in Python
async def _evaluate_single_policy(self, proposal, policy):
    # This violates the envelope principle — conditions belong in YAML
    cel_expr = f"action.payload.amount > {policy.threshold}"
    return self._cel_env.eval(cel_expr, {"action": proposal.action})

# CORRECT — CEL condition comes from the sealed policy envelope
async def _evaluate_single_policy(self, proposal: Proposal, policy: Policy) -> SinglePolicyResult:
    # policy.condition is the CEL string from the stored policy envelope
    # It was compile-checked at policy creation time (§3.9 authoring pipeline)
    program = self._cel_env.compile(policy.condition)
    return program.evaluate({"action": proposal.action.to_cel_map()})
```

**Canonical extraction pattern for policy evaluation:**

```python
# core/policy/engine.py
class PolicyEngine:

    async def evaluate(
        self,
        proposal: Proposal,
        *,
        tenant: TenantId,
    ) -> EvaluationResult:
        """
        Evaluate a proposal against all applicable active policies.
        Returns allow | deny | require_approval.
        Fail-closed: any exception → deny. Never allow on uncertainty.
        """
        try:
            policies = await self._fetch_applicable_policies(proposal, tenant=tenant)
            if not policies:
                # Fail-closed: no applicable policy → deny (never allow by default)
                return EvaluationResult.deny(reason="no_applicable_policy")

            raw_results = [self._evaluate_single_policy(proposal, p) for p in policies]
            return self._resolve_conflicts(raw_results)

        except Exception as exc:
            # Fail-closed: any error in evaluation → deny, never allow
            self._audit_log.error("policy_evaluation_error", exc=exc, proposal_id=proposal.id)
            raise FailClosedError("Policy evaluation failed — action denied") from exc

    def _fetch_applicable_policies(
        self, proposal: Proposal, *, tenant: TenantId
    ) -> list[Policy]:
        # Scope: ACTIVATED policies whose `governs` matches proposal.type
        # and whose `scope.tenant` is "*" or matches the tenant
        ...

    def _evaluate_single_policy(
        self, proposal: Proposal, policy: Policy
    ) -> SinglePolicyResult:
        # CEL evaluation — sandboxed, no I/O, no clock (ADR F-05)
        # cel_env has no access to wall-clock, network, or randomness
        ...

    def _resolve_conflicts(
        self, results: list[SinglePolicyResult]
    ) -> EvaluationResult:
        # Conflict resolution order (spec §1 Core Invariants):
        # 1. deny overrides allow (fail-closed)
        # 2. most-specific scope wins over broader scope
        # 3. require_approval is the middle outcome between allow and deny
        # This method must NEVER return an undefined outcome.
        ...
```

### Anti-Patterns in Governance Code

These are the patterns that are harmless in general software but are **correctness bugs** in a governance kernel. Each one has a description of why it is dangerous here, not just stylistically bad.

#### Anti-Pattern 1 — Catching exceptions and proceeding instead of re-raising

```python
# WRONG — swallowing an exception in a lifecycle step is a fail-open bug
async def evaluate(self, proposal: Proposal) -> EvaluationResult:
    try:
        return await self._policy_engine.evaluate(proposal)
    except PolicyServiceUnavailableError:
        # "Handle" the error by returning allow — catastrophic governance failure
        logger.warning("Policy service unavailable, allowing action")
        return EvaluationResult.allow(reason="policy_service_unavailable")

# CORRECT — re-raise as FailClosedError so the lifecycle halts
async def evaluate(self, proposal: Proposal) -> EvaluationResult:
    try:
        return await self._policy_engine.evaluate(proposal)
    except PolicyServiceUnavailableError as exc:
        # Fail-closed: spec §1 F-03 — if we cannot evaluate, we cannot allow
        raise FailClosedError("Policy service unavailable — action denied") from exc
```

The spec (F-03) is unambiguous: "If the policy service is unreachable, let it proceed" is a catastrophic bug, not a convenience. Every `except` block in a lifecycle step must either re-raise as `FailClosedError` or raise a more specific governance exception. It must never return a permissive default.

#### Anti-Pattern 2 — Returning `None` from port methods

Port methods defined in `core/ports/` are the contract that core depends on. A port method that returns `None` silently to signal "not found" or "unavailable" forces every call site to null-check, and one missed null-check is a fail-open bug.

```python
# WRONG — None return from a port method
class HITLPort(Protocol):
    async def poll(self, handle: ApprovalHandle) -> ApprovalDecision | None: ...
    # None means what? Timeout? Not found? Adapter error? The caller can't tell.

# CORRECT — raise on error, use a typed enum for all outcomes
class HITLPort(Protocol):
    async def poll(self, handle: ApprovalHandle) -> ApprovalDecision: ...
    # ApprovalDecision is PENDING | APPROVED | REJECTED — always one of these
    # On timeout: raise HITLTimeoutError (caller treats as fail-closed)
    # On adapter error: raise HITLAdapterError (caller re-raises as FailClosedError)
```

#### Anti-Pattern 3 — Using wall-clock in evaluation logic

CEL evaluation must be deterministic (spec §1 Core Invariants, F-05). Wall-clock is non-deterministic — it produces a different result on replay. Any policy condition that branches on the current time violates replay fidelity and the determinism invariant.

```python
# WRONG — wall-clock in evaluation
async def _evaluate_single_policy(self, proposal, policy):
    context = {
        "action": proposal.action.to_cel_map(),
        "now": datetime.utcnow().isoformat(),   # <-- non-deterministic: breaks replay
    }
    return self._cel_env.eval(policy.condition, context)

# CORRECT — time comes from the proposal (recorded at submission, replayed identically)
async def _evaluate_single_policy(self, proposal, policy):
    context = {
        "action": proposal.action.to_cel_map(),
        "proposal_time": proposal.submitted_at.isoformat(),  # from the proposal record
    }
    return self._cel_env.eval(policy.condition, context)
```

If a policy genuinely needs to reason about time (e.g. "was this submitted during business hours"), the time used must be the recorded submission time from the proposal, never `datetime.utcnow()` or `time.time()` called inside the evaluation function.

#### Anti-Pattern 4 — Mutable default arguments in policy definitions

Python's mutable default argument trap is doubled in risk when it affects policy definitions, because a shared mutable default in a policy's `__init__` means two policy instances may silently share state.

```python
# WRONG — mutable default in policy constructor
@dataclass
class Policy:
    regulatory_refs: list[str] = []   # shared between all Policy() instances!
    approvers: list[str] = []         # same trap

# CORRECT — use field(default_factory=...) or None + post-init
from dataclasses import dataclass, field

@dataclass(frozen=True)   # frozen=True enforces immutability after creation
class Policy:
    id: str
    version: int
    condition: str
    decision: PolicyDecision
    regulatory_refs: tuple[str, ...] = field(default_factory=tuple)
    approvers: tuple[str, ...] = field(default_factory=tuple)
```

Note that `frozen=True` is not optional here — see the Immutability Patterns section below.

#### Anti-Pattern 5 — Using `isinstance` checks on `Action` subclasses in core

If `core/` code branches on the type of an `Action` subclass, it is a hidden fork — the equivalent of `if customer == "bank":` in the core logic (violating ADR F-01). Action types are identified by their `type` string (e.g. `"ciro.ifrs9.stage_transition"`), resolved by policy. Core must never inspect the Python class of an action.

```python
# WRONG — type dispatch in core
async def execute(self, outcome: GateOutcome) -> ExecutionResult:
    if isinstance(outcome.action, LoanReclassificationAction):
        # domain logic leaking into core — violates zero-domain-imports rule
        ...
    elif isinstance(outcome.action, ModelRoutingAction):
        ...

# CORRECT — core calls execute() on the port; the adapter knows the type
async def execute(self, outcome: GateOutcome) -> ExecutionResult:
    # The execution adapter is responsible for dispatching by action type.
    # Core only cares that execute() was called and the port returned a result.
    return await self._workflow_port.execute_action(outcome)
```

### Commenting Rules for Governance Code

The standard clean code rule is "don't comment what the code does — comment why." In governance code this principle has a sharper form: **comment why a step is fail-closed, not what it does.**

**When a comment is required (not optional) in governance code:**

1. Any `except` block in a lifecycle step that re-raises as `FailClosedError`. The comment must name the spec section that requires this behavior.
2. Any guard clause that checks a failure condition before the happy path (see Guard Clauses section). The comment must state what invariant is being protected.
3. Any place where an action is denied or halted due to an absence of data (e.g. "no applicable policy found → deny"). Denial-by-absence is counterintuitive and must be explained.
4. The conflict resolution order in `_resolve_conflicts`. The order is spec-defined; a future maintainer must know why deny overrides allow and where that rule comes from.

**What not to comment in governance code:**

```python
# BAD — comments the "what," not the "why"
# Get the policies for this proposal
policies = await self._fetch_applicable_policies(proposal, tenant=tenant)

# Check if policies list is empty
if not policies:
    return EvaluationResult.deny(reason="no_applicable_policy")

# GOOD — comment explains the governance reason (why fail-closed here)
policies = await self._fetch_applicable_policies(proposal, tenant=tenant)
if not policies:
    # Fail-closed: spec §1 — no applicable policy is not "allow by default."
    # Absence of a rule governing an action type is a gap, not permission.
    # This prevents unreviewed action types from slipping through.
    return EvaluationResult.deny(reason="no_applicable_policy")
```

**Seal-step comments are mandatory.** The `seal` step is the irreversible write to the TrustLedger. Any code that writes to the ledger must have a comment explaining why it runs only after all prior steps have succeeded. This comment is the audit trail in the code — it explains the causal chain to a future security reviewer.

```python
async def seal(result: ExecutionResult) -> LedgerEntry:
    # Seal runs only after evaluate, gate, and execute have all returned
    # successfully. At this point: the action has been evaluated against all
    # applicable policies, approved (by policy or HITL), and the state
    # transition has been applied. Sealing records the completed governed action
    # with an RFC 6962-style inclusion proof. The entry is immutable after this.
    ...
```

### Immutability Patterns for Core Domain Objects

The spec (§3.13) requires that sealed ledger entries are never modified. The clean code pattern that enforces this is `@dataclass(frozen=True)` on all core domain types that represent completed or in-transit governance state. Immutability is not a performance concern here — it is a correctness guarantee that the domain objects cannot be mutated after construction.

**Frozen dataclasses for `Action`, `Policy`, `LedgerEntry`:**

```python
from dataclasses import dataclass, field
from datetime import datetime

@dataclass(frozen=True)
class Action:
    """
    The proposed change to institutional state. Immutable after construction.
    Any "modification" creates a new Action — Actions are never mutated in place.
    """
    id: str
    type: str                              # e.g. "ciro.ifrs9.stage_transition"
    payload: dict                          # frozen via __post_init__ hash check
    actor: str
    tenant: str
    idempotency_key: str
    submitted_at: datetime

    def __post_init__(self):
        # Freeze the payload dict by converting to a hashable representation.
        # frozen=True prevents attribute reassignment but not dict mutation.
        object.__setattr__(self, 'payload', _freeze_dict(self.payload))


@dataclass(frozen=True)
class Policy:
    """
    A governance rule stored as data. Immutable once activated.
    A change to a policy is a new version — the old version is never mutated.
    """
    id: str
    version: int
    governs: str                           # action type this policy applies to
    condition: str                         # CEL string from the envelope YAML
    decision: PolicyDecision               # ALLOW | DENY | REQUIRE_APPROVAL
    regulatory_refs: tuple[str, ...] = field(default_factory=tuple)
    approvers: tuple[str, ...] = field(default_factory=tuple)
    lifecycle: PolicyLifecycle = PolicyLifecycle.DRAFT


@dataclass(frozen=True)
class LedgerEntry:
    """
    A sealed entry in the TrustLedger. Never modified after creation.
    Immutability here is not convention — it is the product's core guarantee.
    """
    action_id: str
    leaf_index: int
    inclusion_proof: bytes
    tree_head_hash: bytes
    sealed_at: datetime
    policy_versions: tuple[str, ...]       # policies evaluated at seal time
    evaluation_result: str                 # ALLOW | DENY | REQUIRE_APPROVAL
```

**Why `frozen=True` and not just "don't mutate it":**
A governance kernel that relies on programmer discipline to not mutate a `LedgerEntry` is not a governance kernel — it is a suggestion. `frozen=True` makes mutation a `FrozenInstanceError` at runtime and a type error in static analysis. The cost is negligible; the correctness guarantee is not.

**When you need a "mutable stage" during construction:**
Use a builder or intermediate dataclass without `frozen=True`, then convert to the frozen type at the end of the construction phase. Never pass a partially-constructed frozen type through multiple functions.

```python
# Use an intermediate builder for constructing complex entries
@dataclass
class LedgerEntryBuilder:
    action_id: str
    policy_versions: list[str] = field(default_factory=list)
    # ... mutable fields during construction

    def build(self, *, leaf_index: int, inclusion_proof: bytes, ...) -> LedgerEntry:
        # Freezes into the immutable type — the builder is discarded after this
        return LedgerEntry(
            action_id=self.action_id,
            leaf_index=leaf_index,
            policy_versions=tuple(self.policy_versions),
            ...
        )
```

### Guard Clauses for Fail-Closed

The standard clean code pattern for guard clauses is "check the failure conditions first, return early, then write the happy path." In governance code this pattern is mandatory — it is how the fail-closed invariant is made visible in the function structure.

**The pattern:**

```python
# WRONG — happy path first, failure conditions buried at the end
async def gate(self, result: EvaluationResult) -> GateOutcome:
    if result.decision == PolicyDecision.ALLOW:
        # ... happy path logic ...
        return GateOutcome.proceed(result)
    elif result.decision == PolicyDecision.REQUIRE_APPROVAL:
        handle = await self._hitl_port.request_approval(...)
        decision = await self._hitl_port.poll(handle)
        if decision == ApprovalDecision.APPROVED:
            return GateOutcome.proceed(result)
        else:
            return GateOutcome.halt(reason="approval_rejected")
    else:
        return GateOutcome.halt(reason="policy_denied")   # buried — easy to miss

# CORRECT — check all failure/halt conditions first, happy path last
async def gate(self, result: EvaluationResult) -> GateOutcome:
    # Guard 1: deny is the dominant outcome — check first (spec §1: deny overrides allow)
    if result.decision == PolicyDecision.DENY:
        return GateOutcome.halt(
            reason="policy_denied",
            policy_ref=result.deciding_policy_id,
        )

    # Guard 2: HITL required — halt until human decides
    if result.decision == PolicyDecision.REQUIRE_APPROVAL:
        handle = await self._hitl_port.request_approval(
            action=result.proposal.action,
            approvers=result.required_approvers,
            tenant=result.proposal.tenant,
        )
        decision = await self._hitl_port.poll(handle)
        if decision != ApprovalDecision.APPROVED:
            # Fail-closed: anything other than explicit APPROVED is a halt
            # (REJECTED and PENDING_TIMEOUT both resolve to no-execute — spec §5 HITLPort)
            return GateOutcome.halt(reason=f"hitl_{decision.value.lower()}")

    # Happy path: ALLOW (or HITL approved) — proceed to execute
    return GateOutcome.proceed(result)
```

**The guard clause rule for governance functions:**

1. Check DENY first — it is the dominant outcome by spec design.
2. Check HALT/REQUIRE conditions next.
3. Check error/timeout conditions after HALT.
4. The happy path (proceed to the next lifecycle step) is always the last branch.

This structure makes it impossible to accidentally fall through to the happy path when a failure condition is present — you have to explicitly reach the last line.

**Never use `else` to reach the happy path.** An `else` at the end of a chain of governance checks is easy to read past. The happy path should be unreachable unless all failure guards have explicitly passed.

### QUAICU Clean Code Checklist

When reviewing any file in `core/`, enforce these on top of the standard checklist:

- [ ] All domain names come from the spec glossary — no synonyms, no abbreviations
- [ ] Lifecycle step functions (`propose`, `evaluate`, `gate`, `execute`, `seal`, `emit`) are named exactly as in the spec lifecycle contract — no renames
- [ ] No lifecycle steps are merged — each of the six steps is a distinct function
- [ ] No import of a concrete adapter, database driver, or model SDK in any `core/` file
- [ ] `core/` does not re-export any concrete type — all `from core import X` resolve to Protocols, frozen dataclasses, or pure functions
- [ ] No domain-specific term (patient, loan, student, etc.) appears in `core/` — CI grep check is passing
- [ ] Port interfaces are named `*Port` and live in `core/ports/`
- [ ] Adapter classes are named `*Adapter`, live in `adapters/`, and implement exactly one Port
- [ ] No port method returns `None` — errors raise typed exceptions; outcomes use typed enums
- [ ] Lifecycle orchestrator function is under 40 lines; individual step functions are under 30 lines
- [ ] Policy `evaluate()` method is under 25 lines; each sub-step is a named extracted method
- [ ] CEL conditions live in policy envelope YAML — no CEL strings assembled in Python
- [ ] No wall-clock (`datetime.utcnow()`, `time.time()`) inside CEL evaluation context construction
- [ ] No mutable default arguments in `Policy`, `Action`, or `LedgerEntry` dataclasses
- [ ] `Action`, `Policy`, and `LedgerEntry` are `@dataclass(frozen=True)`
- [ ] Every `except` block in a lifecycle step re-raises as `FailClosedError` or a specific governance exception — never returns a permissive default
- [ ] All failure/halt guard clauses appear before the happy path in every lifecycle function
- [ ] Comments on lifecycle steps explain WHY a step is fail-closed, not what it does
- [ ] The `seal` step has a mandatory comment explaining the causal chain
- [ ] No `isinstance` dispatch on `Action` subclasses in `core/`
- [ ] Every extracted helper name reveals a distinct governance concept from the spec
- [ ] No `if customer == "bank":` or customer-specific conditional in `core/` — divergence belongs in adapters or config (ADR F-01, F-11)
