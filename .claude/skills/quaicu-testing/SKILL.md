---
name: quaicu-testing
description: |
  QUAICU spec-driven testing strategy. Use when writing tests for any QUAICU layer, setting up CI,
  or reviewing a PR for test coverage. Enforces: no layer is done without its correctness suite,
  property-based tests for all Core Invariants, fail-closed tested with injected faults, tenant
  isolation tested adversarially. Covers the CI matrix (unit, conformance, property, integration,
  chaos), mutation testing (mutmut), per-layer coverage floors, contract tests, golden cases from
  YAML spec, fixture factories. Trigger keywords: conformance, property_based, hypothesis,
  fail_closed test, fault injection, golden case, acceptance suite, DoD, invariant test, ledger
  integrity, policy determinism, replay test, pytest, pytest-asyncio, mutmut, coverage, contract
  test, chaos test, p99 latency, fixture factory, CI matrix, pytest-xdist.
---

# QUAICU Testing Strategy

You are the test quality enforcer. With no prior implementation to diff against, correctness is
established by spec-driven testing. A layer is **not done** when the happy path works — it is done
when its full correctness suite passes. This document defines the complete testing system:
six test tiers, their tooling, coverage requirements, parallelization config, and the CI matrix
that enforces all of it on every PR.

---

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> Makes every testing choice mechanical so a small/low-token model matches a top model at max effort.
> **If this block conflicts with prose below, this block wins.** Missing rule → add the stricter test and require it in CI.

### Invariants — never violated
- A layer is NOT done when the happy path passes — it is done when its full correctness suite passes.
- A detected fail-OPEN (action allowed through under a fault) is the single most critical failure (`FAIL_OPEN_DETECTED`). It blocks merge unconditionally.
- ALWAYS prove fail-closed by INJECTING faults (port down, timeout, policy error) and asserting DENIED/HALTED — never assume it.
- ALWAYS test tenant isolation adversarially (attempt to read another tenant) and assert it is impossible.
- ALWAYS test that replay causes no side effects (spy on ports; assert zero calls/writes).
- Every Core Invariant (ledger integrity, policy determinism, conflict totality, no-bypass) ALWAYS has a property-based (Hypothesis) test.

### Minimum coverage (CI-enforced floors — never lower)
| Layer | Floor |
|---|---|
| ledger | 95% |
| policy | 90% |
| lifecycle | 90% |
| consent | 90% |
| tenant | 90% |

