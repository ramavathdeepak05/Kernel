"""D2-2: gateway governs provider tool calls (policy + seal + fail-closed block), per shim.

The gateway forwards chat verbatim; a tool call the model asks to make appears in the *response*
(OpenAI `tool_calls`, Anthropic `tool_use`, Bedrock `toolUse`). Each is sealed as an `ai.tool_call`
action; any denial fails the whole response (non-stream → 403, stream → SSE error event).
"""

from __future__ import annotations

from datetime import datetime, timezone

from httpx import ASGITransport, AsyncClient

import delivery.api.ai_providers as ap
import delivery.api.routes.ai_gateway as gw
from core.account import Account, AccountEngine, AccountStatus, AccountStore
from core.entitlements import EntitlementStore
from core.types import Action, Decision, EvaluationResult, TenantId
from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel
from tests.unit.lifecycle.fakes import FakeEvents, FakeHITL, FakeIdentity, FakeLedger

_TENANT = "acme"


class _ToolAwarePolicy:
    """ALLOW everything except `ai.tool_call`, which takes a configured decision — so the chat call
    is admitted and only the tool call is gated (isolates tool-call governance from chat governance).
    """

    def __init__(self, *, tool_decision: Decision = Decision.ALLOW) -> None:
        self.tool_decision = tool_decision
        self.seen: list[str] = []

    async def evaluate(self, action: Action) -> EvaluationResult:
        self.seen.append(action.type)
        decision = self.tool_decision if action.type == "ai.tool_call" else Decision.ALLOW
        return EvaluationResult(decision=decision, policy_versions=("v1",), approvers=())


def _build(policy, *, provider="openai", base_url="https://api.openai.com/v1"):
    accounts = AccountStore()
    accounts.add_account(
        Account(
            account_id="acct_acme",
            tenant_id=TenantId(_TENANT),
            email="acme@b.io",
            name="acme",
            status=AccountStatus.ACTIVE,
            created_at=datetime.now(timezone.utc),
        )
    )
    eng = AccountEngine(accounts, EntitlementStore(), pepper="p", session_secret="s")
    eng.set_ai_connection(
        TenantId(_TENANT), provider=provider, base_url=base_url, api_key="sk-tenant",
        default_model="gpt-4o-mini", mask_pii=False,
    )
    ledger = FakeLedger()
    kernel = Kernel.from_parts(
        tenant=TenantId(_TENANT), policy=policy, hitl=FakeHITL(), ledger=ledger,
        events=FakeEvents(), identity=FakeIdentity(),
    )
    app = create_app(kernel, account_engine=eng, require_api_key=True, rate_limit=False)
    _, key = eng.issue_api_key(TenantId(_TENANT))
    return app, key, ledger


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "X-Tenant-Id": _TENANT}


_OPENAI_TOOL_CALL = {
    "id": "call_1", "type": "function",
    "function": {"name": "wire_transfer", "arguments": '{"amount": 5000}'},
}


