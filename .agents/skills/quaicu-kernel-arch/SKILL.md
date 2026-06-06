---
name: quaicu-kernel-arch
description: |
  QUAICU Kernel core architecture enforcer. Use for ANY code written in core/ — verifies hexagonal
  ports/adapters structure, enforces all 11 frozen architecture decisions (F-01 to F-11), checks for
  domain imports, ensures fail-closed everywhere, and validates the one-core-no-forks invariant.
  Trigger keywords: core/, ports/, adapters/, delivery/, InferencePort, StoragePort, HITLPort,
  WorkflowPort, IdentityPort, fail-closed, no forks, one core, governance kernel, QUAICU, kernel.toml.
---

# QUAICU Kernel Architecture Enforcer

You are the QUAICU architecture guardian. Every file in `core/` must pass all checks below before
it is written or approved. Violations are build failures, not warnings. This skill is authoritative
over the entire repository structure, import graph, CI enforcement, and adapter wiring.

---

## ⚡ Deterministic Decision Contract — READ THIS FIRST

> Purpose: make every choice in this skill **mechanical**, so a small or low-token model produces the
> same code as a top model at maximum effort. **If this block and any prose below ever conflict, this
> block wins.** Do not deliberate on these items — look them up and apply them exactly. If a needed
> rule is missing here, choose the most restrictive option (deny/halt/refuse) and stop.

### Invariants — never violated, no exceptions
- ALWAYS: `core/` imports only from `core/`. Concrete SDKs, DB drivers, queues, model clients live in `adapters/` only.
- ALWAYS: raise a typed subclass of `QUAICUError`. NEVER `raise Exception(...)`, NEVER return a permissive default.
- ALWAYS: fail-closed. Failure / timeout / missing data / ambiguity → DENY or HALT. NEVER `except: return allow`.
- NEVER: `if tenant ==`, `if customer ==`, `if deployment_type ==` in `core/`. Differences live in config/packs/adapters.
- NEVER: `eval`, `exec`, raw Rego, or a custom DSL for conditions. CEL only.
- NEVER: wall-clock, `random`, env vars, or live network reads inside evaluation logic.

### Where does this code go? (decide once, mechanically)
| What you are writing | Put it in | Never in |
|---|---|---|
| An interface / Protocol / contract | `core/ports/` | adapters/, delivery/ |
| Pure governance logic (lifecycle, policy, ledger) | `core/<layer>/` | adapters/, delivery/ |
| Concrete tech: SDK call, DB driver, HTTP client | `adapters/<port>/` | core/ |
| Wiring / DI / config loading / app assembly | `delivery/` | core/ |
| Policy CEL, regmaps, tenant-specific content | `packs/` | core/ |

### DENY vs HALT — the decision people get wrong
| Cause | State | Error type | Retryable? |
|---|---|---|---|
| Policy returned deny / no policy found / empty result | DENIED | `LifecycleDeniedError` | No (terminal) |
| HITL rejected OR timed out | DENIED | `LifecycleDeniedError` | No |
| Port down / timeout / storage error / seal failed | HALTED | `LifecycleHaltedError` | Maybe (after fix) |
| You cannot classify the cause | DENIED | `LifecycleDeniedError` | No — most conservative wins |

### Which error type? (pick the most specific matching subtype; never the base class)
| Symptom | Raise |
|---|---|
| CEL failed to evaluate / returned non-bool | `PolicyEvaluationError` |
| No policy governs the action | `PolicyNotFoundError` |
| Ledger seal failed | `LedgerSealError` (→ action HALTED) |
| Merkle/consistency proof failed | `LedgerProofError` / `LedgerTamperError` |
| Port timed out | `PortTimeoutError` |
| Port/service unreachable | `PortUnavailableError` |
| Saw another tenant's data | `TenantCrossContaminationError` (halt all, alert) |
| Duplicate idempotency key | `LifecycleIdempotencyError` (return existing state) |

### Stop-and-apply triggers (before writing the construct, jump to the named template)
- About to write `try/except`? → it MUST end in DENY/HALT + re-raise. See "Anti-pattern 1".
- About to write a DB/SDK import in `core/`? → STOP, route through a Port. See "Anti-pattern 2".
- About to call `seal`? → seal-fail = HALTED, never COMPLETED. See "Anti-pattern 4".
- About to add an `if` on tenant/customer? → STOP, move to config/pack. See "Anti-pattern 3".

### Self-check — run on your own output before returning it
- [ ] core/ contains no `eval(`, `exec(`, `import openai|anthropic|boto3|sqlalchemy|asyncpg|temporalio`.
- [ ] core/ contains no domain terms (student/patient/loan/customer_type/order/claim/…).
- [ ] Every `except` ends in a raised `QUAICUError` subtype or a fail-closed state — no silent continue.
- [ ] Every public lifecycle method opens an OTel span with `tenant_id` + `action_id` set.
- [ ] Every function is fully type-annotated (passes `mypy --strict`).
- [ ] Every new port implementation has an adapter conformance test subclass.

---

## The Two Rules That Override Everything

1. **One core, no forks.** `core/` is identical for every customer. Customer differences live ONLY
   in `adapters/`, `packs/`, and `kernel.toml`. The moment you write `if customer_type ==` anywhere
   in `core/` you have broken F-01 and the build fails.

2. **Fail-closed always.** Any failure, timeout, ambiguity, or missing data → DENY or HALT. Never
   return a permissive default. Never catch an exception and proceed. If you cannot evaluate it,
   you deny it. "Fail open for convenience" is the single worst bug in a governance kernel.

---

## The 11 Frozen Architecture Decisions (F-01 to F-11)

These are settled. A PR that violates one is rejected regardless of other merit.

