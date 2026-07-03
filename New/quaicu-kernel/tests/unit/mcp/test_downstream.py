"""HttpDownstream: opens an mcp client (Streamable HTTP or SSE) to the tenant's downstream and
forwards list/call, reusing a shared httpx client (keep-alive). No network."""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

pytest.importorskip("mcp")

from core.account.model import MCPConnection  # noqa: E402
from delivery.mcp import downstream as dstream  # noqa: E402
from delivery.mcp.downstream import HttpDownstream, _NoCloseClient  # noqa: E402

_captured: dict = {}


class _FakeClientSession:
    def __init__(self, read, write) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def initialize(self):
        _captured["initialized"] = True

    async def list_tools(self):
        return "LIST_RESULT"

    async def call_tool(self, name, arguments):
        _captured["call"] = (name, arguments)
        return "CALL_RESULT"


def _fake_streamablehttp_client(url, headers=None, httpx_client_factory=None, **_):
    _captured["transport"] = "streamable_http"
    _captured["url"] = url
    _captured["headers"] = headers
    _captured["factory"] = httpx_client_factory

    @asynccontextmanager
    async def _cm():
        yield ("read", "write", lambda: None)  # 3-tuple

    return _cm()


def _fake_sse_client(url, headers=None, httpx_client_factory=None, **_):
    _captured["transport"] = "sse"
    _captured["url"] = url
    _captured["headers"] = headers
    _captured["factory"] = httpx_client_factory

    @asynccontextmanager
    async def _cm():
        yield ("read", "write")  # 2-tuple

    return _cm()


@pytest.fixture(autouse=True)
def _patch_mcp(monkeypatch):
    import mcp
    import mcp.client.sse as sse
    import mcp.client.streamable_http as sh

    monkeypatch.setattr(mcp, "ClientSession", _FakeClientSession)
    monkeypatch.setattr(sh, "streamablehttp_client", _fake_streamablehttp_client)
    monkeypatch.setattr(sse, "sse_client", _fake_sse_client)
    _captured.clear()


async def test_streamable_http_forwards_call_with_shared_factory():
    conn = MCPConnection(url="https://tools.acme.io/mcp", auth_value="Bearer sk", auth_header="Authorization")
    ds = HttpDownstream.from_connection(conn)

    result = await ds.call_tool("search", {"q": "x"})

    assert result == "CALL_RESULT"
    assert _captured["transport"] == "streamable_http"
    assert _captured["url"] == "https://tools.acme.io/mcp"
    assert _captured["headers"] == {"Authorization": "Bearer sk"}
    assert _captured["call"] == ("search", {"q": "x"})
    assert _captured["initialized"] is True
    # The shared-client factory was passed (HTTP keep-alive) and yields a no-close wrapper.
    assert _captured["factory"] is dstream._shared_client_factory
    assert isinstance(_captured["factory"](), _NoCloseClient)


async def test_sse_transport_uses_sse_client():
    conn = MCPConnection(url="https://tools.acme.io/sse", transport="sse")
    ds = HttpDownstream.from_connection(conn)
    assert await ds.list_tools() == "LIST_RESULT"
    assert _captured["transport"] == "sse"
    assert _captured["headers"] == {}  # no auth configured


async def test_noclose_wrapper_does_not_close_shared_client():
    # The shared client survives an mcp client's `async with factory() as c: ...` exit + aclose().
    calls = {"closed": 0}

    class _FakeShared:
        is_closed = False

        async def aclose(self):
            calls["closed"] += 1

    wrapper = _NoCloseClient(_FakeShared())
    async with wrapper as c:
        assert c is wrapper
    await wrapper.aclose()
    assert calls["closed"] == 0  # never propagated to the shared client


def test_empty_url_rejected():
    with pytest.raises(ValueError):
        HttpDownstream("")


def test_bad_transport_rejected():
    with pytest.raises(ValueError):
        HttpDownstream("https://x/mcp", transport="ws")
