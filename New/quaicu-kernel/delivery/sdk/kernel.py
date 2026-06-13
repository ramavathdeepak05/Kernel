"""QUAICU Kernel — SDK entry point.

``Kernel`` holds injected collaborators and vends the governance decorators:
  - ``@kernel.governed(...)`` — wrap an action function.
  - ``@kernel.governed_tool(...)`` — wrap an agent tool (returns the tool's own result).
  - ``kernel.generate(...)`` — a governed model call through the AI Gateway.
  - ``kernel.for_agent(actor)`` — a handle that stamps every action with that agent's identity.

It is a thin composition root; all governance logic lives in ``core/``.

Composable enforcement (F-11): every governed action runs under a ``GovernanceProfile`` that
declares which layers are enforced (identity, consent, policy, HITL gate, gateway protections,
ledger seal, event emit). The profile is resolved per action type, overridable per call.
"""

from __future__ import annotations

import dataclasses
import functools
import importlib
import inspect
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.errors import LifecycleDeniedError, LifecycleHaltedError  # noqa: F401 (re-exported)
from core.gateway.allowlist import InMemoryModelAllowlist
from core.gateway.budget import InMemoryBudgetTracker
from core.gateway.engine import AIGateway
from core.gateway.masking import MaskingConfig
from core.lifecycle.context import async_actor_scope, get_current_actor, set_actor
from core.lifecycle.decision import AuthorizationResult
from core.lifecycle.engine import LifecycleEngine
from core.ledger.repository import LedgerRepository
from core.lifecycle.profile import GovernanceProfile, resolve_preset
from core.lifecycle.protocols import ActionRepository, EventBus, Ledger, PolicyEvaluator
from core.policy import (
    ImpactReport,
    PolicyEngine,
    PolicyEnvelope,
    PolicyRepository,
    PolicyStore,
)
from core.ports import HITLPort, IdentityPort
from core.ports.consent import ConsentPort
from core.types import (
    Action,
    ActionId,
    ActionState,
    Actor,
    ActorId,
    IdempotencyKey,
    ModelRef,
    ModelResponse,
    RequestContext,
    TenantId,
)