| ADR | Rule | What it forbids |
|-----|------|-----------------|
| F-01 | One core, no forks | Forking core for any customer or deployment type |
| F-02 | Model/deployment agnostic | Bundling models or mandating inference location in core |
| F-03 | Fail-closed everywhere | Any "let it through if service is slow/down" path |
| F-04 | No bypass | Any path that executes without evaluate + gate |
| F-05 | CEL for conditions | Python `eval`, raw Rego, custom DSLs in policy conditions |
| F-06 | RFC 6962 for ledger | Custom proof structures; any deviation from the RFC |
| F-07 | Per-tenant ledger | Shared ledger table with `tenant_id` column |
| F-08 | Ports and adapters | Direct imports of model SDKs, DB drivers, queues in `core/` |
| F-09 | Replay-safe, side-effect-free | Recomputing non-determinism on replay; replay causing effects |
| F-10 | Simulation before enforcement | Activating a policy without a backtest impact report |
| F-11 | Config over code | Adding `if` branches in core for specific customers |

---

## Error Type Hierarchy

All exceptions raised in `core/` must be typed. Never raise bare `Exception`. The hierarchy below
is authoritative — add new subtypes under the correct parent, never invent a parallel tree.

```python
# core/errors.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


class QUAICUError(Exception):
    """Root of all kernel errors. All kernel code catches or raises subtypes."""
    code: str = "QUAICU_ERROR"

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail: dict[str, Any] = detail or {}


# ── Architecture / wiring errors ──────────────────────────────────────────────

class ArchitectureViolationError(QUAICUError):
    """Raised when a frozen ADR is violated at runtime (misconfigured wiring)."""
    code = "ARCH_VIOLATION"


class DomainImportError(ArchitectureViolationError):
    """Raised when a domain concept is detected in core/ at runtime (should be CI-caught first)."""
    code = "DOMAIN_IMPORT"


class PortContractError(ArchitectureViolationError):
    """A port implementation returned None or an invalid value when it must raise."""
    code = "PORT_CONTRACT"


# ── Lifecycle errors ───────────────────────────────────────────────────────────

class LifecycleError(QUAICUError):
    """Base for all lifecycle spine errors."""
    code = "LIFECYCLE_ERROR"


class LifecycleDeniedError(LifecycleError):
    """Action was denied at evaluate or gate. Terminal — do not retry."""
    code = "LIFECYCLE_DENIED"


class LifecycleHaltedError(LifecycleError):
    """Action was halted due to an internal error. May be retryable depending on cause."""
    code = "LIFECYCLE_HALTED"


class LifecycleIdempotencyError(LifecycleError):
    """Idempotency key already processed. Return existing action state."""
    code = "LIFECYCLE_IDEMPOTENT"


class LifecycleBypassAttemptError(LifecycleError):
    """Code attempted to execute without going through evaluate+gate. F-04 violation."""
    code = "LIFECYCLE_BYPASS"


class LifecycleInvalidTransitionError(LifecycleError):
    """State machine transition not permitted from current state."""
    code = "LIFECYCLE_INVALID_TRANSITION"


# ── Policy engine errors ───────────────────────────────────────────────────────

class PolicyError(QUAICUError):
    """Base for all policy engine errors."""
    code = "POLICY_ERROR"


class PolicyEvaluationError(PolicyError):
    """CEL evaluation failed or returned an unexpected type."""
    code = "POLICY_EVAL_FAILED"


class PolicyCompileError(PolicyError):
    """CEL expression failed to compile during authoring."""
    code = "POLICY_COMPILE_ERROR"


class PolicyActivationError(PolicyError):
    """Policy cannot be activated — preconditions not met."""
    code = "POLICY_ACTIVATION_BLOCKED"


class PolicyConflictError(PolicyError):
    """Policy conflict resolution produced an undefined result (should never happen)."""
    code = "POLICY_CONFLICT_UNDEFINED"


class PolicyNotFoundError(PolicyError):
    """No policy governs this action type. Resolution: fail-closed DENY."""
    code = "POLICY_NOT_FOUND"


# ── Ledger errors ─────────────────────────────────────────────────────────────

class LedgerError(QUAICUError):
    """Base for all TrustLedger errors."""
    code = "LEDGER_ERROR"


class LedgerSealError(LedgerError):
    """Ledger seal failed. Action must be HALTED — not marked EXECUTED."""
    code = "LEDGER_SEAL_FAILED"


class LedgerProofError(LedgerError):
    """Merkle proof verification failed."""
    code = "LEDGER_PROOF_INVALID"


class LedgerTamperError(LedgerError):
    """Consistency proof detected tampering — critical, alert immediately."""
    code = "LEDGER_TAMPERED"


class LedgerClockSkewError(LedgerError):
    """Monotonic sequence violated — possible clock skew on this node."""
    code = "LEDGER_CLOCK_SKEW"


# ── Port / adapter errors ─────────────────────────────────────────────────────

class PortError(QUAICUError):
    """Base for all port adapter errors."""
    code = "PORT_ERROR"


class PortTimeoutError(PortError):
    """Port call timed out. Resolution: fail-closed."""
    code = "PORT_TIMEOUT"


class PortUnavailableError(PortError):
    """Port (service behind adapter) is unreachable. Resolution: fail-closed."""
    code = "PORT_UNAVAILABLE"


class InferencePortError(PortError):
    """InferencePort adapter error."""
    code = "PORT_INFERENCE_ERROR"


class HITLPortError(PortError):
    """HITLPort adapter error."""
    code = "PORT_HITL_ERROR"


class StoragePortError(PortError):
    """StoragePort adapter error."""
    code = "PORT_STORAGE_ERROR"


class WorkflowPortError(PortError):
    """WorkflowPort adapter error."""
    code = "PORT_WORKFLOW_ERROR"


# ── Tenant isolation errors ───────────────────────────────────────────────────

class TenantError(QUAICUError):
    """Base for all tenant boundary errors."""
    code = "TENANT_ERROR"


class TenantCrossContaminationError(TenantError):
    """Data from another tenant was observed — critical, halt everything, alert."""
    code = "TENANT_CROSS_CONTAMINATION"


class TenantNotFoundError(TenantError):
    """Requested tenant does not exist or is not provisioned."""
    code = "TENANT_NOT_FOUND"
```

