---
name: quaicu-policy-engine
description: |
  QUAICU K·01 Policy Engine — CEL-based policy evaluation, policy envelope authoring, lifecycle
  (DRAFT→REVIEW→ACTIVATED→DEPRECATED), simulation gate, activation gate enforcement, shadow mode,
  and conflict resolution. Use when building core/policy/, adapters for policy storage, the policy
  authoring API, or any code that evaluates or activates a policy. Enforces: CEL only (no eval, no
  Rego), determinism, total conflict resolution, fail-closed evaluation, mandatory backtest before
  activation. Trigger keywords: policy, PolicyEngine, CEL, condition, evaluate, policy_envelope,
  ACTIVATED, DRAFT, REVIEW, backtest, shadow_mode, impact_report, conflict_resolution, deny_overrides.
---

# QUAICU K·01 Policy Engine

You are the policy engine expert. The policy engine is the first step in every governed action's
lifecycle. It must be deterministic (identical inputs → identical decision), total (every action
gets a decision — never "undefined"), fail-closed (any error → DENY), and CEL-only for conditions.

---

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> Makes every policy choice mechanical so a small/low-token model matches a top model at max effort.
> **If this block conflicts with prose below, this block wins.** Missing rule → DENY and stop.

### Invariants — never violated
- ALWAYS write conditions in CEL. NEVER `eval`/`exec`, Rego, or a custom DSL (F-05).
- ALWAYS deterministic: same inputs → same decision. CEL gets NO clock/network/random/external state.
- ALWAYS total: every action gets exactly one decision. There is no "undefined" — empty result set → DENY.
- ALWAYS require a backtest impact report before ACTIVATED (F-10). No report → activation blocked.
- A CEL evaluation that errors or returns a non-bool → treat as `False` (condition did not match) → contributes to DENY, never allow.

### Conflict resolution (this precedence is total — apply exactly)
| If any applicable policy says… | Final decision |
|---|---|
| `deny` | **deny** (deny overrides everything) |
| else `require_approval` | **require_approval** |
| else `allow` (≥1 allow, no deny) | **allow** |
| no applicable policy / empty set | **deny** (fail-closed) |

### Scope resolution (specificity)
- More specific wins: exact tenant > group > wildcard; exact `action_type` > prefix > wildcard.
- A specificity TIE does not pick one — ALL tied policies apply and run through conflict resolution above.

### Policy lifecycle (allowed transitions only)
`DRAFT → REVIEW → ACTIVATED → DEPRECATED`. Activation requires ALL: status==REVIEW, CEL compiles, fresh impact report exists, reviewer ≠ author. Any missing → `PolicyActivationError`, stay in REVIEW.

### Tie-break rules
- Unsure whether an evaluation failure allows or denies? → DENY (condition treated as false/unmet).
- Unsure whether to block activation? → BLOCK (require the backtest). Activation is the dangerous direction.
- Shadow/simulation mode NEVER enforces — it records what WOULD happen; never denies a live action.

### Stop-and-apply triggers
- About to write `eval(`/assemble a condition string in Python? → STOP, author it as CEL in the envelope.
- About to return from `resolve()` with no matching policy? → return DENY, never allow.
- About to activate a policy? → verify all four preconditions first.

### Self-check
- [ ] No `eval`/`exec`/Rego anywhere; conditions are CEL strings in the envelope.
- [ ] `resolve()` returns a decision for every input including empty (→ deny).
- [ ] deny overrides require_approval overrides allow; empty → deny.
- [ ] Activation path verifies impact-report freshness + reviewer ≠ author.
- [ ] CEL eval errors map to False, not allow.

---

## Frozen Decision F-05 — CEL Is the Only Condition Language

| Language | Status | Reason |
|---|---|---|
| **CEL** | **Required** | Deterministic, non-Turing-complete, guaranteed to terminate, sandboxed (no I/O, no clock, no randomness), proven at scale in K8s admission control |
| Python `eval` / `exec` | **Banned** | Non-deterministic, unsandboxable, security hole, violates determinism invariant |
| Raw Rego / OPA | **Banned** | Over-engineered for this use case; harder for compliance officers to audit |
| Custom DSL | **Banned** | Unreviewed, unproven, maintenance burden |
| YAML/JSON conditions without CEL | **Banned** | Insufficient expressiveness for real governance rules |

CEL expressions have **no access** to wall-clock, network, randomness, or external state.
This is what makes the determinism invariant provable.

---

## Error Type Hierarchy

```python
# core/errors.py (policy section)
from core.errors import QUAICUError

class PolicyError(QUAICUError):
    """Base for all policy engine errors."""
    code = "POLICY_ERROR"

class PolicyEvaluationError(PolicyError):
    """CEL evaluation failed or returned unexpected type. Resolution: fail-closed DENY."""
    code = "POLICY_EVAL_FAILED"

class PolicyCompileError(PolicyError):
    """CEL expression failed to compile. Raised during authoring — prevents bad policy from saving."""
    code = "POLICY_COMPILE_ERROR"

class PolicyActivationError(PolicyError):
    """Policy cannot transition to ACTIVATED. One or more preconditions failed."""
    code = "POLICY_ACTIVATION_BLOCKED"

class PolicyConflictError(PolicyError):
    """
    Conflict resolution returned undefined. Should never happen — the resolution algorithm
    is total. If this is raised it is a bug in the resolver, not a valid policy state.
    """
    code = "POLICY_CONFLICT_UNDEFINED"

class PolicyNotFoundError(PolicyError):
    """
    No ACTIVATED policy governs this action type for this tenant.
    Resolution: fail-closed DENY. This is expected — not every action type has a policy.
    The absence of a policy is a DENY, not an allow.
    """
    code = "POLICY_NOT_FOUND"

class PolicyVersionImmutableError(PolicyError):
    """Attempt to mutate an ACTIVATED policy version. Must create a new version instead."""
    code = "POLICY_VERSION_IMMUTABLE"

class PolicyShadowModeRequiredError(PolicyError):
    """
    High-impact policy change requires shadow mode window before activation.
    The backtest impact report's flip_pct exceeds the configured threshold.
    """
    code = "POLICY_SHADOW_MODE_REQUIRED"

class PolicyImpactReportRequiredError(PolicyError):
    """REVIEW → ACTIVATED transition attempted without a reviewed impact report."""
    code = "POLICY_IMPACT_REPORT_REQUIRED"

class PolicyRegulatoryRefInvalidError(PolicyError):
    """A regulatory_ref in the policy does not exist in the K·14 regulation catalog."""
    code = "POLICY_REG_REF_INVALID"

class PolicyScopeConflictError(PolicyError):
    """
    Two or more ACTIVATED policies at the same scope level produce conflicting decisions
    on the same action type. This must be surfaced to the policy author, not silently resolved.
    (Distinct from normal conflict resolution, which handles deny-vs-allow. This is a
    structural authoring error where two policies at the same specificity level conflict.)
    """
    code = "POLICY_SCOPE_CONFLICT"
```

