"""Per-tenant BYO downstream MCP connection (the MCP twin of /v1/ai/connection).

    GET    /v1/mcp/connection   → masked status of the tenant's downstream MCP server
    PUT    /v1/mcp/connection   → set/replace it (url, auth, name)
    DELETE /v1/mcp/connection   → remove it

The hosted `/mcp` endpoint (when running in BYO-proxy mode) reads this connection per request to
mirror the tenant's own tools and govern+forward each call. The secret is stored encrypted and shown
back only masked.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.errors import QUAICUError

router = APIRouter(prefix="/v1/mcp", tags=["mcp-gateway"])


def _principal(request: Request):
    from delivery.api.auth import current_principal

    p = current_principal(request)
    if p is None:
        raise HTTPException(
            status_code=401, detail={"error": "Authentication required", "code": "AUTH_REQUIRED"}
        )
    return p


def _engine(request: Request):
    engine = getattr(request.app.state, "account_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail={"error": "Account management is not enabled", "code": "ACCOUNTS_DISABLED"},
        )
    return engine


_TRANSPORTS = ("streamable_http", "sse")


class ConnectionBody(BaseModel):
    url: str = Field(..., description="Downstream MCP server URL")
    auth_value: str = Field("", description="Secret sent to your downstream (e.g. 'Bearer …'); stored encrypted")
    auth_header: str = Field("Authorization", description="Header name carrying the secret")
    transport: str = Field("streamable_http", description="Downstream transport: streamable_http | sse")
    name: str = Field("", description="Display label")


@router.get("/connection", summary="Get this tenant's downstream MCP connection (masked)")
async def get_connection(request: Request) -> dict:
    principal = _principal(request)
    status = _engine(request).mcp_connection_status(principal.tenant_id)
    return status or {"connected": False}


@router.put("/connection", summary="Set/replace this tenant's downstream MCP connection")
async def put_connection(body: ConnectionBody, request: Request) -> dict:
    principal = _principal(request)
    if not body.url.strip():
        raise HTTPException(
            status_code=422,
            detail={"error": "url is required", "code": "MCP_CONNECTION_INVALID"},
        )
    transport = (body.transport or "streamable_http").strip()
    if transport not in _TRANSPORTS:
        raise HTTPException(
            status_code=422,
            detail={
                "error": f"transport must be one of {_TRANSPORTS}",
                "code": "MCP_CONNECTION_INVALID",
            },
        )
    engine = _engine(request)
    try:
        engine.set_mcp_connection(
            principal.tenant_id,
            url=body.url.strip(),
            auth_value=body.auth_value.strip(),
            auth_header=body.auth_header.strip() or "Authorization",
            transport=transport,
            name=body.name.strip(),
        )
    except QUAICUError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc), "code": exc.code})
    return engine.mcp_connection_status(principal.tenant_id) or {"connected": False}


@router.delete("/connection", summary="Remove this tenant's downstream MCP connection")
async def delete_connection(request: Request) -> dict:
    principal = _principal(request)
    removed = _engine(request).clear_mcp_connection(principal.tenant_id)
    return {"connected": False, "removed": removed}