---

## Port Interfaces — Full Typed Contracts

All ports live in `core/ports/`. Core imports ONLY these — never a concrete adapter.
Every method must raise on failure. Returning `None` or a permissive default is a port contract
violation caught by the adapter conformance test suite.

```python
# core/ports/__init__.py
from core.ports.inference import InferencePort
from core.ports.hitl import HITLPort
from core.ports.identity import IdentityPort
from core.ports.storage import StoragePort
from core.ports.workflow import WorkflowPort

__all__ = [
    "InferencePort", "HITLPort", "IdentityPort", "StoragePort", "WorkflowPort"
]
```

```python
# core/ports/inference.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from core.types import Prompt, ModelRef, ModelResponse, TenantId


@runtime_checkable
class InferencePort(Protocol):
    """
    Abstracts ALL inference backends (Ollama, vLLM, OpenAI, Bedrock, etc.).
    Core NEVER imports a model SDK directly — only this port.

    Fail-closed contract:
      - If the model is unavailable, raise InferencePortError (never return empty).
      - If the model is not in the tenant's approved registry, raise InferencePortError.
      - If the call cannot be logged (K·05 requirement), raise InferencePortError.
        An unlogged model call is an ungoverned call and is categorically forbidden.
    """

    async def generate(
        self,
        *,
        prompt: Prompt,
        model_ref: ModelRef,
        tenant: TenantId,
    ) -> ModelResponse:
        """
        Generate a model response.

        Args:
            prompt: The masked prompt to send. PII masking is done by the Gateway
                    before this call; the port receives the already-masked prompt.
            model_ref: Identifies which model to invoke (name + version + runtime).
            tenant: Tenant boundary. The adapter must verify the model is approved
                    for this tenant via the Model Registry before executing.

        Returns:
            ModelResponse with the full response, metadata, and the recorded
            output that will be sealed to the ledger (non-determinism recorded here).

        Raises:
            InferencePortError: model unavailable, unapproved, or logging failed.
            PortTimeoutError: call exceeded configured timeout. Caller must DENY.
        """
        ...
```

```python
# core/ports/hitl.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from core.types import Action, ApproverRef, ApprovalHandle, ApprovalDecision, TenantId


@runtime_checkable
class HITLPort(Protocol):
    """
    Human-in-the-loop gate (K·03). Routes approval requests to humans.
    Implementations: webhook (default), email, slack, inapp.

    Fail-closed contract:
      - Timeout → caller must treat as REJECTED (not approved). Never allow on timeout.
      - Approver not reachable → raise HITLPortError, caller must HALT.
      - The port does NOT enforce who can approve — that is LifecycleEngine's job.
    """

    async def request_approval(
        self,
        *,
        action: Action,
        approvers: list[ApproverRef],
        tenant: TenantId,
    ) -> ApprovalHandle:
        """
        Send approval request. Returns a handle for polling.
        Raises HITLPortError if the request cannot be dispatched.
        """
        ...

    async def poll(
        self,
        handle: ApprovalHandle,
    ) -> ApprovalDecision:
        """
        Poll for a decision.

        Returns:
            ApprovalDecision: PENDING | APPROVED | REJECTED | TIMED_OUT

        TIMED_OUT is a valid terminal state — LifecycleEngine treats it as REJECTED (fail-closed).
        Raises HITLPortError if the poll backend is unreachable.
        """
        ...
```

```python
# core/ports/identity.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from core.types import RequestContext, Actor, TenantId


@runtime_checkable
class IdentityPort(Protocol):
    """
    Resolves the authenticated identity. The kernel takes identity FROM the host.
    It does NOT own authentication. Implementations: oidc, jwt, host_provided.

    Fail-closed contract:
      - Unresolvable identity → raise PortError. Never proceed with anonymous actor.
      - Token expired or invalid → raise PortError.
      - Tenant mismatch (token claims different tenant than request) → raise TenantError.
    """

    async def resolve_actor(
        self,
        *,
        context: RequestContext,
        tenant: TenantId,
    ) -> Actor:
        """
        Resolve the caller's identity from the request context.

        Raises:
            PortError: identity cannot be resolved.
            TenantError: token tenant claim does not match requested tenant.
        """
        ...
```

```python
# core/ports/storage.py
from __future__ import annotations
from contextlib import AbstractAsyncContextManager
from typing import Protocol, runtime_checkable
from core.types import Transaction


@runtime_checkable
class StoragePort(Protocol):
    """
    Transactional storage for kernel-owned tables ONLY.
    Core NEVER reads or writes host domain tables.

    Fail-closed contract:
      - Transaction commit failure → raise StoragePortError. Never swallow.
      - Concurrent write conflict (unique constraint) → raise StoragePortError
        with detail indicating the conflict type so callers can distinguish
        idempotency duplicates from actual errors.
    """

    def transaction(self) -> AbstractAsyncContextManager[Transaction]:
        """
        Return an async context manager that provides a transaction.
        On __aexit__ with exception, rolls back. On clean __aexit__, commits.
        """
        ...

    async def health_check(self) -> bool:
        """
        Returns True if the storage backend is reachable.
        Raises StoragePortError if not (never returns False silently).
        """
        ...
```

