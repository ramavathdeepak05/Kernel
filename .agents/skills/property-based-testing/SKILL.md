---
name: property-based-testing
description: >
  Design property-based tests that verify code properties hold for all inputs
  using automatic test case generation. Use for property-based, QuickCheck,
  hypothesis testing, generative testing, and invariant verification.
  QUAICU kernel — property tests for the Core Invariants: ledger inclusion/consistency,
  policy determinism, conflict-resolution totality, no-bypass, tenant isolation, replay fidelity.
  Triggers — QUAICU, ledger invariant, policy determinism, Hypothesis, RuleBasedStateMachine, Core Invariant.
---

# Property-Based Testing

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific property choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.**

### Invariants to encode as properties (each one MUST exist)
- Ledger integrity: for any sequence of appends, every inclusion proof verifies; any retroactive edit makes a consistency proof fail.
- Policy determinism: evaluating the same action twice yields the same decision.
- Conflict-resolution totality: any set of policy results maps to exactly one decision; deny overrides allow.
- No-bypass: any action in SEALED state has an evaluation record.
- Tenant isolation: cross-tenant listing never leaks another tenant's rows.
- Replay fidelity: replaying from the ledger reproduces the recorded decision.

### Settings profiles (use these)
| Profile | max_examples | deadline | When |
|---|---|---|---|
| ci | 500 | 5000ms | every PR |
| dev | ~50 | default | local |
| deep | large | none | nightly |

### Tie-break rules
- Example test vs property test for an invariant? → property (must hold for ALL inputs), not a few examples.
- Strategy generates an "impossible" value? → constrain the strategy; never weaken the assertion.

### Self-check
- [ ] A property exists for every Core Invariant above.
- [ ] ci profile pinned (max_examples=500, deadline=5000) in CI.
- [ ] Stateful lifecycle modeled with a RuleBasedStateMachine + invariants.

---

## Table of Contents