---

## Policy Envelope — Full Schema

Author in YAML, store as JSON. Validate on write (during authoring), never on read.

```yaml
id: ciro.ifrs9.stage_transition         # globally unique, dot-namespaced
                                         # convention: <tenant_namespace>.<domain>.<rule>
version: 3                              # monotonically increasing integer
                                         # versions are immutable once ACTIVATED
governs: ciro.ifrs9.stage_transition    # action type this policy applies to
                                         # must match Action.type exactly
scope:
  tenant: "*"                           # "*" = all tenants, or exact tenant_id string
  segment: null                         # optional actor/entity segment filter
                                         # e.g., { "actor_role": "relationship_manager" }
condition: |                            # CEL expression — must compile AND be statically bounded
  action.payload.to_stage > action.payload.from_stage
  && action.payload.exposure > 5000000
decision: require_approval              # allow | deny | require_approval
approvers:                              # only populated when decision == require_approval
  - "role:risk_head"                    # format: "role:<role_id>" or "user:<user_id>"
regulatory_refs:                        # links to K·14 regulation catalog
  - "rbi.ifrs9.staging"                 # must exist in regulation catalog (validated at authoring)
  - "rbi.free_ai.governance"
lifecycle: ACTIVATED                    # DRAFT | REVIEW | ACTIVATED | DEPRECATED
activated_at: "2026-06-01T00:00:00Z"   # set by activation gate — not author-supplied
activated_by: "user:compliance_officer"# set by activation gate
impact_report_id: "rpt_abc123"         # set by activation gate — must reference a reviewed report
```

---

## Policy Lifecycle State Machine

```
DRAFT ──────────► REVIEW ─────────────────────────► ACTIVATED ──────► DEPRECATED
  ▲                  │                                    │
  │   edit creates   │  requires:                        │  deprecation requires:
  │   new version    │  · impact_report (reviewed)       │  · new version already ACTIVATED
  └──────────────────┘  · shadow_mode_cleared            └──────────────────────────────────
                         (if flip_pct > threshold)

Any change to an ACTIVATED policy creates a NEW version (DRAFT).
The ACTIVATED version is immutable — it is the evidence artifact.
```

### Transitions and Guards

| From | To | Guard |
|------|----|-------|
| DRAFT | REVIEW | Caller has `policy:author` permission; envelope validates against JSON schema; CEL compiles |
| REVIEW | ACTIVATED | `impact_report_id` present, report reviewed, shadow mode cleared if required |
| ACTIVATED | DEPRECATED | A different version of the same policy is ACTIVATED; explicit deprecation call |
| Any | DRAFT (new ver) | Any attempted edit to REVIEW or ACTIVATED creates a new version |

---

## Scope Resolution Algorithm

The scope selector determines which policies apply to a given action. The resolution is deterministic
and uses specificity scoring to rank overlapping policies. Higher specificity wins when two policies
at the same decision tier conflict.

### Pseudocode

```
function resolve_scope(action, all_activated_policies):
    candidates = []

    for policy in all_activated_policies:
        if policy.governs != action.type:
            continue  # wrong action type

        tenant_match = (policy.scope.tenant == "*") or (policy.scope.tenant == action.tenant_id)
        if not tenant_match:
            continue

        segment_match = (policy.scope.segment is null) or segment_matches(action.actor, policy.scope.segment)
        if not segment_match:
            continue

        specificity = compute_specificity(policy.scope)
        candidates.append((policy, specificity))

    if candidates is empty:
        return []  # no governing policy → DENY (PolicyNotFoundError → fail-closed)

    # Sort by specificity descending — most specific first
    candidates.sort(key=lambda x: x.specificity, reverse=True)

    # Return candidates ordered by specificity
    return [policy for policy, _ in candidates]


function compute_specificity(scope):
    score = 0
    if scope.tenant != "*":
        score += 100   # tenant-specific > wildcard
    if scope.segment is not null:
        score += 10    # segment-specific > no-segment
    return score


function segment_matches(actor, segment_selector):
    # segment_selector is a dict like {"actor_role": "relationship_manager"}
    # All keys in selector must match actor attributes
    for key, value in segment_selector.items():
        if actor.attributes.get(key) != value:
            return false
    return true
```

### Specificity Scoring

| Scope | Score | Example |
|-------|-------|---------|
| `tenant: "*"`, no segment | 0 | Global default policy |
| `tenant: "*"`, segment present | 10 | All tenants, specific actor role |
| `tenant: "bank_xyz"`, no segment | 100 | Tenant-specific, all actors |
| `tenant: "bank_xyz"`, segment present | 110 | Tenant-specific, specific actor role |

---

## Total Conflict Resolution Algorithm

Policy evaluation **never** returns "undefined." The resolution order is explicit and exhaustive:

1. **Deny overrides all.** Any `deny` → result is `deny`.
2. **require_approval overrides allow** (but is overridden by deny).
3. **Most-specific scope wins** when policies at the SAME decision tier conflict (e.g., two `require_approval` at different tenant scopes — use the more specific one's approvers list).
4. **No governing policy → DENY** (fail-closed, not allow).
5. **Policy engine error or None → DENY** (fail-closed).

```python
# core/policy/conflict_resolution.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Sequence

from core.errors import PolicyConflictError, PolicyNotFoundError
from core.policy.types import PolicyResult, PolicyDecision


@dataclass
class PolicyResult:
    policy_id: str
    policy_version: int
    decision: str                 # "allow" | "deny" | "require_approval"
    approvers: list[str] = field(default_factory=list)
    specificity: int = 0          # computed from scope — higher = more specific


def resolve(results: Sequence[PolicyResult]) -> PolicyDecision:
    """
    Total resolution — every possible input produces a defined output.
    Never returns None. Never raises for a valid (possibly empty) input list.

    Raises:
        PolicyNotFoundError: if results is empty (no governing policy → fail-closed DENY).
        PolicyConflictError: if resolution produces undefined result (should be unreachable).
    """
    if not results:
        raise PolicyNotFoundError(
            "No ACTIVATED policy governs this action type — fail-closed DENY",
        )

    # Rule 1: any deny → deny (regardless of scope specificity)
    deny_results = [r for r in results if r.decision == "deny"]
    if deny_results:
        return PolicyDecision(
            decision="deny",
            governing_policy_ids=[f"{r.policy_id}@v{r.policy_version}" for r in deny_results],
            approvers=[],
        )

    # Rule 2: require_approval overrides allow
    require_results = [r for r in results if r.decision == "require_approval"]
    if require_results:
        # Rule 3: among require_approval policies, use highest-specificity approvers list
        # (most specific tenant/segment scope wins)
        most_specific = max(require_results, key=lambda r: r.specificity)
        # Merge approvers from all require_approval policies at the highest specificity level
        top_specificity = most_specific.specificity
        top_results = [r for r in require_results if r.specificity == top_specificity]
        merged_approvers = _merge_approvers(top_results)
        return PolicyDecision(
            decision="require_approval",
            governing_policy_ids=[f"{r.policy_id}@v{r.policy_version}" for r in require_results],
            approvers=merged_approvers,
        )

    # Rule 4: all allow
    allow_results = [r for r in results if r.decision == "allow"]
    if not allow_results:
        # This branch is logically unreachable given the above checks, but guard it.
        raise PolicyConflictError(
            "Conflict resolution produced undefined result — this is a resolver bug",
            detail={"results": [r.decision for r in results]},
        )
    return PolicyDecision(
        decision="allow",
        governing_policy_ids=[f"{r.policy_id}@v{r.policy_version}" for r in allow_results],
        approvers=[],
    )


def _merge_approvers(results: list[PolicyResult]) -> list[str]:
    """Union of all approver lists — all listed approvers may approve."""
    seen: set[str] = set()
    merged: list[str] = []
    for r in results:
        for approver in r.approvers:
            if approver not in seen:
                seen.add(approver)
                merged.append(approver)
    return merged
```

### Conflict Resolution Trace Example

**Scenario:** Action `ciro.ifrs9.stage_transition` for tenant `bank_xyz`, actor role `analyst`.

Active policies:
1. `global.allow` — tenant: `*`, no segment, decision: `allow`, specificity: 0
2. `bank_xyz.require_approval` — tenant: `bank_xyz`, no segment, decision: `require_approval`, specificity: 100, approvers: `[role:risk_head]`
3. `bank_xyz.analyst.deny` — tenant: `bank_xyz`, segment: `{actor_role: analyst}`, decision: `deny`, specificity: 110

**Resolution trace:**

```
Step 1: Scope filter
  · global.allow       → tenant "*" matches, no segment → included (specificity 0)
  · bank_xyz.require   → tenant "bank_xyz" matches, no segment → included (specificity 100)
  · bank_xyz.analyst.deny → tenant "bank_xyz" matches, segment {actor_role: analyst}
                           → actor.role == "analyst"? YES → included (specificity 110)

Step 2: Denial check
  · deny_results = [bank_xyz.analyst.deny]
  → DENY wins. Final decision: DENY
  → governing: ["bank_xyz.analyst.deny@v1"]

Conclusion: Action DENIED because analyst-role actors are explicitly denied at scope 110.
The allow at scope 0 and require_approval at scope 100 are irrelevant once any deny is present.
```

**Scenario 2:** Same action, same tenant, actor role `senior_manager` (no deny applies).

Active policies:
1. `global.allow` — tenant: `*`, no segment, decision: `allow`, specificity: 0
2. `bank_xyz.require_approval` — tenant: `bank_xyz`, no segment, decision: `require_approval`, specificity: 100, approvers: `[role:risk_head]`

```
Step 1: Scope filter
  · global.allow        → included (specificity 0)
  · bank_xyz.require    → included (specificity 100)
  · bank_xyz.analyst.deny → segment {actor_role: analyst}, but actor is senior_manager → EXCLUDED

Step 2: Denial check → no deny results

Step 3: require_approval check
  · require_results = [bank_xyz.require_approval]
  · most_specific specificity = 100
  · approvers = ["role:risk_head"]
  → REQUIRE_APPROVAL

Conclusion: Action requires approval from role:risk_head.
```

---

## CEL Evaluation — Full Implementation with QUAICU Type Activations

```python
# core/policy/cel_evaluator.py
from __future__ import annotations
import logging
from typing import Any

import cel_python  # google-cel-python

from core.errors import PolicyEvaluationError, PolicyCompileError
from core.lifecycle.types import Action
from core.telemetry import tracer, Spans, Attrs, policy_evaluation_duration

logger = logging.getLogger("quaicu.policy.cel")


# ── Custom QUAICU CEL type registrations ─────────────────────────────────────
# These type activations are available in ALL CEL expressions.
# They extend the standard CEL activation with QUAICU-specific types.

def _build_quaicu_cel_env() -> cel_python.Environment:
    """
    Build a CEL environment with QUAICU-specific type declarations.
    Called once at startup; cached on the evaluator instance.
    """
    # Declare the 'action' variable type available in all policy CEL expressions
    # CEL type system: action is a map with typed fields
    env = cel_python.Environment(
        annotations={
            # action.type: string — the governed action type
            "action.type": cel_python.CELType.string,
            # action.payload: map — key-value payload (values can be any CEL type)
            "action.payload": cel_python.CELType.map(
                cel_python.CELType.string, cel_python.CELType.dyn
            ),
            # action.actor_id: string — the resolved actor identifier
            "action.actor_id": cel_python.CELType.string,
            # action.tenant_id: string — the tenant boundary
            "action.tenant_id": cel_python.CELType.string,
            # action.proposed_at: timestamp — when the action was proposed (RFC 3339)
            # NOTE: proposed_at is from the action payload (recorded at proposal time),
            # NOT from wall-clock at evaluation time. This preserves determinism.
            "action.proposed_at": cel_python.CELType.timestamp,
        }
    )
    return env


class CELEvaluator:
    """
    Stateless CEL evaluator. One instance per PolicyEngine.
    Thread-safe (program cache is read-only after initial compilation).

    DETERMINISM GUARANTEE:
    CEL expressions have no access to wall-clock, network calls, randomness,
    or mutable external state. Identical activation → identical result, always.
    """

    def __init__(self) -> None:
        self._program_cache: dict[str, cel_python.Program] = {}
        self._env = _build_quaicu_cel_env()

    def compile(self, expression: str) -> cel_python.Program:
        """
        Compile a CEL expression. Called during policy authoring.

        Args:
            expression: CEL source string.

        Returns:
            Compiled Program (cached by expression text).

        Raises:
            PolicyCompileError: if the expression is invalid CEL.
        """
        if expression in self._program_cache:
            return self._program_cache[expression]

        with tracer.start_as_current_span(Spans.POLICY_CEL_COMPILE) as span:
            try:
                prog = self._env.compile(expression)
                self._program_cache[expression] = prog
                span.set_attribute("cel.expression_len", len(expression))
                return prog
            except cel_python.CELParseError as exc:
                raise PolicyCompileError(
                    f"CEL expression failed to parse: {exc}",
                    detail={"expression": expression, "parse_error": str(exc)},
                ) from exc
            except cel_python.CELTypeError as exc:
                raise PolicyCompileError(
                    f"CEL expression has a type error: {exc}",
                    detail={"expression": expression, "type_error": str(exc)},
                ) from exc

    def evaluate(
        self,
        program: cel_python.Program,
        action: Action,
    ) -> bool:
        """
        Evaluate a compiled CEL program against an action.

        FAIL-CLOSED CONTRACT: any exception → False (condition not met).
        The caller (PolicyEngine) then uses the policy's decision field;
        a False condition means the policy does not apply to this action.

        Returns:
            True if the condition is satisfied (policy applies to this action).
            False if not satisfied, OR if evaluation raises any error.

        Never raises — any exception is caught and returns False.
        """
        with tracer.start_as_current_span(Spans.POLICY_CEL_EVALUATE) as span:
            activation = _build_activation(action)
            span.set_attribute(Attrs.ACTION_TYPE, action.type)
            span.set_attribute(Attrs.TENANT_ID, action.tenant_id)

            try:
                result = program.evaluate(activation)
                bool_result = bool(result)
                span.set_attribute("cel.result", bool_result)
                return bool_result
            except Exception as exc:
                # Any CEL runtime error → condition not satisfied → fail-closed
                logger.warning(
                    "CEL evaluation error — condition treated as False (fail-closed). "
                    "action_id=%s error=%s",
                    action.id, exc,
                )
                span.record_exception(exc)
                span.set_attribute("cel.result", False)
                span.set_attribute("cel.error", str(exc))
                return False


def _build_activation(action: Action) -> dict[str, Any]:
    """
    Build the CEL activation map from an Action.
    This is the ONLY data available to CEL expressions — no external state, no clock.
    """
    return {
        "action": {
            "type": action.type,
            "payload": action.payload,
            "actor_id": action.actor_id,
            "tenant_id": action.tenant_id,
            # proposed_at comes from the action (recorded at proposal time, not eval time)
            "proposed_at": action.proposed_at.isoformat() if action.proposed_at else "",
        }
    }
```

---

## Policy Engine — Full Evaluation Flow

```python
# core/policy/engine.py
from __future__ import annotations
import time
import logging
from typing import Sequence

from core.errors import PolicyEvaluationError, PolicyNotFoundError
from core.lifecycle.types import Action, EvaluationResult
from core.policy.cel_evaluator import CELEvaluator
from core.policy.conflict_resolution import resolve, PolicyResult
from core.policy.types import PolicyVersion, PolicyDecision
from core.ports import StoragePort
from core.telemetry import tracer, Spans, Attrs, policy_evaluation_duration

logger = logging.getLogger("quaicu.policy.engine")


class PolicyEngine:
    """
    K·01 Policy Engine.

    Evaluation is:
    - Deterministic: identical inputs → identical decision.
    - Total: every action gets a decision (no "undefined").
    - Fail-closed: any error → DENY (raised as PolicyEvaluationError → caught by LifecycleEngine).
    - CEL-only: no eval, no exec, no Rego.
    """

    def __init__(self, *, storage: StoragePort) -> None:
        self._storage = storage
        self._cel = CELEvaluator()

    async def evaluate(self, action: Action) -> EvaluationResult:
        """
        Evaluate all applicable ACTIVATED policies for this action.

        Returns:
            EvaluationResult with decision, policy_versions evaluated, and approvers.

        Raises:
            PolicyEvaluationError: on any error (caller must treat as DENY).
            PolicyNotFoundError: if no policy governs this action type (caller treats as DENY).
        """
        with tracer.start_as_current_span(Spans.POLICY_EVALUATE) as span:
            t_start = time.monotonic()
            span.set_attribute(Attrs.TENANT_ID, action.tenant_id)
            span.set_attribute(Attrs.ACTION_ID, str(action.id))
            span.set_attribute(Attrs.ACTION_TYPE, action.type)

            # Step 1: load all ACTIVATED policies for this action type + tenant
            try:
                candidates: list[PolicyVersion] = await self._load_candidates(
                    action_type=action.type,
                    tenant_id=action.tenant_id,
                )
            except Exception as exc:
                raise PolicyEvaluationError(
                    f"Failed to load policies: {exc}",
                    detail={"action_id": str(action.id)},
                ) from exc

            if not candidates:
                raise PolicyNotFoundError(
                    f"No ACTIVATED policy governs action type '{action.type}' "
                    f"for tenant '{action.tenant_id}' — fail-closed DENY",
                    detail={"action_type": action.type, "tenant_id": action.tenant_id},
                )

            # Step 2: evaluate each candidate policy's CEL condition
            results: list[PolicyResult] = []
            evaluated_versions: list[str] = []

            for policy in candidates:
                version_ref = f"{policy.id}@v{policy.version}"
                evaluated_versions.append(version_ref)

                try:
                    program = self._cel.compile(policy.condition)
                    condition_met = self._cel.evaluate(program, action)
                except Exception as exc:
                    raise PolicyEvaluationError(
                        f"CEL evaluation failed for policy {version_ref}: {exc}",
                        detail={"policy_id": policy.id, "version": policy.version},
                    ) from exc

                if condition_met:
                    results.append(PolicyResult(
                        policy_id=policy.id,
                        policy_version=policy.version,
                        decision=policy.decision,
                        approvers=policy.approvers,
                        specificity=policy.specificity,
                    ))

            span.set_attribute("quaicu.policies_evaluated", len(evaluated_versions))
            span.set_attribute("quaicu.policies_matched", len(results))

            # Step 3: if no policy's condition matched → default DENY
            if not results:
                span.set_attribute(Attrs.POLICY_DECISION, "deny")
                duration_ms = (time.monotonic() - t_start) * 1000
                policy_evaluation_duration.record(
                    duration_ms,
                    {Attrs.TENANT_ID: action.tenant_id, Attrs.POLICY_DECISION: "deny"},
                )
                return EvaluationResult(
                    decision="deny",
                    policy_versions=evaluated_versions,
                    consent_checked=False,
                    assurance_signals={},
                    approvers=[],
                    governing_policy_ids=[],
                )

            # Step 4: conflict resolution — total, never undefined
            with tracer.start_as_current_span(Spans.POLICY_CONFLICT_RESOLVE):
                final_decision: PolicyDecision = resolve(results)

            span.set_attribute(Attrs.POLICY_DECISION, final_decision.decision)
            duration_ms = (time.monotonic() - t_start) * 1000
            policy_evaluation_duration.record(
                duration_ms,
                {Attrs.TENANT_ID: action.tenant_id, Attrs.POLICY_DECISION: final_decision.decision},
            )

            return EvaluationResult(
                decision=final_decision.decision,
                policy_versions=evaluated_versions,  # ALL versions evaluated — required for replay
                consent_checked=False,                # K·04 consent check is a separate step
                assurance_signals={},                 # K·08–K·11 signals added by assurance layer
                approvers=final_decision.approvers,
                governing_policy_ids=final_decision.governing_policy_ids,
            )

    async def _load_candidates(
        self, *, action_type: str, tenant_id: str
    ) -> list[PolicyVersion]:
        """
        Load all ACTIVATED policies that govern this action type for this tenant.
        Includes both tenant-specific (scope.tenant == tenant_id) and
        universal (scope.tenant == "*") policies.
        """
        async with self._storage.transaction() as tx:
            rows = await tx.fetch_all(
                """
                SELECT id, version, governs, condition, decision, scope, approvers,
                       reg_refs, activated_at
                FROM   policies
                WHERE  governs = $1
                AND    lifecycle = 'ACTIVATED'
                AND    (scope->>'tenant' = '*' OR scope->>'tenant' = $2)
                ORDER  BY id, version DESC
                """,
                action_type,
                tenant_id,
            )
        return [_row_to_policy_version(row) for row in rows]
```

---

## Policy Bundle Loading from packs/

Packs ship as YAML files in `packs/policies/`. Loading a pack inserts or updates policy records
in the tenant's schema. Packs are data — never code.

```python
# core/policy/pack_loader.py
from __future__ import annotations
import json
import logging
from pathlib import Path

import yaml
import jsonschema

from core.errors import PolicyCompileError, PolicyRegulatoryRefInvalidError
from core.policy.cel_evaluator import CELEvaluator
from core.ports import StoragePort

logger = logging.getLogger("quaicu.policy.pack_loader")

POLICY_ENVELOPE_SCHEMA_PATH = Path("packs/schemas/policy_envelope.json")


class PolicyPackLoader:
    """
    Loads policy packs from packs/policies/ into tenant storage.

    Loading a pack:
    1. Parses YAML
    2. Validates against JSON schema (envelope contract)
    3. CEL compile-checks every condition
    4. Validates all regulatory_refs exist in the regulation catalog
    5. Inserts as DRAFT policies (does NOT auto-activate)

    IMPORTANT: Loading a pack does NOT activate the policies. Activation goes through
    the full authoring pipeline (backtest → review → activation gate).
    """

    def __init__(
        self,
        *,
        storage: StoragePort,
        regulation_catalog,    # core.regmap.catalog.RegulationCatalog
    ) -> None:
        self._storage = storage
        self._catalog = regulation_catalog
        self._cel = CELEvaluator()
        with open(POLICY_ENVELOPE_SCHEMA_PATH) as f:
            self._envelope_schema = json.load(f)

    async def load_pack(
        self,
        pack_path: Path,
        *,
        tenant_id: str,
        loaded_by: str,
    ) -> list[str]:
        """
        Load all policies from a pack directory.

        Args:
            pack_path: Path to pack directory (e.g., packs/policies/ciro.ifrs9/)
            tenant_id: Target tenant. Use "*" for universal policies.
            loaded_by: Actor ID for audit trail.

        Returns:
            List of policy IDs loaded.

        Raises:
            PolicyCompileError: if any policy's CEL condition is invalid.
            PolicyRegulatoryRefInvalidError: if a regulatory_ref does not exist in the catalog.
            jsonschema.ValidationError: if a policy fails envelope schema validation.
        """
        loaded_ids: list[str] = []

        for yaml_file in sorted(pack_path.glob("**/*.yaml")):
            with open(yaml_file) as f:
                raw = yaml.safe_load(f)

            # Step 1: JSON schema validation
            jsonschema.validate(raw, self._envelope_schema)

            # Step 2: CEL compile-check
            condition = raw.get("condition", "")
            if condition:
                self._cel.compile(condition)  # raises PolicyCompileError if invalid

            # Step 3: Regulatory ref validation
            for ref in raw.get("regulatory_refs", []):
                if not await self._catalog.exists(ref):
                    raise PolicyRegulatoryRefInvalidError(
                        f"Regulatory ref '{ref}' in policy '{raw['id']}' "
                        f"does not exist in the regulation catalog.",
                        detail={"policy_id": raw["id"], "ref": ref},
                    )

            # Step 4: Insert as DRAFT
            policy_version = _raw_to_policy_version(raw, tenant_id=tenant_id)
            async with self._storage.transaction() as tx:
                await tx.upsert_policy_draft(policy_version, loaded_by=loaded_by)

            loaded_ids.append(raw["id"])
            logger.info(
                "Loaded policy '%s' v%d as DRAFT for tenant '%s'",
                raw["id"], raw["version"], tenant_id,
            )

        return loaded_ids
```

---

## Activation Gate — Full Authoring Pipeline Validation

```python
# core/policy/activation.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

from core.errors import (
    PolicyActivationError,
    PolicyImpactReportRequiredError,
    PolicyShadowModeRequiredError,
    PolicyVersionImmutableError,
    PolicyRegulatoryRefInvalidError,
)
from core.policy.types import PolicyVersion, ImpactReport
from core.ports import StoragePort
from core.telemetry import tracer, Spans, Attrs

# Default impact threshold for requiring shadow mode (configurable per tenant via kernel.toml)
DEFAULT_SHADOW_MODE_FLIP_PCT_THRESHOLD = 0.05  # 5% of decisions would flip


async def transition_to_activated(
    *,
    policy_id: str,
    version: int,
    impact_report_id: str,
    reviewer_id: str,
    tenant_id: str,
    storage: StoragePort,
    shadow_mode_flip_threshold: float = DEFAULT_SHADOW_MODE_FLIP_PCT_THRESHOLD,
) -> PolicyVersion:
    """
    The ONLY path to ACTIVATED. Cannot be bypassed.
    Every precondition is checked before the state transition is written.

    Args:
        policy_id: Policy to activate.
        version: Version to activate.
        impact_report_id: ID of the reviewed impact report (from backtest).
        reviewer_id: Identity of the human approver.
        tenant_id: Tenant context.
        storage: Injected storage port.
        shadow_mode_flip_threshold: flip_pct above which shadow mode is required.

    Returns:
        The ACTIVATED PolicyVersion record.

    Raises:
        PolicyActivationError: on any precondition failure.
        PolicyImpactReportRequiredError: missing or unreviewed impact report.
        PolicyShadowModeRequiredError: shadow mode not cleared for high-impact change.
        PolicyVersionImmutableError: this version is already ACTIVATED.
    """
    with tracer.start_as_current_span(Spans.POLICY_ACTIVATE) as span:
        span.set_attribute(Attrs.POLICY_ID, policy_id)
        span.set_attribute(Attrs.POLICY_VERSION, version)
        span.set_attribute(Attrs.TENANT_ID, tenant_id)

        async with storage.transaction() as tx:
            policy = await tx.get_policy_version(policy_id, version, tenant_id)

        if policy is None:
            raise PolicyActivationError(
                f"Policy '{policy_id}' version {version} not found for tenant '{tenant_id}'",
                detail={"policy_id": policy_id, "version": version, "tenant_id": tenant_id},
            )

        # Guard: version must be in REVIEW to activate
        if policy.lifecycle == "ACTIVATED":
            raise PolicyVersionImmutableError(
                f"Policy '{policy_id}' v{version} is already ACTIVATED and is immutable. "
                f"Create a new version to make changes.",
                detail={"policy_id": policy_id, "version": version},
            )
        if policy.lifecycle not in ("REVIEW",):
            raise PolicyActivationError(
                f"Policy must be in REVIEW to activate, currently: '{policy.lifecycle}'",
                detail={"policy_id": policy_id, "current_lifecycle": policy.lifecycle},
            )

        # Guard: impact report must exist
        async with storage.transaction() as tx:
            report: ImpactReport | None = await tx.get_impact_report(impact_report_id)

        if report is None:
            raise PolicyImpactReportRequiredError(
                f"Impact report '{impact_report_id}' not found. "
                f"A reviewed backtest impact report is required before activation.",
                detail={"impact_report_id": impact_report_id},
            )

        # Guard: report must be for this specific policy version
        if report.policy_id != policy_id or report.policy_version != version:
            raise PolicyActivationError(
                f"Impact report '{impact_report_id}' is for policy "
                f"'{report.policy_id}' v{report.policy_version}, "
                f"not for '{policy_id}' v{version}.",
                detail={"report_policy_id": report.policy_id, "report_version": report.policy_version},
            )

        # Guard: report must be reviewed (human acknowledgment)
        if not report.reviewed_by:
            raise PolicyImpactReportRequiredError(
                f"Impact report '{impact_report_id}' has not been reviewed. "
                f"A human must acknowledge the impact before activation.",
                detail={"impact_report_id": impact_report_id},
            )

        # Guard: shadow mode required for high-impact changes
        if report.flip_pct > shadow_mode_flip_threshold:
            if not report.shadow_mode_cleared:
                raise PolicyShadowModeRequiredError(
                    f"Policy '{policy_id}' v{version} would flip {report.flip_pct:.1%} of decisions "
                    f"(threshold: {shadow_mode_flip_threshold:.1%}). "
                    f"Shadow mode window must be completed and cleared before activation.",
                    detail={
                        "flip_pct": report.flip_pct,
                        "threshold": shadow_mode_flip_threshold,
                        "shadow_mode_cleared": report.shadow_mode_cleared,
                    },
                )

        # All preconditions met — write ACTIVATED state
        policy.lifecycle = "ACTIVATED"
        policy.activated_at = datetime.now(timezone.utc)
        policy.activated_by = reviewer_id
        policy.impact_report_id = impact_report_id

        async with storage.transaction() as tx:
            await tx.save_policy_version(policy)

        return policy
```

---

## Shadow Mode — Full Implementation

```python
# core/policy/shadow.py
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from core.lifecycle.types import Action
from core.policy.cel_evaluator import CELEvaluator
from core.policy.types import PolicyVersion, PolicyDecision

logger = logging.getLogger("quaicu.policy.shadow")


@dataclass
class ShadowResult:
    action_id: UUID
    tenant_id: str
    active_decision: PolicyDecision
    candidate_decision: PolicyDecision
    would_flip: bool
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # NEVER written to the production ledger — shadow partition only


class ShadowEvaluator:
    """
    Runs a candidate policy IN PARALLEL with the active policy.
    The candidate decision is NEVER enforced — it is observational only.
    The active policy still governs the live action.

    Side-effect guarantee: shadow evaluations write ONLY to a shadow partition.
    They never trigger HITL requests, never seal production ledger entries,
    never execute state changes.
    """

    def __init__(
        self,
        *,
        policy_engine,          # PolicyEngine
        shadow_storage,         # shadow partition storage — NEVER the production ledger
        cel: CELEvaluator,
    ) -> None:
        self._policy_engine = policy_engine
        self._shadow_storage = shadow_storage
        self._cel = cel

    async def shadow_evaluate(
        self,
        action: Action,
        candidate_policy: PolicyVersion,
    ) -> ShadowResult:
        """
        Evaluate the action under BOTH the currently active policy set AND the candidate.
        Record the comparison to the shadow partition.

        Returns ShadowResult — never raises (errors are logged and result.would_flip = None).
        """
        # Active policy evaluation (this is already done by the live lifecycle; replicate it here)
        try:
            active_decision = await self._policy_engine.evaluate(action)
        except Exception as exc:
            logger.warning("Shadow: active policy eval failed — skipping shadow record. %s", exc)
            return ShadowResult(
                action_id=action.id,
                tenant_id=action.tenant_id,
                active_decision=PolicyDecision(decision="error", governing_policy_ids=[], approvers=[]),
                candidate_decision=PolicyDecision(decision="error", governing_policy_ids=[], approvers=[]),
                would_flip=False,
            )

        # Candidate policy evaluation — isolated, side-effect-free
        try:
            program = self._cel.compile(candidate_policy.condition)
            condition_met = self._cel.evaluate(program, action)
            if condition_met:
                candidate_dec = PolicyDecision(
                    decision=candidate_policy.decision,
                    governing_policy_ids=[f"{candidate_policy.id}@v{candidate_policy.version}"],
                    approvers=candidate_policy.approvers,
                )
            else:
                candidate_dec = PolicyDecision(decision="allow", governing_policy_ids=[], approvers=[])
        except Exception as exc:
            logger.warning(
                "Shadow: candidate policy eval failed — recording as 'error'. policy=%s@v%d error=%s",
                candidate_policy.id, candidate_policy.version, exc,
            )
            candidate_dec = PolicyDecision(decision="error", governing_policy_ids=[], approvers=[])

        active_dec = PolicyDecision(
            decision=active_decision.decision,
            governing_policy_ids=active_decision.governing_policy_ids,
            approvers=active_decision.approvers,
        )

        result = ShadowResult(
            action_id=action.id,
            tenant_id=action.tenant_id,
            active_decision=active_dec,
            candidate_decision=candidate_dec,
            would_flip=(active_dec.decision != candidate_dec.decision),
        )

        # Write to shadow partition ONLY — never to production ledger
        try:
            await self._shadow_storage.record_shadow_result(result)
        except Exception as exc:
            # Shadow record failure is non-fatal — the live action is unaffected
            logger.warning("Shadow: failed to record shadow result: %s", exc)

        return result
```

---

## Impact Report — Full Structure and Generation

```python
# core/policy/impact_report.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class ImpactReport:
    id: str
    policy_id: str
    policy_version: int
    generated_at: datetime

    # Backtest results — generated by running candidate against historical ledger data
    total_actions_tested: int
    decision_distribution_active: dict[str, int]    # {"allow": 920, "deny": 80}
    decision_distribution_candidate: dict[str, int] # {"allow": 850, "deny": 150}
    flip_count: int           # actions where decision would change under candidate
    flip_pct: float           # flip_count / total_actions_tested
    flipped_action_ids: list[str] = field(default_factory=list)  # sample for reviewer inspection

    # Fairness delta from K·09 — delta of fairness metric between active and candidate
    fairness_delta: float = 0.0
    fairness_metric: str = "demographic_parity"  # which fairness metric was used

    # Shadow mode status
    requires_shadow_mode: bool = False    # True if flip_pct > configured threshold
    shadow_mode_window_start: datetime | None = None
    shadow_mode_window_end: datetime | None = None
    shadow_mode_cleared: bool = False     # True if shadow window completed without incident

    # Human review
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    acknowledged_risks: str | None = None

    def is_review_complete(self) -> bool:
        return self.reviewed_by is not None and self.reviewed_at is not None

    def requires_shadow_mode_clearance(self, threshold: float) -> bool:
        return self.flip_pct > threshold and not self.shadow_mode_cleared
```

---

## Authoring Pipeline — Complete Validation Code

```python
# core/policy/authoring.py
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import yaml
import jsonschema

from core.errors import (
    PolicyCompileError,
    PolicyRegulatoryRefInvalidError,
    PolicyVersionImmutableError,
)
from core.policy.cel_evaluator import CELEvaluator
from core.policy.types import PolicyVersion, PolicyLifecycle

logger = logging.getLogger("quaicu.policy.authoring")


class PolicyAuthoringService:
    """
    Enforces the authoring pipeline:
    1. YAML parse
    2. JSON schema validation
    3. CEL compile-check
    4. Regulatory ref validation
    5. Save as DRAFT
    (Backtest and activation are separate operations.)
    """

    def __init__(
        self,
        *,
        storage,
        regulation_catalog,
        cel: CELEvaluator,
        envelope_schema_path: Path,
    ) -> None:
        self._storage = storage
        self._catalog = regulation_catalog
        self._cel = cel
        with open(envelope_schema_path) as f:
            self._schema = json.load(f)

    async def submit_draft(
        self,
        yaml_source: str,
        *,
        tenant_id: str,
        author_id: str,
    ) -> PolicyVersion:
        """
        Validate and save a policy as DRAFT.
        Raises on any validation failure — a bad policy is rejected at authoring time.
        """
        # Step 1: YAML parse
        try:
            raw = yaml.safe_load(yaml_source)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML: {exc}") from exc

        # Step 2: JSON schema validation
        try:
            jsonschema.validate(raw, self._schema)
        except jsonschema.ValidationError as exc:
            raise ValueError(f"Policy envelope schema violation: {exc.message}") from exc

        # Step 3: CEL compile-check
        condition = raw.get("condition", "")
        if condition:
            # This raises PolicyCompileError if the CEL is invalid — prevents bad policies
            self._cel.compile(condition)

        # Step 4: Regulatory ref validation
        for ref in raw.get("regulatory_refs", []):
            if not await self._catalog.exists(ref):
                raise PolicyRegulatoryRefInvalidError(
                    f"Regulatory ref '{ref}' not found in regulation catalog. "
                    f"Available refs can be listed via GET /kernel/v1/regmap/catalog",
                    detail={"ref": ref, "policy_id": raw.get("id")},
                )

        # Step 5: Check immutability if version already exists
        existing = await self._storage.get_policy_version(
            raw["id"], raw["version"], tenant_id
        )
        if existing and existing.lifecycle == "ACTIVATED":
            raise PolicyVersionImmutableError(
                f"Policy '{raw['id']}' v{raw['version']} is already ACTIVATED and immutable. "
                f"Increment the version number to create a new draft.",
                detail={"policy_id": raw["id"], "version": raw["version"]},
            )

        # Step 6: Save as DRAFT
        policy = PolicyVersion(
            id=raw["id"],
            version=raw["version"],
            tenant_id=tenant_id,
            governs=raw["governs"],
            condition=condition,
            decision=raw["decision"],
            scope=raw.get("scope", {"tenant": "*"}),
            approvers=raw.get("approvers", []),
            regulatory_refs=raw.get("regulatory_refs", []),
            lifecycle=PolicyLifecycle.DRAFT,
            created_at=datetime.now(timezone.utc),
            created_by=author_id,
        )
        await self._storage.upsert_policy_draft(policy, loaded_by=author_id)
        return policy

    async def submit_for_review(
        self, policy_id: str, version: int, tenant_id: str, *, author_id: str
    ) -> PolicyVersion:
        """Transition DRAFT → REVIEW."""
        policy = await self._storage.get_policy_version(policy_id, version, tenant_id)
        if policy is None or policy.lifecycle != "DRAFT":
            raise ValueError(
                f"Policy '{policy_id}' v{version} is not in DRAFT state (got "
                f"'{policy.lifecycle if policy else 'not found'}')."
            )
        policy.lifecycle = PolicyLifecycle.REVIEW
        policy.reviewed_at = datetime.now(timezone.utc)
        policy.reviewed_by = author_id
        await self._storage.save_policy_version(policy)
        return policy
```

---

## Regulatory Ref Validation — Full Pipeline Code

```python
# core/policy/reg_ref_validator.py
from __future__ import annotations
import logging
from core.errors import PolicyRegulatoryRefInvalidError

logger = logging.getLogger("quaicu.policy.reg_ref_validator")

# Regulatory ref format: <regulation_namespace>.<clause_id>
# Examples: "rbi.ifrs9.staging", "eu_ai_act.article_6.a", "dpdp.section_4"
REF_FORMAT_EXAMPLE = "rbi.ifrs9.staging"


async def validate_regulatory_refs(
    refs: list[str],
    *,
    policy_id: str,
    catalog,  # core.regmap.catalog.RegulationCatalog
) -> None:
    """
    Validate all regulatory refs in a policy against the K·14 regulation catalog.
    Raises PolicyRegulatoryRefInvalidError on the first invalid ref.

    Called during:
    - Policy pack loading
    - Policy draft submission (authoring pipeline)
    - Policy review (belt-and-suspenders check)
    """
    for ref in refs:
        # Format check: must be dot-namespaced
        parts = ref.split(".")
        if len(parts) < 2:
            raise PolicyRegulatoryRefInvalidError(
                f"Regulatory ref '{ref}' in policy '{policy_id}' has invalid format. "
                f"Expected format: '{REF_FORMAT_EXAMPLE}' (dot-namespaced, minimum 2 parts).",
                detail={"ref": ref, "policy_id": policy_id},
            )

        # Existence check against live catalog
        if not await catalog.exists(ref):
            raise PolicyRegulatoryRefInvalidError(
                f"Regulatory ref '{ref}' in policy '{policy_id}' does not exist "
                f"in the regulation catalog. Check the ref ID or add it to the catalog first.",
                detail={
                    "ref": ref,
                    "policy_id": policy_id,
                    "hint": "List available refs via GET /kernel/v1/regmap/catalog",
                },
            )

        logger.debug("Regulatory ref '%s' validated for policy '%s'", ref, policy_id)
```

---

## Storage Schema

```sql
-- Policy versions (immutable once ACTIVATED)
-- Per-tenant schema: this DDL runs inside the tenant's own schema.
CREATE TABLE IF NOT EXISTS policies (
    id               TEXT        NOT NULL,
    version          INT         NOT NULL,
    tenant_id        TEXT        NOT NULL,   -- "*" for universal policies
    governs          TEXT        NOT NULL,   -- action type
    condition        TEXT        NOT NULL,   -- CEL expression
    decision         TEXT        NOT NULL,   -- allow | deny | require_approval
    scope            JSONB       NOT NULL,   -- { tenant, segment }
    approvers        JSONB       NOT NULL DEFAULT '[]',
    regulatory_refs  JSONB       NOT NULL DEFAULT '[]',
    lifecycle        TEXT        NOT NULL DEFAULT 'DRAFT',
    impact_report_id TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by       TEXT,
    activated_at     TIMESTAMPTZ,
    activated_by     TEXT,
    deprecated_at    TIMESTAMPTZ,
    deprecated_by    TEXT,
    PRIMARY KEY (id, version)
);

-- Prevent mutation of ACTIVATED versions (enforced at DB level, not just application level)
-- This trigger fires BEFORE UPDATE on any ACTIVATED policy row.
CREATE OR REPLACE FUNCTION prevent_activated_policy_mutation()
RETURNS trigger AS $$
BEGIN
    IF OLD.lifecycle = 'ACTIVATED' THEN
        RAISE EXCEPTION 'Policy %.% is ACTIVATED and immutable — create a new version',
            OLD.id, OLD.version;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trig_prevent_activated_mutation
BEFORE UPDATE ON policies
FOR EACH ROW EXECUTE FUNCTION prevent_activated_policy_mutation();

-- Impact reports
CREATE TABLE IF NOT EXISTS policy_impact_reports (
    id                          TEXT        PRIMARY KEY,
    policy_id                   TEXT        NOT NULL,
    policy_version              INT         NOT NULL,
    generated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    total_actions_tested        INT         NOT NULL DEFAULT 0,
    decision_distribution_active  JSONB     NOT NULL DEFAULT '{}',
    decision_distribution_candidate JSONB   NOT NULL DEFAULT '{}',
    flip_count                  INT         NOT NULL DEFAULT 0,
    flip_pct                    NUMERIC(6,4) NOT NULL DEFAULT 0,
    flipped_action_ids          JSONB       NOT NULL DEFAULT '[]',
    fairness_delta              NUMERIC(8,6) NOT NULL DEFAULT 0,
    fairness_metric             TEXT        NOT NULL DEFAULT 'demographic_parity',
    requires_shadow_mode        BOOLEAN     NOT NULL DEFAULT FALSE,
    shadow_mode_cleared         BOOLEAN     NOT NULL DEFAULT FALSE,
    reviewed_by                 TEXT,
    reviewed_at                 TIMESTAMPTZ,
    acknowledged_risks          TEXT,
    FOREIGN KEY (policy_id, policy_version) REFERENCES policies (id, version)
);

-- Shadow mode results (separate partition — never mixed with production ledger)
CREATE TABLE IF NOT EXISTS policy_shadow_results (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    action_id           UUID        NOT NULL,
    tenant_id           TEXT        NOT NULL,
    candidate_policy_id TEXT        NOT NULL,
    candidate_version   INT         NOT NULL,
    active_decision     TEXT        NOT NULL,
    candidate_decision  TEXT        NOT NULL,
    would_flip          BOOLEAN     NOT NULL,
    evaluated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## CI Enforcement for Policy Engine

```bash
#!/usr/bin/env bash
# ci/checks/policy_eval_check.sh
# Ensures no banned evaluation methods in core/policy/

set -euo pipefail
echo "=== Policy evaluation method check ==="

EVAL_USES=$(grep -rn --include="*.py" \
    -E "\beval\s*\(|\bexec\s*\(" core/policy/ 2>/dev/null || true)

REGO_USES=$(grep -rn --include="*.py" \
    -E "import opa|from opa|rego\." core/policy/ 2>/dev/null || true)

MUTABLE_ACTIVATED=$(grep -rn --include="*.py" \
    -E '\.lifecycle\s*=\s*"ACTIVATED"' core/policy/ 2>/dev/null || \
    grep -v "transition_to_activated" || true)

FAILED=0
[[ -n "$EVAL_USES" ]] && echo "FAIL: eval/exec in policy engine" && echo "$EVAL_USES" && FAILED=1
[[ -n "$REGO_USES" ]] && echo "FAIL: Rego/OPA in policy engine" && echo "$REGO_USES" && FAILED=1
[[ "${FAILED}" -eq 1 ]] && exit 1
echo "PASS: policy evaluation checks passed"
```

---

## Anti-Patterns

### Anti-pattern 1 — CEL evaluate failure swallowed (fail-open)

```python
# WRONG — if CEL raises, condition is treated as True (policy applies = may allow through).
def evaluate(self, program, action):
    try:
        return bool(program.evaluate(_build_activation(action)))
    except Exception:
        return True  # CATASTROPHIC: evaluation failure → policy applies → may allow

# CORRECT — evaluation failure → False (condition not met) → fail-closed.
def evaluate(self, program, action):
    try:
        return bool(program.evaluate(_build_activation(action)))
    except Exception as exc:
        logger.warning("CEL eval error → False (fail-closed): %s", exc)
        return False
```

### Anti-pattern 2 — resolve() returns None for empty list

```python
# WRONG — None leaks out and causes AttributeError later.
def resolve(results):
    if not results:
        return None  # caller won't notice until runtime crash

# CORRECT — empty list is PolicyNotFoundError → fail-closed DENY.
def resolve(results):
    if not results:
        raise PolicyNotFoundError("No governing policy — fail-closed DENY")
```

### Anti-pattern 3 — Activating without impact report (F-10 violation)

```python
# WRONG — convenience activation bypasses the gate.
async def quick_activate(policy_id, version):
    policy.lifecycle = "ACTIVATED"  # skips backtest, skips review — catastrophic

# CORRECT — always use transition_to_activated() which enforces all preconditions.
policy = await transition_to_activated(
    policy_id=policy_id,
    version=version,
    impact_report_id=report_id,
    reviewer_id=reviewer_id,
    tenant_id=tenant_id,
    storage=storage,
)
```

### Anti-pattern 4 — Wall-clock in CEL activation

```python
# WRONG — evaluation result changes based on when it runs.
# Do NOT include datetime.now() in the CEL activation.
activation = {
    "action": {...},
    "now": datetime.now().isoformat(),  # NEVER — destroys determinism invariant
}

# CORRECT — if time-sensitivity is needed, it comes from action.proposed_at
# (recorded at proposal time, not evaluation time).
activation = {
    "action": {
        ...
        "proposed_at": action.proposed_at.isoformat(),  # from the recorded action payload
    }
}
```

---

## Checklist Before Merging Any Policy Engine Change

- [ ] No Python `eval`, no `exec`, no Rego, no custom DSL — CEL only
- [ ] `resolve()` handles empty-list case → raises `PolicyNotFoundError` (never returns None)
- [ ] `CELEvaluator.evaluate()` wraps in try/except → returns False on any error (fail-closed)
- [ ] `transition_to_activated()` is the ONLY activation path — no other code sets lifecycle=ACTIVATED
- [ ] DB trigger `prevent_activated_policy_mutation` exists in migration
- [ ] Evaluation result records the **full list of policy_version IDs evaluated** (for replay)
- [ ] No wall-clock, network, or randomness in CEL activations
- [ ] All `regulatory_refs` validated against regulation catalog at authoring time
- [ ] OTel spans emitted for evaluate, CEL compile, CEL evaluate, conflict resolve, activate
- [ ] Full type annotations on every method — mypy --strict passes
- [ ] Shadow mode results written ONLY to shadow partition, never to production ledger
- [ ] Impact report `flip_pct > threshold` → shadow mode required before activation