```python
# core/ports/workflow.py
from __future__ import annotations
from typing import Protocol, runtime_checkable
from core.types import ProcessDef, WorkflowHandle, Signal, ProcessState, TenantId


@runtime_checkable
class WorkflowPort(Protocol):
    """
    Durable workflow execution engine (K·06).
    Implementations:
      - postgres_statemachine: sovereign/MVP — no extra server required.
      - temporal: dedicated/cloud — full durable execution with replay.

    Fail-closed contract:
      - start() failure → raise WorkflowPortError. Caller must not proceed.
      - signal() failure → raise WorkflowPortError. Gate cannot be considered applied.
      - state() failure → raise WorkflowPortError. Caller must treat as UNKNOWN → HALT.
    """

    async def start(
        self,
        *,
        definition: ProcessDef,
        payload: dict,
        tenant: TenantId,
    ) -> WorkflowHandle:
        """Start a durable workflow. Returns a handle for subsequent operations."""
        ...

    async def signal(
        self,
        handle: WorkflowHandle,
        signal: Signal,
    ) -> None:
        """Send a signal to a running workflow (e.g., APPROVED, REJECTED)."""
        ...

    async def state(
        self,
        handle: WorkflowHandle,
    ) -> ProcessState:
        """Return current process state. Raises on unreachable backend."""
        ...
```

---

## Adapter Contract Test Pattern (ABC + Protocol Enforcement)

Every adapter must pass its port's conformance suite before it is accepted. The test pattern below
is the contract — write one `AdapterConformanceTestBase` per port, then subclass it for each adapter.

```python
# tests/conformance/ports/base_inference.py
import abc
import pytest
from core.errors import InferencePortError, PortTimeoutError
from core.ports import InferencePort
from core.types import Prompt, ModelRef, TenantId


class BaseInferencePortConformanceTests(abc.ABC):
    """
    Abstract conformance suite for InferencePort.
    Every adapter subclasses this and provides a concrete port instance.
    All tests run against the real (or test-double) adapter.
    """

    @abc.abstractmethod
    def make_port(self) -> InferencePort:
        """Return a fully initialised port instance for testing."""
        ...

    @abc.abstractmethod
    def make_prompt(self) -> Prompt:
        """Return a valid masked prompt for testing."""
        ...

    @abc.abstractmethod
    def make_model_ref(self) -> ModelRef:
        """Return a valid approved model ref for the test tenant."""
        ...

    @pytest.fixture
    def port(self) -> InferencePort:
        return self.make_port()

    @pytest.fixture
    def tenant(self) -> TenantId:
        return TenantId("test-tenant-001")

    # ── Protocol structural check ──────────────────────────────────────────────

    def test_is_protocol_instance(self, port: InferencePort) -> None:
        """Port must satisfy the Protocol at runtime."""
        assert isinstance(port, InferencePort), (
            "Adapter does not satisfy InferencePort Protocol. "
            "Ensure all methods are implemented with matching signatures."
        )

    # ── Happy path ────────────────────────────────────────────────────────────

    async def test_generate_returns_model_response(
        self, port: InferencePort, tenant: TenantId
    ) -> None:
        response = await port.generate(
            prompt=self.make_prompt(),
            model_ref=self.make_model_ref(),
            tenant=tenant,
        )
        assert response is not None
        assert response.content  # must have non-empty content
        assert response.model_id  # must record which model was used
        assert response.recorded_output  # must record for ledger replay

    # ── Fail-closed paths — CRITICAL ─────────────────────────────────────────

    async def test_raises_on_unapproved_model(
        self, port: InferencePort, tenant: TenantId
    ) -> None:
        unapproved_ref = ModelRef(id="unapproved-model-xyz", version="1.0")
        with pytest.raises(InferencePortError) as exc_info:
            await port.generate(
                prompt=self.make_prompt(),
                model_ref=unapproved_ref,
                tenant=tenant,
            )
        assert exc_info.value.code == "PORT_INFERENCE_ERROR"

    async def test_never_returns_none(
        self, port: InferencePort, tenant: TenantId
    ) -> None:
        """A port that returns None instead of raising violates the contract."""
        # Under any failure condition, the port must raise, never return None.
        # This test injects a fault via the adapter's test interface.
        try:
            result = await port.generate(
                prompt=self.make_prompt(),
                model_ref=self.make_model_ref(),
                tenant=tenant,
            )
            assert result is not None, "Port returned None — contract violation"
        except (InferencePortError, PortTimeoutError):
            pass  # raising is the correct fail-closed behavior


# Adapter implementation subclass example:
# tests/conformance/adapters/test_ollama_inference.py
#
# class TestOllamaInferenceConformance(BaseInferencePortConformanceTests):
#     def make_port(self) -> InferencePort:
#         return OllamaInferenceAdapter(base_url="http://localhost:11434")
#     def make_prompt(self) -> Prompt:
#         return Prompt(text="[MASKED] Classify this document.")
#     def make_model_ref(self) -> ModelRef:
#         return ModelRef(id="llama3", version="latest")
```

---

## Dependency Injection Wiring

The kernel kernel is assembled in `delivery/` — never in `core/`. Core receives its dependencies
through constructor injection. No global singletons in core.

