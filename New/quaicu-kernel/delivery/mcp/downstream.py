"""HTTP downstream client for the BYO-downstream hosted MCP endpoint.

`HttpDownstream` satisfies the proxy's `Downstream` protocol (`delivery/mcp/proxy.py`) by talking to a
tenant's own downstream MCP server over **Streamable HTTP** or **SSE**. Each call opens a fresh mcp
client *session* (connect → initialize → call): MCP sessions are stateful and their anyio streams are
task-bound, so in a stateless multi-worker server they cannot be safely pooled across requests.

What *is* pooled is the underlying **HTTP connection**: a single shared `httpx.AsyncClient` per worker
(per event loop) is passed to the mcp client so TCP/TLS connections to downstreams stay warm across
calls (httpx pools per host internally). The `mcp` SDK is imported lazily.
"""

from __future__ import annotations

import asyncio
from typing import Any

from core.account.model import MCPConnection

# One shared httpx client per event loop (a worker has one loop; workers are separate processes each
# with their own). Keyed by loop id so a client is never used across loops.
_shared_clients: dict[int, Any] = {}


def _shared_http_client() -> Any:
    import httpx

    loop_id = id(asyncio.get_running_loop())
    client = _shared_clients.get(loop_id)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(follow_redirects=True, timeout=30.0)
        _shared_clients[loop_id] = client
    return client


async def aclose_shared_clients() -> None:
    """Close the shared downstream HTTP clients (best-effort; call from the app lifespan shutdown)."""
    for client in list(_shared_clients.values()):
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001 — shutdown best-effort
            pass
    _shared_clients.clear()


class _NoCloseClient:
    """Delegates to a shared `httpx.AsyncClient` but makes close/exit no-ops.

    The mcp client uses its ``httpx_client_factory`` as ``async with factory(...) as client``, whose
    ``__aexit__`` would otherwise close our shared client. This wrapper keeps the shared client (and
    its warm connection pool) alive across calls.
    """

    def __init__(self, client: Any) -> None:
        self._client = client

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    async def __aenter__(self) -> "_NoCloseClient":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def aclose(self) -> None:  # never close the shared client
        return None


def _shared_client_factory(
    headers: dict[str, str] | None = None, timeout: Any = None, auth: Any = None
) -> _NoCloseClient:
    """An mcp ``httpx_client_factory`` that reuses the per-loop shared client (keep-alive)."""
    return _NoCloseClient(_shared_http_client())


class HttpDownstream:
    """Front a tenant's downstream MCP server (Streamable HTTP or SSE) as a `Downstream`."""

    def __init__(
        self, url: str, headers: dict[str, str] | None = None, *, transport: str = "streamable_http"
    ) -> None:
        if not url:
            raise ValueError("HttpDownstream requires a downstream MCP url.")
        if transport not in ("streamable_http", "sse"):
            raise ValueError(f"Unsupported MCP transport {transport!r}; use 'streamable_http' or 'sse'.")
        self._url = url
        self._headers = headers or {}
        self._transport = transport

    @classmethod
    def from_connection(cls, conn: MCPConnection) -> "HttpDownstream":
        headers: dict[str, str] = {}
        if conn.auth_value:
            headers[conn.auth_header or "Authorization"] = conn.auth_value
        return cls(conn.url, headers, transport=conn.transport or "streamable_http")

    async def list_tools(self) -> Any:
        async with self._session() as session:
            return await session.list_tools()

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        async with self._session() as session:
            return await session.call_tool(name, arguments)

    # ── internal ────────────────────────────────────────────────────────────────
    def _session(self):
        """An async context manager yielding an initialised `ClientSession` to the downstream.

        A fresh mcp session per call (task-bound streams → not poolable); the HTTP connection under it
        is reused via the shared-client factory.
        """
        from contextlib import asynccontextmanager

        from mcp import ClientSession

        url, headers, transport = self._url, self._headers, self._transport

        @asynccontextmanager
        async def _open():
            if transport == "sse":
                from mcp.client.sse import sse_client

                async with sse_client(
                    url, headers=headers, httpx_client_factory=_shared_client_factory
                ) as (read, write):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield session
            else:
                from mcp.client.streamable_http import streamablehttp_client

                async with streamablehttp_client(
                    url, headers=headers, httpx_client_factory=_shared_client_factory
                ) as (read, write, _get_id):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        yield session

        return _open()
