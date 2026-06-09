"""QUAICU Kernel — SDK entry point.

``Kernel`` holds injected collaborators and vends the ``@governed`` decorator.
It is a thin composition root; all governance logic lives in ``core/``.

Config-driven construction (F-11 — config over code): ``Kernel.from_config`` reads
a TOML file and selects adapter implementations by name from an adapter registry.
No ``if/elif`` chains — the registry maps config strings to adapter classes.
"""

from __future__ import annotations

import dataclasses
import importlib
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.errors import LifecycleDeniedError, LifecycleHaltedError
from core.lifecycle.engine import LifecycleEngine
from core.lifecycle.protocols import ActionRepository, EventBus, Ledger, PolicyEvaluator
from core.ports import HITLPort, IdentityPort
from core.types import (
    Action,
    ActionId,
    ActionState,
    Actor,
    IdempotencyKey,
    RequestContext,
    TenantId,
)


# ── In-process action repository (used when no storage adapter is provided) ────

class _InMemoryActionRepository:
    """Minimal in-process action store for SDK demos and tests."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], Action] = {}

    async def insert_if_absent(self, action: Action) -> Action | None:
        key = (str(action.tenant), str(action.idempotency_key))
        if key in self._store:
            return self._store[key]
        self._store[key] = action
        return None

    async def update_state(self, action: Action) -> None:
        key = (str(action.tenant), str(action.idempotency_key))
        self._store[key] = action

    async def get_by_idempotency_key(
        self, tenant: TenantId, key: IdempotencyKey
    ) -> Action | None:
        return self._store.get((str(tenant), str(key)))

    @property
    def by_key(self) -> dict[tuple[str, str], Action]:
        return self._store


# ── Adapter registry (F-11 config over code) ───────────────────────────────────

# Maps config key → (module_path, class_name). Extended by plugins via register_adapter().
_ADAPTER_REGISTRY: dict[str, tuple[str, str]] = {
    # WorkflowPort
    "memory":                  ("adapters.workflow.memory",          "InMemoryWorkflowAdapter"),
    # InferencePort
    "openai_compat":           ("adapters.inference.openai_compat",  "OpenAICompatInferenceAdapter"),
    # HITLPort
    "webhook":                 ("adapters.hitl.webhook",             "WebhookHITLAdapter"),
    # IdentityPort
    "jwt":                     ("adapters.identity.jwt_adapter",     "JWTIdentityAdapter"),
    # StoragePort
    "memory_storage":          ("adapters.storage.memory",           "InMemoryStorageAdapter"),
    "postgres_storage":        ("adapters.storage.postgres",         "PostgresStorageAdapter"),
    # PolicyEvaluator (dev/demo only)
    "always_allow":            ("adapters.policy.always_allow",      "AlwaysAllowPolicyAdapter"),
    # Ledger
    "memory_ledger":           ("adapters.ledger.memory",            "InMemoryLedgerAdapter"),
    # EventBus
    "memory_events":           ("adapters.events.memory",            "InMemoryEventBusAdapter"),
}


def _load_adapter(name: str, **kwargs: Any) -> Any:
    """Import and instantiate an adapter by registry name."""
    if name not in _ADAPTER_REGISTRY:
        raise ValueError(
            f"Unknown adapter {name!r}. Available: {sorted(_ADAPTER_REGISTRY)}"
        )
    module_path, class_name = _ADAPTER_REGISTRY[name]
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls(**kwargs) if kwargs else cls()


# ── Kernel ─────────────────────────────────────────────────────────────────────


@dataclasses.dataclass
class Kernel:
    """Composition root for the QUAICU governance kernel.

    Holds all port adapters and vends the ``@governed`` decorator.
    Create via ``Kernel.from_config(path)`` for production, or construct
    directly in tests by injecting fakes.
    """

    engine: LifecycleEngine
    tenant: TenantId

    # ── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, path: str | Path) -> "Kernel":
        """Build a Kernel from a TOML config file.

        Selects concrete adapter classes by the names declared under
        ``[adapters]`` in the config — no code changes needed to swap adapters.
        """
        import tomllib

        with open(path, "rb") as f:
            cfg = tomllib.load(f)

        tenant = TenantId(cfg.get("tenant", {}).get("id", "default"))
        adapter_cfg = cfg.get("adapters", {})

        repo: ActionRepository = _InMemoryActionRepository()
        storage_adapter = None
        policy: PolicyEvaluator | None = None
        hitl: HITLPort | None = None
        ledger: Ledger | None = None
        events: EventBus | None = None
        identity: IdentityPort | None = None

        if "storage" in adapter_cfg:
            storage_adapter = _load_adapter(adapter_cfg["storage"], **cfg.get("storage", {}))
            repo = storage_adapter  # PostgresStorageAdapter implements ActionRepository
        if "policy" in adapter_cfg:
            policy = _load_adapter(adapter_cfg["policy"])
        if "hitl" in adapter_cfg:
            hitl = _load_adapter(adapter_cfg["hitl"], **cfg.get("hitl", {}))
        if "ledger" in adapter_cfg:
            ledger = _load_adapter(adapter_cfg["ledger"])
        if "events" in adapter_cfg:
            events = _load_adapter(adapter_cfg["events"])
        if "identity" in adapter_cfg:
            identity = _load_adapter(adapter_cfg["identity"], **cfg.get("identity", {}))

        if policy is None or hitl is None or ledger is None or events is None:
            raise ValueError(
                "kernel.toml must declare [adapters] for: policy, hitl, ledger, events"
            )

        engine = LifecycleEngine(
            repository=repo,
            policy=policy,
            hitl=hitl,
            ledger=ledger,
            events=events,
            identity=identity,
        )
        return cls(engine=engine, tenant=tenant)

    @classmethod
    def from_parts(
        cls,
        *,
        tenant: TenantId | str,
        policy: PolicyEvaluator,
        hitl: HITLPort,
        ledger: Ledger,
        events: EventBus,
        identity: IdentityPort | None = None,
        repository: ActionRepository | None = None,
        max_poll_attempts: int = 1,
    ) -> "Kernel":
        """Build a Kernel directly from collaborator instances (for tests and SDK demos)."""
        engine = LifecycleEngine(
            repository=repository or _InMemoryActionRepository(),
            policy=policy,
            hitl=hitl,
            ledger=ledger,
            events=events,
            identity=identity,
            max_poll_attempts=max_poll_attempts,
        )
        return cls(engine=engine, tenant=TenantId(str(tenant)))

    # ── Decorator factory ─────────────────────────────────────────────────────

    def governed(
        self,
        *,
        policy: str,
        action_type: str | None = None,
    ) -> Callable:
        """Decorator factory. Wraps an async function as a governed action.

        The decorated function must accept ``actor: Actor`` as a keyword argument.
        On COMPLETED the decorated function's return value is returned unchanged.
        On DENIED the call raises ``LifecycleDeniedError``.
        On HALTED the call raises ``LifecycleHaltedError``.

        Example::

            @kernel.governed(policy="ciro.ifrs9.stage_transition")
            async def reclassify(loan_id: str, to_stage: int, *, actor: Actor):
                await db.update(loan_id, to_stage)
        """
        import functools

        effective_type = action_type or policy

        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                actor: Actor = kwargs.get("actor")  # type: ignore[assignment]
                if actor is None:
                    raise TypeError(
                        f"@governed function {fn.__name__!r} must receive actor=<Actor> as a kwarg"
                    )

                # Build payload from kwargs, excluding 'actor'
                payload = {k: v for k, v in kwargs.items() if k != "actor"}

                action = Action(
                    id=ActionId(str(uuid.uuid4())),
                    type=effective_type,
                    payload=payload,
                    actor=actor,
                    tenant=self.tenant,
                    idempotency_key=IdempotencyKey(str(uuid.uuid4())),
                    proposed_at=datetime.now(tz=timezone.utc),
                )

                # The execute step is the decorated function body
                async def execute_fn() -> Any:
                    return await fn(*args, **kwargs)

                final_action = await self.engine.run(action, execute_fn)

                if final_action.state is ActionState.DENIED:
                    raise LifecycleDeniedError(
                        f"Action {final_action.id} denied by governance",
                        detail={"action_id": str(final_action.id), "type": effective_type},
                    )
                if final_action.state is ActionState.HALTED:
                    raise LifecycleHaltedError(
                        f"Action {final_action.id} halted by governance",
                        detail={"action_id": str(final_action.id), "type": effective_type},
                    )
                return final_action

            wrapper._governed_policy = policy  # type: ignore[attr-defined]
            wrapper._governed_action_type = effective_type  # type: ignore[attr-defined]
            return wrapper

        return decorator
