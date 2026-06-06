---
name: python-testing
description: Expert in Python testing with pytest and test-driven development. QUAICU kernel — fail-closed fake adapters, fault-injection tests proving DENIED/HALTED, conformance suites against port contracts, adversarial tenant-isolation and replay side-effect tests, per-layer coverage floors. Triggers — QUAICU, conformance, fail-closed test, fault injection, FAIL_OPEN_DETECTED, coverage floor, fixture factory.
---

# Python Testing

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific test choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.** Missing rule → add the stricter test.

### Invariants — never violated
- Fake port adapters default to FAIL-CLOSED (raise/deny), not happy-path success. A test only proves fail-closed if it INJECTS a fault and asserts DENIED/HALTED.
- An action allowed through under a fault is `FAIL_OPEN_DETECTED` — the most critical failure; it blocks merge.
- Tenant isolation is tested ADVERSARIALLY (attempt cross-tenant read → assert impossible).
- Replay tests spy on ports and assert ZERO external calls / live writes.
- Per-layer coverage floors are CI-enforced: ledger 95%; policy / lifecycle / consent / tenant 90%.

### Decision table — which tier
| Verifying… | Tier / tool |
|---|---|
| one function/branch | unit (pytest) |
| adapter ↔ port contract | conformance (subclass the port base suite) |
| invariant for all inputs | property (Hypothesis) |
| against real Postgres | integration |
| behavior under faults | chaos (fault injection) |
| p99 latency | performance |

### Tie-break rules
- Assert allow or deny under a fault? → DENIED/HALTED. An allow-through is a test bug.
- Happy-path only? → not done; add fault-injection + adversarial cases.

### Self-check
- [ ] Fakes fail closed by default; faults injected to prove it.
- [ ] Isolation tested adversarially; replay asserts no side effects.
- [ ] Property tests cover Core Invariants.
- [ ] Coverage meets per-layer floors.

---

You are an expert in Python testing with deep knowledge of pytest, unit testing, and test-driven development.

## Core Principles

- Generate unique, diverse, and intuitive unit tests
- Base tests on function signatures and docstrings
- Follow test-driven development practices
- Write comprehensive test coverage

## Test Structure

- Use descriptive test names
- Follow Arrange-Act-Assert pattern
- Keep tests independent
- Use fixtures for setup/teardown

## pytest Best Practices

- Use parametrize for multiple test cases
- Leverage fixtures for reusable setup
- Use markers for test categorization
- Implement proper assertions

## Test Types

### Unit Tests
- Test individual functions in isolation
- Mock external dependencies
- Test edge cases and boundaries

### Integration Tests
- Test component interactions
- Use test databases
- Test API endpoints

### Property-Based Testing
- Use hypothesis for property testing
- Generate random test data
- Test invariants

## Mocking

- Use unittest.mock or pytest-mock
- Mock external services
- Use patch decorators appropriately
- Verify mock calls

## Coverage

- Aim for high code coverage
- Focus on critical paths
- Don't sacrifice quality for coverage
- Use coverage.py for reporting

---

# QUAICU Governance Kernel — pytest Testing Guide

This section covers the complete testing infrastructure for the QUAICU governance kernel. Because there is no prior implementation to diff against, **correctness is established exclusively by rigorous spec-driven testing**. Every layer ships with a conformance suite, property-based invariant tests, and fail-closed fault injection tests before it is considered done.

## 1. pytest + pytest-asyncio Configuration

### pyproject.toml / pytest.ini configuration

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"           # all async test functions run under anyio automatically
testpaths = ["tests"]
addopts = [
    "--strict-markers",         # unregistered markers are errors, not warnings
    "--tb=short",
    "--no-header",
    "-q",
]
markers = [
    "conformance: spec-derived acceptance tests for a single kernel layer",
    "property: hypothesis-driven invariant tests",
    "integration: tests that require a live PostgreSQL instance",
    "chaos: fault-injection tests that verify fail-closed behaviour",
    "slow: tests that take > 5 seconds (excluded from default run)",
    "tenant_isolation: adversarial cross-tenant leakage tests",
]

