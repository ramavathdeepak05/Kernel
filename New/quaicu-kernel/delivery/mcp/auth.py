"""Per-request tenant authentication for the hosted (multi-tenant) MCP endpoint.

The hosted MCP transport authenticates **every** request from its ``Authorization: Bearer <qk_…>``
API key and routes it to that tenant's kernel — the same trust model as the BYO AI gateway. A
resolved session carries the tenant, the governance actor derived from the verified principal, and
the tenant's kernel; the MCP tool handler then governs the call against *that* kernel and seals to
*that* tenant's ledger.

The API key is cryptographically verified (HMAC lookup in the ``AccountEngine``), so the resolved
principal is a trusted host identity, not a spoofable caller claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.account import AuthenticatedPrincipal
from core.errors import ApiKeyInvalidError
from core.types import Actor, ActorId, TenantId
from delivery.sdk.kernel import Kernel


@dataclass(frozen=True)
class ResolvedSession:
    """The tenant identity + kernel a single MCP request is governed under."""

    tenant: TenantId
    actor: Actor
    kernel: Kernel


def actor_from_principal(principal: AuthenticatedPrincipal, tenant: TenantId) -> Actor:
    """Build the governance actor from a verified API-key principal (mirrors deps.resolve_governed_actor).

    The actor id is the principal's ``subject`` — a member-bound key carries the member id (distinct
    actor → separation-of-duties holds), the account/bootstrap key carries the account id.
    """
    return Actor(
        id=ActorId(str(principal.subject or principal.account_id)),
        tenant=tenant,
        roles=tuple(principal.roles or ()),
    )


class MCPAuthenticator:
    """Resolve a per-request ``ResolvedSession`` from an MCP HTTP request's bearer API key."""

    def __init__(self, account_engine: Any, provider: Any) -> None:
        self._accounts = account_engine
        self._provider = provider

    @staticmethod
    def _bearer(request: Any) -> str | None:
        header = request.headers.get("authorization", "") if request is not None else ""
        scheme, _, token = header.partition(" ")
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()
        return None

    def resolve(self, request: Any) -> ResolvedSession:
        """Verify the request's API key and resolve (tenant, actor, kernel). Fail-closed.

        Raises ``ApiKeyInvalidError`` when the bearer is missing or does not verify — the transport
        maps that to 401 / an MCP error so the call never runs ungoverned.
        """
        token = self._bearer(request)
        if token is None:
            raise ApiKeyInvalidError("Missing API key on MCP request")
        principal: AuthenticatedPrincipal = self._accounts.resolve_principal(token)
        tenant = principal.tenant_id
        kernel = self._provider.kernel_for(tenant)
        return ResolvedSession(tenant=tenant, actor=actor_from_principal(principal, tenant), kernel=kernel)
