"""AI-assisted CEL policy authoring (K·01 helper).

Turns a plain-English rule ("loans over 1,000,000 need a human") into a candidate CEL policy a
non-expert can review and submit through the normal DRAFT→REVIEW→backtest→ACTIVATE lifecycle. It is a
*drafting aid*, not an authority: the suggestion is always validated by **actually compiling the CEL**
against the same `celpy` engine the kernel runs, so the assistant never hands back a broken expression.

Hexagonal/fail-closed:
- Core depends only on `InferencePort` (F-08) — no model SDK here; the model is whatever adapter the
  deployment wires (Vertex/OpenAI-compat/Ollama). The call is fail-closed via the port's contract.
- The LLM output is untrusted: we parse it defensively and mark `valid=False` (never raise) when the
  model returns malformed JSON or non-compiling CEL, so the endpoint degrades gracefully.

The CEL is written against the kernel's activation schema (see `core/policy/evaluator.py`):
``action_type``, ``action_tenant``, ``actor_id``, ``actor_roles`` (list), and ``payload_<field>`` for
each flattened payload field.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from core.types import Decision, ModelRef, Prompt, TenantId

# The InferencePort contract; imported for typing only (string annotation avoids a hard import cycle).
try:  # pragma: no cover - typing convenience
    from core.ports.inference import InferencePort
except Exception:  # pragma: no cover
    InferencePort = object  # type: ignore[assignment,misc]


_DECISIONS = {d.value for d in Decision}


def validate_cel(condition: str) -> tuple[bool, str | None]:
    """Compile ``condition`` with celpy exactly as the policy store does. Returns (ok, error)."""
    if not condition or not condition.strip():
        return False, "empty condition"
    try:
        import celpy

        env = celpy.Environment()
        env.program(env.compile(condition))
        return True, None
    except Exception as exc:  # noqa: BLE001 — any compile/parse failure is an invalid suggestion
        return False, str(exc)


@dataclass(frozen=True)
class PolicySuggestion:
    """A drafted CEL policy for human review before it enters the DRAFT→…→ACTIVATE lifecycle."""

    condition: str
    decision: str               # "allow" | "deny" | "require_approval"
    explanation: str
    valid: bool                 # did the CEL compile against the engine?
    error: str | None = None    # why it is not valid / not usable
    warnings: tuple[str, ...] = ()
    raw_model_output: str = ""


_SYSTEM_RULES = """\
You translate a plain-English governance rule into a single QUAICU CEL policy.

Output STRICT JSON only (no prose, no markdown fences):
{"condition": "<CEL boolean expression>", "decision": "allow|deny|require_approval", "explanation": "<one sentence>"}

CEL variables available (use EXACTLY these names; payload fields are flattened and prefixed):
- action_type        (string)   e.g. "loan.approve"
- action_tenant      (string)
- actor_id           (string)
- actor_roles        (list<string>)   use: "role:x" in actor_roles
- payload_<field>    one per payload field, typed (string/int/double/bool), e.g. payload_amount

Rules:
- The condition is the set of actions the decision applies to (true => the decision is returned).
- Prefer the least-privilege decision the rule implies (deny / require_approval over allow).
- Only reference variables that plausibly exist for the action; do not invent CEL functions.
- Keep it to one boolean expression.

Example:
Rule: "Loan approvals over 1,000,000 must be approved by a human."
{"condition": "action_type == \\"loan.approve\\" && payload_amount > 1000000", "decision": "require_approval", "explanation": "High-value loan approvals are routed to human approval."}
"""


def _build_prompt(
    description: str,
    *,
    action_types: list[str] | None,
    payload_fields: list[str] | None,
    actor_roles: list[str] | None,
) -> str:
    ctx_lines = []
    if action_types:
        ctx_lines.append(f"Known action_type values: {', '.join(action_types)}")
    if payload_fields:
        ctx_lines.append(f"Known payload variables: {', '.join('payload_' + f for f in payload_fields)}")
    if actor_roles:
        ctx_lines.append(f"Known actor roles: {', '.join(actor_roles)}")
    context = ("\nContext from this tenant's observed actions:\n" + "\n".join(ctx_lines)) if ctx_lines else ""
    return f"{_SYSTEM_RULES}{context}\n\nRule: {description.strip()}\n"


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response (tolerates fences / surrounding prose)."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match is None:
            raise ValueError("no JSON object in model response")
        return json.loads(match.group(0))


class PolicyAuthoringAssistant:
    """Draft a CEL policy from natural language via an `InferencePort`, validated by real compilation."""

    def __init__(self, inference: "InferencePort", *, model_ref: ModelRef) -> None:
        self._inference = inference
        self._model_ref = model_ref

    async def suggest(
        self,
        *,
        description: str,
        tenant: TenantId,
        action_types: list[str] | None = None,
        payload_fields: list[str] | None = None,
        actor_roles: list[str] | None = None,
    ) -> PolicySuggestion:
        """Draft a `PolicySuggestion`. Never raises on bad LLM output — returns ``valid=False``."""
        prompt = _build_prompt(
            description,
            action_types=action_types,
            payload_fields=payload_fields,
            actor_roles=actor_roles,
        )
        # Inference errors (model down / timeout) propagate as the port's fail-closed exceptions.
        resp = await self._inference.generate(
            prompt=Prompt(text=prompt, metadata={"purpose": "policy_authoring", "temperature": 0}),
            model_ref=self._model_ref,
            tenant=tenant,
        )
        raw = resp.content or ""

        try:
            obj = _extract_json(raw)
        except Exception as exc:  # noqa: BLE001 — malformed model output is a soft failure
            return PolicySuggestion(
                condition="", decision="deny", explanation="",
                valid=False, error=f"could not parse a policy from the model: {exc}",
                raw_model_output=raw,
            )

        condition = str(obj.get("condition", "")).strip()
        decision = str(obj.get("decision", "")).strip().lower()
        explanation = str(obj.get("explanation", "")).strip()

        warnings: list[str] = []
        if decision not in _DECISIONS:
            warnings.append(f"model returned unknown decision {decision!r}; defaulting to require_approval")
            decision = Decision.REQUIRE_APPROVAL.value
        warnings.extend(_unknown_variable_warnings(condition, payload_fields))

        ok, err = validate_cel(condition)
        return PolicySuggestion(
            condition=condition,
            decision=decision,
            explanation=explanation,
            valid=ok,
            error=err,
            warnings=tuple(warnings),
            raw_model_output=raw,
        )


_PAYLOAD_VAR_RE = re.compile(r"\bpayload_([A-Za-z0-9_]+)\b")


def _unknown_variable_warnings(condition: str, payload_fields: list[str] | None) -> list[str]:
    """Warn (don't fail) when the CEL references payload vars not in the tenant's observed set."""
    if not payload_fields:
        return []
    known = {f"payload_{f}" for f in payload_fields}
    referenced = {m.group(0) for m in _PAYLOAD_VAR_RE.finditer(condition)}
    unknown = sorted(referenced - known)
    return [f"references payload variable not seen in this tenant's actions: {v}" for v in unknown]