```python
# delivery/sdk/kernel.py
from __future__ import annotations
import tomllib
from pathlib import Path
from core.lifecycle.engine import LifecycleEngine
from core.policy.engine import PolicyEngine
from core.ledger.trust_ledger import TrustLedger
from core.events.bus import EventBus
from core.errors import ArchitectureViolationError


class Kernel:
    """
    The assembled kernel. One instance per process.
    Wires ports (selected from config) into core components.
    This is the ONLY place where concrete adapter imports appear.
    """

    def __init__(
        self,
        lifecycle_engine: LifecycleEngine,
        policy_engine: PolicyEngine,
        ledger: TrustLedger,
        event_bus: EventBus,
    ) -> None:
        self._lifecycle = lifecycle_engine
        self._policy = policy_engine
        self._ledger = ledger
        self._event_bus = event_bus

    @classmethod
    def from_config(cls, config_path: str | Path) -> "Kernel":
        """
        Assemble kernel from kernel.toml.
        This is where adapters are imported and instantiated.
        core/ is never imported here for its adapter-selection logic.
        """
        with open(config_path, "rb") as f:
            config = tomllib.load(f)

        # Adapter selection — imports of concrete adapters happen HERE, not in core/
        inference_port = _load_inference_adapter(config["adapters"]["inference"])
        hitl_port = _load_hitl_adapter(config["adapters"]["hitl"])
        identity_port = _load_identity_adapter(config["adapters"]["identity"])
        storage_port = _load_storage_adapter(config["adapters"]["storage"])
        workflow_port = _load_workflow_adapter(config["adapters"]["workflow"])

        # Validate all adapters satisfy their Protocol before wiring
        from core.ports import InferencePort, HITLPort, IdentityPort, StoragePort, WorkflowPort
        _assert_port(inference_port, InferencePort, "inference")
        _assert_port(hitl_port, HITLPort, "hitl")
        _assert_port(identity_port, IdentityPort, "identity")
        _assert_port(storage_port, StoragePort, "storage")
        _assert_port(workflow_port, WorkflowPort, "workflow")

        policy_engine = PolicyEngine(storage=storage_port)
        ledger = TrustLedger(storage=storage_port)
        event_bus = EventBus()

        lifecycle_engine = LifecycleEngine(
            policy_engine=policy_engine,
            hitl_port=hitl_port,
            workflow_port=workflow_port,
            ledger=ledger,
            event_bus=event_bus,
            identity_port=identity_port,
        )

        return cls(
            lifecycle_engine=lifecycle_engine,
            policy_engine=policy_engine,
            ledger=ledger,
            event_bus=event_bus,
        )

    def governed(self, *, policy: str):
        """Decorator factory. Returns @governed(policy=...) for the Python SDK surface."""
        from delivery.sdk.decorator import _make_governed_decorator
        return _make_governed_decorator(policy=policy, kernel=self)


def _assert_port(instance: object, protocol: type, name: str) -> None:
    if not isinstance(instance, protocol):
        raise ArchitectureViolationError(
            f"Adapter '{name}' does not satisfy {protocol.__name__} Protocol. "
            f"Check that all required methods are implemented.",
            detail={"adapter_type": type(instance).__name__, "port": protocol.__name__},
        )


def _load_inference_adapter(name: str):
    # Adapter registry — adding a new backend does NOT change core/
    from adapters.inference.ollama import OllamaAdapter
    from adapters.inference.vllm import VLLMAdapter
    from adapters.inference.openai import OpenAIAdapter
    from adapters.inference.anthropic import AnthropicAdapter
    from adapters.inference.bedrock import BedrockAdapter
    registry = {
        "ollama": OllamaAdapter,
        "vllm": VLLMAdapter,
        "openai": OpenAIAdapter,
        "anthropic": AnthropicAdapter,
        "bedrock": BedrockAdapter,
    }
    if name not in registry:
        raise ArchitectureViolationError(
            f"Unknown inference adapter: '{name}'. "
            f"Valid options: {sorted(registry.keys())}",
            detail={"requested": name},
        )
    return registry[name]()
```

---

## CI Enforcement Scripts

These run in CI on every PR that touches `core/`. Any failure is a build failure, not a warning.

```bash
#!/usr/bin/env bash
# ci/checks/domain_import_check.sh
# Fails the build if domain terms appear in core/.
# Add new domain terms to the list as the business expands.

set -euo pipefail

DOMAIN_TERMS="student|patient|loan|applicant|employee|order|invoice|customer_type|\
claim|policy_holder|borrower|depositor|claimant|beneficiary|enrollee|subscriber"

echo "=== Domain import check: scanning core/ ==="
MATCHES=$(grep -rn --include="*.py" -E "${DOMAIN_TERMS}" core/ 2>/dev/null || true)

if [[ -n "${MATCHES}" ]]; then
    echo "FAIL: Domain terms found in core/:"
    echo "${MATCHES}"
    echo ""
    echo "core/ knows: Action, Proposal, Policy, Evaluation, Gate, Execute, Seal,"
    echo "             Emit, Actor, Tenant — and nothing else."
    echo "Move domain knowledge to adapters/, packs/, or delivery/."
    exit 1
fi

echo "PASS: No domain terms in core/"
```