[tool.pytest-asyncio]
asyncio_mode = "auto"

[tool.coverage.run]
source = ["core", "adapters"]
omit = ["tests/*", "migrations/*"]
branch = true

[tool.coverage.report]
fail_under = 90
show_missing = true
```

### conftest.py — top-level structure

The root conftest sets up the entire test infrastructure. Place it at `tests/conftest.py`.

```python
# tests/conftest.py
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio

# ── event-loop policy (one loop per session) ──────────────────────────────────
@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


# ── fake time provider ─────────────────────────────────────────────────────────
@pytest.fixture()
def frozen_clock(monkeypatch):
    """
    Deterministic time provider for policy evaluation tests.

    Core invariant: identical inputs → identical policy decision.
    Policy CEL has no access to wall-clock, but the lifecycle spine uses time
    for ledger sequencing. Replace it everywhere with a controllable fake.
    """
    return FakeClock(initial=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc))


class FakeClock:
    """Controllable clock for determinism testing."""

    def __init__(self, initial: datetime):
        self._now = initial

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        from datetime import timedelta
        self._now += timedelta(seconds=seconds)

    def set(self, dt: datetime) -> None:
        self._now = dt
```

### Per-test database schema isolation

Every test that touches the database runs inside a transaction that is rolled back at the end of the test. This guarantees zero state leakage between tests and avoids the need to truncate tables.

```python
# tests/conftest.py (continued)
import asyncpg

DATABASE_URL = "postgresql://quaicu_test:quaicu_test@localhost:5432/quaicu_test"


@pytest.fixture(scope="session")
async def db_pool() -> AsyncGenerator[asyncpg.Pool, None]:
    """Session-scoped connection pool. Schema is created once per session."""
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    async with pool.acquire() as conn:
        await _apply_kernel_schema(conn)
    yield pool
    await pool.close()