class _OpenAIToolClient:
    """Fake upstream returning an OpenAI response that carries a tool_call."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        class _Resp:
            status_code = 200

            def json(self_inner):
                return {
                    "id": "cmpl_1", "object": "chat.completion", "model": "gpt-4o-mini",
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": None, "tool_calls": [_OPENAI_TOOL_CALL]},
                        "finish_reason": "tool_calls",
                    }],
                }

            text = ""

        return _Resp()


async def _post_chat(app, key, body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/v1/ai/chat/completions", headers=_auth(key), json=body)


async def test_openai_tool_call_allowed_passes_through_and_seals(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _OpenAIToolClient)
    policy = _ToolAwarePolicy(tool_decision=Decision.ALLOW)
    app, key, ledger = _build(policy)
    resp = await _post_chat(app, key, {"messages": [{"role": "user", "content": "pay"}], "tools": []})
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "wire_transfer"
    # Both the chat and the tool call were sealed.
    assert "ai.chat" in policy.seen and "ai.tool_call" in policy.seen
    assert len(ledger.sealed) >= 2


async def test_openai_tool_call_denied_blocks_whole_response(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _OpenAIToolClient)
    app, key, _ = _build(_ToolAwarePolicy(tool_decision=Decision.DENY))
    resp = await _post_chat(app, key, {"messages": [{"role": "user", "content": "pay"}]})
    assert resp.status_code == 403
    err = resp.json()["error"]
    assert err["code"] == "GOVERNANCE_DENIED" and "wire_transfer" in err["message"]


class _AnthropicToolClient(_OpenAIToolClient):
    async def post(self, url, json=None, headers=None):
        class _Resp:
            status_code = 200

            def json(self_inner):
                return {
                    "id": "msg_1", "model": "claude-3-5",
                    "content": [{"type": "tool_use", "id": "tu1", "name": "wire_transfer",
                                 "input": {"amount": 5000}}],
                    "stop_reason": "tool_use",
                    "usage": {"input_tokens": 3, "output_tokens": 4},
                }

            text = ""

        return _Resp()


async def test_anthropic_tool_use_is_translated_and_governed(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _AnthropicToolClient)
    app, key, _ = _build(_ToolAwarePolicy(tool_decision=Decision.DENY),
                         provider="anthropic", base_url="https://api.anthropic.com")
    resp = await _post_chat(app, key, {"messages": [{"role": "user", "content": "pay"}]})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "GOVERNANCE_DENIED"


async def test_bedrock_tooluse_is_translated_and_governed(monkeypatch):
    class _FakeBedrock:
        def converse(self, modelId, **kw):
            return {
                "output": {"message": {"content": [
                    {"toolUse": {"toolUseId": "tu1", "name": "wire_transfer", "input": {"amount": 5000}}}
                ]}},
                "stopReason": "tool_use",
                "usage": {"inputTokens": 4, "outputTokens": 3},
            }

    monkeypatch.setattr(ap, "_BEDROCK", ap.BedrockShim(client_factory=lambda conn: _FakeBedrock()))
    app, key, _ = _build(_ToolAwarePolicy(tool_decision=Decision.DENY), provider="bedrock", base_url="")
    resp = await _post_chat(app, key, {"messages": [{"role": "user", "content": "pay"}]})
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "GOVERNANCE_DENIED"


# ── Streaming: buffer tool_call deltas, seal at end, emit only if allowed ───────────


class _StreamClient:
    """Streams a text delta, then a tool_call delta, then a finish chunk + [DONE]."""

    lines = [
        'data: {"choices":[{"index":0,"delta":{"role":"assistant","content":"working"},"finish_reason":null}]}',
        'data: {"choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function",'
        '"function":{"name":"wire_transfer","arguments":"{\\"amount\\":5000}"}}]},"finish_reason":null}]}',
        'data: {"choices":[{"index":0,"delta":{},"finish_reason":"tool_calls"}]}',
        "data: [DONE]",
    ]

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def stream(self, method, url, json=None, headers=None):
        lines = self.lines

        class _S:
            async def __aenter__(self_inner):
                return self_inner

            async def __aexit__(self_inner, *a):
                return False

            async def aiter_lines(self_inner):
                for ln in lines:
                    yield ln

        return _S()


async def test_streaming_tool_call_allowed_emits_after_text(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _StreamClient)
    app, key, _ = _build(_ToolAwarePolicy(tool_decision=Decision.ALLOW))
    resp = await _post_chat(app, key, {"messages": [{"role": "user", "content": "pay"}], "stream": True})
    assert resp.status_code == 200
    body = resp.text
    assert "working" in body and "wire_transfer" in body and body.rstrip().endswith("[DONE]")
    # Text chunk precedes the (buffered-then-flushed) tool_call chunk.
    assert body.index("working") < body.index("wire_transfer")


async def test_streaming_tool_call_denied_emits_error_event(monkeypatch):
    monkeypatch.setattr(gw.httpx, "AsyncClient", _StreamClient)
    app, key, _ = _build(_ToolAwarePolicy(tool_decision=Decision.DENY))
    resp = await _post_chat(app, key, {"messages": [{"role": "user", "content": "pay"}], "stream": True})
    assert resp.status_code == 200  # headers already sent → error surfaces in-stream
    body = resp.text
    assert "GOVERNANCE_DENIED" in body
    # Text still streamed, but the buffered tool_call chunk (its arguments) was never emitted.
    assert "working" in body and "5000" not in body
