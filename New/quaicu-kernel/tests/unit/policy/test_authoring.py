"""Unit tests for the AI-assisted CEL policy authoring helper (core/policy/authoring.py).

A fake InferencePort returns canned model output, so no real model is called. The key guarantee under
test: the assistant validates the CEL by actually compiling it, and degrades gracefully (never raises)
on malformed model output."""

from __future__ import annotations

import json

from core.policy.authoring import PolicyAuthoringAssistant, PolicySuggestion, validate_cel
from core.types import ModelRef, ModelResponse, Prompt, TenantId

TENANT = TenantId("acme")
MODEL = ModelRef(id="test-model", version="1")


class _FakeInference:
    """InferencePort stub: returns a fixed content and captures the prompt it was given."""

    def __init__(self, content: str) -> None:
        self._content = content
        self.last_prompt: Prompt | None = None

    async def generate(self, *, prompt: Prompt, model_ref: ModelRef, tenant: TenantId) -> ModelResponse:
        self.last_prompt = prompt
        return ModelResponse(content=self._content, model_id=model_ref.id, recorded_output={})


def _assistant(content: str) -> tuple[PolicyAuthoringAssistant, _FakeInference]:
    inf = _FakeInference(content)
    return PolicyAuthoringAssistant(inf, model_ref=MODEL), inf


# ── validate_cel ──────────────────────────────────────────────────────────────


def test_validate_cel_accepts_valid_expression():
    ok, err = validate_cel('action_type == "loan.approve" && payload_amount > 1000000')
    assert ok and err is None


def test_validate_cel_rejects_garbage():
    ok, err = validate_cel("this is not (cel")
    assert not ok and err


def test_validate_cel_rejects_empty():
    ok, err = validate_cel("   ")
    assert not ok


# ── suggest() ───────────────────────────────────────────────────────────────


async def test_suggest_parses_and_validates_clean_json():
    content = json.dumps({
        "condition": 'action_type == "loan.approve" && payload_amount > 1000000',
        "decision": "require_approval",
        "explanation": "High-value loans need a human.",
    })
    assistant, _ = _assistant(content)
    s = await assistant.suggest(description="loans over 1M need a human", tenant=TENANT)
    assert isinstance(s, PolicySuggestion)
    assert s.valid is True and s.error is None
    assert s.decision == "require_approval"
    assert "loan.approve" in s.condition


async def test_suggest_tolerates_markdown_fences_and_prose():
    content = "Sure! Here is the policy:\n```json\n" + json.dumps({
        "condition": 'action_type == "x"', "decision": "deny", "explanation": "block x",
    }) + "\n```\n"
    assistant, _ = _assistant(content)
    s = await assistant.suggest(description="block x", tenant=TENANT)
    assert s.valid is True and s.decision == "deny"


async def test_suggest_marks_invalid_cel_without_raising():
    content = json.dumps({
        "condition": "action_type == (broken", "decision": "deny", "explanation": "x",
    })
    assistant, _ = _assistant(content)
    s = await assistant.suggest(description="x", tenant=TENANT)
    assert s.valid is False and s.error  # compiled → caught, surfaced, not raised


async def test_suggest_handles_non_json_model_output():
    assistant, _ = _assistant("I'm not sure how to express that rule.")
    s = await assistant.suggest(description="???", tenant=TENANT)
    assert s.valid is False and "could not parse" in (s.error or "")


async def test_suggest_normalizes_unknown_decision():
    content = json.dumps({"condition": 'action_type == "x"', "decision": "BLOCK", "explanation": "x"})
    assistant, _ = _assistant(content)
    s = await assistant.suggest(description="x", tenant=TENANT)
    assert s.decision == "require_approval"  # unknown → safest decision
    assert any("unknown decision" in w for w in s.warnings)


async def test_suggest_warns_on_unknown_payload_variable():
    content = json.dumps({
        "condition": "payload_ssn != \"\"", "decision": "deny", "explanation": "x",
    })
    assistant, _ = _assistant(content)
    s = await assistant.suggest(description="x", tenant=TENANT, payload_fields=["amount"])
    assert any("payload_ssn" in w for w in s.warnings)


async def test_prompt_includes_schema_and_context():
    assistant, inf = _assistant(json.dumps({"condition": "true", "decision": "allow", "explanation": "x"}))
    await assistant.suggest(
        description="allow everything",
        tenant=TENANT,
        action_types=["loan.approve"],
        payload_fields=["amount"],
        actor_roles=["role:analyst"],
    )
    text = inf.last_prompt.text
    assert "action_type" in text and "payload_<field>" in text and "actor_roles" in text
    assert "loan.approve" in text and "payload_amount" in text  # tenant context threaded in