def _normalize_roles(roles: Any) -> tuple[str, ...]:
    """Normalise role names to the ``role:<name>`` convention used across the kernel (cf. the HITL
    approver matching in core/hitl). Bare names are prefixed; already-prefixed names pass through."""
    return tuple(r if str(r).startswith("role:") else f"role:{r}" for r in roles)


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
    # PolicyRepository (durable policy store backends; CEL engine wired via _build_policy)
    "memory_policy":           ("adapters.policy.memory",            "InMemoryPolicyRepository"),
    "postgres_policy":         ("adapters.policy.postgres",          "PostgresPolicyRepository"),
    # Ledger
    "memory_ledger":           ("adapters.ledger.memory",            "InMemoryLedgerAdapter"),
    "openbao_ledger":          ("adapters.ledger.openbao",           "OpenBaoLedgerAdapter"),
    # LedgerRepository (durable ledger backends; the TrustLedger writes through to these)
    "memory_ledger_repo":      ("adapters.ledger.memory_repo",       "InMemoryLedgerRepository"),
    "postgres_ledger":         ("adapters.ledger.postgres",          "PostgresLedgerRepository"),
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

    Holds all port adapters, the optional AI Gateway, and the governance profiles. Create via
    ``Kernel.from_config(path)`` for production, or ``Kernel.from_parts(...)`` in tests.
    """

    engine: LifecycleEngine
    tenant: TenantId
    gateway: AIGateway | None = None
    default_profile: GovernanceProfile = dataclasses.field(default_factory=GovernanceProfile.all)
    action_profiles: dict[str, GovernanceProfile] = dataclasses.field(default_factory=dict)
    # Set only when the CEL policy engine is wired (policy = "cel_policy"). The store is the
    # in-memory read cache; the repository is its durable backend. Both are exposed so the policy
    # management API (and the SDK write-through primitives below) can author and persist policies.
    policy_store: PolicyStore | None = None
    policy_repository: PolicyRepository | None = None
    # Set when a durable ledger backend is wired ([adapters].ledger_store). Exposed so the kernel can
    # close its pool on shutdown; the TrustLedger writes through to it and hydrates from it on boot.
    ledger_repository: LedgerRepository | None = None
    # Control-plane roles permitted to author/manage policies via the management API. Normalised to
    # the ``role:<name>`` convention. An actor needs at least one of these to use ``/v1/policies``.
    policy_admin_roles: tuple[str, ...] = ("role:policy_admin",)

    @property
    def has_identity(self) -> bool:
        """True if an IdentityPort is wired. The standalone REST API requires this so it never
        trusts a caller-supplied actor."""
        return self.engine.has_identity

    @property
    def has_inference(self) -> bool:
        """True if an AI Gateway (inference adapter) is wired — i.e. ``generate`` is available."""
        return self.gateway is not None

    @property
    def has_policy_store(self) -> bool:
        """True if the CEL policy engine is wired — i.e. policies can be authored/persisted."""
        return self.policy_store is not None

    @property
    def hitl_queue_depth(self) -> int:
        """Number of HITL approvals still pending (dashboard read-model).

        Only the in-process HITL adapter exposes a queryable store; for any other adapter
        (e.g. a webhook adapter whose queue lives in an external system) this returns 0 — the
        dashboard should source that depth from the external system in that deployment.
        """
        from core.hitl.engine import InProcessHITLPort

        hitl = self.engine._hitl  # type: ignore[attr-defined]
        if isinstance(hitl, InProcessHITLPort):
            return hitl._store.pending_count()
        return 0

    def _in_process_hitl(self) -> Any:
        """Return the wired HITL port if it is an in-process (queryable) one, else None.

        Only the in-process adapter exposes a listable approval store; a webhook/external adapter
        keeps its queue in another system, so the control-plane approvals surface is unavailable
        (the route maps None → 503).
        """
        from core.hitl.engine import InProcessHITLPort

        hitl = self.engine._hitl  # type: ignore[attr-defined]
        return hitl if isinstance(hitl, InProcessHITLPort) else None

    def list_pending_approvals(self) -> list[Any]:
        """List pending HITL approval records (operator queue). Empty if no in-process port."""
        hitl = self._in_process_hitl()
        return hitl.list_pending() if hitl is not None else []

    async def decide_approval(self, handle_id: str, *, decision: str, actor: Actor) -> Any:
        """Approve or reject a pending HITL request as ``actor``.

        ``decision`` is ``"approved"`` or ``"rejected"``. Delegates to the HITL port, which enforces
        approver eligibility + the self-approval guard (raises ``HITLPortError`` otherwise). Returns
        the updated ``ApprovalRecord``. Raises ``RuntimeError`` if no in-process HITL port is wired.
        """
        hitl = self._in_process_hitl()
        if hitl is None:
            raise RuntimeError("No in-process HITL port configured — approvals unavailable.")
        if decision == "approved":
            await hitl.approve(
                handle_id, approver_actor_id=actor.id, approver_roles=tuple(actor.roles)
            )
        elif decision == "rejected":
            await hitl.reject(
                handle_id, approver_actor_id=actor.id, approver_roles=tuple(actor.roles)
            )
        else:
            raise ValueError(f"decision must be 'approved' or 'rejected', got {decision!r}")
        return hitl.get_record(handle_id)

    # ── Lifecycle hooks (startup / shutdown) ─────────────────────────────────────

    async def startup(self) -> None:
        """Initialise async resources. Call once before serving (the API does this via lifespan).

        Hydrates the policy store and the durable ledger from their repositories so a restarted
        kernel enforces the same policies and serves the same transparency log. No-op for the
        in-memory backends.
        """
        if self.policy_store is not None:
            await self.policy_store.hydrate()
        ledger_hydrate = getattr(self.engine._ledger, "hydrate", None)  # type: ignore[attr-defined]
        if ledger_hydrate is not None:
            await ledger_hydrate()

    async def shutdown(self) -> None:
        """Release async resources (connection pools). Call once on shutdown."""
        for collaborator in (
            self.policy_repository,
            self.ledger_repository,
            self.engine._ledger,  # type: ignore[attr-defined]
            self.gateway,
        ):
            close = getattr(collaborator, "close", None)
            if close is not None:
                try:
                    await close()
                except Exception:  # noqa: BLE001 — shutdown is best-effort
                    pass

    # ── Identity (control-plane actor resolution) ────────────────────────────────

    async def resolve_actor(
        self, context: RequestContext, *, tenant: TenantId | None = None
    ) -> Actor:
        """Resolve the authenticated actor from a request context via the IdentityPort.

        Used by control-plane surfaces (the policy management API) that authenticate a caller
        outside the run lifecycle. ``tenant`` overrides the kernel's default tenant — required on a
        shared tier-kernel that serves many tenants, so identity is verified against the *request's*
        tenant (F-07), not the kernel's fixed one. Raises ``RuntimeError`` if no IdentityPort is
        wired; propagates ``IdentityPortError`` / ``TenantIsolationError`` fail-closed.
        """
        identity = self.engine.identity
        if identity is None:
            raise RuntimeError("No identity adapter configured.")
        return await identity.resolve_actor(context=context, tenant=tenant or self.tenant)

    # ── Policy authoring (write-through primitives the management API wraps) ──────

    async def register_policy(self, envelope: PolicyEnvelope) -> PolicyEnvelope:
        """Persist a policy envelope and register it in the live store. Requires the CEL engine."""
        if self.policy_store is None:
            raise RuntimeError(
                "No policy store configured — set policy = \"cel_policy\" to author policies."
            )
        return await self.policy_store.register_persisted(envelope)

    async def activate_policy(
        self, policy_id: str, version: int, impact_report: ImpactReport
    ) -> PolicyEnvelope:
        """Run the F-10 activation gate and persist the ACTIVATED policy. Requires the CEL engine."""
        if self.policy_store is None:
            raise RuntimeError("No policy store configured.")
        return await self.policy_store.activate_persisted(policy_id, version, impact_report)

    async def deprecate_policy(self, policy_id: str, version: int) -> PolicyEnvelope:
        """Deprecate a policy (stops matching in lookups) and persist it. Requires the CEL engine."""
        if self.policy_store is None:
            raise RuntimeError("No policy store configured.")
        return await self.policy_store.deprecate_persisted(policy_id, version)

    async def submit_policy_for_review(self, policy_id: str, version: int) -> PolicyEnvelope:
        """Transition a DRAFT policy to REVIEW and persist it. Requires the CEL engine."""
        if self.policy_store is None:
            raise RuntimeError("No policy store configured.")
        return await self.policy_store.submit_for_review_persisted(policy_id, version)

    async def store_policy_impact_report(self, report: ImpactReport) -> None:
        """Persist a policy's F-10 impact report so a later activation can reference it."""
        if self.policy_store is None:
            raise RuntimeError("No policy store configured.")
        await self.policy_store.store_impact_report_persisted(report)

    def resolve_profile(
        self, action_type: str, override: GovernanceProfile | None = None
    ) -> GovernanceProfile:
        """Resolve the governance profile for an action type.

        Precedence: explicit call override > per-action-type config > kernel default.
        """
        if override is not None:
            return override
        return self.action_profiles.get(action_type, self.default_profile)

    # ── Factory ──────────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, path: str | Path) -> "Kernel":
        """Build a Kernel from a TOML config file.

        Selects concrete adapter classes by the names declared under ``[adapters]``. Optionally
        wires the AI Gateway (``[adapters].inference`` + ``[gateway]``) and the governance
        profiles (``[governance]``).
        """
        import tomllib

        with open(path, "rb") as f:
            cfg = tomllib.load(f)

        tenant = TenantId(cfg.get("tenant", {}).get("id", "default"))
        adapter_cfg = cfg.get("adapters", {})

        repo: ActionRepository = _InMemoryActionRepository()
        policy: PolicyEvaluator | None = None
        policy_store: PolicyStore | None = None
        policy_repository: PolicyRepository | None = None
        ledger_repository: LedgerRepository | None = None
        hitl: HITLPort | None = None
        ledger: Ledger | None = None
        events: EventBus | None = None
        identity: IdentityPort | None = None
        consent: ConsentPort | None = None

        if "storage" in adapter_cfg:
            repo = _load_adapter(adapter_cfg["storage"], **cfg.get("storage", {}))
        if "policy" in adapter_cfg:
            if adapter_cfg["policy"] == "cel_policy":
                # The real K·01 CEL engine needs composition (PolicyEngine over a PolicyStore over an
                # optional durable repository), so it is built here rather than via the flat registry.
                policy, policy_store, policy_repository = cls._build_policy(adapter_cfg, cfg)
            else:
                policy = _load_adapter(adapter_cfg["policy"])
        if "hitl" in adapter_cfg:
            hitl = _load_adapter(adapter_cfg["hitl"], **cfg.get("hitl", {}))
        if "ledger" in adapter_cfg:
            ledger, ledger_repository = cls._build_ledger(adapter_cfg, cfg)
        if "events" in adapter_cfg:
            events = _load_adapter(adapter_cfg["events"])
        if "identity" in adapter_cfg:
            identity = _load_adapter(adapter_cfg["identity"], **cfg.get("identity", {}))
        if "consent" in adapter_cfg:
            consent = _load_adapter(adapter_cfg["consent"], **cfg.get("consent", {}))

        if policy is None or hitl is None or ledger is None or events is None:
            raise ValueError(
                "kernel.toml must declare [adapters] for: policy, hitl, ledger, events"
            )

        # Governance profiles (composable enforcement).
        gov_cfg = cfg.get("governance", {})
        default_profile = resolve_preset(gov_cfg.get("default", "all"))
        action_profiles = {
            at: resolve_preset(name)
            for at, name in gov_cfg.get("action_profiles", {}).items()
        }
        policy_admin_roles = _normalize_roles(gov_cfg.get("policy_admin_roles", ["policy_admin"]))

        # Optional AI Gateway for governed inference.
        gateway = cls._build_gateway(tenant, adapter_cfg, cfg) if "inference" in adapter_cfg else None

        engine = LifecycleEngine(
            repository=repo,
            policy=policy,
            hitl=hitl,
            ledger=ledger,
            events=events,
            identity=identity,
            consent=consent,
            default_profile=default_profile,
        )
        return cls(
            engine=engine,
            tenant=tenant,
            gateway=gateway,
            default_profile=default_profile,
            action_profiles=action_profiles,
            policy_store=policy_store,
            policy_repository=policy_repository,
            ledger_repository=ledger_repository,
            policy_admin_roles=policy_admin_roles,
        )

    @staticmethod
    def _build_ledger(
        adapter_cfg: dict[str, Any], cfg: dict[str, Any]
    ) -> tuple[Ledger, LedgerRepository | None]:
        """Assemble the ledger adapter, optionally backed by a durable LedgerRepository.

        ``[adapters].ledger_store`` selects the durable backend (``"postgres_ledger"`` /
        ``"memory_ledger_repo"``); omit it for a non-durable in-memory ledger. Durability is wired
        through the TrustLedger-based ``openbao_ledger`` adapter — the dev ``memory_ledger`` adapter
        does not persist. The ledger hydrates from the repository at ``kernel.startup()``.
        """
        name = adapter_cfg["ledger"]
        ledger_kwargs = cfg.get("ledger", {})
        repository: LedgerRepository | None = None
        if "ledger_store" in adapter_cfg:
            repository = _load_adapter(adapter_cfg["ledger_store"], **cfg.get("ledger_store", {}))
        if name == "openbao_ledger" and repository is not None:
            ledger = _load_adapter(name, **ledger_kwargs, repository=repository)
        else:
            ledger = _load_adapter(name, **ledger_kwargs)
            repository = None  # adapter does not support durability; don't expose an unused pool
        return ledger, repository

    @staticmethod
    def _build_policy(
        adapter_cfg: dict[str, Any], cfg: dict[str, Any]
    ) -> tuple[PolicyEngine, PolicyStore, PolicyRepository | None]:
        """Assemble the K·01 CEL policy engine over a (optionally durable) PolicyStore.

        ``[adapters].policy_store`` selects the durable backend (``"postgres_policy"`` /
        ``"memory_policy"``); omit it for an in-process store with no persistence. The store is
        hydrated from the repository at ``kernel.startup()``, not here (hydration is async).
        """
        repository: PolicyRepository | None = None
        if "policy_store" in adapter_cfg:
            repository = _load_adapter(
                adapter_cfg["policy_store"], **cfg.get("policy_store", {})
            )
        store = PolicyStore(repository=repository)
        return PolicyEngine(store), store, repository

    @staticmethod
    def _build_gateway(
        tenant: TenantId, adapter_cfg: dict[str, Any], cfg: dict[str, Any]
    ) -> AIGateway:
        """Assemble the AI Gateway from the inference adapter + ``[gateway]`` config."""
        inference = _load_adapter(adapter_cfg["inference"], **cfg.get("inference", {}))
        gw_cfg = cfg.get("gateway", {})

        allowlist = InMemoryModelAllowlist()
        for model_id in gw_cfg.get("permitted_models", []):
            allowlist.permit(tenant, str(model_id))

        budget = InMemoryBudgetTracker()
        if gw_cfg.get("max_tokens"):
            budget.set_budget(tenant, max_tokens=int(gw_cfg["max_tokens"]))

        masking_configs = {
            str(tenant): MaskingConfig(
                sensitive_fields=frozenset(gw_cfg.get("sensitive_fields", [])),
                mask_patterns=bool(gw_cfg.get("mask_patterns", True)),
            )
        }
        return AIGateway(
            inference=inference,
            allowlist=allowlist,
            budget=budget,
            masking_configs=masking_configs,
        )

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
        consent: ConsentPort | None = None,
        repository: ActionRepository | None = None,
        gateway: AIGateway | None = None,
        default_profile: GovernanceProfile | None = None,
        action_profiles: dict[str, GovernanceProfile] | None = None,
        policy_store: PolicyStore | None = None,
        policy_repository: PolicyRepository | None = None,
        ledger_repository: LedgerRepository | None = None,
        policy_admin_roles: tuple[str, ...] | None = None,
        max_poll_attempts: int = 1,
    ) -> "Kernel":
        """Build a Kernel directly from collaborator instances (for tests and SDK demos)."""
        profile = default_profile or GovernanceProfile.all()
        engine = LifecycleEngine(
            repository=repository or _InMemoryActionRepository(),
            policy=policy,
            hitl=hitl,
            ledger=ledger,
            events=events,
            identity=identity,
            consent=consent,
            default_profile=profile,
            max_poll_attempts=max_poll_attempts,
        )
        return cls(
            engine=engine,
            tenant=TenantId(str(tenant)),
            gateway=gateway,
            default_profile=profile,
            action_profiles=action_profiles or {},
            policy_store=policy_store,
            policy_repository=policy_repository,
            ledger_repository=ledger_repository,
            policy_admin_roles=(
                _normalize_roles(policy_admin_roles)
                if policy_admin_roles is not None
                else ("role:policy_admin",)
            ),
        )

    # ── Agent binding ──────────────────────────────────────────────────────────

    def for_agent(
        self,
        actor: Actor | str,
        *,
        roles: tuple[str, ...] = (),
        profile: GovernanceProfile | None = None,
    ) -> "BoundAgent":
        """Return a handle whose tool/generate calls are stamped with this agent's identity.

        ``actor`` may be an ``Actor`` or a bare id string (e.g. ``"agent:researcher"``), in which
        case an ``Actor`` is built under this kernel's tenant. In a multi-agent system, give each
        agent its own handle so the ledger attributes every action to the right agent.
        """
        if isinstance(actor, str):
            actor = Actor(id=ActorId(actor), tenant=self.tenant, roles=tuple(roles))
        return BoundAgent(self, actor, profile)

    # ── Governed inference ──────────────────────────────────────────────────────

    async def generate(
        self,
        *,
        prompt_text: str,
        model_ref: ModelRef,
        actor: Actor,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        profile: GovernanceProfile | None = None,
        context: Any | None = None,
        tenant: TenantId | None = None,
    ) -> ModelResponse:
        """Make a governed model call.

        The call becomes an ``inference.generate`` action: the active profile decides which layers
        run (policy/HITL/seal/emit + gateway allowlist/mask/log/budget). The AI Gateway is the
        execute step. Returns the ``ModelResponse`` on success; raises ``LifecycleDeniedError`` /
        ``LifecycleHaltedError`` otherwise.
        """
        if self.gateway is None:
            raise RuntimeError(
                "No inference adapter configured — kernel.generate is unavailable. "
                "Set [adapters].inference and [gateway] in your config."
            )

        action_type = "inference.generate"
        tenant = tenant or self.tenant
        resolved = self.resolve_profile(action_type, profile)
        captured: dict[str, ModelResponse] = {}

        action = Action(
            id=ActionId(str(uuid.uuid4())),
            type=action_type,
            payload={
                "model_id": model_ref.id,
                "model_version": model_ref.version,
                **(payload or {}),
            },
            actor=actor,
            tenant=tenant,
            idempotency_key=IdempotencyKey(idempotency_key or str(uuid.uuid4())),
            proposed_at=datetime.now(tz=timezone.utc),
        )

        async def execute_fn() -> dict[str, Any]:
            resp = await self.gateway.generate(
                prompt_text=prompt_text,
                model_ref=model_ref,
                tenant=tenant,
                action_id=action.id,
                payload=payload,
                profile=resolved,
            )
            captured["response"] = resp
            return dict(resp.recorded_output)

        final = await self.engine.run(action, execute_fn, context=context, profile=resolved)
        self._raise_on_terminal_failure(final, action_type)
        # Surface the action id to the caller (the sealed leaf already covers action.id).
        resp = captured["response"]
        return dataclasses.replace(
            resp, recorded_output={**dict(resp.recorded_output), "action_id": str(final.id)}
        )

    # ── Decision-only (PDP) ─────────────────────────────────────────────────────

    async def check(
        self,
        *,
        action_type: str,
        actor: Actor,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        profile: GovernanceProfile | None = None,
        context: Any | None = None,
        record: bool | None = None,
        tenant: TenantId | None = None,
    ) -> AuthorizationResult:
        """Ask the kernel: "is this action allowed?" without performing it.

        Returns an ``AuthorizationResult`` on all outcomes — never raises on DENY. The caller (the
        enforcement point, or PEP) decides what to do with the verdict.

        When ``record`` is None (the default), the monitoring seal follows the active profile's
        ``seal_to_ledger`` flag: the default ``all()`` profile seals every check into the
        tamper-evident ledger. Pass ``record=False`` to suppress sealing on the hot path.
        """
        resolved = self.resolve_profile(action_type, profile)
        action = self._build_action(action_type, payload or {}, actor, tenant)
        if idempotency_key is not None:
            action = dataclasses.replace(action, idempotency_key=IdempotencyKey(idempotency_key))
        return await self.engine.decide(action, context=context, profile=resolved, record=record)

    # ── Zero-friction integration ────────────────────────────────────────────────

    def actor_context(self, actor: Actor | str, *, roles: tuple[str, ...] = ()):
        """Context manager that binds ``actor`` for all ``guard``/``wrap`` calls inside the block.

        Works as both a sync (``with``) and async (``async with``) context manager so the same
        one-liner covers request handlers, background tasks, and sync code alike.

        Usage::

            async with kernel.actor_context(current_user_actor):
                result = await existing_function(arg1, arg2)  # unchanged call-site

            # String shorthand:
            async with kernel.actor_context("agent:planner"):
                ...

        The actor is task-local (ContextVar): concurrent async tasks each have their own actor and
        cannot see each other's.
        """
        if isinstance(actor, str):
            actor = Actor(id=ActorId(actor), tenant=self.tenant, roles=tuple(roles))
        # Return the async context manager; the sync one is also available via actor_scope.
        return async_actor_scope(actor)

    def set_actor(self, actor: Actor | str, *, roles: tuple[str, ...] = ()) -> None:
        """Imperatively set the governed actor for this async task / thread.

        Prefer ``actor_context`` (auto-cleanup). Use this only when a context manager scope is
        impractical (e.g. long-lived coroutine sessions).
        """
        if isinstance(actor, str):
            actor = Actor(id=ActorId(actor), tenant=self.tenant, roles=tuple(roles))
        set_actor(actor)

    def get_actor(self) -> Actor | None:
        """Return the actor currently bound in this async task / thread, or None."""
        return get_current_actor()

    def guard(
        self,
        *,
        policy: str,
        action_type: str | None = None,
        profile: GovernanceProfile | None = None,
    ) -> Callable:
        """Decorator that governs any existing function **without changing its signature**.

        The actor is resolved from the ContextVar set by ``kernel.actor_context()``.  The
        decorated function's signature, call-sites, and return type are **completely unchanged**.
        Zero codebase modification required.

        Usage::

            # BEFORE — existing function, untouched:
            async def approve_loan(loan_id: str, amount: float) -> dict:
                return await db.approve(loan_id, amount)

            # AFTER — add one decorator line:
            @kernel.guard(policy="loans.approve")
            async def approve_loan(loan_id: str, amount: float) -> dict:
                return await db.approve(loan_id, amount)

            # Caller — add actor_context once at the request boundary:
            async with kernel.actor_context(user_actor):
                result = await approve_loan(loan_id="L-1", amount=5000)  # unchanged

        On DENY the call raises ``LifecycleDeniedError``; on HALT it raises ``LifecycleHaltedError``.
        """
        effective_type = action_type or policy

        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                # Pop actor= if the caller passed it as an escape-hatch override; otherwise use ctx.
                actor: Actor | None = kwargs.pop("actor", None)
                if actor is None:
                    actor = get_current_actor()
                if actor is None:
                    raise RuntimeError(
                        f"@kernel.guard on {fn.__name__!r}: no actor in scope. "
                        "Call this function inside `async with kernel.actor_context(actor): ...` "
                        "or pass actor=<Actor> as a keyword argument."
                    )
                payload = dict(kwargs)
                action = self._build_action(effective_type, payload, actor)
                captured: dict[str, Any] = {}

                async def execute_fn() -> dict[str, Any]:
                    result = fn(*args, **kwargs)
                    if inspect.isawaitable(result):
                        result = await result
                    captured["result"] = result
                    return {"result": result}

                resolved = self.resolve_profile(effective_type, profile)
                final = await self.engine.run(action, execute_fn, profile=resolved)
                self._raise_on_terminal_failure(final, effective_type)
                return captured.get("result")

            wrapper._governed_policy = policy  # type: ignore[attr-defined]
            wrapper._governed_action_type = effective_type  # type: ignore[attr-defined]
            wrapper._zero_friction = True  # type: ignore[attr-defined]
            return wrapper

        return decorator

    def proxy(
        self,
        target: Any,
        *,
        policies: dict[str, str],
        actor: Actor | None = None,
    ) -> Any:
        """Wrap any existing object so that specified method calls are governed before execution.

        ``policies`` maps dotted method paths to policy names. Every listed method goes through
        ``kernel.check()`` before being called on the underlying object; unlisted methods pass
        through unchanged — the proxy is fully transparent to the rest of the codebase.

        Usage::

            client = kernel.proxy(
                openai.AsyncOpenAI(api_key="..."),
                policies={
                    "chat.completions.create": "ai.chat",
                    "embeddings.create":        "ai.embed",
                },
            )

            # Existing code completely unchanged:
            async with kernel.actor_context(user):
                response = await client.chat.completions.create(model="gpt-4", messages=[...])
        """
        from delivery.sdk.proxy import GovernedProxy

        return GovernedProxy(target, policies=policies, kernel=self, actor=actor)

    def wrap(
        self,
        fn: Callable,
        *,
        policy: str,
        action_type: str | None = None,
        actor: Actor | None = None,
        profile: GovernanceProfile | None = None,
    ) -> Callable:
        """Govern any existing callable **without modifying it** — programmatic (non-decorator) form.

        Identical to ``guard`` but applied at call-time rather than definition-time. Use this to
        govern functions you don't own (third-party libraries, imported modules):

        Usage::

            # One line to govern an external function:
            governed_transfer = kernel.wrap(payments_lib.transfer, policy="payments.transfer")

            # Caller unchanged:
            async with kernel.actor_context(user_actor):
                result = await governed_transfer(amount=100, to="ACC-2")

        An explicit ``actor=`` bound at wrap-time takes priority over the ContextVar.
        """
        bound_actor = actor  # bound at wrap-time (optional override)
        effective_type = action_type or policy

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Priority: call-time actor= kwarg > wrap-time bound actor > context var
            act: Actor | None = kwargs.pop("actor", None) or bound_actor or get_current_actor()
            if act is None:
                raise RuntimeError(
                    f"kernel.wrap({fn.__name__!r}): no actor in scope. "
                    "Call inside `async with kernel.actor_context(actor): ...` "
                    "or pass actor=<Actor> as a keyword argument."
                )
            payload = dict(kwargs)
            action = self._build_action(effective_type, payload, act)
            captured: dict[str, Any] = {}

            async def execute_fn() -> dict[str, Any]:
                result = fn(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
                captured["result"] = result
                return {"result": result}

            resolved = self.resolve_profile(effective_type, profile)
            final = await self.engine.run(action, execute_fn, profile=resolved)
            self._raise_on_terminal_failure(final, effective_type)
            return captured.get("result")

        wrapper._governed_policy = policy  # type: ignore[attr-defined]
        wrapper._governed_action_type = effective_type  # type: ignore[attr-defined]
        wrapper._zero_friction = True  # type: ignore[attr-defined]
        return wrapper

    # ── Decorator factories ─────────────────────────────────────────────────────

    def governed(
        self,
        *,
        policy: str,
        action_type: str | None = None,
        profile: GovernanceProfile | None = None,
    ) -> Callable:
        """Decorator factory. Wraps an async function as a governed action.

        The decorated function must accept ``actor: Actor`` as a keyword argument. On COMPLETED the
        final ``Action`` is returned; on DENIED/HALTED it raises. (For tools, prefer
        ``governed_tool``, which returns the function's own result.)
        """
        effective_type = action_type or policy

        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                actor: Actor | None = kwargs.get("actor")
                if actor is None:
                    raise TypeError(
                        f"@governed function {fn.__name__!r} must receive actor=<Actor> as a kwarg"
                    )
                payload = {k: v for k, v in kwargs.items() if k != "actor"}
                action = self._build_action(effective_type, payload, actor)

                async def execute_fn() -> Any:
                    return await fn(*args, **kwargs)

                resolved = self.resolve_profile(effective_type, profile)
                final = await self.engine.run(action, execute_fn, profile=resolved)
                self._raise_on_terminal_failure(final, effective_type)
                return final

            wrapper._governed_policy = policy  # type: ignore[attr-defined]
            wrapper._governed_action_type = effective_type  # type: ignore[attr-defined]
            return wrapper

        return decorator

    def governed_tool(
        self,
        *,
        policy: str,
        name: str | None = None,
        actor: Actor | None = None,
        profile: GovernanceProfile | None = None,
    ) -> Callable:
        """Decorator factory for an agent tool. Governs the call and returns the tool's own result.

        Unlike ``governed``, this returns whatever the wrapped tool returns (not the Action) — which
        is what an agent framework expects. Works on sync or async tools. The actor may be bound (via
        ``for_agent``) or passed as ``actor=`` at call time. On DENIED/HALTED it raises.
        """
        effective_type = name or policy

        def decorator(fn: Callable) -> Callable:
            @functools.wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                act: Actor | None = kwargs.pop("actor", None) or actor
                if act is None:
                    raise TypeError(
                        f"governed tool {fn.__name__!r} needs an actor — bind one with "
                        "kernel.for_agent(...) or pass actor=<Actor> at call time"
                    )
                payload = {k: v for k, v in kwargs.items()}
                action = self._build_action(effective_type, payload, act)
                captured: dict[str, Any] = {}

                async def execute_fn() -> dict[str, Any]:
                    result = fn(*args, **kwargs)
                    if inspect.isawaitable(result):
                        result = await result
                    captured["result"] = result
                    # Seal a dict (recorded_result is a Mapping); the leaf hash covers the value.
                    return {"result": result}

                resolved = self.resolve_profile(effective_type, profile)
                final = await self.engine.run(action, execute_fn, profile=resolved)
                self._raise_on_terminal_failure(final, effective_type)
                return captured.get("result")

            wrapper._governed_policy = policy  # type: ignore[attr-defined]
            wrapper._governed_action_type = effective_type  # type: ignore[attr-defined]
            return wrapper

        return decorator

    # ── Internal helpers ─────────────────────────────────────────────────────────

    def _build_action(
        self,
        action_type: str,
        payload: dict[str, Any],
        actor: Actor,
        tenant: TenantId | None = None,
    ) -> Action:
        return Action(
            id=ActionId(str(uuid.uuid4())),
            type=action_type,
            payload=payload,
            actor=actor,
            tenant=tenant or self.tenant,
            idempotency_key=IdempotencyKey(str(uuid.uuid4())),
            proposed_at=datetime.now(tz=timezone.utc),
        )

    @staticmethod
    def _raise_on_terminal_failure(final: Action, action_type: str) -> None:
        if final.state is ActionState.DENIED:
            raise LifecycleDeniedError(
                f"Action {final.id} denied by governance",
                detail={"action_id": str(final.id), "type": action_type},
            )
        if final.state is ActionState.HALTED:
            raise LifecycleHaltedError(
                f"Action {final.id} halted by governance",
                detail={"action_id": str(final.id), "type": action_type},
            )


# ── Bound agent handle ──────────────────────────────────────────────────────────


class BoundAgent:
    """A kernel handle bound to one agent's ``Actor``.

    Every tool or model call made through it is attributed to that agent in the ledger, enabling
    per-agent audit trails in a multi-agent system.
    """

    def __init__(
        self, kernel: Kernel, actor: Actor, profile: GovernanceProfile | None = None
    ) -> None:
        self._kernel = kernel
        self._actor = actor
        self._profile = profile

    @property
    def actor(self) -> Actor:
        return self._actor

    def tool(
        self,
        *,
        policy: str,
        name: str | None = None,
        profile: GovernanceProfile | None = None,
    ) -> Callable:
        """Decorator: govern this agent's tool, attributed to this agent."""
        return self._kernel.governed_tool(
            policy=policy, name=name, actor=self._actor, profile=profile or self._profile
        )

    async def generate(
        self,
        *,
        prompt_text: str,
        model_ref: ModelRef,
        payload: dict[str, Any] | None = None,
        profile: GovernanceProfile | None = None,
    ) -> ModelResponse:
        """Make a governed model call attributed to this agent."""
        return await self._kernel.generate(
            prompt_text=prompt_text,
            model_ref=model_ref,
            actor=self._actor,
            payload=payload,
            profile=profile or self._profile,
        )

    async def check(
        self,
        *,
        action_type: str,
        payload: dict[str, Any] | None = None,
        profile: GovernanceProfile | None = None,
        record: bool | None = None,
    ) -> "AuthorizationResult":
        """Ask whether this agent is allowed to perform an action, without performing it."""
        return await self._kernel.check(
            action_type=action_type,
            actor=self._actor,
            payload=payload,
            profile=profile or self._profile,
            record=record,
        )
