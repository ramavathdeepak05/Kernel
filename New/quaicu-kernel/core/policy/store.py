"""K·01 Policy Engine — in-memory policy store.

Responsibilities:
- Compile CEL at `register` time so evaluation never silently uses a broken expression.
- Enforce the F-10 simulation gate at `activate` time: a policy moves REVIEW → ACTIVATED only
  with a matching, acknowledged `ImpactReport`.
- `lookup` returns only ACTIVATED policies that match (action_type, tenant_id), applying the
  specificity rule: both exact-tenant and wildcard policies are returned; conflict resolution
  happens in the evaluator, not here.

Thread-safety: a `threading.Lock` guards all mutations. The store is synchronous because no async
DB exists in Wave 1 (the storage adapter replaces this in Wave 2 without changing the evaluator).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import celpy

from core.errors import PolicyActivationError, PolicyCompileError
from core.policy.model import ImpactReport, PolicyEnvelope, PolicyLifecycle

log = logging.getLogger("quaicu.policy")


def _compile_cel(condition: str) -> tuple[Any, Any]:
    """Compile a CEL expression and return (env, program).

    Raises `PolicyCompileError` on any parse or type-check failure so the author gets immediate
    feedback at registration time rather than a runtime DENY on every evaluation.
    """
    try:
        env = celpy.Environment()
        ast = env.compile(condition)
        prog = env.program(ast)
        return env, prog
    except Exception as exc:
        raise PolicyCompileError(
            f"CEL compile failed for expression {condition!r}: {exc}",
            detail={"condition": condition, "cause": str(exc)},
        ) from exc


class PolicyStore:
    """Mutable (Wave 1) in-memory registry of all policy envelopes.

    Wave 2 will replace the storage layer with a Postgres-backed adapter implementing the same
    interface; this class becomes the in-process cache / write-through layer at that point.
    """

    def __init__(self) -> None:
        # Primary index: (policy_id, version) → PolicyEnvelope
        self._policies: dict[tuple[str, int], PolicyEnvelope] = {}
        # Impact-report index: (policy_id, version) → ImpactReport
        self._impact_reports: dict[tuple[str, int], ImpactReport] = {}
        self._lock = threading.Lock()

    # ── Authoring ───────────────────────────────────────────────────────────────

    def register(self, envelope: PolicyEnvelope) -> PolicyEnvelope:
        """Compile the CEL condition and store the envelope.

        Returns the stored envelope (with `compiled_condition` populated).
        Raises `PolicyCompileError` if the CEL expression is syntactically invalid.
        ACTIVATED policies cannot be re-registered; create a new version instead.
        """
        _env, prog = _compile_cel(envelope.condition)
        # frozen=True prevents normal attribute assignment; use object.__setattr__ as sanctioned
        # by the dataclass docs for exactly this post-init population pattern.
        stored = object.__new__(PolicyEnvelope)
        object.__setattr__(stored, "id", envelope.id)
        object.__setattr__(stored, "version", envelope.version)
        object.__setattr__(stored, "governs", envelope.governs)
        object.__setattr__(stored, "scope", envelope.scope)
        object.__setattr__(stored, "condition", envelope.condition)
        object.__setattr__(stored, "decision", envelope.decision)
        object.__setattr__(stored, "approvers", envelope.approvers)
        object.__setattr__(stored, "regulatory_refs", envelope.regulatory_refs)
        object.__setattr__(stored, "lifecycle", envelope.lifecycle)
        object.__setattr__(stored, "compiled_condition", prog)

        with self._lock:
            self._policies[(envelope.id, envelope.version)] = stored

        log.info("policy registered: %s@v%d (lifecycle=%s)", envelope.id, envelope.version, envelope.lifecycle.value)
        return stored

    def store_impact_report(self, report: ImpactReport) -> None:
        """Persist an impact report so `activate` can verify it."""
        with self._lock:
            self._impact_reports[(report.policy_id, report.policy_version)] = report

    def activate(self, policy_id: str, version: int, impact_report: ImpactReport) -> PolicyEnvelope:
        """Transition a REVIEW policy to ACTIVATED.

        F-10 gate: the `impact_report` must:
        - Match `policy_id` and `version`.
        - Have `acknowledged == True`.

        Raises `PolicyActivationError` if any precondition fails.
        """
        if not impact_report.acknowledged:
            raise PolicyActivationError(
                f"Impact report for {policy_id}@v{version} is not acknowledged — cannot activate.",
                detail={"policy_id": policy_id, "version": version},
            )

        if impact_report.policy_id != policy_id or impact_report.policy_version != version:
            raise PolicyActivationError(
                f"Impact report mismatch: report is for {impact_report.policy_id}@v{impact_report.policy_version}, "
                f"but activation requested for {policy_id}@v{version}.",
                detail={
                    "policy_id": policy_id,
                    "version": version,
                    "report_policy_id": impact_report.policy_id,
                    "report_version": impact_report.policy_version,
                },
            )

        with self._lock:
            key = (policy_id, version)
            envelope = self._policies.get(key)
            if envelope is None:
                raise PolicyActivationError(
                    f"Policy {policy_id}@v{version} not found in the store.",
                    detail={"policy_id": policy_id, "version": version},
                )

            if envelope.lifecycle not in (PolicyLifecycle.REVIEW, PolicyLifecycle.ACTIVATED):
                raise PolicyActivationError(
                    f"Policy {policy_id}@v{version} is in lifecycle state {envelope.lifecycle.value!r}; "
                    "only REVIEW policies may be activated.",
                    detail={"policy_id": policy_id, "version": version, "lifecycle": envelope.lifecycle.value},
                )

            # Build the activated envelope (same compiled_condition, new lifecycle value).
            activated = object.__new__(PolicyEnvelope)
            object.__setattr__(activated, "id", envelope.id)
            object.__setattr__(activated, "version", envelope.version)
            object.__setattr__(activated, "governs", envelope.governs)
            object.__setattr__(activated, "scope", envelope.scope)
            object.__setattr__(activated, "condition", envelope.condition)
            object.__setattr__(activated, "decision", envelope.decision)
            object.__setattr__(activated, "approvers", envelope.approvers)
            object.__setattr__(activated, "regulatory_refs", envelope.regulatory_refs)
            object.__setattr__(activated, "lifecycle", PolicyLifecycle.ACTIVATED)
            object.__setattr__(activated, "compiled_condition", envelope.compiled_condition)

            self._policies[key] = activated
            self._impact_reports[key] = impact_report

        log.info("policy activated: %s@v%d (reviewed_by=%s)", policy_id, version, impact_report.reviewed_by)
        return activated

    # ── Query ───────────────────────────────────────────────────────────────────

    def lookup(self, action_type: str, tenant_id: str) -> list[PolicyEnvelope]:
        """Return all ACTIVATED policies that govern `action_type` for `tenant_id`.

        Scope matching rules:
        - `{"tenant": "exact-id"}` matches only that tenant.
        - `{"tenant": "*"}` matches any tenant.
        - Both are returned if they match — conflict resolution is the evaluator's job.
        - `governs: "*"` matches any action type.
        """
        with self._lock:
            candidates = list(self._policies.values())

        result: list[PolicyEnvelope] = []
        for env in candidates:
            if env.lifecycle is not PolicyLifecycle.ACTIVATED:
                continue

            # action-type filter
            if env.governs != "*" and env.governs != action_type:
                continue

            # tenant-scope filter
            scope_tenant = env.scope.get("tenant", "*")
            if scope_tenant != "*" and scope_tenant != tenant_id:
                continue

            result.append(env)

        return result