```bash
#!/usr/bin/env bash
# ci/checks/import_boundary_check.sh
# Validates the dependency direction: core/ must not import from adapters/ or delivery/.

set -euo pipefail

echo "=== Import boundary check: core/ must not import adapters/ or delivery/ ==="

# Check for adapter imports in core/
ADAPTER_IMPORTS=$(grep -rn --include="*.py" \
    -E "from adapters\.|import adapters\." core/ 2>/dev/null || true)

DELIVERY_IMPORTS=$(grep -rn --include="*.py" \
    -E "from delivery\.|import delivery\." core/ 2>/dev/null || true)

# Check for banned direct SDK imports in core/
SDK_IMPORTS=$(grep -rn --include="*.py" \
    -E "import openai|import anthropic|import boto3|import google\.cloud|import sqlalchemy|import asyncpg|import temporalio" \
    core/ 2>/dev/null || true)

# Check for vault imports (must use OpenBao)
VAULT_IMPORTS=$(grep -rn --include="*.py" \
    -E "import hvac|from hvac|hashicorp.vault" \
    . 2>/dev/null || true)

FAILED=0

if [[ -n "${ADAPTER_IMPORTS}" ]]; then
    echo "FAIL: core/ imports from adapters/:"
    echo "${ADAPTER_IMPORTS}"
    FAILED=1
fi

if [[ -n "${DELIVERY_IMPORTS}" ]]; then
    echo "FAIL: core/ imports from delivery/:"
    echo "${DELIVERY_IMPORTS}"
    FAILED=1
fi

if [[ -n "${SDK_IMPORTS}" ]]; then
    echo "FAIL: core/ has direct SDK imports (must use ports):"
    echo "${SDK_IMPORTS}"
    FAILED=1
fi

if [[ -n "${VAULT_IMPORTS}" ]]; then
    echo "FAIL: HashiCorp Vault (hvac) import detected — use OpenBao (MPL 2.0) instead."
    echo "${VAULT_IMPORTS}"
    FAILED=1
fi

if [[ "${FAILED}" -eq 1 ]]; then
    exit 1
fi

echo "PASS: All import boundaries respected"
```

```bash
#!/usr/bin/env bash
# ci/checks/eval_ban_check.sh
# Bans Python eval, exec, and raw Rego in core/ and adapters/.
# F-05: CEL only.

set -euo pipefail

echo "=== eval/exec/rego ban check ==="

EVAL_USES=$(grep -rn --include="*.py" \
    -E "\beval\s*\(|\bexec\s*\(" \
    core/ adapters/ 2>/dev/null || true)

REGO_USES=$(grep -rn --include="*.py" \
    -E "import opa|from opa|rego\.Module|rego\.New" \
    core/ adapters/ 2>/dev/null || true)

FAILED=0

if [[ -n "${EVAL_USES}" ]]; then
    echo "FAIL: eval/exec found — F-05 violation. Use CEL."
    echo "${EVAL_USES}"
    FAILED=1
fi

if [[ -n "${REGO_USES}" ]]; then
    echo "FAIL: Raw Rego/OPA import found — F-05 violation. Use CEL."
    echo "${REGO_USES}"
    FAILED=1
fi

[[ "${FAILED}" -eq 1 ]] && exit 1
echo "PASS: No eval/exec/rego usage"
```

---

## Makefile / Task Targets

```makefile
# Makefile — all CI targets plus local development workflow

.PHONY: check lint typecheck test ci-gate

## ── CI gate (runs everything; must pass before merge) ────────────────────────
ci-gate: check lint typecheck test
	@echo "=== CI GATE PASSED ==="

## ── Architecture checks (run first — fast, catch structural violations) ──────
check:
	@bash ci/checks/domain_import_check.sh
	@bash ci/checks/import_boundary_check.sh
	@bash ci/checks/eval_ban_check.sh
	@echo "=== All architecture checks passed ==="

## ── Lint ─────────────────────────────────────────────────────────────────────
lint:
	ruff check core/ adapters/ delivery/ tests/
	ruff format --check core/ adapters/ delivery/ tests/

## ── Type checking ────────────────────────────────────────────────────────────
typecheck:
	mypy core/ adapters/ delivery/ \
	    --strict \
	    --ignore-missing-imports \
	    --disallow-any-generics

## ── Tests ────────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v --tb=short

test-conformance:
	pytest tests/conformance/ -v --tb=short -m conformance

test-property:
	pytest tests/property/ -v --tb=short -m property

test-integration:
	pytest tests/integration/ -v --tb=short -m integration

## ── Migrations ───────────────────────────────────────────────────────────────
migrate:
	alembic upgrade head

migrate-check:
	alembic check  # fails if there are pending migrations not yet applied

## ── Pack validation ──────────────────────────────────────────────────────────
validate-packs:
	python -m tools.validate_packs packs/

## ── Secrets (OpenBao) ────────────────────────────────────────────────────────
secrets-check:
	@grep -rn "hvac\|hashicorp" . --include="*.py" --include="*.toml" || true
	@echo "Confirm above output is empty — no HashiCorp Vault dependencies allowed"
```

---

## OpenTelemetry Instrumentation

Every span emitted from `core/` must use these attribute conventions. Adapters may add adapter-specific
attributes but must not omit the core ones.