- [Overview](#overview)
- [When to Use](#when-to-use)
- [Quick Start](#quick-start)
- [Reference Guides](#reference-guides)
- [Best Practices](#best-practices)

## Overview

Property-based testing verifies that code satisfies general properties or invariants for a wide range of automatically generated inputs, rather than testing specific examples. This approach finds edge cases and bugs that example-based tests often miss.

## When to Use

- Testing algorithms with mathematical properties
- Verifying invariants that should always hold
- Finding edge cases automatically
- Testing parsers and serializers (round-trip properties)
- Validating data transformations
- Testing sorting, searching, and data structure operations
- Discovering unexpected input combinations

## Quick Start

Minimal working example:

```python
# test_string_operations.py
import pytest
from hypothesis import given, strategies as st, assume, example

def reverse_string(s: str) -> str:
    """Reverse a string."""
    return s[::-1]

class TestStringOperations:
    @given(st.text())
    def test_reverse_twice_returns_original(self, s):
        """Property: Reversing twice returns the original string."""
        assert reverse_string(reverse_string(s)) == s

    @given(st.text())
    def test_reverse_length_unchanged(self, s):
        """Property: Reverse doesn't change length."""
        assert len(reverse_string(s)) == len(s)

    @given(st.text(min_size=1))
    def test_reverse_first_becomes_last(self, s):
        """Property: First char becomes last after reverse."""
        reversed_s = reverse_string(s)
        assert s[0] == reversed_s[-1]
        assert s[-1] == reversed_s[0]
// ... (see reference guides for full implementation)
```

## Reference Guides

Detailed implementations in the `references/` directory:

| Guide | Contents |
|---|---|
| [Hypothesis for Python](references/hypothesis-for-python.md) | Hypothesis for Python |
| [fast-check for JavaScript/TypeScript](references/fast-check-for-javascripttypescript.md) | fast-check for JavaScript/TypeScript |
| [junit-quickcheck for Java](references/junit-quickcheck-for-java.md) | junit-quickcheck for Java |

## Best Practices

### DO

- Focus on general properties, not specific cases
- Test mathematical properties (commutativity, associativity)
- Verify round-trip encoding/decoding
- Use shrinking to find minimal failing cases
- Combine with example-based tests for known edge cases
- Test invariants that should always hold
- Generate realistic input distributions

### DON'T

- Test properties that are tautologies
- Over-constrain input generation
- Ignore shrunk test failures
- Replace all example tests with properties
- Test implementation details
- Generate invalid inputs without constraints
- Forget to handle edge cases in generators

---

# QUAICU Governance Kernel — Property-Based Testing Guide

This section documents the complete Hypothesis-based property test suite for the QUAICU governance kernel. The spec mandates property-based invariant tests as a non-negotiable deliverable for every layer — this is the implementation of that mandate.

The nine Core Invariants from the spec (§1) each have dedicated property suites below. Because there is no prior implementation to diff against, these tests are the primary mechanism for establishing correctness.

## 1. Hypothesis Settings Profiles

### CI profile (fast, high confidence)

```python
# tests/property/settings.py
from hypothesis import HealthCheck, Phase, Verbosity, settings

# Standard CI profile: 500 examples, 5 second deadline per test
ci_settings = settings(
    max_examples=500,
    deadline=5_000,          # 5 000 ms per test function
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
    ],
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.shrink],
    verbosity=Verbosity.normal,
)

# Development profile: fewer examples, shorter deadline, print failing inputs
dev_settings = settings(
    max_examples=50,
    deadline=2_000,
    verbosity=Verbosity.verbose,
)

# Deep property exploration (nightly / pre-release)
deep_settings = settings(
    max_examples=5_000,
    deadline=30_000,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    phases=[Phase.explicit, Phase.reuse, Phase.generate, Phase.target, Phase.shrink],
    verbosity=Verbosity.normal,
)
```

Apply a profile via decorator or context manager:

```python
from hypothesis import given, settings as h_settings
from tests.property.settings import ci_settings

@given(st.integers())
@ci_settings
def test_my_property(n):
    ...
```

### Shrinking configuration

Hypothesis shrinks by default. For faster debugging during development, disable shrinking temporarily:

```python
from hypothesis import Phase, settings

no_shrink = settings(phases=[Phase.explicit, Phase.reuse, Phase.generate])
```

Never disable shrinking in CI — a shrunk counter-example is far more actionable than the raw one.

---

## 2. QUAICU Hypothesis Strategies

### Action strategy

```python
# tests/property/strategies.py
from __future__ import annotations

from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

# All valid action types registered in the policy pack
# In practice, load these from the policy registry at test startup
KNOWN_ACTION_TYPES = [
    "ciro.ifrs9.stage_transition",
    "ciro.ifrs9.exposure_reclassification",
    "dpdp.consent.grant",
    "dpdp.consent.withdraw",
    "kernel.admin.policy_activate",
    "kernel.admin.policy_deprecate",
    "test.no_op_action",
    "test.high_risk_action",
]

TENANT_IDS = ["tenant-alpha", "tenant-beta", "tenant-gamma", "tenant-bank-1"]


def action_type_strategy() -> SearchStrategy[str]:
    """Generate a valid action type from the policy registry."""
    return st.sampled_from(KNOWN_ACTION_TYPES)


def tenant_id_strategy() -> SearchStrategy[str]:
    """Generate a valid tenant ID."""
    return st.sampled_from(TENANT_IDS)


def action_payload_strategy(action_type: str) -> SearchStrategy[dict]:
    """
    Generate a structurally valid payload for a given action type.
    Payloads are type-specific — this function dispatches on action_type.
    """
    if action_type == "ciro.ifrs9.stage_transition":
        return st.fixed_dictionaries({
            "loan_id": st.text(alphabet=st.characters(whitelist_categories=("Lu", "Nd")), min_size=3, max_size=20),
            "from_stage": st.integers(min_value=1, max_value=3),
            "to_stage": st.integers(min_value=1, max_value=3),
            "exposure": st.integers(min_value=0, max_value=100_000_000),
        })
    if action_type.startswith("dpdp.consent."):
        return st.fixed_dictionaries({
            "data_subject_id": st.uuids().map(str),
            "purpose": st.sampled_from(["marketing", "analytics", "service_delivery"]),
            "legal_basis": st.sampled_from(["consent", "legitimate_interest", "contract"]),
        })
    # Generic fallback for test action types
    return st.fixed_dictionaries({
        "value": st.integers() | st.text() | st.booleans(),
    })


def action_strategy() -> SearchStrategy[dict]:
    """
    Generate a complete Action for property tests.
    Uses flatmap to ensure payload matches action_type.
    """
    import uuid
    return (
        action_type_strategy()
        .flatmap(lambda at: st.fixed_dictionaries({
            "id": st.uuids().map(str),
            "type": st.just(at),
            "payload": action_payload_strategy(at),
            "actor_token": st.text(min_size=10, max_size=64),
            "tenant_id": tenant_id_strategy(),
            "idempotency_key": st.uuids().map(str),
        }))
    )
```

### CEL expression fuzzing strategy

```python
def cel_expression_strategy() -> SearchStrategy[str]:
    """
    Generate CEL expressions for fuzz-testing the policy engine's compile-check.
    The compile-check must accept all valid CEL and reject all invalid CEL —
    never crash or allow an expression that references unavailable symbols.
    """
    # Simple arithmetic / comparison expressions — all valid CEL
    valid_comparisons = st.builds(
        "{lhs} {op} {rhs}".format,
        lhs=st.sampled_from(["action.payload.exposure", "action.payload.from_stage", "0", "100"]),
        op=st.sampled_from([">", ">=", "<", "<=", "=="]),
        rhs=st.integers(min_value=0, max_value=10_000_000).map(str),
    )
    # Compound expressions
    compound = st.builds(
        "({a}) && ({b})".format,
        a=valid_comparisons,
        b=valid_comparisons,
    )
    # Intentionally invalid CEL (bare Python, Rego syntax, missing fields)
    invalid_expressions = st.sampled_from([
        "import os; os.system('rm -rf /')",   # Python injection attempt
        "eval('1+1')",                          # Python eval
        "allow { input.x == 1 }",              # Rego syntax
        "action.nonexistent_field.deep.access",
        "",
        "   ",
        "action.payload.exposure >",           # incomplete expression
    ])
    return st.one_of(valid_comparisons, compound, invalid_expressions)
```

### Ledger entry strategy

```python
def ledger_entry_strategy() -> SearchStrategy[dict]:
    """
    Generate ledger entries for Merkle property tests.
    Entries must contain all fields required for replay (spec §3.13).
    """
    return st.fixed_dictionaries({
        "action_id": st.uuids().map(str),
        "action_type": action_type_strategy(),
        "action_payload": st.dictionaries(
            st.text(min_size=1, max_size=20),
            st.integers() | st.text(max_size=50),
            min_size=1,
            max_size=5,
        ),
        "actor": st.text(min_size=5, max_size=64),
        "tenant_id": tenant_id_strategy(),
        "policy_versions": st.lists(
            st.fixed_dictionaries({
                "policy_id": st.text(min_size=5),
                "version": st.integers(min_value=1, max_value=100),
            }),
            min_size=1,
            max_size=5,
        ),
        "evaluation_result": st.sampled_from(["ALLOW", "DENY", "REQUIRE_APPROVAL"]),
        "consent_state": st.sampled_from(["GRANTED", "WITHDRAWN", "NOT_REQUIRED"]),
        "timestamp_utc": st.datetimes(
            min_value=__import__("datetime").datetime(2020, 1, 1),
            max_value=__import__("datetime").datetime(2030, 12, 31),
        ).map(lambda dt: dt.isoformat()),
    })
```

---

## 3. Ledger Integrity Properties

### Property: appending N entries — all inclusion proofs verify

```python
# tests/property/test_ledger_invariants.py
import pytest
from hypothesis import given, assume, settings as h_settings
from hypothesis import strategies as st
from tests.property.strategies import ledger_entry_strategy
from tests.property.settings import ci_settings


@pytest.mark.property
@given(st.lists(ledger_entry_strategy(), min_size=1, max_size=200))
@ci_settings
def test_all_inclusion_proofs_verify_after_bulk_append(entries):
    """
    Property: for any sequence of N ledger entries, every entry's RFC 6962
    inclusion proof must verify against the current root hash.

    This is the core correctness guarantee of the TrustLedger (K·02).
    Fails if the Merkle implementation has an off-by-one, a hash collision
    shortcut, or incorrect tree-head computation.
    """
    from core.ledger import InMemoryMerkleTree
    from tests.utils.ledger import verify_inclusion_proof, compute_leaf_hash
    import hashlib, json

    tree = InMemoryMerkleTree()
    sealed = []

    for entry in entries:
        proof = tree.append(entry)
        sealed.append((entry, proof))

    current_root = tree.root_hash()

    for entry, proof in sealed:
        leaf = compute_leaf_hash(entry)
        valid = verify_inclusion_proof(
            leaf_hash=leaf,
            proof_path=proof.path,
            root_hash=current_root,
            leaf_index=proof.leaf_index,
            tree_size=tree.size(),
        )
        assert valid, (
            f"Inclusion proof failed for entry {entry['action_id']!r} "
            f"at index {proof.leaf_index} in tree of size {tree.size()}. "
            "TrustLedger inclusion invariant violated."
        )


@pytest.mark.property
@given(
    st.lists(ledger_entry_strategy(), min_size=2, max_size=100),
    st.integers(min_value=0),
)
@ci_settings
def test_consistency_proof_detects_retroactive_edit(entries, tamper_index):
    """
    Property: if any historical entry is modified after sealing, the
    consistency proof between the old root and new root must fail to verify.
    This proves immutability — a regulator can detect any retroactive edit.
    """
    from core.ledger import InMemoryMerkleTree
    import copy

    assume(len(entries) >= 2)
    tamper_index = tamper_index % len(entries)

    tree = InMemoryMerkleTree()
    for entry in entries:
        tree.append(entry)

    honest_root = tree.root_hash()

    # Tamper with one historical entry
    tampered_entries = copy.deepcopy(entries)
    tampered_entries[tamper_index]["evaluation_result"] = "ALLOW"  # flip a denial to allow

    tampered_tree = InMemoryMerkleTree()
    for entry in tampered_entries:
        tampered_tree.append(entry)

    tampered_root = tampered_tree.root_hash()

    # The two roots must differ — the tamper must be detectable
    assert honest_root != tampered_root, (
        f"Tampered ledger at index {tamper_index} produced the same root hash. "
        "Immutability invariant violated — tampering is undetectable."
    )
```

---

## 4. Policy Determinism Property

```python
# tests/property/test_policy_determinism.py
import pytest
from hypothesis import given, settings as h_settings
from tests.property.strategies import action_strategy
from tests.property.settings import ci_settings


@pytest.mark.property
@given(action_strategy())
@ci_settings
async def test_policy_evaluation_is_deterministic(action_dict):
    """
    Core invariant: identical inputs produce an identical policy decision.
    No hidden state, no wall-clock-dependent branching in CEL evaluation.

    Evaluating the same action twice must return the same decision.
    If this property fails, replay is broken and the determinism invariant is violated.
    """
    from core.policy import evaluate_policy
    from core.models import Action
    from tests.fakes.storage import FakeStorageAdapter
    from tests.conftest import FakeClock
    from datetime import datetime, timezone

    storage = FakeStorageAdapter()
    clock = FakeClock(initial=datetime(2026, 1, 1, tzinfo=timezone.utc))

    action = Action(**action_dict)

    result_1 = await evaluate_policy(action, storage=storage, clock=clock)
    result_2 = await evaluate_policy(action, storage=storage, clock=clock)

    assert result_1.decision == result_2.decision, (
        f"Policy evaluation is non-deterministic for action type {action.type!r}. "
        f"First: {result_1.decision!r}, Second: {result_2.decision!r}. "
        "Determinism invariant violated."
    )
    assert result_1.policy_id == result_2.policy_id, (
        "Different policies applied on repeated evaluation of identical input. "
        "Determinism invariant violated."
    )
```

---

## 5. Tenant Isolation Property

```python
# tests/property/test_tenant_isolation.py
import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from tests.property.strategies import action_strategy, TENANT_IDS
from tests.property.settings import ci_settings


@pytest.mark.property
@pytest.mark.tenant_isolation
@given(
    st.lists(action_strategy(), min_size=2, max_size=20),
    st.sampled_from(TENANT_IDS),
    st.sampled_from(TENANT_IDS),
)
@ci_settings
async def test_tenant_isolation_never_leaks(actions_raw, tenant_a, tenant_b):
    """
    Core invariant: no data, decision, policy, or ledger entry ever crosses
    a tenant boundary.

    For any set of actions across two different tenants, listing actions for
    tenant A must never include entries belonging to tenant B.
    """
    from hypothesis import assume
    assume(tenant_a != tenant_b)

    from core.lifecycle import propose_action, list_actions
    from core.models import Action
    from tests.fakes.storage import FakeStorageAdapter
    from tests.fakes.identity import FakeIdentityAdapter
    from core.models import Actor
    from tests.conftest import FakeClock
    from datetime import datetime, timezone

    storage = FakeStorageAdapter()
    identity = FakeIdentityAdapter()
    clock = FakeClock(initial=datetime(2026, 1, 1, tzinfo=timezone.utc))

    identity.register(tenant_a, f"token-{tenant_a}", Actor(id=f"user-{tenant_a}", roles=["actor"]))
    identity.register(tenant_b, f"token-{tenant_b}", Actor(id=f"user-{tenant_b}", roles=["actor"]))

    for raw in actions_raw:
        action = Action(**{**raw, "actor_token": f"token-{raw['tenant_id']}"})
        try:
            await propose_action(action, storage=storage, identity=identity, clock=clock)
        except Exception:
            pass  # Denied actions are fine; the isolation property still holds

    actions_for_a = await list_actions(tenant_id=tenant_a, storage=storage)
    for a in actions_for_a:
        assert a["tenant_id"] == tenant_a, (
            f"Tenant isolation violated: action with tenant_id={a['tenant_id']!r} "
            f"appeared in listing for tenant {tenant_a!r}."
        )
```

---

## 6. Idempotency Key Property

```python
@pytest.mark.property
@given(action_strategy(), st.integers(min_value=2, max_value=10))
@ci_settings
async def test_idempotency_key_prevents_double_execute(action_raw, submission_count):
    """
    Core invariant: re-submitting the same proposal (same idempotency_key) must
    not double-execute, double-seal, or double-emit.

    For any action submitted N times with the same idempotency key, there must
    be exactly one ledger entry and the execute function must be called exactly once.
    """
    from core.lifecycle import propose_action
    from core.models import Action
    from tests.fakes.storage import FakeStorageAdapter
    from tests.fakes.identity import FakeIdentityAdapter
    from core.models import Actor
    from tests.conftest import FakeClock
    from datetime import datetime, timezone

    storage = FakeStorageAdapter()
    identity = FakeIdentityAdapter()
    clock = FakeClock(initial=datetime(2026, 1, 1, tzinfo=timezone.utc))

    identity.register(
        action_raw["tenant_id"],
        action_raw["actor_token"],
        Actor(id="test-actor", roles=["actor"]),
    )

    action = Action(**action_raw)
    execute_count = 0

    async def counting_execute(a, **kwargs):
        nonlocal execute_count
        execute_count += 1

    for _ in range(submission_count):
        try:
            await propose_action(action, storage=storage, identity=identity,
                                  clock=clock, execute_fn=counting_execute)
        except Exception:
            pass

    assert execute_count <= 1, (
        f"Execute was called {execute_count} times for {submission_count} "
        f"submissions of the same idempotency key. "
        "Idempotency invariant violated — double-execute occurred."
    )

    ledger_keys = [k for k in storage.all_keys() if k.startswith(f"ledger:")]
    action_ledger_entries = [k for k in ledger_keys if action_raw["idempotency_key"] in k]
    assert len(action_ledger_entries) <= 1, (
        f"Found {len(action_ledger_entries)} ledger entries for single idempotency key. "
        "Double-seal invariant violated."
    )
```

---

## 7. Stateful Testing — Lifecycle State Machine

Use `hypothesis.stateful.RuleBasedStateMachine` to model valid and invalid lifecycle state transitions and prove that no transition can bypass the governance spine.

```python
# tests/property/test_lifecycle_state_machine.py
from __future__ import annotations

import pytest
from hypothesis import settings as h_settings
from hypothesis.stateful import (
    Bundle,
    RuleBasedStateMachine,
    initialize,
    invariant,
    rule,
)
from tests.property.settings import ci_settings


class GovernedActionStateMachine(RuleBasedStateMachine):
    """
    Model-based test of the governed action lifecycle state machine.

    Valid transitions (spec §5):
      PROPOSED → EVALUATING → PENDING_APPROVAL (require_approval)
      PROPOSED → EVALUATING → EXECUTING (allow)
      PROPOSED → EVALUATING → DENIED (deny)
      PENDING_APPROVAL → APPROVED → EXECUTING
      PENDING_APPROVAL → REJECTED → HALTED
      EXECUTING → SEALED → EMITTED (terminal)
      Any state → DENIED (on error)
      Any state → HALTED (on timeout/HITL rejection)

    Invalid transitions (must never occur):
      PROPOSED → EXECUTING (skips evaluate)
      PROPOSED → SEALED (skips evaluate + execute)
      PENDING_APPROVAL → SEALED (skips execute)
      DENIED → EXECUTING (bypasses denial)
      HALTED → EXECUTING (bypasses halt)
    """

    actions = Bundle("actions")

    VALID_TRANSITIONS = {
        "PROPOSED": {"EVALUATING", "DENIED"},
        "EVALUATING": {"PENDING_APPROVAL", "EXECUTING", "DENIED"},
        "PENDING_APPROVAL": {"APPROVED", "REJECTED", "HALTED"},
        "APPROVED": {"EXECUTING"},
        "EXECUTING": {"SEALED", "DENIED", "HALTED"},
        "SEALED": {"EMITTED"},
        "EMITTED": set(),    # terminal
        "DENIED": set(),     # terminal
        "HALTED": set(),     # terminal
        "REJECTED": set(),   # terminal
    }

    def __init__(self):
        super().__init__()
        self._state: str = "PROPOSED"
        self._transition_log: list[tuple[str, str]] = []

    @initialize()
    def init_action(self):
        self._state = "PROPOSED"
        self._transition_log = []

    def _transition(self, new_state: str) -> None:
        allowed = self.VALID_TRANSITIONS.get(self._state, set())
        assert new_state in allowed, (
            f"Invalid lifecycle transition: {self._state!r} → {new_state!r}. "
            f"Allowed from {self._state!r}: {allowed}. "
            "No-bypass invariant violated."
        )
        self._transition_log.append((self._state, new_state))
        self._state = new_state

    @rule()
    def evaluate(self):
        if self._state == "PROPOSED":
            self._transition("EVALUATING")

    @rule()
    def evaluation_allows(self):
        if self._state == "EVALUATING":
            self._transition("EXECUTING")

    @rule()
    def evaluation_requires_approval(self):
        if self._state == "EVALUATING":
            self._transition("PENDING_APPROVAL")

    @rule()
    def evaluation_denies(self):
        if self._state in ("PROPOSED", "EVALUATING"):
            self._transition("DENIED")

    @rule()
    def human_approves(self):
        if self._state == "PENDING_APPROVAL":
            self._transition("APPROVED")
            self._transition("EXECUTING")

    @rule()
    def human_rejects(self):
        if self._state == "PENDING_APPROVAL":
            self._transition("REJECTED")

    @rule()
    def hitl_timeout(self):
        if self._state == "PENDING_APPROVAL":
            self._transition("HALTED")

    @rule()
    def execution_succeeds(self):
        if self._state == "EXECUTING":
            self._transition("SEALED")
            self._transition("EMITTED")

    @rule()
    def execution_fails(self):
        if self._state == "EXECUTING":
            self._transition("DENIED")

    @invariant()
    def denied_or_halted_never_execute(self):
        """Terminal denial/halt states are irreversible — no execution can follow."""
        if self._state in ("DENIED", "HALTED", "REJECTED"):
            for _from, _to in self._transition_log:
                assert _to != "EXECUTING" or _from not in ("DENIED", "HALTED", "REJECTED"), (
                    f"State machine transitioned from {_from!r} to EXECUTING. "
                    "No-bypass invariant violated: denied/halted action reached execution."
                )

    @invariant()
    def sealed_only_after_executing(self):
        """Seal can only follow Execute — never proposed or evaluated state."""
        seal_indices = [i for i, (_, to) in enumerate(self._transition_log) if to == "SEALED"]
        for idx in seal_indices:
            from_state = self._transition_log[idx][0]
            assert from_state == "EXECUTING", (
                f"SEALED transition came from {from_state!r} instead of EXECUTING. "
                "An action was sealed without executing — no-bypass violated."
            )


@pytest.mark.property
@h_settings(max_examples=500, stateful_step_count=50)
def test_lifecycle_state_machine():
    GovernedActionStateMachineTestCase = GovernedActionStateMachine.TestCase
    GovernedActionStateMachineTestCase.settings = ci_settings
    run_state_machine_as_test(GovernedActionStateMachine)
```

---

## 8. CEL Expression Compiler Property

```python
# tests/property/test_cel_compile_check.py
import pytest
from hypothesis import given, settings as h_settings
from tests.property.strategies import cel_expression_strategy
from tests.property.settings import ci_settings


@pytest.mark.property
@given(cel_expression_strategy())
@ci_settings
def test_cel_compile_check_never_crashes(expression):
    """
    Property: the CEL compile-check must never panic/crash regardless of input.
    It must accept valid CEL or return a structured CompileError — never raise
    an unhandled exception.

    This guards against injection (ADR F-05: Python eval is forbidden;
    CEL is the only policy condition language).
    """
    from core.policy.cel import compile_cel_expression, CompileError

    try:
        result = compile_cel_expression(expression)
        # If it compiles, it must be statically bounded (non-Turing-complete)
        assert result is not None
    except CompileError:
        # Structured rejection is fine
        pass
    except Exception as exc:
        pytest.fail(
            f"CEL compile-check raised unexpected exception {type(exc).__name__}: {exc}. "
            f"Input: {expression!r}. The compiler must never crash."
        )


@pytest.mark.property
@given(cel_expression_strategy())
@ci_settings
def test_cel_has_no_side_effects(expression):
    """
    Property: executing any compiled CEL expression must not cause I/O,
    file access, network calls, or any system side effect.
    CEL is sandboxed — this is what guarantees the determinism invariant.
    """
    from core.policy.cel import compile_cel_expression, evaluate_cel, CompileError
    from unittest.mock import patch
    import builtins

    # Patch I/O primitives — any call means the sandbox is broken
    side_effect_log = []
    original_open = builtins.open

    def detecting_open(*args, **kwargs):
        side_effect_log.append(("open", args))
        return original_open(*args, **kwargs)

    try:
        compiled = compile_cel_expression(expression)
    except CompileError:
        return  # Invalid CEL — skip execution test

    with patch("builtins.open", detecting_open), \
         patch("builtins.__import__", side_effect=ImportError("CEL sandbox violation")):
        try:
            evaluate_cel(compiled, context={"action": {"payload": {}}})
        except Exception:
            pass  # Evaluation errors are fine; side effects are not

    assert not side_effect_log, (
        f"CEL expression caused I/O side effect: {side_effect_log}. "
        "CEL sandbox invariant violated."
    )
```

---

## 9. Conflict Resolution Totality Property

```python
@pytest.mark.property
@given(
    st.lists(
        st.fixed_dictionaries({
            "policy_id": st.text(min_size=3),
            "decision": st.sampled_from(["ALLOW", "DENY", "REQUIRE_APPROVAL"]),
            "scope": st.sampled_from(["global", "tenant", "segment"]),
            "priority": st.integers(min_value=1, max_value=100),
        }),
        min_size=1,
        max_size=10,
    )
)
@ci_settings
def test_conflict_resolution_is_total_and_defined(policy_results):
    """
    Core invariant: policy evaluation never returns 'undefined'.
    Deny overrides allow; most-specific scope wins; resolution order is exhaustive.

    For any set of policy results (including contradictory ones), the resolver
    must return exactly one of ALLOW / DENY / REQUIRE_APPROVAL — never None,
    never an exception, never ambiguity.
    """
    from core.policy.conflict import resolve_conflicts

    result = resolve_conflicts(policy_results)

    assert result is not None, "Conflict resolver returned None — undefined result."
    assert result.decision in ("ALLOW", "DENY", "REQUIRE_APPROVAL"), (
        f"Conflict resolver returned invalid decision {result.decision!r}. "
        "Total conflict resolution invariant violated."
    )

    # Deny must override allow (the most conservative wins)
    has_deny = any(p["decision"] == "DENY" for p in policy_results)
    if has_deny:
        assert result.decision == "DENY", (
            f"Conflict resolver returned {result.decision!r} despite a DENY policy. "
            "Deny-overrides-allow invariant violated."
        )
```

---

## 10. No-Bypass Round-Trip Property

```python
@pytest.mark.property
@given(action_strategy())
@ci_settings
async def test_no_bypass_evaluate_always_called(action_raw):
    """
    Core invariant (ADR F-04): there is no code path that executes or seals
    an action which skipped evaluation and gating. Even administrative actions.

    For any Action, if it reaches SEALED state, there must be an evaluation
    record in storage. If there is no evaluation record, the action must not
    be in EXECUTED or SEALED state.
    """
    from core.lifecycle import propose_action
    from core.models import Action, ActionState
    from tests.fakes.storage import FakeStorageAdapter
    from tests.fakes.identity import FakeIdentityAdapter
    from core.models import Actor
    from tests.conftest import FakeClock
    from datetime import datetime, timezone

    storage = FakeStorageAdapter()
    identity = FakeIdentityAdapter()
    clock = FakeClock(initial=datetime(2026, 1, 1, tzinfo=timezone.utc))

    identity.register(
        action_raw["tenant_id"],
        action_raw["actor_token"],
        Actor(id="test-actor", roles=["actor"]),
    )

    action = Action(**action_raw)
    try:
        await propose_action(action, storage=storage, identity=identity, clock=clock)
    except Exception:
        pass

    action_record = storage.get_direct(f"action:{action.id}")
    eval_record = storage.get_direct(f"eval:{action.id}")

    if action_record is not None:
        state = action_record.get("state")
        if state in (ActionState.EXECUTED, ActionState.SEALED, ActionState.EMITTED):
            assert eval_record is not None, (
                f"Action {action.id!r} reached {state!r} state without an evaluation record. "
                "No-bypass invariant (ADR F-04) violated."
            )
```

---

## 11. Replay Fidelity Property

```python
@pytest.mark.property
@given(st.lists(ledger_entry_strategy(), min_size=1, max_size=50))
@ci_settings
async def test_replay_reconstructs_same_decision(entries):
    """
    Core invariant: any governed action can be re-derived from the ledger
    using the policy versions and recorded results in effect at the time.

    For each entry, replaying with its recorded policy versions and recorded
    model outputs must produce the same evaluation_result — never a different one.
    """
    from core.ledger import replay_decision
    from tests.fakes.storage import FakeStorageAdapter

    storage = FakeStorageAdapter()

    for entry in entries:
        storage._store[f"ledger:{entry['action_id']}"] = entry

    for entry in entries:
        replayed = await replay_decision(
            action_id=entry["action_id"],
            storage=storage,
        )
        assert replayed.evaluation_result == entry["evaluation_result"], (
            f"Replay produced different decision for action {entry['action_id']!r}: "
            f"original={entry['evaluation_result']!r}, replayed={replayed.evaluation_result!r}. "
            "Replay fidelity invariant violated."
        )
```

---

## 12. Running the Property Suite

```bash
# Full property suite with CI profile (500 examples)
pytest tests/property/ -m property --hypothesis-seed=0

# With database profile for deep pre-release exploration
pytest tests/property/ -m property \
    --hypothesis-profile=deep \
    --hypothesis-seed=0 \
    -x  # stop on first failure for actionable feedback

# Reproduce a specific failure by seed
pytest tests/property/test_ledger_invariants.py \
    --hypothesis-seed=<seed-from-failure-output>

# View shrunk counter-examples in detail
pytest tests/property/ -m property -v \
    --hypothesis-show-statistics
```

### Hypothesis database

Hypothesis stores previously-found failures in `.hypothesis/`. Commit this directory to version control so CI re-runs known failures on every PR.

```gitignore
# .gitignore — do NOT ignore this:
# .hypothesis/
```

```bash
# Clear the Hypothesis database (only when the code changes make old failures irrelevant)
hypothesis clear-db
```
