"""Policy Engine — Rules-as-Data DSL Interpreter

MODULE: Core Infrastructure
LAYER: Layer 1 + Layer 3 (Domain Logic + State Machine enforcement)
REFERENCE: ALIS-skills/references/architecture.md §10

This module makes ALIS multi-institution without code forks.
Every threshold, rule, or progression criterion that differs between
institutions is stored in `tenant_policies` JSONB and evaluated here
at runtime.

Usage
─────
    from server.core.policy_engine import policy_engine

    result = policy_engine.evaluate(
        policy_id="attendance_eligibility",
        context={
            "student": {
                "attendance_pct": 71.5,
                "category": "SC",
                "has_valid_reason": True,
            }
        },
        tenant_id=tenant_id,
    )
    # result.verdict   → "ELIGIBLE" | "INELIGIBLE" | "CONDONATION_PENDING" | ...
    # result.reason_code → e.g. "ATTENDANCE_BELOW_MINIMUM"
    # result.rule_id     → which rule fired
    # result.policy_version → integer version — store in audit log

    # Simple value lookup (no rule evaluation)
    threshold = policy_engine.get_value("attendance.minimum_threshold", tenant_id, default=75)

CRITICAL Rules
──────────────
- NEVER use Python eval() for policy expressions — asteval is the only safe evaluator
- NEVER evaluate a policy with status != 'APPROVED' — DRAFT policies are invisible to the engine
- NEVER call the LLM for eligibility/progression/penalty decisions — rules engine only
- Every call to evaluate() must record result.policy_version in the audit log
- Policy cache is per (tenant_id, policy_id) — invalidate on policy approval

Must Align With
───────────────
- architecture.md §10 (Policy Engine — Rules-as-Data)
- SKILL.md invariant 2 (Configuration is data, not code)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from server.core.settings import settings
from server.db_service import execute_query

logger = logging.getLogger(__name__)

# Redis TTL for policy cache entries (seconds)
_POLICY_CACHE_TTL = 300  # 5 minutes


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class PolicyResult:
    """The outcome of a PolicyEngine.evaluate() call.

    Always persist policy_version in the audit log for regulatory traceability.
    """

    verdict: str  # "ELIGIBLE" | "INELIGIBLE" | outcome codes
    reason_code: str | None = None  # machine-readable reason (for UI / audit)
    rule_id: str | None = None  # which rule produced this verdict
    policy_id: str | None = None
    policy_version: int | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def formatted_reason(self) -> str:
        """Human-readable decision summary for ops teams and audit display.

        Example output:
            Decision: ELIGIBLE
            Reason: ATTENDANCE_MEETS_THRESHOLD (Policy v3, Rule r1)
        """
        parts = [f"Decision: {self.verdict}"]
        if self.reason_code:
            rule_ref = f"Rule {self.rule_id}" if self.rule_id else "default"
            policy_ref = (
                f"Policy v{self.policy_version}"
                if self.policy_version
                else "unversioned"
            )
            parts.append(f"Reason: {self.reason_code} ({policy_ref}, {rule_ref})")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Safe expression evaluator
# ---------------------------------------------------------------------------


def _build_evaluator_namespace(
    context: dict[str, Any],
    rule_params: dict[str, Any],
) -> dict[str, Any]:
    """Merge rule-level params and context into a flat namespace for asteval.

    Nested dict access (e.g. student.attendance_pct) is flattened by
    materialising each top-level key as both a dict AND via dotted attribute
    access using a simple SimpleNamespace wrapper.

    Rule params (threshold: 75) shadow nothing — they are prefixed by their
    own names and are distinct from context keys.
    """
    from types import SimpleNamespace

    ns: dict[str, Any] = {}

    # 1. Inject rule-level params at the top level
    #    e.g. threshold=75, relaxed_categories=["SC","ST"]
    for k, v in rule_params.items():
        ns[k] = v

    # 2. Inject context variables
    #    Top-level keys become SimpleNamespace objects so that
    #    "student.attendance_pct" resolves as attribute lookup.
    for top_key, value in context.items():
        if isinstance(value, dict):
            ns[top_key] = SimpleNamespace(**value)
        else:
            ns[top_key] = value

    return ns


def _safe_eval(expression: str, namespace: dict[str, Any]) -> bool:
    """Evaluate a DSL boolean expression using asteval.

    Falls back to False (safe deny) if asteval is unavailable or the
    expression fails — always log the error.

    Expression examples:
        "student.attendance_pct >= threshold"
        "student.attendance_pct >= condonation_min AND student.has_valid_reason"
        "student.category IN relaxed_categories AND student.attendance_pct >= relaxed_threshold"
        "fee_days_overdue > grace_period_days"
    """
    # Normalise 'AND' / 'OR' → 'and' / 'or' for Python semantics
    expr = expression.replace(" AND ", " and ").replace(" OR ", " or ")
    # Normalise 'IN' → 'in'
    expr = expr.replace(" IN ", " in ")

    try:
        from asteval import Interpreter

        aeval = Interpreter(usersyms=namespace, minimal=False, no_print=True)
        result = aeval(expr)
        if aeval.error:
            for err in aeval.error:
                logger.warning(
                    "policy_engine: asteval error in %r — %s",
                    expression,
                    err.get_error(),
                )
            return False
        return bool(result)
    except ImportError:
        logger.error(
            "policy_engine: asteval not installed. "
            "Run: pip install asteval  OR add to requirements.txt"
        )
        return False
    except Exception as exc:
        logger.error("policy_engine: expression %r failed — %s", expression, exc)
        return False


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------


class PolicyEngine:
    """Evaluates tenant-specific policy rules stored in `tenant_policies`."""

    # ------------------------------------------------------------------
    # Policy loading
    # ------------------------------------------------------------------

    @staticmethod
    def _cache_key(tenant_id: str, policy_id: str) -> str:
        return f"alis:policy:{tenant_id}:{policy_id}"

    @staticmethod
    def _get_redis():
        import redis as _redis_lib

        return _redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)

    def _load_policy(self, policy_id: str, tenant_id: str) -> dict[str, Any] | None:
        """Load the active (APPROVED, currently effective) policy from cache or DB.

        Returns None if no active policy exists for this key.
        DRAFT policies are never loaded — hard invariant.
        """
        # 1. Try Redis cache
        try:
            r = self._get_redis()
            cached = r.get(self._cache_key(tenant_id, policy_id))
            if cached is not None:
                return json.loads(cached)
        except Exception as exc:
            logger.warning("policy_engine: Redis unavailable for load — %s", exc)

        # 2. DB: most recent APPROVED policy that is currently effective
        rows = execute_query(
            """
            SELECT id, policy_id, version, scope, rules, effective_from, effective_until
            FROM tenant_policies
            WHERE tenant_id = %s
              AND policy_id = %s
              AND status = 'APPROVED'
              AND effective_from <= NOW()
              AND (effective_until IS NULL OR effective_until > NOW())
            ORDER BY version DESC
            LIMIT 1
            """,
            (tenant_id, policy_id),
            tenant_id=tenant_id,
        )
        if not rows:
            return None

        policy = dict(rows[0])
        # Ensure rules is a Python object (psycopg2 returns JSONB as dict already)
        if isinstance(policy.get("rules"), str):
            policy["rules"] = json.loads(policy["rules"])

        # Cache for TTL — use explicit serialisation to avoid type loss.
        # json.dumps(default=str) would silently convert datetimes to strings,
        # causing type mismatches (str vs datetime) when rules compare dates.
        def _json_serial(obj):
            if hasattr(obj, "isoformat"):
                return obj.isoformat()
            if hasattr(obj, "hex"):  # UUID
                return str(obj)
            raise TypeError(f"Cannot serialise type: {type(obj)}")

        try:
            r = self._get_redis()
            r.setex(
                self._cache_key(tenant_id, policy_id),
                _POLICY_CACHE_TTL,
                json.dumps(policy, default=_json_serial),
            )
        except Exception:
            pass  # noqa: S110 — intentionally suppressed

        return policy

    # ------------------------------------------------------------------
    # Rule evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        policy_id: str,
        context: dict[str, Any],
        tenant_id: str,
        default_verdict: str = "INELIGIBLE",
        actor_id: str = "system",
        entity_id: str | None = None,
    ) -> PolicyResult:
        """Evaluate a policy against the provided context.

        Rules are evaluated in order. First match wins (short-circuit).
        If no rule fires, default_verdict is returned.

        SECURITY: default_verdict defaults to "INELIGIBLE" (deny-by-default)
        to align with the ALIS Engineering Constitution's default-deny posture.
        Call sites that require permissive defaults (e.g. informational lookups)
        must explicitly pass default_verdict="ELIGIBLE".

        Every evaluation is automatically traced to the immutable audit
        ledger (action=POLICY_EVALUATED) with the full inputs snapshot,
        the condition expression that fired, and a human-readable reason.

        Args:
            policy_id:       Dot-notation policy key e.g. "attendance_eligibility"
            context:         Runtime data dict — shape defined per policy
            tenant_id:       Institution UUID
            default_verdict: Outcome if no rule fires
            actor_id:        Who triggered this evaluation (default "system")
            entity_id:       Business entity being evaluated (e.g. student UUID)

        Returns:
            PolicyResult with verdict, reason_code, rule_id, policy_version,
            and a formatted_reason property for human-readable display.
        """
        # Local import avoids circular dependency (audit → policy_engine)
        from server.core.audit import AuditAction, AuditLog

        def _trace(result: PolicyResult, condition: str | None = None) -> None:
            """Persist a decision trace to the immutable audit ledger."""
            try:
                AuditLog.log(
                    action=AuditAction.POLICY_EVALUATED,
                    actor_id=actor_id,
                    actor_type="system",
                    actor_role=None,
                    entity_type="policy",
                    entity_id=entity_id or policy_id,
                    tenant_id=tenant_id,
                    metadata={
                        "policy_id": policy_id,
                        "policy_version": result.policy_version,
                        "rule_id": result.rule_id,
                        "verdict": result.verdict,
                        "reason_code": result.reason_code,
                        "condition": condition,
                        "inputs_snapshot": context,
                        "formatted": result.formatted_reason,
                    },
                )
            except Exception as exc:
                # Trace failure must never block the evaluation result
                logger.error(
                    "policy_engine: audit trace failed for policy '%s' — %s",
                    policy_id,
                    exc,
                )

        policy = self._load_policy(policy_id, tenant_id)
        if policy is None:
            logger.warning(
                "policy_engine: no APPROVED policy '%s' for tenant %s — returning default '%s'",
                policy_id,
                tenant_id,
                default_verdict,
            )
            result = PolicyResult(
                verdict=default_verdict,
                reason_code="NO_POLICY_FOUND",
                policy_id=policy_id,
            )
            _trace(result)
            return result

        rules: list[dict[str, Any]] = policy.get("rules", [])
        version: int = policy.get("version", 0)

        for rule in rules:
            rule_id = rule.get("id", "unknown")
            condition = rule.get("condition", "")

            if not condition:
                continue

            # Build namespace: rule-level params + context variables
            # Exclude known structural keys; auto_execute_if is reserved for Phase D
            rule_params = {
                k: v
                for k, v in rule.items()
                if k
                not in {
                    "id",
                    "condition",
                    "on_pass",
                    "on_fail",
                    "reason_code",
                    "auto_execute_if",
                }
            }
            namespace = _build_evaluator_namespace(context, rule_params)

            passed = _safe_eval(condition, namespace)

            if passed and rule.get("on_pass"):
                result = PolicyResult(
                    verdict=rule["on_pass"],
                    reason_code=rule.get("reason_code"),
                    rule_id=rule_id,
                    policy_id=policy_id,
                    policy_version=version,
                )
                # Phase D: evaluate auto_execute_if if policy master switch is on
                if policy.get("allow_auto_execute", False):
                    auto_cond = rule.get("auto_execute_if", "")
                    if auto_cond and _safe_eval(
                        auto_cond, _build_evaluator_namespace(context, {})
                    ):
                        result.detail["auto_execute"] = True
                _trace(result, condition)
                return result

            if not passed and rule.get("on_fail"):
                result = PolicyResult(
                    verdict=rule["on_fail"],
                    reason_code=rule.get("reason_code"),
                    rule_id=rule_id,
                    policy_id=policy_id,
                    policy_version=version,
                )
                _trace(result, condition)
                return result

        # No rule fired — return the caller-specified default
        result = PolicyResult(
            verdict=default_verdict,
            reason_code="NO_RULE_FIRED",
            policy_id=policy_id,
            policy_version=version,
        )
        _trace(result)
        return result

    # ------------------------------------------------------------------
    # Simple value lookup (no rule evaluation)
    # ------------------------------------------------------------------

    def get_value(
        self,
        key: str,
        tenant_id: str,
        default: Any = None,
    ) -> Any:
        """Read a scalar configuration value from `tenant_config` by dotted key.

        This is the canonical way to access any tenant-specific threshold,
        percentage, or constant that differs per institution.

        Args:
            key:      Dotted key e.g. "attendance.minimum_threshold"
            tenant_id: Institution UUID
            default:  Returned when key is absent for this tenant

        Usage:
            threshold = policy_engine.get_value("attendance.minimum_threshold", tid, 75)
        """
        cache_key = f"alis:config:{tenant_id}:{key}"

        # Try Redis
        try:
            r = self._get_redis()
            cached = r.get(cache_key)
            if cached is not None:
                return json.loads(cached)
        except Exception:
            pass  # noqa: S110 — intentionally suppressed

        # DB: tenant_config is a flat key-value store with JSONB values
        rows = execute_query(
            "SELECT config_value FROM tenant_config WHERE tenant_id = %s AND config_key = %s",
            (tenant_id, key),
            tenant_id=tenant_id,
        )
        if not rows:
            return default

        value = rows[0]["config_value"]

        # Cache
        try:
            r = self._get_redis()
            r.setex(cache_key, _POLICY_CACHE_TTL, json.dumps(value, default=str))
        except Exception:
            pass  # noqa: S110 — intentionally suppressed

        return value

    # ------------------------------------------------------------------
    # Cache invalidation
    # ------------------------------------------------------------------

    def invalidate(self, policy_id: str, tenant_id: str) -> None:
        """Invalidate the cached policy after approval or version bump."""
        try:
            self._get_redis().delete(self._cache_key(tenant_id, policy_id))
        except Exception:
            pass  # noqa: S110 — intentionally suppressed

    def invalidate_config(self, key: str, tenant_id: str) -> None:
        """Invalidate a cached tenant_config value."""
        try:
            self._get_redis().delete(f"alis:config:{tenant_id}:{key}")
        except Exception:
            pass  # noqa: S110 — intentionally suppressed


# Module-level singleton
policy_engine = PolicyEngine()