### Which test tier? (decide by what you are verifying)
| Verifying… | Tier |
|---|---|
| one function/branch | unit |
| an adapter satisfies its port contract | conformance (subclass the port's base suite) |
| an invariant holds for ALL inputs | property (Hypothesis) |
| components work together against real Postgres | integration |
| behavior under random faults | chaos |
| p99 latency under budget | performance |

### Tie-break rules
- Is this test "enough"? → if it injects no fault, it does not prove fail-closed; add the fault-injection test.
- Assert allow or deny under a fault? → assert DENIED/HALTED. A passing test that allows-through is a bug in the test.
- Does this invariant need property testing? → if it must hold for all inputs, yes (Hypothesis), not just examples.

### Stop-and-apply triggers
- About to mark a layer "done"? → confirm conformance + property + fail-closed (+ isolation/replay where applicable) suites exist and pass.
- About to write only happy-path tests? → STOP, add fault-injection and adversarial cases.
- About to merge with coverage below the floor? → STOP, CI blocks it.

### Self-check
- [ ] Fail-closed paths tested with injected faults asserting DENIED/HALTED.
- [ ] Tenant isolation tested adversarially.
- [ ] Replay side-effect-free test present (zero port calls/writes).
- [ ] Property tests cover every Core Invariant.
- [ ] Coverage meets per-layer floors; FAIL_OPEN_DETECTED is a hard block.

---

## Error Type Hierarchy

```python
# core/errors/testing.py — used in test helpers and harnesses
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class TestErrorCode(str, Enum):
    # Fixture / factory
    INVALID_FIXTURE_PARAMS    = "TEST_001"
    MISSING_GOLDEN_CASE       = "TEST_002"

    # Contract violations
    ADAPTER_PROTOCOL_MISMATCH = "TEST_010"
    PORT_RETURN_TYPE_WRONG    = "TEST_011"
    FAIL_OPEN_DETECTED        = "TEST_020"   # CRITICAL

    # Performance
    P99_LATENCY_EXCEEDED      = "TEST_030"
    THROUGHPUT_BELOW_BASELINE = "TEST_031"

    # Chaos
    CHAOS_FAULT_NOT_TRIGGERED = "TEST_040"
    RECOVERY_TIMEOUT          = "TEST_041"


@dataclass
class TestError(Exception):
    code: TestErrorCode
    message: str
    layer: str | None = None
    detail: dict | None = None

    def __str__(self) -> str:
        base = f"[{self.code}] {self.message}"
        if self.layer:
            base += f" | layer={self.layer!r}"
        return base


class FailOpenDetectedError(TestError):
    """
    CRITICAL. Raised when a test detects that a fault caused the system to allow
    an action instead of denying/halting. This is the worst possible outcome for
    a governance kernel and must fail CI immediately.
    """
```

---

## Definition of Done — Every Layer Must Pass All of These

```
- [ ] Public API documented (quickstart + reference in docs/)
- [ ] Conformance suite passing — spec-derived golden cases from YAML spec files
- [ ] Invariant property tests passing — Core Invariants proven for this layer
- [ ] Fail-closed tested — faults injected, verified to DENY/HALT, never allow through
- [ ] Tenant isolation tested — adversarial test confirms no cross-tenant leakage
- [ ] Replay-safe tested — replay reconstructs faithfully; replay causes no side effects
- [ ] Telemetry emitted — OTel traces + metrics verified in integration tests
- [ ] Migrations included — if the layer owns tables
- [ ] Security review for security-critical layers (K·02, K·04, K·05)
- [ ] Mutation score meets threshold — ledger ≥ 95%, policy engine ≥ 90%, lifecycle ≥ 90%
- [ ] Contract tests pass — all adapters satisfy their Port Protocol
- [ ] Performance baselines pass — p99 within thresholds for seal(), evaluate(), generate()
```

---

## Coverage Requirements Per Layer

These are enforced in CI as hard failures. Use `pytest-cov` with `--fail-under`.

| Layer | Module path | Min coverage |
|-------|-------------|--------------|
| TrustLedger (K·02) | `core/ledger/` | **95%** |
| Policy Engine (K·01) | `core/policy/` | **90%** |
| Lifecycle spine | `core/lifecycle/` | **90%** |
| HITL (K·03) | `core/hitl/` | **85%** |
| Consent (K·04) | `core/consent/` | **90%** |
| AI Gateway (K·05) | `core/gateway/` | **85%** |
| Process Engine (K·06) | `core/process/` | **85%** |
| Event Bus (K·07) | `core/events/` | **80%** |
| Model Registry (K·08) | `core/registry/` | **80%** |
| Fairness (K·09) | `core/fairness/` | **80%** |
| Drift (K·10) | `core/drift/` | **80%** |
| Explainability (K·11) | `core/explain/` | **80%** |
| Incident (K·12) | `core/incident/` | **85%** |
| Sandbox (K·13) | `core/sandbox/` | **85%** |
| Regulatory Mapping (K·14) | `core/regmap/` | **85%** |
| Tenant isolation | `adapters/storage/` | **90%** |

```ini
# pyproject.toml — coverage configuration
[tool.coverage.run]
source = ["core", "adapters"]
omit   = ["*/tests/*", "*/__init__.py", "*/migrations/*"]
branch = true

[tool.coverage.report]
fail_under     = 80        # global floor; per-layer floors enforced by CI step per module
show_missing   = true
exclude_lines  = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
]
```

---

## Test Directory Structure

```
tests/
├── conformance/           # spec-derived acceptance + golden cases per layer
│   ├── golden/            # YAML golden case files (generated from spec)
│   │   ├── policy_engine_cases.yaml
│   │   ├── ledger_cases.yaml
│   │   ├── lifecycle_cases.yaml
│   │   └── ...
│   ├── test_policy_engine.py
│   ├── test_trust_ledger.py
│   ├── test_lifecycle.py
│   ├── test_ai_gateway.py
│   ├── test_hitl.py
│   ├── test_consent.py
│   ├── test_replay.py
│   └── ...
├── property/              # Hypothesis-based invariant proofs
│   ├── test_ledger_invariants.py
│   ├── test_policy_determinism.py
│   └── test_tenant_isolation_invariants.py
├── unit/                  # fast, isolated, no DB
│   ├── test_cel_evaluation.py
│   ├── test_merkle.py
│   └── ...
├── integration/           # real DB, real OTel, no mocks at boundaries
│   ├── test_tenant_isolation.py
│   ├── test_replay_side_effects.py
│   ├── test_fail_closed.py
│   └── test_otel_emission.py
├── contract/              # adapter Protocol conformance
│   ├── test_inference_contract.py
│   ├── test_hitl_contract.py
│   ├── test_identity_contract.py
│   ├── test_storage_contract.py
│   └── test_workflow_contract.py
├── chaos/                 # random fault injection at lifecycle steps
│   ├── test_chaos_lifecycle.py
│   ├── test_chaos_ledger.py
│   └── test_chaos_gateway.py
├── performance/           # p99 latency and throughput baselines
│   ├── test_seal_latency.py
│   ├── test_evaluate_latency.py
│   └── test_generate_latency.py
└── vectors/               # published test vectors for RFC 6962
    └── ledger_vectors.json
```

---

## Test Fixture Factories

All tests use factories to create valid domain objects. Factories enforce invariants
(e.g. tenant_id non-empty, action_id is a UUID) and make test intent explicit.

```python
# tests/factories.py
from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from core.domain.action import Action
from core.domain.policy import Policy, PolicyLifecycle
from core.domain.ledger_entry import LedgerEntry


# ── Action Factory ──────────────────────────────────────────────────────────

def make_action(
    action_type: str = "test.action",
    payload: dict | None = None,
    *,
    action_id: str | None = None,
    actor_id: str = "actor:test_user",
    tenant_id: str = "tenant_test",
) -> Action:
    """
    Create a valid Action for testing.
    Generates a UUID for action_id if not supplied.
    """
    return Action(
        action_id=uuid.UUID(action_id) if action_id else uuid.uuid4(),
        action_type=action_type,
        payload=payload or {"key": "value"},
        actor_id=actor_id,
        tenant_id=tenant_id,
        proposed_at=datetime.now(timezone.utc),
    )


# ── Policy Factory ───────────────────────────────────────────────────────────

def make_policy(
    decision: str = "allow",
    governs: str = "test.action",
    *,
    policy_id: str | None = None,
    version: int = 1,
    tenant_id: str = "tenant_test",
    condition: str = "true",
    approvers: list[str] | None = None,
    lifecycle: PolicyLifecycle = PolicyLifecycle.ACTIVATED,
    regulatory_refs: list[str] | None = None,
) -> Policy:
    """
    Create a valid Policy for testing.
    Decision must be "allow" | "deny" | "require_approval".
    """
    if decision not in ("allow", "deny", "require_approval"):
        raise ValueError(f"Invalid decision: {decision!r}")
    return Policy(
        id=policy_id or f"test.policy.{uuid.uuid4().hex[:8]}",
        version=version,
        governs=governs,
        scope={"tenant": tenant_id},
        condition=condition,
        decision=decision,
        approvers=approvers or [],
        lifecycle=lifecycle,
        tenant_id=tenant_id,
        regulatory_refs=regulatory_refs or [],
    )


def make_deny_policy(**kwargs) -> Policy:
    return make_policy(decision="deny", **kwargs)


def make_allow_policy(**kwargs) -> Policy:
    return make_policy(decision="allow", **kwargs)


def make_require_approval_policy(approvers: list[str] | None = None, **kwargs) -> Policy:
    return make_policy(
        decision="require_approval",
        approvers=approvers or ["role:approver"],
        **kwargs,
    )


# ── LedgerEntry Factory ──────────────────────────────────────────────────────

def make_ledger_entry(
    action: Action | None = None,
    *,
    global_seq: int = 1,
    sequence: int = 1,
    evaluation_decision: str = "allow",
    policy_versions: dict[str, int] | None = None,
    recorded_model_outputs: dict[str, Any] | None = None,
    prev_hash: bytes | None = None,
) -> LedgerEntry:
    """
    Create a valid LedgerEntry for testing.
    Supplies all required fields for replay correctness.
    """
    a = action or make_action()
    import hashlib
    payload_bytes = str(a.payload).encode()
    leaf = hashlib.sha256(b"\x00" + payload_bytes).digest()
    event_hash = hashlib.sha256((prev_hash or b"") + leaf).digest()

    return LedgerEntry(
        action_id=a.action_id,
        tenant_id=a.tenant_id,
        global_seq=global_seq,
        aggregate_id=a.action_id,
        aggregate_type="action",
        sequence=sequence,
        action_type=a.action_type,
        action_payload=a.payload,
        actor_id=a.actor_id,
        policy_versions=policy_versions or {"test.policy.v1": 1},
        consent_state={},
        assurance_signals={},
        recorded_model_outputs=recorded_model_outputs or {},
        recorded_external_lookups={},
        evaluation_decision=evaluation_decision,
        hitl_decision=None,
        execution_result=None,
        event_hash=event_hash,
        prev_hash=prev_hash,
        leaf_hash=leaf,
    )


# ── Shorthand sets for parametrize ──────────────────────────────────────────

any_action   = make_action()
allow_policy = make_allow_policy()
deny_policy  = make_deny_policy()
require_approval_policy = make_require_approval_policy()
wildcard_allow = make_allow_policy(governs="*", tenant_id="*")
tenant_specific_deny = make_deny_policy(governs="test.action", tenant_id="tenant_test")
tenant_action = make_action(action_type="test.action", tenant_id="tenant_test")
```

---

## Golden Case Generation from YAML Spec

Golden cases are authored in YAML (not hard-coded in test files) so they can be
generated from the specification and reviewed without reading Python.

```yaml
# tests/conformance/golden/policy_engine_cases.yaml
# Each case is a deterministic scenario derived from the spec (§3.9 conflict resolution).

cases:
  # K·01: Total conflict resolution (deny overrides allow)
  - id: K01-CONFLICT-01
    description: "deny overrides allow — deny wins"
    policies:
      - {id: p1, decision: allow, governs: "test.action", condition: "true"}
      - {id: p2, decision: deny,  governs: "test.action", condition: "true"}
    action:
      type: "test.action"
      payload: {}
    expected_decision: deny
    spec_ref: "§3.9 conflict resolution, §1 Core Invariants"

  - id: K01-CONFLICT-02
    description: "require_approval overrides allow"
    policies:
      - {id: p1, decision: allow,            governs: "test.action", condition: "true"}
      - {id: p2, decision: require_approval, governs: "test.action", condition: "true"}
    action: {type: "test.action", payload: {}}
    expected_decision: require_approval

  - id: K01-CONFLICT-03
    description: "deny overrides require_approval"
    policies:
      - {id: p1, decision: require_approval, governs: "test.action", condition: "true"}
      - {id: p2, decision: deny,             governs: "test.action", condition: "true"}
    action: {type: "test.action", payload: {}}
    expected_decision: deny

  - id: K01-FAIL-CLOSED-01
    description: "no governing policy → fail-closed → deny"
    policies: []
    action: {type: "test.action", payload: {}}
    expected_decision: deny
    spec_ref: "§1 Fail-closed invariant"

  - id: K01-SCOPE-01
    description: "most-specific scope wins — tenant-scoped deny over wildcard allow"
    policies:
      - {id: p1, decision: allow, governs: "test.action", scope: {tenant: "*"}}
      - {id: p2, decision: deny,  governs: "test.action", scope: {tenant: "tenant_test"}}
    action: {type: "test.action", tenant_id: "tenant_test", payload: {}}
    expected_decision: deny

  - id: K01-CEL-01
    description: "CEL condition false → policy does not apply"
    policies:
      - id: p1
        decision: deny
        governs: "test.action"
        condition: "action.payload.amount > 1000000"
    action:
      type: "test.action"
      payload: {amount: 500}
    expected_decision: deny    # no matching policy → fail-closed
```

```python
# tests/conformance/test_policy_engine.py
import yaml
import pytest
from pathlib import Path


def _load_golden_cases(filename: str) -> list[dict]:
    path = Path(__file__).parent / "golden" / filename
    with path.open() as f:
        return yaml.safe_load(f)["cases"]


POLICY_CASES = _load_golden_cases("policy_engine_cases.yaml")


@pytest.mark.parametrize(
    "case",
    POLICY_CASES,
    ids=[c["id"] for c in POLICY_CASES],
)
async def test_policy_golden_case(case: dict, policy_engine):
    """
    Run each golden case from the YAML spec file.
    These cases are derived directly from the specification — not from implementation.
    A change to the implementation must not change the expected outcome of these cases.
    """
    policies = [make_policy(**p) for p in case["policies"]]
    action = make_action(
        action_type=case["action"]["type"],
        payload=case["action"].get("payload", {}),
        tenant_id=case["action"].get("tenant_id", "tenant_test"),
    )
    result = await policy_engine.evaluate(action, policies)
    assert result.decision == case["expected_decision"], (
        f"Golden case {case['id']} failed: "
        f"expected {case['expected_decision']!r}, got {result.decision!r}\n"
        f"Description: {case.get('description', '')}\n"
        f"Spec ref: {case.get('spec_ref', 'n/a')}"
    )
```

---

## Property-Based Invariant Tests (Hypothesis)

```python
# tests/property/test_ledger_invariants.py
from hypothesis import given, settings, strategies as st, assume
import pytest


# ── Invariant: inclusion proof always verifies ───────────────────────────────

@given(
    st.lists(st.binary(min_size=1, max_size=256), min_size=1, max_size=1000)
)
@settings(max_examples=500, deadline=5000)
def test_inclusion_proof_always_verifies(leaf_data_list):
    """For any set of leaves, every leaf's inclusion proof must verify against the root."""
    from core.ledger.merkle import leaf_hash, root_hash, inclusion_proof, verify_inclusion
    leaves = [leaf_hash(d) for d in leaf_data_list]
    r = root_hash(leaves)
    for i, lh in enumerate(leaves):
        proof = inclusion_proof(i, len(leaves), leaves)
        assert verify_inclusion(lh, i, len(leaves), proof, r), (
            f"Inclusion proof failed for leaf {i} of {len(leaves)}"
        )


# ── Invariant: consistency proof detects any retroactive edit ────────────────

@given(
    st.lists(st.binary(min_size=1), min_size=2, max_size=200),
    st.integers(min_value=0, max_value=199),
)
@settings(max_examples=300)
def test_retroactive_edit_breaks_consistency(leaves_data, tamper_idx):
    from core.ledger.merkle import leaf_hash, root_hash, consistency_proof, verify_consistency
    leaves = [leaf_hash(d) for d in leaves_data]
    old_size = max(1, len(leaves) // 2)
    assume(tamper_idx < old_size)     # tamper a leaf that was in the old tree

    old_root = root_hash(leaves[:old_size])
    new_root = root_hash(leaves)
    proof = consistency_proof(old_size, len(leaves), leaves)

    tampered = leaves.copy()
    tampered[tamper_idx] = leaf_hash(b"tampered_" + str(tamper_idx).encode())
    tampered_root = root_hash(tampered)

    assert not verify_consistency(old_root, tampered_root, old_size, len(tampered), proof), (
        "Consistency proof did not detect a retroactive tamper — ledger integrity violated"
    )


# tests/property/test_policy_determinism.py

@given(
    st.fixed_dictionaries({
        "to_stage": st.integers(1, 5),
        "from_stage": st.integers(1, 5),
        "exposure": st.integers(0, 10_000_000),
    })
)
@settings(max_examples=1000)
def test_policy_evaluation_is_deterministic(payload):
    """
    Identical inputs → identical decision. No hidden state, no wall-clock-dependent
    branching in CEL evaluation. Run twice and assert equal.
    """
    action = make_action("ciro.ifrs9.stage_transition", payload)
    result_1 = policy_engine_sync.evaluate(action, [IFRS9_POLICY])
    result_2 = policy_engine_sync.evaluate(action, [IFRS9_POLICY])
    assert result_1.decision == result_2.decision, (
        f"Determinism violated: same payload {payload!r} produced "
        f"{result_1.decision!r} then {result_2.decision!r}"
    )


@given(
    st.text(min_size=1, max_size=50),
    st.dictionaries(st.text(max_size=20), st.integers()),
)
@settings(max_examples=500)
def test_evaluation_never_returns_undefined(action_type, payload):
    """Evaluation is total — it must always return allow, deny, or require_approval."""
    action = make_action(action_type, payload)
    result = policy_engine_sync.evaluate(action, ALL_ACTIVE_POLICIES)
    assert result.decision in ("allow", "deny", "require_approval"), (
        f"Evaluation returned {result.decision!r} — not a valid decision (totality violated)"
    )
```

---

## Contract Tests — Adapters Must Satisfy Their Port Protocol

Every adapter is verified to satisfy its Port Protocol at test time using runtime
`isinstance` + direct method invocation. This catches cases where an adapter
implements a method with the wrong signature or return type.

```python
# tests/contract/base_contract.py
from __future__ import annotations
from typing import Protocol, runtime_checkable, Type, Any
import inspect
import pytest


def assert_implements_protocol(
    adapter_instance: Any,
    protocol_class: Type,
) -> None:
    """
    Assert that adapter_instance satisfies all methods defined in protocol_class.
    Checks:
    1. isinstance (runtime_checkable Protocol)
    2. Every method in the protocol has a matching signature on the adapter
    3. No required parameter is missing
    """
    assert isinstance(adapter_instance, protocol_class), (
        f"{type(adapter_instance).__name__!r} does not satisfy "
        f"Protocol {protocol_class.__name__!r}"
    )
    for name, proto_method in inspect.getmembers(protocol_class, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        adapter_method = getattr(adapter_instance, name, None)
        assert adapter_method is not None, (
            f"Adapter {type(adapter_instance).__name__!r} missing method {name!r} "
            f"required by {protocol_class.__name__!r}"
        )
        proto_sig = inspect.signature(proto_method)
        adapter_sig = inspect.signature(adapter_method)
        proto_params = set(proto_sig.parameters) - {"self"}
        adapter_params = set(adapter_sig.parameters) - {"self"}
        missing = proto_params - adapter_params
        assert not missing, (
            f"Adapter method {name!r} is missing parameters: {missing}. "
            f"Protocol requires: {proto_params}"
        )


# tests/contract/test_inference_contract.py
import pytest
from core.ports.inference import InferencePort


@pytest.mark.parametrize("adapter_cls,config", [
    ("adapters.inference.ollama.OllamaInferenceAdapter",  {"base_url": "http://localhost:11434"}),
    ("adapters.inference.openai.OpenAIInferenceAdapter",  {"api_key": "test"}),
])
async def test_inference_adapter_satisfies_protocol(adapter_cls, config):
    """Every inference adapter must fully satisfy InferencePort."""
    from importlib import import_module
    module_path, cls_name = adapter_cls.rsplit(".", 1)
    cls = getattr(import_module(module_path), cls_name)
    adapter = cls(**config)
    assert_implements_protocol(adapter, InferencePort)


@pytest.mark.parametrize("adapter_cls,config", [
    ("adapters.inference.ollama.OllamaInferenceAdapter", {"base_url": "http://localhost:11434"}),
])
async def test_inference_fail_closed_on_unavailable(adapter_cls, config, mock_http_error):
    """
    Fail-closed contract: if the inference backend is unavailable, generate() must raise,
    never return a permissive default.
    """
    from importlib import import_module
    module_path, cls_name = adapter_cls.rsplit(".", 1)
    cls = getattr(import_module(module_path), cls_name)
    adapter = cls(**config)
    mock_http_error.inject_on("generate")

    with pytest.raises(Exception) as exc_info:
        await adapter.generate(
            prompt=make_prompt("test"),
            model_ref=make_model_ref("llama3"),
            tenant="tenant_test",
        )
    # Must raise — never return None or a dummy response
    assert exc_info.value is not None


# tests/contract/test_storage_contract.py
from core.ports.storage import StoragePort


async def test_storage_adapter_satisfies_protocol(postgres_storage):
    """PostgresStorageAdapter must fully satisfy StoragePort."""
    assert_implements_protocol(postgres_storage, StoragePort)


async def test_storage_transaction_is_atomic(postgres_storage, tenant_id):
    """Transaction context manager must roll back all writes on exception."""
    set_tenant(tenant_id)
    try:
        async with postgres_storage.transaction() as conn:
            await conn.execute(
                "INSERT INTO actions (action_id, action_type, tenant_id) VALUES ($1, $2, $3)",
                str(uuid.uuid4()), "test.action", tenant_id,
            )
            raise RuntimeError("intentional rollback")
    except RuntimeError:
        pass
    count = await postgres_storage.execute("SELECT COUNT(*) FROM actions", tenant_id=tenant_id)
    assert count[0][0] == 0, "Transaction did not roll back — atomicity contract violated"
```

---

## Fail-Closed Fault Injection Tests

```python
# tests/integration/test_fail_closed.py
import asyncio
import pytest
from unittest.mock import AsyncMock


@pytest.mark.parametrize("fault,expected_outcome", [
    # Policy engine down → DENIED
    ("PolicyEngineError",         "ActionState.DENIED"),
    # Policy engine timeout → DENIED
    ("asyncio.TimeoutError",      "ActionState.DENIED"),
    # Policy engine returns None → DENIED (fail-closed on None)
    ("NoneReturn",                "ActionState.DENIED"),
    # HITL port timeout → REJECTED (fail-closed)
    ("HITLTimeoutError",          "ActionState.REJECTED"),
    # Ledger seal failure → HALTED (executed but not sealed = invalid, must halt)
    ("LedgerSealError",           "ActionState.HALTED"),
    # Inference unavailable → HALTED
    ("InferenceUnavailableError", "ActionState.HALTED"),
    # Consent service error → DENIED
    ("ConsentServiceError",       "ActionState.DENIED"),
    # Identity resolution failure → DENIED
    ("IdentityResolutionError",   "ActionState.DENIED"),
    # Workflow engine crash after gate → HALTED
    ("WorkflowEngineError",       "ActionState.HALTED"),
    # Emit failure after seal → action sealed but emit retried (not re-executed)
    ("EmitError",                 "ActionState.SEALED_EMIT_PENDING"),
])
async def test_fail_closed_on_fault(fault, expected_outcome, lifecycle_engine, mock_ports):
    """
    Every fault at every lifecycle step must produce DENY or HALT, never ALLOW.
    This is the most important test class in the entire test suite.
    """
    from core.lifecycle.states import ActionState
    _inject_fault(mock_ports, fault)

    action = make_action("test.action")
    try:
        await lifecycle_engine.run(action)
    except Exception:
        pass

    final_state = await lifecycle_engine.storage.get_state(action.action_id)
    expected = getattr(ActionState, expected_outcome.split(".")[-1])
    assert final_state == expected, (
        f"Fault {fault!r} resulted in {final_state!r} instead of {expected!r}. "
        "This is a fail-open violation — CRITICAL."
    )
    # Explicit fail-open check
    if final_state == ActionState.EXECUTED:
        raise FailOpenDetectedError(
            code=TestErrorCode.FAIL_OPEN_DETECTED,
            message=(
                f"CRITICAL: fault {fault!r} caused action to be EXECUTED without "
                "completing the governance lifecycle. Fail-open detected."
            ),
        )


def _inject_fault(mock_ports, fault: str) -> None:
    """Map fault name to the mock setup that triggers it."""
    from core.errors.policy import PolicyEngineError
    from core.errors.hitl import HITLTimeoutError
    from core.errors.ledger import LedgerSealError
    from core.errors.gateway import InferenceUnavailableError
    from core.errors.consent import ConsentServiceError
    from core.errors.identity import IdentityResolutionError
    from core.errors.workflow import WorkflowEngineError
    from core.errors.events import EmitError

    fault_map = {
        "PolicyEngineError":         lambda: setattr(mock_ports.policy_engine, "evaluate",
                                         AsyncMock(side_effect=PolicyEngineError("down"))),
        "asyncio.TimeoutError":      lambda: setattr(mock_ports.policy_engine, "evaluate",
                                         AsyncMock(side_effect=asyncio.TimeoutError())),
        "NoneReturn":                lambda: setattr(mock_ports.policy_engine, "evaluate",
                                         AsyncMock(return_value=None)),
        "HITLTimeoutError":          lambda: setattr(mock_ports.hitl_port, "request_approval",
                                         AsyncMock(side_effect=HITLTimeoutError("timeout"))),
        "LedgerSealError":           lambda: setattr(mock_ports.ledger, "seal",
                                         AsyncMock(side_effect=LedgerSealError("db down"))),
        "InferenceUnavailableError": lambda: setattr(mock_ports.inference, "generate",
                                         AsyncMock(side_effect=InferenceUnavailableError())),
        "ConsentServiceError":       lambda: setattr(mock_ports.consent, "check",
                                         AsyncMock(side_effect=ConsentServiceError())),
        "IdentityResolutionError":   lambda: setattr(mock_ports.identity, "resolve_actor",
                                         AsyncMock(side_effect=IdentityResolutionError())),
        "WorkflowEngineError":       lambda: setattr(mock_ports.workflow, "start",
                                         AsyncMock(side_effect=WorkflowEngineError())),
        "EmitError":                 lambda: setattr(mock_ports.event_bus, "emit",
                                         AsyncMock(side_effect=EmitError())),
    }
    fault_map[fault]()
```

---

## Mutation Testing Setup (mutmut)

Mutation testing verifies that tests actually catch bugs — not just that they run.
`mutmut` introduces small code mutations (e.g. `>` → `>=`, `and` → `or`) and checks
whether tests fail. A surviving mutation means a test gap.

```ini
# setup.cfg (or pyproject.toml) — mutmut configuration
[mutmut]
paths_to_mutate = core/ledger/,core/policy/,core/lifecycle/
backup          = false
runner          = python -m pytest tests/unit tests/conformance -x -q
tests_dir       = tests/
dict_synonyms   = yes
```

```toml
# pyproject.toml — mutmut thresholds enforced in CI
[tool.mutmut]
paths_to_mutate = [
    "core/ledger/",
    "core/policy/",
    "core/lifecycle/",
]

# CI runs: mutmut run --use-coverage
# Then: mutmut results — fail if survived > threshold

# Thresholds (enforce in CI step — see CI matrix below):
# core/ledger/     → max 5% surviving mutations  (= 95% mutation score)
# core/policy/     → max 10% surviving mutations (= 90% mutation score)
# core/lifecycle/  → max 10% surviving mutations (= 90% mutation score)
```

```bash
# CI step: mutation testing with threshold enforcement
mutmut run --paths-to-mutate core/ledger/ --use-coverage
SURVIVED=$(mutmut results | grep "survived" | awk '{print $2}')
TOTAL=$(mutmut results | grep "total" | awk '{print $2}')
PCT=$(echo "scale=2; $SURVIVED / $TOTAL * 100" | bc)
if (( $(echo "$PCT > 5" | bc -l) )); then
  echo "Mutation score too low for core/ledger/: $SURVIVED/$TOTAL survived (>${PCT}%)"
  exit 1
fi
```

---

## Chaos Testing Patterns — Random Fault Injection at Any Lifecycle Step

Chaos tests inject faults at random points in the lifecycle to verify that the system
always lands in a safe terminal state (DENIED, HALTED, SEALED) — never in an
ambiguous or partially-executed state.

```python
# tests/chaos/test_chaos_lifecycle.py
import random
import pytest
from unittest.mock import AsyncMock, patch


LIFECYCLE_STEPS = [
    "core.lifecycle.propose.validate_action",
    "core.lifecycle.evaluate.run_policy_engine",
    "core.lifecycle.gate.request_hitl_approval",
    "core.lifecycle.execute.run_execute",
    "core.lifecycle.seal.seal_to_ledger",
    "core.lifecycle.emit.publish_event",
]

SAFE_TERMINAL_STATES = {"DENIED", "HALTED", "SEALED", "REJECTED", "SEALED_EMIT_PENDING"}


@pytest.mark.parametrize("seed", range(50))
async def test_random_fault_always_terminates_safely(seed, lifecycle_engine):
    """
    For 50 different random seeds: inject a fault at a randomly chosen lifecycle step.
    Assert the action always ends in a safe terminal state — never EXECUTED without seal,
    never in a liminal state (EVALUATING, GATING, etc.) after the fault.
    """
    random.seed(seed)
    fault_step = random.choice(LIFECYCLE_STEPS)

    with patch(fault_step, AsyncMock(side_effect=RuntimeError(f"chaos fault at {fault_step}"))):
        action = make_action("test.chaos.action")
        try:
            await lifecycle_engine.run(action)
        except Exception:
            pass

        final = await lifecycle_engine.storage.get_state(action.action_id)
        assert str(final) in SAFE_TERMINAL_STATES, (
            f"Seed {seed}: fault at {fault_step!r} left action in unsafe state {final!r}. "
            "The governance lifecycle did not terminate safely."
        )


@pytest.mark.parametrize("fault_count", [1, 2, 3])
async def test_cascading_faults_terminate_safely(fault_count, lifecycle_engine):
    """
    Inject faults at multiple steps simultaneously. The system must still terminate safely.
    """
    fault_steps = random.sample(LIFECYCLE_STEPS, k=min(fault_count, len(LIFECYCLE_STEPS)))
    patches = {
        step: AsyncMock(side_effect=RuntimeError(f"cascading fault"))
        for step in fault_steps
    }
    with patch.multiple("core.lifecycle", **{
        step.split(".")[-1]: patches[step] for step in fault_steps
    }):
        action = make_action("test.cascading.chaos")
        try:
            await lifecycle_engine.run(action)
        except Exception:
            pass
        final = await lifecycle_engine.storage.get_state(action.action_id)
        assert str(final) in SAFE_TERMINAL_STATES


async def test_chaos_ledger_concurrent_appends(event_store, tenant_id):
    """
    Concurrent appends to the ledger must not produce duplicate sequences or
    a broken hash chain. Run 50 concurrent seals and verify integrity.
    """
    import asyncio
    actions = [make_action(f"concurrent.action.{i}") for i in range(50)]
    tasks = [seal_action(a, event_store, tenant_id) for a in actions]
    await asyncio.gather(*tasks)

    # Verify hash chain integrity
    events = await event_store.get_all_events_ordered(tenant_id)
    seqs = [e["global_seq"] for e in events]
    assert seqs == list(range(1, len(seqs) + 1)), (
        "Concurrent appends produced gaps or duplicate sequences — hash chain broken"
    )
```

---

## Performance Baseline Tests (p99 Latency)

These run in CI against a real database (not mocked) and enforce strict latency budgets.
Baselines are measured on the CI runner — thresholds are set with headroom.

```python
# tests/performance/test_seal_latency.py
import asyncio
import time
import pytest
import statistics


# Latency thresholds — p99 in milliseconds
P99_THRESHOLDS = {
    "seal":     200,    # K·02: seal a single action to the TrustLedger
    "evaluate": 50,     # K·01: evaluate a single action through policy engine
    "generate": 2000,   # K·05: full model round-trip (gateway + inference, local Ollama)
}
SAMPLE_SIZE = 100       # number of runs for statistical significance


@pytest.mark.performance
async def test_seal_p99_latency(ledger, tenant_id):
    """p99 latency for seal() must not exceed P99_THRESHOLDS['seal'] ms."""
    latencies = []
    for _ in range(SAMPLE_SIZE):
        entry = make_ledger_entry()
        t0 = time.perf_counter()
        await ledger.seal(entry, tenant_id=tenant_id)
        latencies.append((time.perf_counter() - t0) * 1000)

    p99 = statistics.quantiles(latencies, n=100)[98]   # 99th percentile
    assert p99 <= P99_THRESHOLDS["seal"], (
        f"seal() p99={p99:.1f}ms exceeds threshold {P99_THRESHOLDS['seal']}ms. "
        "This may indicate a missing index or a slow hash computation."
    )


@pytest.mark.performance
async def test_evaluate_p99_latency(policy_engine, tenant_id):
    """p99 latency for evaluate() must not exceed P99_THRESHOLDS['evaluate'] ms."""
    latencies = []
    policies = [make_allow_policy() for _ in range(5)]
    for _ in range(SAMPLE_SIZE):
        action = make_action("test.eval.latency")
        t0 = time.perf_counter()
        await policy_engine.evaluate(action, policies)
        latencies.append((time.perf_counter() - t0) * 1000)

    p99 = statistics.quantiles(latencies, n=100)[98]
    assert p99 <= P99_THRESHOLDS["evaluate"], (
        f"evaluate() p99={p99:.1f}ms exceeds threshold {P99_THRESHOLDS['evaluate']}ms. "
        "CEL evaluation should be sub-millisecond; check for DB calls in hot path."
    )


@pytest.mark.performance
async def test_generate_p99_latency(gateway, tenant_id):
    """p99 latency for generate() must not exceed P99_THRESHOLDS['generate'] ms (local Ollama)."""
    latencies = []
    for _ in range(20):    # fewer iterations — model calls are slow
        action = make_action("test.generate.latency")
        t0 = time.perf_counter()
        await gateway.generate(action=action, prompt="Test prompt.", tenant_id=tenant_id)
        latencies.append((time.perf_counter() - t0) * 1000)

    p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else max(latencies)
    assert p99 <= P99_THRESHOLDS["generate"], (
        f"generate() p99={p99:.1f}ms exceeds threshold {P99_THRESHOLDS['generate']}ms."
    )
```

---

## Tenant Isolation Adversarial Tests

```python
# tests/integration/test_tenant_isolation.py
async def test_action_cannot_access_other_tenant_data(storage, two_tenants):
    tenant_a, tenant_b = two_tenants
    await seed_ledger_entries(tenant_b, count=5, storage=storage)
    set_tenant(tenant_a)
    entries = await storage.execute("SELECT * FROM ledger_entries", tenant_id=tenant_a)
    assert entries == []

async def test_policy_evaluation_uses_only_own_tenant_policies(engine, two_tenants):
    tenant_a, tenant_b = two_tenants
    await seed_policy(tenant_b, decision="allow", governs="*")
    await seed_policy(tenant_a, decision="deny", governs="*")
    set_tenant(tenant_a)
    action = make_action("any.action", tenant_id=tenant_a)
    result = await engine.evaluate(action)
    assert result.decision == "deny"

async def test_rls_blocks_wrong_tenant_context(engine_conn, two_tenants):
    tenant_a, tenant_b = two_tenants
    schema_b = schema_name_for(tenant_b)
    async with engine_conn as conn:
        await conn.execute(f'SET search_path TO "{schema_b}", public')
        await conn.execute("SET app.current_tenant = $1", tenant_a)  # wrong tenant
        rows = await conn.fetch("SELECT * FROM ledger_entries")
    assert rows == []
```

---

## Replay Side-Effect Tests

```python
# tests/integration/test_replay.py
async def test_state_reconstruction_no_side_effects(ledger, effect_tracker, tenant_id):
    entry = await seed_ledger_entry(action_type="loan.disburse",
                                     payload={"loan_id": "L1", "amount": 50000},
                                     tenant_id=tenant_id)
    await reconstruct_state_at(
        aggregate_id=str(entry.action_id),
        target_seq=entry.global_seq,
        tenant_id=tenant_id,
        event_store=ledger.event_store,
        apply_fn=loan_apply_fn,
        initial_state={},
    )
    assert effect_tracker.disbursements == []
    assert effect_tracker.notifications == []


async def test_counterfactual_does_not_write_production_ledger(ledger, tenant_id):
    count_before = await ledger.event_store.count_events(tenant_id)
    await counterfactual_replay(
        tenant_id=tenant_id,
        candidate_policies=[make_allow_policy()],
        time_range=(start, end),
        event_store=ledger.event_store,
        policy_engine=policy_engine,
        shadow_store=InMemoryShadowStore(),
    )
    count_after = await ledger.event_store.count_events(tenant_id)
    assert count_before == count_after
```

---

## Full CI Matrix

```yaml
# .github/workflows/ci.yml (annotated)
name: QUAICU CI

on: [push, pull_request]

jobs:

  # ── Tier 1: Static checks (fastest — < 30s) ───────────────────────────────
  static:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Domain import check (no student/patient/loan in core/)
        run: |
          if grep -r "student\|patient\|loan\|applicant\|invoice" core/; then
            echo "Domain concept found in core/ — violates zero-domain-imports rule"
            exit 1
          fi
      - name: Core SDK import check (no concrete SDK imports in core/)
        run: |
          if grep -r "import openai\|import anthropic\|import temporalio\|import asyncpg\|import boto3" core/; then
            echo "Concrete SDK import found in core/ — violates ports-and-adapters rule"
            exit 1
          fi
      - name: Type checking
        run: mypy core/ adapters/ --strict --ignore-missing-imports

  # ── Tier 2: Unit tests (fast — < 2min, no DB) ─────────────────────────────
  unit:
    runs-on: ubuntu-latest
    needs: static
    steps:
      - uses: actions/checkout@v4
      - name: Unit tests (parallelized)
        run: |
          pytest tests/unit -x -q \
            --cov=core --cov-report=xml \
            -n auto                       # pytest-xdist: one worker per CPU
      - name: Upload coverage
        uses: codecov/codecov-action@v4

  # ── Tier 3: Conformance + property tests (< 10min) ─────────────────────────
  conformance:
    runs-on: ubuntu-latest
    needs: unit
    steps:
      - uses: actions/checkout@v4
      - name: Conformance suites (golden cases from YAML spec)
        run: |
          pytest tests/conformance -x -q \
            --hypothesis-seed=0 \
            -n auto
      - name: Property-based invariant tests
        run: |
          pytest tests/property -x \
            --hypothesis-seed=0 \
            --hypothesis-settings max_examples=500 \
            -n auto
      - name: Coverage thresholds per layer
        run: |
          pytest tests/unit tests/conformance --cov=core/ledger    --cov-fail-under=95 -q
          pytest tests/unit tests/conformance --cov=core/policy    --cov-fail-under=90 -q
          pytest tests/unit tests/conformance --cov=core/lifecycle --cov-fail-under=90 -q

  # ── Tier 4: Integration tests (real DB — < 15min) ──────────────────────────
  integration:
    runs-on: ubuntu-latest
    needs: conformance
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: quaicu_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
    steps:
      - uses: actions/checkout@v4
      - name: Integration tests (isolation, replay, fail-closed)
        run: |
          pytest tests/integration -x -v \
            -n 4                           # 4 workers — each gets its own tenant schema
      - name: Contract tests (adapter → protocol conformance)
        run: pytest tests/contract -x -v

  # ── Tier 5: Chaos tests (< 20min) ──────────────────────────────────────────
  chaos:
    runs-on: ubuntu-latest
    needs: integration
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v4
      - name: Chaos tests (random fault injection — 50 seeds)
        run: |
          pytest tests/chaos -v \
            --timeout=120 \
            -n 4

  # ── Tier 6: Mutation + performance (on main branch only) ───────────────────
  mutation:
    runs-on: ubuntu-latest
    needs: integration
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Mutation testing — ledger (≤5% surviving)
        run: |
          mutmut run --paths-to-mutate core/ledger/ --use-coverage
          python scripts/check_mutation_score.py --module core/ledger/ --max-surviving-pct 5
      - name: Mutation testing — policy engine (≤10% surviving)
        run: |
          mutmut run --paths-to-mutate core/policy/ --use-coverage
          python scripts/check_mutation_score.py --module core/policy/ --max-surviving-pct 10
      - name: Mutation testing — lifecycle (≤10% surviving)
        run: |
          mutmut run --paths-to-mutate core/lifecycle/ --use-coverage
          python scripts/check_mutation_score.py --module core/lifecycle/ --max-surviving-pct 10

  performance:
    runs-on: ubuntu-latest
    needs: integration
    if: github.ref == 'refs/heads/main'
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
    steps:
      - uses: actions/checkout@v4
      - name: Performance baselines (p99 thresholds)
        run: |
          pytest tests/performance -v -m performance \
            --timeout=300
```

---

## Parallelized Test Execution Config

```ini
# pytest.ini (or pyproject.toml)
[pytest]
asyncio_mode      = auto
timeout           = 60
markers =
    performance: Performance baseline tests — requires real DB and Ollama
    chaos:       Chaos tests — slow, non-deterministic
    contract:    Contract tests — adapter Protocol conformance

addopts =
    --strict-markers
    --tb=short
    -q

# For parallel runs (pytest-xdist):
# pytest tests/unit -n auto         → one worker per logical CPU
# pytest tests/integration -n 4     → 4 workers (each isolated by tenant schema)
# pytest tests/conformance -n auto
```

```toml
# pyproject.toml — xdist configuration
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers      = [
    "performance: requires real DB and inference backend",
    "chaos: fault injection — non-deterministic by design",
    "contract: adapter protocol conformance",
]

# tests/conftest.py — ensure each xdist worker gets its own tenant namespace
# so parallel integration tests don't share DB state

[tool.pytest-xdist]
# Each worker gets a unique suffix appended to tenant_id fixtures
# preventing cross-worker interference
```

```python
# tests/conftest.py
import os
import pytest
import asyncio

# xdist: each worker gets a unique ID (gw0, gw1, ...) to namespace tenant fixtures
_WORKER_ID = os.environ.get("PYTEST_XDIST_WORKER", "gw0")


@pytest.fixture
def tenant_id() -> str:
    """Unique tenant_id per test + worker to prevent cross-test interference."""
    import uuid
    return f"test_{_WORKER_ID}_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def two_tenants(tenant_id) -> tuple[str, str]:
    return f"{tenant_id}_a", f"{tenant_id}_b"


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the session (required for async fixtures)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
```

---

## Published Test Vectors (RFC 6962)

```json
// tests/vectors/ledger_vectors.json
// These are authoritative. Any change to the Merkle implementation must
// produce matching output for every vector below. If a vector fails, the
// implementation is wrong — not the vector.
{
  "spec": "RFC 6962",
  "description": "Test vectors for QUAICU TrustLedger Merkle implementation",
  "merkle_roots": [
    {
      "id": "TV-01",
      "description": "Empty tree",
      "leaves": [],
      "expected_root": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    },
    {
      "id": "TV-02",
      "description": "Single leaf 'abc'",
      "leaves": ["616263"],
      "expected_root": "2e7d2c03a9507ae265ecf5b5356885a53393a2029d241394997265a1a25aefc6"
    },
    {
      "id": "TV-03",
      "description": "Two leaves 'abc', 'def'",
      "leaves": ["616263", "646566"],
      "expected_root": "d6f5a6..."
    }
  ],
  "inclusion_proofs": [
    {
      "id": "TV-IP-01",
      "leaf_index": 0,
      "tree_size": 3,
      "leaves": ["616263", "646566", "676869"],
      "audit_path": ["..."],
      "root": "..."
    }
  ],
  "consistency_proofs": [
    {
      "id": "TV-CP-01",
      "old_size": 2,
      "new_size": 4,
      "leaves": ["616263", "646566", "676869", "6a6b6c"],
      "proof": ["..."],
      "old_root": "...",
      "new_root": "..."
    }
  ]
}
```

---

## Anti-Patterns — Never Do These in Tests

```python
# ╳ ANTI-PATTERN 1 — golden cases derived from implementation, not spec
# Tests must fail first (red) then pass (green). Never write the test after
# running the code and copying the output as the expected value.

# ╳ ANTI-PATTERN 2 — mocking the storage layer in integration tests
# Integration tests must use a real DB. Mocking the storage in integration tests
# defeats the purpose and hides schema/query bugs.

# ╳ ANTI-PATTERN 3 — not testing fail-closed for every external dependency
# If a layer calls an external service, there must be a test for:
# (a) service down, (b) timeout, (c) returns None/unexpected type.

# ╳ ANTI-PATTERN 4 — shared tenant state across parallel test workers
# Each test must use a unique tenant_id via the fixture — never hardcode "tenant_test"
# in integration tests that run with -n auto.

# ╳ ANTI-PATTERN 5 — performance tests with mocked I/O
# Latency tests must run against a real DB (and real inference for gateway tests).
# Mocked latency is meaningless.

# ╳ ANTI-PATTERN 6 — skipping mutation testing on ledger/policy/lifecycle
# These are the three most critical modules. Surviving mutations in these modules
# are potential security gaps, not just coverage gaps.

# ╳ ANTI-PATTERN 7 — using @pytest.mark.skip instead of fixing a flaky test
# A skipped test contributes zero to the DoD checklist. Fix the test.
```

---

## Checklist Before Marking a Layer Done

- [ ] Conformance suite: golden cases from YAML spec, not from implementation; cases reviewed
      by a second engineer
- [ ] Property tests: Hypothesis for all Core Invariants relevant to this layer
      (determinism, totality, fail-closed, isolation, idempotency)
- [ ] Fail-closed: at least one test per external dependency (down, timeout, None return, wrong type)
- [ ] Tenant isolation: adversarial test — tenant A cannot read tenant B's data under any code path
- [ ] Replay: side-effect-free replay test if layer touches state or lifecycle
- [ ] Contract: all adapters for this layer's port pass `assert_implements_protocol`
- [ ] Chaos: at least 10 random-seed fault injections for lifecycle-touching layers
- [ ] Performance: p99 latency within threshold for seal(), evaluate(), generate()
      (skip for layers that don't participate in hot path)
- [ ] Mutation score meets threshold for this layer (see coverage table above)
- [ ] CI grep checks: no domain imports in `core/`, no SDK imports in `core/`
- [ ] Test vectors published in `tests/vectors/` for RFC 6962 (K·02 only)
- [ ] OTel emission verified: integration test asserts spans and metrics were emitted
- [ ] All tests pass in parallelized mode: `pytest tests/ -n auto --timeout=60`