@pytest.fixture()
async def db_conn(db_pool: asyncpg.Pool) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Per-test isolated database connection.

    Wraps each test in a SAVEPOINT so the outer transaction rolls back
    on teardown — no truncation, no migration re-run, ~1 ms teardown.
    """
    async with db_pool.acquire() as conn:
        tr = conn.transaction()
        await tr.start()
        try:
            yield conn
        finally:
            await tr.rollback()


async def _apply_kernel_schema(conn: asyncpg.Connection) -> None:
    """Run Alembic migrations or raw DDL for the test DB.  Called once per session."""
    import subprocess
    subprocess.run(
        ["alembic", "upgrade", "head"],
        env={"DATABASE_URL": DATABASE_URL},
        check=True,
    )
```

---

## 2. Fake Adapter Implementations for All Five Ports

All five port adapters are in-memory fakes. They implement the exact same `typing.Protocol` contract as the real adapters. Core never imports real adapters during unit/conformance tests.

### FakeInferenceAdapter

```python
# tests/fakes/inference.py
from __future__ import annotations

from dataclasses import dataclass, field
from core.ports.inference import InferencePort, Prompt, ModelRef, ModelResponse, TenantId


@dataclass
class FakeInferenceAdapter:
    """
    Deterministic fake for InferencePort.

    Pre-programme responses per (model_ref, prompt_hash). Unknown combinations
    raise — enforcing fail-closed: no permissive default.
    """
    _responses: dict[tuple[str, str], ModelResponse] = field(default_factory=dict)
    _calls: list[dict] = field(default_factory=list)

    def register(self, model_ref: str, prompt_content: str, response: ModelResponse) -> None:
        import hashlib
        key = (model_ref, hashlib.sha256(prompt_content.encode()).hexdigest())
        self._responses[key] = response

    async def generate(
        self,
        *,
        prompt: Prompt,
        model_ref: ModelRef,
        tenant: TenantId,
    ) -> ModelResponse:
        import hashlib
        key = (str(model_ref), hashlib.sha256(str(prompt).encode()).hexdigest())
        self._calls.append({"model_ref": model_ref, "tenant": tenant, "prompt": prompt})
        if key not in self._responses:
            raise RuntimeError(
                f"FakeInferenceAdapter: no registered response for model={model_ref}. "
                "Fail-closed: unknown inference request → error."
            )
        return self._responses[key]

    @property
    def call_count(self) -> int:
        return len(self._calls)

    def assert_called_with_tenant(self, tenant: TenantId) -> None:
        tenants_seen = {c["tenant"] for c in self._calls}
        assert tenant in tenants_seen, f"Expected call with tenant {tenant!r}, saw {tenants_seen}"
```

### FakeHITLAdapter

```python
# tests/fakes/hitl.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from core.ports.hitl import HITLPort, ApprovalHandle, ApprovalDecision, Action, ApproverRef, TenantId


class ApprovalOutcome(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PENDING = "PENDING"


@dataclass
class FakeHITLAdapter:
    """
    Pre-configured HITL fake.

    Default outcome is PENDING — tests that need approval must explicitly set it.
    A timeout or missing configuration raises, honoring fail-closed.
    """
    _outcomes: dict[str, ApprovalOutcome] = field(default_factory=dict)
    _requests: list[dict] = field(default_factory=list)
    _handle_counter: int = 0

    def set_outcome(self, action_type: str, outcome: ApprovalOutcome) -> None:
        self._outcomes[action_type] = outcome

    async def request_approval(
        self,
        *,
        action: Action,
        approvers: list[ApproverRef],
        tenant: TenantId,
    ) -> ApprovalHandle:
        self._handle_counter += 1
        handle = ApprovalHandle(id=f"hitl-handle-{self._handle_counter}", action_id=str(action.id))
        self._requests.append({"action": action, "approvers": approvers, "tenant": tenant, "handle": handle})
        return handle

    async def poll(self, handle: ApprovalHandle) -> ApprovalDecision:
        # look up by action type of the corresponding request
        matching = [r for r in self._requests if r["handle"].id == handle.id]
        if not matching:
            raise RuntimeError(f"FakeHITLAdapter: unknown handle {handle.id!r} — fail-closed.")
        action = matching[0]["action"]
        outcome = self._outcomes.get(action.type, ApprovalOutcome.PENDING)
        return ApprovalDecision(status=outcome.value, handle=handle)

    @property
    def pending_count(self) -> int:
        return sum(
            1 for r in self._requests
            if self._outcomes.get(r["action"].type, ApprovalOutcome.PENDING) == ApprovalOutcome.PENDING
        )
```

### FakeIdentityAdapter

```python
# tests/fakes/identity.py
from __future__ import annotations

from dataclasses import dataclass, field
from core.ports.identity import IdentityPort, Actor, RequestContext, TenantId


@dataclass
class FakeIdentityAdapter:
    """
    Maps (tenant_id, token) → Actor. Unknown tokens raise — fail-closed.
    """
    _registry: dict[tuple[str, str], Actor] = field(default_factory=dict)

    def register(self, tenant: str, token: str, actor: Actor) -> None:
        self._registry[(tenant, token)] = actor

    async def resolve_actor(
        self,
        *,
        context: RequestContext,
        tenant: TenantId,
    ) -> Actor:
        key = (str(tenant), str(context.token))
        if key not in self._registry:
            raise PermissionError(
                f"FakeIdentityAdapter: unrecognised token for tenant {tenant!r}. "
                "Fail-closed: unknown identity → deny."
            )
        return self._registry[key]
```

### FakeStorageAdapter

```python
# tests/fakes/storage.py
from __future__ import annotations

from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from core.ports.storage import StoragePort, Transaction


class InMemoryTransaction:
    """Simple in-memory transaction with rollback support."""

    def __init__(self, store: dict[str, Any]) -> None:
        self._store = store
        self._pending: dict[str, Any] = {}
        self._deletes: set[str] = set()
        self._committed = False

    def put(self, key: str, value: Any) -> None:
        self._pending[key] = value

    def get(self, key: str) -> Any:
        if key in self._deletes:
            return None
        return self._pending.get(key, self._store.get(key))

    def delete(self, key: str) -> None:
        self._deletes.add(key)
        self._pending.pop(key, None)

    def commit(self) -> None:
        self._store.update(self._pending)
        for k in self._deletes:
            self._store.pop(k, None)
        self._committed = True

    def rollback(self) -> None:
        self._pending.clear()
        self._deletes.clear()


@dataclass
class FakeStorageAdapter:
    """Thread-safe, transactional in-memory store."""

    _store: dict[str, Any] = field(default_factory=dict)

    @asynccontextmanager
    async def transaction(self):
        txn = InMemoryTransaction(self._store)
        try:
            yield txn
            txn.commit()
        except Exception:
            txn.rollback()
            raise

    def get_direct(self, key: str) -> Any:
        return self._store.get(key)

    def all_keys(self) -> list[str]:
        return list(self._store.keys())
```

### FakeWorkflowAdapter

```python
# tests/fakes/workflow.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from core.ports.workflow import WorkflowPort, ProcessDef, WorkflowHandle, Signal, ProcessState, TenantId


class FakeProcessState(str, Enum):
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    HALTED = "HALTED"


@dataclass
class FakeWorkflowAdapter:
    """
    In-memory workflow engine. Supports signal delivery and state inspection.

    Defaults to fail-closed: a workflow that errors moves to HALTED.
    """
    _workflows: dict[str, dict] = field(default_factory=dict)
    _handle_counter: int = 0
    _signal_log: list[dict] = field(default_factory=list)

    async def start(
        self,
        *,
        definition: ProcessDef,
        payload: dict,
        tenant: TenantId,
    ) -> WorkflowHandle:
        self._handle_counter += 1
        wf_id = f"wf-{self._handle_counter}"
        self._workflows[wf_id] = {
            "definition": definition,
            "payload": payload,
            "tenant": tenant,
            "state": FakeProcessState.RUNNING,
        }
        return WorkflowHandle(id=wf_id)

    async def signal(self, handle: WorkflowHandle, signal: Signal) -> None:
        if handle.id not in self._workflows:
            raise KeyError(f"FakeWorkflowAdapter: unknown workflow {handle.id!r}")
        self._signal_log.append({"handle": handle.id, "signal": signal})
        wf = self._workflows[handle.id]
        if signal.type == "APPROVE":
            wf["state"] = FakeProcessState.COMPLETED
        elif signal.type == "REJECT":
            wf["state"] = FakeProcessState.HALTED
        elif signal.type == "PAUSE":
            wf["state"] = FakeProcessState.WAITING_APPROVAL

    async def state(self, handle: WorkflowHandle) -> ProcessState:
        if handle.id not in self._workflows:
            raise KeyError(f"FakeWorkflowAdapter: unknown workflow {handle.id!r}")
        raw = self._workflows[handle.id]["state"]
        return ProcessState(status=raw.value)

    def workflow_count_for_tenant(self, tenant: TenantId) -> int:
        return sum(1 for wf in self._workflows.values() if wf["tenant"] == tenant)
```

### Fixture wiring all fakes together

```python
# tests/conftest.py (continued)
from tests.fakes.inference import FakeInferenceAdapter
from tests.fakes.hitl import FakeHITLAdapter
from tests.fakes.identity import FakeIdentityAdapter
from tests.fakes.storage import FakeStorageAdapter
from tests.fakes.workflow import FakeWorkflowAdapter


@pytest.fixture()
def fake_inference():
    return FakeInferenceAdapter()

@pytest.fixture()
def fake_hitl():
    return FakeHITLAdapter()

@pytest.fixture()
def fake_identity():
    return FakeIdentityAdapter()

@pytest.fixture()
def fake_storage():
    return FakeStorageAdapter()

@pytest.fixture()
def fake_workflow():
    return FakeWorkflowAdapter()


@pytest.fixture()
def kernel_ports(fake_inference, fake_hitl, fake_identity, fake_storage, fake_workflow):
    """Convenience bundle of all five fake ports for integration-style tests."""
    from core.ports import Ports
    return Ports(
        inference=fake_inference,
        hitl=fake_hitl,
        identity=fake_identity,
        storage=fake_storage,
        workflow=fake_workflow,
    )
```

---

## 3. Async Fixture Patterns

pytest-asyncio `asyncio_mode = "auto"` means all `async def` fixtures and test functions run automatically. Use `scope` to control lifecycle.

```python
# Session-scoped async fixture (DB pool — expensive to create)
@pytest_asyncio.fixture(scope="session")
async def db_pool():
    pool = await asyncpg.create_pool(DATABASE_URL)
    yield pool
    await pool.close()

# Function-scoped async fixture (per-test transaction)
@pytest_asyncio.fixture()
async def txn(db_pool):
    async with db_pool.acquire() as conn:
        tr = conn.transaction()
        await tr.start()
        yield conn
        await tr.rollback()

# Async fixture with parametrize
@pytest_asyncio.fixture(params=["tenant-alpha", "tenant-beta", "tenant-gamma"])
async def tenant_id(request):
    return request.param
```

---

## 4. Test Markers — Registration and Use

All markers declared in `pyproject.toml` under `[tool.pytest.ini_options].markers`. Running subsets:

```bash
# Only conformance suite (fast, no DB)
pytest -m conformance

# Fail-closed chaos tests only
pytest -m chaos

# Tenant-isolation adversarial suite
pytest -m tenant_isolation

# Full CI run (excludes slow)
pytest -m "not slow"

# Property tests with extended max_examples
pytest -m property --hypothesis-seed=0
```

---

## 5. Conformance Suite Structure

Each kernel layer has its own conformance module. Structure follows the spec's Definition of Done.

```
tests/
├── conformance/
│   ├── conftest.py          # shared fixtures for conformance tests
│   ├── test_k01_policy.py   # Policy Engine acceptance tests
│   ├── test_k02_ledger.py   # TrustLedger acceptance tests
│   ├── test_k03_hitl.py     # HITL / gate acceptance tests
│   ├── test_k04_consent.py
│   ├── test_k05_gateway.py
│   ├── test_k06_process.py
│   └── test_k07_events.py
├── property/
│   ├── test_ledger_invariants.py
│   ├── test_policy_determinism.py
│   └── test_tenant_isolation.py
├── integration/
│   └── test_lifecycle_end_to_end.py
└── chaos/
    ├── test_inference_down.py
    ├── test_storage_timeout.py
    └── test_hitl_timeout.py
```

---

## 6. Testing Fail-Closed Behaviour

### Pattern 1: Dependency down → DENY

```python
import pytest
from core.lifecycle import propose_action
from core.models import Action, ActionState

@pytest.mark.chaos
async def test_inference_port_failure_denies_action(kernel_ports, frozen_clock):
    """
    Core invariant: any failure at any lifecycle step → DENY/HALT, never proceed.
    When InferencePort raises, the action must be denied — not allowed through.
    """
    # Arrange: make inference always fail
    async def failing_generate(**kwargs):
        raise ConnectionError("Inference service unreachable")

    kernel_ports.inference.generate = failing_generate

    action = Action(
        type="ciro.ifrs9.stage_transition",
        payload={"loan_id": "123", "from_stage": 1, "to_stage": 2},
        actor_token="valid-token",
        tenant_id="tenant-alpha",
    )

    # Act + Assert: exception raised, state is DENIED
    with pytest.raises(Exception):
        await propose_action(action, ports=kernel_ports, clock=frozen_clock)

    # Verify: if the kernel records the attempt, it must be DENIED
    stored = kernel_ports.storage.get_direct(f"action:{action.id}")
    if stored is not None:
        assert stored["state"] in (ActionState.DENIED, ActionState.HALTED), (
            f"Action reached state {stored['state']!r} instead of DENIED/HALTED "
            "after inference failure — fail-closed violated."
        )


@pytest.mark.chaos
async def test_policy_evaluation_timeout_denies_action(kernel_ports, frozen_clock, monkeypatch):
    """Policy Engine timeout → DENY. Never allow on uncertainty."""
    import asyncio
    from core.policy import evaluate

    async def timing_out(*args, **kwargs):
        raise asyncio.TimeoutError("CEL evaluation timed out")

    monkeypatch.setattr("core.policy.evaluate", timing_out)

    action = Action(
        type="test.any_action",
        payload={},
        actor_token="valid-token",
        tenant_id="tenant-alpha",
    )

    with pytest.raises((asyncio.TimeoutError, PermissionError, RuntimeError)):
        await propose_action(action, ports=kernel_ports, clock=frozen_clock)
```

### Pattern 2: HITL timeout → HALT, not approve

```python
@pytest.mark.chaos
async def test_hitl_timeout_halts_action(fake_hitl, fake_storage):
    """
    A HITL timeout must never resolve to APPROVED.
    Fail-closed: no human decision within the timeout window → HALTED.
    """
    from core.hitl import wait_for_approval
    from core.models import ApprovalDecision

    async def always_timeout(handle):
        import asyncio
        raise asyncio.TimeoutError("HITL approval window expired")

    fake_hitl.poll = always_timeout

    from core.models import Action, ApprovalHandle
    handle = ApprovalHandle(id="h-001", action_id="a-001")

    with pytest.raises(Exception):  # must raise, not return APPROVED
        await wait_for_approval(handle, hitl_port=fake_hitl, timeout_seconds=1)
```

### Pattern 3: assert state is DENIED/HALTED helper

```python
# tests/utils/assertions.py

def assert_action_denied(storage: FakeStorageAdapter, action_id: str) -> None:
    """Assert that a given action is in a terminal denied/halted state."""
    from core.models import ActionState
    record = storage.get_direct(f"action:{action_id}")
    assert record is not None, f"No storage record for action {action_id!r}"
    assert record["state"] in (ActionState.DENIED, ActionState.HALTED), (
        f"Expected action {action_id!r} to be DENIED or HALTED, "
        f"got {record['state']!r}. Fail-closed invariant violated."
    )

def assert_no_ledger_entry(storage: FakeStorageAdapter, action_id: str) -> None:
    """Assert that a denied/halted action was NOT sealed into the ledger."""
    record = storage.get_direct(f"ledger:{action_id}")
    assert record is None, (
        f"Action {action_id!r} was sealed into the ledger despite being denied. "
        "No-bypass invariant violated."
    )
```

---

## 7. Ledger Entry Verification Utilities

```python
# tests/utils/ledger.py
from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_leaf_hash(entry: dict[str, Any]) -> bytes:
    """
    Recompute the RFC 6962-style leaf hash for an entry.
    leaf_hash = SHA-256(0x00 || entry_json_canonical)
    """
    canonical = json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(b"\x00" + canonical).digest()


def verify_inclusion_proof(
    *,
    leaf_hash: bytes,
    proof_path: list[bytes],
    root_hash: bytes,
    leaf_index: int,
    tree_size: int,
) -> bool:
    """
    Verify an RFC 6962 inclusion proof.
    Returns True if the leaf at leaf_index is included in the tree with root_hash.
    """
    node = leaf_hash
    index = leaf_index
    size = tree_size

    for sibling in proof_path:
        if index % 2 == 0:
            node = hashlib.sha256(b"\x01" + node + sibling).digest()
        else:
            node = hashlib.sha256(b"\x01" + sibling + node).digest()
        index //= 2
        size = (size + 1) // 2

    return node == root_hash


def assert_ledger_entry_sealed(
    storage,
    action_id: str,
    *,
    verify_proof: bool = True,
) -> dict:
    """
    Assert that a ledger entry exists for action_id and that its inclusion proof verifies.
    Returns the entry for further assertions.
    """
    entry = storage.get_direct(f"ledger:{action_id}")
    assert entry is not None, f"Expected ledger entry for action {action_id!r} — not found."

    required_fields = {"action_id", "actor", "tenant_id", "policy_versions", "result",
                       "timestamp", "leaf_hash", "tree_size", "leaf_index", "proof_path", "root_hash"}
    missing = required_fields - set(entry.keys())
    assert not missing, f"Ledger entry missing required fields for replay: {missing}"

    if verify_proof:
        leaf = bytes.fromhex(entry["leaf_hash"])
        proof = [bytes.fromhex(p) for p in entry["proof_path"]]
        root = bytes.fromhex(entry["root_hash"])
        valid = verify_inclusion_proof(
            leaf_hash=leaf,
            proof_path=proof,
            root_hash=root,
            leaf_index=entry["leaf_index"],
            tree_size=entry["tree_size"],
        )
        assert valid, (
            f"RFC 6962 inclusion proof for action {action_id!r} failed to verify. "
            "Ledger immutability invariant violated."
        )

    return entry


def assert_entry_contains_replay_inputs(entry: dict) -> None:
    """
    Assert that the ledger entry captures enough to reconstruct the decision.
    Per spec §3.13: inputs + results must be recorded, not just outcomes.
    """
    assert entry.get("action_payload"), "Ledger entry missing action_payload — not replayable."
    assert entry.get("policy_versions"), "Ledger entry missing policy_versions — not replayable."
    assert "evaluation_result" in entry, "Ledger entry missing evaluation_result."
    assert "consent_state" in entry, "Ledger entry missing consent_state."
```

---

## 8. Parametrised Test Patterns

```python
# tests/conformance/test_k01_policy.py
import pytest
from core.policy import evaluate_policy
from core.models import Action, PolicyDecision

# Golden cases derived directly from the policy envelope spec
POLICY_GOLDEN_CASES = [
    pytest.param(
        {"loan_id": "L001", "from_stage": 1, "to_stage": 2, "exposure": 6_000_000},
        PolicyDecision.REQUIRE_APPROVAL,
        id="high-exposure-stage-up-requires-approval",
    ),
    pytest.param(
        {"loan_id": "L002", "from_stage": 1, "to_stage": 2, "exposure": 4_000_000},
        PolicyDecision.ALLOW,
        id="low-exposure-stage-up-allows",
    ),
    pytest.param(
        {"loan_id": "L003", "from_stage": 2, "to_stage": 1, "exposure": 9_000_000},
        PolicyDecision.DENY,
        id="stage-downgrade-always-denied",
    ),
]

@pytest.mark.conformance
@pytest.mark.parametrize("payload,expected_decision", POLICY_GOLDEN_CASES)
async def test_policy_golden_cases(payload, expected_decision, fake_storage, frozen_clock):
    action = Action(
        type="ciro.ifrs9.stage_transition",
        payload=payload,
        actor_token="system",
        tenant_id="tenant-bank",
    )
    result = await evaluate_policy(action, storage=fake_storage, clock=frozen_clock)
    assert result.decision == expected_decision, (
        f"Policy golden case mismatch for payload {payload}: "
        f"expected {expected_decision!r}, got {result.decision!r}"
    )
```

---

## 9. Idempotency Key Testing

```python
@pytest.mark.conformance
async def test_duplicate_idempotency_key_does_not_double_execute(kernel_ports, frozen_clock):
    """
    Core invariant: re-submitting the same proposal (same idempotency_key) must
    not double-execute, double-seal, or double-emit.
    """
    from core.lifecycle import propose_action
    from core.models import Action

    action = Action(
        type="test.idempotent_action",
        payload={"value": 42},
        actor_token="valid-actor",
        tenant_id="tenant-alpha",
        idempotency_key="idem-key-001",
    )

    # First proposal — should execute and seal
    result_1 = await propose_action(action, ports=kernel_ports, clock=frozen_clock)

    # Second proposal with same key — must return same result, no second execution
    result_2 = await propose_action(action, ports=kernel_ports, clock=frozen_clock)

    assert result_1.action_id == result_2.action_id, "Idempotency key must map to same action."

    # Verify only one ledger entry sealed
    ledger_entries = [
        k for k in kernel_ports.storage.all_keys()
        if k.startswith("ledger:") and action.idempotency_key in k
    ]
    assert len(ledger_entries) == 1, (
        f"Expected 1 ledger entry for idempotency key, found {len(ledger_entries)}. "
        "Idempotency invariant violated."
    )
```

---

## 10. Tenant Isolation Testing

```python
@pytest.mark.tenant_isolation
async def test_tenant_alpha_cannot_read_tenant_beta_actions(kernel_ports, frozen_clock):
    """
    Core invariant: no data, decision, policy, or ledger entry crosses a tenant boundary.
    """
    from core.lifecycle import propose_action, list_actions
    from core.models import Action

    # Register two separate actors for two separate tenants
    kernel_ports.identity.register("tenant-alpha", "token-alpha", Actor(id="user-A", roles=["actor"]))
    kernel_ports.identity.register("tenant-beta", "token-beta", Actor(id="user-B", roles=["actor"]))

    action_alpha = Action(
        type="test.sensitive_action",
        payload={"secret": "alpha-secret"},
        actor_token="token-alpha",
        tenant_id="tenant-alpha",
    )
    action_beta = Action(
        type="test.sensitive_action",
        payload={"secret": "beta-secret"},
        actor_token="token-beta",
        tenant_id="tenant-beta",
    )

    await propose_action(action_alpha, ports=kernel_ports, clock=frozen_clock)
    await propose_action(action_beta, ports=kernel_ports, clock=frozen_clock)

    # alpha's view must not include beta's actions
    alpha_actions = await list_actions(tenant_id="tenant-alpha", ports=kernel_ports)
    alpha_payloads = [a["payload"].get("secret") for a in alpha_actions]
    assert "beta-secret" not in alpha_payloads, (
        "Tenant isolation violated: tenant-alpha's action list contains tenant-beta's payload."
    )
```

---

## 11. Replay Safety Testing

```python
@pytest.mark.conformance
async def test_replay_does_not_cause_side_effects(kernel_ports, frozen_clock):
    """
    Core invariant: replay reconstructs or re-evaluates; it NEVER re-performs external effects.
    """
    from core.ledger import replay_action
    side_effect_calls = []

    async def side_effecting_execute(action, **kwargs):
        side_effect_calls.append(action.id)

    # Seal a real action with a recorded side effect
    from core.models import Action, LedgerEntry
    entry = LedgerEntry(
        action_id="action-replay-test",
        action_type="test.action",
        recorded_result={"approved": True},
        side_effects_recorded=["side-effect-was-done"],
    )
    kernel_ports.storage._store["ledger:action-replay-test"] = entry.dict()

    # Replay must not call side_effecting_execute
    await replay_action(
        action_id="action-replay-test",
        storage=kernel_ports.storage,
        execute_fn=side_effecting_execute,
    )

    assert len(side_effect_calls) == 0, (
        "Replay triggered a side effect. Replay-safe invariant violated."
    )
```

---

## 12. No-Bypass Invariant Testing

```python
@pytest.mark.conformance
async def test_admin_action_still_goes_through_evaluation(kernel_ports, frozen_clock):
    """
    Frozen ADR F-04: No bypass — governance is total. Even admin actions are governed.
    There is no fast-path that skips the kernel.
    """
    from core.lifecycle import propose_action
    from core.models import Action

    # An action with admin-level actor must still be evaluated
    kernel_ports.identity.register(
        "tenant-alpha", "admin-token",
        Actor(id="admin-user", roles=["admin", "superuser"])
    )

    evaluation_calls = []
    original_evaluate = kernel_ports.storage.get_direct  # track via storage reads

    action = Action(
        type="kernel.admin.override",
        payload={"override": True},
        actor_token="admin-token",
        tenant_id="tenant-alpha",
    )

    # Even if the action is denied, the point is that evaluate was called
    try:
        await propose_action(action, ports=kernel_ports, clock=frozen_clock)
    except Exception:
        pass  # Denial is fine; skipping evaluation is not.

    # Verify evaluation was invoked (policy must be consulted for admin actions)
    # Implementation: check that a policy evaluation record exists in storage
    eval_record = kernel_ports.storage.get_direct(f"eval:{action.id}")
    assert eval_record is not None, (
        "Admin action bypassed policy evaluation. No-bypass invariant (ADR F-04) violated."
    )
```