```python
# core/telemetry.py
"""
OTel instrumentation conventions for the QUAICU kernel.
Import this module for span/metric naming constants.
"""
from opentelemetry import trace, metrics
from opentelemetry.trace import Span, Status, StatusCode

TRACER_NAME = "quaicu.kernel"
METER_NAME = "quaicu.kernel"

tracer = trace.get_tracer(TRACER_NAME, schema_url="https://opentelemetry.io/schemas/1.24.0")
meter = metrics.get_meter(METER_NAME)


# ── Span names (use these exact strings) ──────────────────────────────────────
class Spans:
    LIFECYCLE_PROPOSE        = "quaicu.lifecycle.propose"
    LIFECYCLE_EVALUATE       = "quaicu.lifecycle.evaluate"
    LIFECYCLE_GATE           = "quaicu.lifecycle.gate"
    LIFECYCLE_EXECUTE        = "quaicu.lifecycle.execute"
    LIFECYCLE_SEAL           = "quaicu.lifecycle.seal"
    LIFECYCLE_EMIT           = "quaicu.lifecycle.emit"
    POLICY_EVALUATE          = "quaicu.policy.evaluate"
    POLICY_CEL_COMPILE       = "quaicu.policy.cel.compile"
    POLICY_CEL_EVALUATE      = "quaicu.policy.cel.evaluate"
    POLICY_CONFLICT_RESOLVE  = "quaicu.policy.conflict.resolve"
    POLICY_ACTIVATE          = "quaicu.policy.activate"
    LEDGER_SEAL              = "quaicu.ledger.seal"
    LEDGER_VERIFY            = "quaicu.ledger.verify"
    LEDGER_PROOF_GENERATE    = "quaicu.ledger.proof.generate"
    HITL_REQUEST             = "quaicu.hitl.request"
    HITL_POLL                = "quaicu.hitl.poll"
    INFERENCE_GENERATE       = "quaicu.inference.generate"
    IDENTITY_RESOLVE         = "quaicu.identity.resolve"


# ── Required span attributes ──────────────────────────────────────────────────
class Attrs:
    TENANT_ID          = "quaicu.tenant_id"
    ACTION_ID          = "quaicu.action_id"
    ACTION_TYPE        = "quaicu.action_type"
    ACTION_STATE       = "quaicu.action_state"
    POLICY_ID          = "quaicu.policy_id"
    POLICY_VERSION     = "quaicu.policy_version"
    POLICY_DECISION    = "quaicu.policy_decision"
    LEDGER_SEQ         = "quaicu.ledger_seq"
    ACTOR_ID           = "quaicu.actor_id"
    ERROR_CODE         = "quaicu.error_code"
    IDEMPOTENCY_KEY    = "quaicu.idempotency_key"
    MODEL_ID           = "quaicu.model_id"
    DEPLOYMENT_TIER    = "quaicu.deployment_tier"
    WORKFLOW_ENGINE    = "quaicu.workflow_engine"


# ── Metrics ───────────────────────────────────────────────────────────────────
actions_proposed_counter = meter.create_counter(
    "quaicu.actions.proposed",
    description="Total actions proposed",
)
actions_denied_counter = meter.create_counter(
    "quaicu.actions.denied",
    description="Total actions denied by policy or lifecycle error",
)
actions_completed_counter = meter.create_counter(
    "quaicu.actions.completed",
    description="Total actions completed (sealed + emitted)",
)
actions_pending_approval_gauge = meter.create_up_down_counter(
    "quaicu.actions.pending_approval",
    description="Actions currently awaiting HITL approval",
)
lifecycle_step_duration = meter.create_histogram(
    "quaicu.lifecycle.step.duration_ms",
    description="Duration of each lifecycle step in milliseconds",
    unit="ms",
)
policy_evaluation_duration = meter.create_histogram(
    "quaicu.policy.evaluation.duration_ms",
    description="Duration of policy evaluation (CEL + conflict resolution) in milliseconds",
    unit="ms",
)
ledger_seal_duration = meter.create_histogram(
    "quaicu.ledger.seal.duration_ms",
    description="Duration of ledger seal (Merkle append) in milliseconds",
    unit="ms",
)


def record_lifecycle_step(
    span: Span,
    step: str,
    tenant_id: str,
    action_id: str,
    action_type: str,
    state: str,
    duration_ms: float,
    error_code: str | None = None,
) -> None:
    """Convenience function: set all required attributes on a lifecycle span."""
    span.set_attribute(Attrs.TENANT_ID, tenant_id)
    span.set_attribute(Attrs.ACTION_ID, action_id)
    span.set_attribute(Attrs.ACTION_TYPE, action_type)
    span.set_attribute(Attrs.ACTION_STATE, state)
    if error_code:
        span.set_attribute(Attrs.ERROR_CODE, error_code)
        span.set_status(Status(StatusCode.ERROR, error_code))
    lifecycle_step_duration.record(
        duration_ms,
        attributes={
            "step": step,
            Attrs.TENANT_ID: tenant_id,
            Attrs.ACTION_TYPE: action_type,
        },
    )
```

---

## Anti-Patterns (Common Mistakes and Corrected Code)

### Anti-pattern 1 — Catching exception and continuing (F-03 violation)

```python
# WRONG — catastrophic. On policy failure, the action proceeds as if allowed.
async def _evaluate(self, action):
    try:
        return await self.policy_engine.evaluate(action)
    except Exception:
        return EvaluationResult(decision="allow", ...)  # NEVER DO THIS

# CORRECT — fail-closed. Policy failure = DENY.
async def _evaluate(self, action: Action) -> EvaluationResult:
    try:
        result = await self.policy_engine.evaluate(action)
    except Exception as exc:
        action.state = ActionState.DENIED
        raise LifecycleDeniedError(
            "Policy evaluation failed — fail-closed",
            detail={"action_id": str(action.id), "cause": str(exc)},
        ) from exc
    if result is None:
        action.state = ActionState.DENIED
        raise LifecycleDeniedError(
            "Policy engine returned None — port contract violation",
            detail={"action_id": str(action.id)},
        )
    return result
```

### Anti-pattern 2 — Direct DB import in core/ (F-08 violation)

```python
# WRONG — core/ imports SQLAlchemy directly.
# core/lifecycle/engine.py
import sqlalchemy  # NEVER in core/
from sqlalchemy.ext.asyncio import AsyncSession

async def propose(self, action):
    async with AsyncSession(engine) as session:  # NEVER
        session.add(action)

# CORRECT — use StoragePort.
# core/lifecycle/engine.py
from core.ports import StoragePort  # the interface only

async def propose(self, action: Action) -> Action:
    async with self._storage.transaction() as tx:
        await tx.save_action(action)
    return action
```

### Anti-pattern 3 — Customer conditional in core/ (F-01 / F-11 violation)

```python
# WRONG — core/ branches on customer identity.
async def evaluate(self, action, tenant_id):
    if tenant_id == "bank_of_ciro":
        return await self._bank_policy_engine.evaluate(action)  # fork in disguise
    return await self._standard_policy_engine.evaluate(action)

# CORRECT — the difference is in configuration, not code.
# kernel.toml for bank_of_ciro loads different policy packs.
# The engine code is identical; only the loaded policies differ.
async def evaluate(self, action: Action) -> EvaluationResult:
    # PolicyEngine loaded applicable policies from tenant's pack at startup.
    return await self.policy_engine.evaluate(action)
```

