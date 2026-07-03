"""Hosted (multi-tenant) MCP over Streamable HTTP.

Turns a tools-only `GovernedMCPServer` into an authenticated, per-tenant ASGI endpoint: every request
carries an ``Authorization: Bearer <qk_…>`` API key, which is resolved to (tenant, actor, kernel) and
used to govern the tool call and seal it to that tenant's ledger — the direct analogue of the BYO AI
gateway. One endpoint serves every tenant; onboarding is just issuing an API key.

`build_streamable_http_app` wires the server's per-request identity resolver to read the transport's
Starlette request (`request_context.request`) and authenticate it, then wraps the MCP
`StreamableHTTPSessionManager` (json responses, stateless — no sticky sessions, scales horizontally).
The returned session manager's ``run()`` MUST be entered in the app lifespan.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from delivery.mcp.auth import MCPAuthenticator
from delivery.mcp.downstream import HttpDownstream
from delivery.mcp.proxy import ProxySession

log = logging.getLogger("quaicu.mcp.http")


def _has_bearer(scope: dict[str, Any]) -> bool:
    for key, value in scope.get("headers", []):
        if key == b"authorization" and value.strip().lower().startswith(b"bearer "):
            return True
    return False


async def _send_json(send: Any, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


def build_proxy_resolver(authenticator: MCPAuthenticator, account_engine: Any) -> Any:
    """A per-request resolver for the BYO-downstream proxy: authenticate → the tenant's downstream.

    Returns ``resolve(request) -> ProxySession``. Fail-closed: a tenant with no configured downstream
    gets a clear error (their agent is told to register one at ``PUT /v1/mcp/connection``).
    """

    def _resolve(request: Any) -> ProxySession:
        session = authenticator.resolve(request)  # verifies the API key → (tenant, actor, kernel)
        conn = account_engine.get_mcp_connection(session.tenant)
        if conn is None or not conn.url:
            raise RuntimeError(
                f"Tenant {session.tenant} has no downstream MCP server configured — "
                "register one at PUT /v1/mcp/connection."
            )
        return ProxySession(session.kernel, session.actor, HttpDownstream.from_connection(conn))

    return _resolve


def build_streamable_http_app(governed: Any, *, resolve_from_request: Any) -> tuple[Any, Any]:
    """Wire a governed MCP server/proxy to an authenticated Streamable-HTTP ASGI app.

    ``governed`` is a ``GovernedMCPServer`` (operator-registered tools) or a ``GovernedMCPProxy``
    (BYO downstream) — anything exposing ``build_mcp_server()`` + ``bind_session_resolver()``.
    ``resolve_from_request(request) -> session`` maps the transport's Starlette request to the
    per-request session the governed object expects (``authenticator.resolve`` for a server;
    ``build_proxy_resolver(...)`` for a proxy).

    Returns ``(asgi_app, session_manager)``. The caller mounts ``asgi_app`` and MUST enter
    ``session_manager.run()`` for the app's lifetime (it owns the request task group).
    """
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    low_level = governed.build_mcp_server()

    def _resolve() -> Any:
        # `request_context.request` is the Starlette Request the transport attaches per call; read it
        # here (inside the server task) and resolve → per-tenant session. Fail-closed.
        return resolve_from_request(low_level.request_context.request)

    governed.bind_session_resolver(_resolve)

    # json_response: single-JSON replies (safe under the app's BaseHTTP middleware; no SSE).
    # stateless: no server-side session state → no sticky routing, scales with --workers>1.
    manager = StreamableHTTPSessionManager(low_level, json_response=True, stateless=True)

    async def asgi_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await _send_json(send, 400, {"error": "MCP endpoint speaks HTTP only", "code": "BAD_TRANSPORT"})
            return
        # Reject an unauthenticated probe early (defense in depth — the handlers also fail closed, so
        # the tool catalogue / calls are never reachable without a valid tenant key).
        if not _has_bearer(scope):
            await _send_json(send, 401, {"error": "Missing API key", "code": "API_KEY_REQUIRED"})
            return
        await manager.handle_request(scope, receive, send)

    return asgi_app, manager