### Anti-pattern 4 — Skip-ahead on seal failure (F-04 / F-03 violation)

```python
# WRONG — if seal fails, marking the action COMPLETED anyway.
async def _seal(self, action, eval_result, exec_result):
    try:
        entry = await self.ledger.seal(action, eval_result, exec_result)
    except Exception:
        action.state = ActionState.COMPLETED  # LIE — action is NOT sealed
        return None  # pretending it's fine

# CORRECT — seal failure → HALTED. The action remains unconfirmed until sealed.
async def _seal(
    self, action: Action, eval_result: EvaluationResult, exec_result: Any
) -> LedgerEntry:
    action.state = ActionState.SEALING
    try:
        entry = await self.ledger.seal(action, eval_result, exec_result)
    except Exception as exc:
        action.state = ActionState.HALTED
        raise LifecycleHaltedError(
            "Ledger seal failed — action halted, integrity not confirmed",
            detail={"action_id": str(action.id), "cause": str(exc)},
        ) from exc
    action.state = ActionState.SEALED
    return entry
```

### Anti-pattern 5 — Using wall-clock in evaluation logic (determinism violation)

```python
# WRONG — evaluation result depends on when it runs.
async def evaluate(self, action):
    import datetime
    if datetime.datetime.now().hour < 8:
        return PolicyDecision(decision="deny")  # non-deterministic

# CORRECT — if time-of-day matters, it must be in the action payload, recorded at proposal time.
# The policy CEL expression reads action.payload.proposed_at_hour.
# Never use wall-clock in evaluation.
```

---

## Edge Cases

### Concurrent Submissions (same idempotency key, two threads/processes)

The idempotency check must be atomic. A DB-level unique constraint is the only reliable guard.
SELECT then INSERT in separate statements will race. Use INSERT ... ON CONFLICT.

```sql
-- migrations: unique constraint (enforced at DB level, not application level)
ALTER TABLE actions ADD CONSTRAINT uq_tenant_idempotency
    UNIQUE (tenant_id, idempotency_key);
```

```python
# core/lifecycle/engine.py — idempotency handled via ON CONFLICT, not SELECT-then-INSERT
async def propose(self, action: Action) -> Action:
    async with self._storage.transaction() as tx:
        try:
            await tx.insert_action_or_conflict(action)
        except StoragePortError as exc:
            if exc.detail.get("constraint") == "uq_tenant_idempotency":
                existing = await tx.get_by_idempotency_key(
                    action.idempotency_key, action.tenant_id
                )
                action.state = ActionState.CANCELLED
                return existing  # return existing state, do NOT double-execute
            raise  # unexpected storage error → let it propagate → HALTED
```

### Clock Skew in Air-Gapped Deployments

The ledger's monotonic sequence must not depend on wall-clock ordering. Use a DB sequence for
ordering; wall-clock timestamps are metadata only. If the DB sequence advances and timestamp goes
backward, record it as a `LedgerClockSkewEvent` and continue — never reject the seal.

```python
# core/ledger/trust_ledger.py
async def _next_seq(self, tx: Transaction) -> tuple[int, datetime]:
    """Returns (sequence_number, wall_clock_timestamp)."""
    seq = await tx.nextval("ledger_seq")  # DB sequence — monotonic regardless of clock
    ts = datetime.now(tz=timezone.utc)

    # Detect clock skew: if our timestamp is earlier than the previous entry's timestamp
    prev_ts = await tx.get_last_ledger_timestamp(self._tenant_id)
    if prev_ts and ts < prev_ts:
        # Record skew event but do NOT reject — ordering is guaranteed by seq, not ts.
        await tx.record_clock_skew_event(seq=seq, observed_ts=ts, expected_min_ts=prev_ts)

    return seq, ts
```

### Partial Failures After Execute But Before Seal

If `execute()` succeeds but `seal()` fails, the action is in an inconsistent state: the external
state change happened but the ledger has no record. This is the most dangerous partial failure.

Resolution protocol:
1. Set action state to `HALTED` (not `EXECUTED` — execution without a ledger entry is ungoverned).
2. Emit an alert to the operator channel immediately.
3. Provide a `reconcile` admin command that re-attempts sealing without re-executing.
4. The reconcile path is a first-class lifecycle operation with its own audit trail.

```python
# core/lifecycle/engine.py
async def _execute_then_seal(
    self, action: Action, execute_fn, eval_result: EvaluationResult
) -> LedgerEntry:
    exec_result = await self._execute(action, execute_fn)  # may succeed
    try:
        entry = await self._seal(action, eval_result, exec_result)  # may fail
    except LifecycleHaltedError:
        # CRITICAL: state change happened, ledger record missing.
        # Alert operator immediately. Do not silently swallow.
        await self._alert_partial_failure(action, exec_result)
        raise  # propagate — caller must not mark action COMPLETED
    return entry
```

---

## Checklist Before Writing Any core/ File

- [ ] No domain imports (student, loan, patient, etc.) — CI will catch; don't wait for CI
- [ ] No concrete adapter or SDK imports — only core/ports/ interfaces
- [ ] All external calls go through a Port interface
- [ ] Every error path raises a typed subclass of QUAICUError — no bare `raise Exception`
- [ ] No customer-specific conditionals
- [ ] No wall-clock, randomness, or live external state in evaluation logic
- [ ] OTel span opened for every public method in a lifecycle step; required attributes set
- [ ] Type annotations on every function signature (mypy --strict passes)
- [ ] Adapter conformance test exists for every new port implementation
