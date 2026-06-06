"""HITLPort (K·03) — FROZEN. Routes approval requests to humans. The gate step of the lifecycle."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.types import Action, ApprovalDecision, ApprovalHandle, ApproverRef, TenantId


@runtime_checkable
class HITLPort(Protocol):
    """Human-in-the-loop gate. Implementations: webhook (default), email, slack, inapp.

    Fail-closed contract:
      - Timeout → the caller treats the outcome as REJECTED (never approved).
      - Approver unreachable / dispatch failed → raise `HITLPortError`; the caller HALTS.
      - The port does NOT decide who may approve — approver authority is enforced by the lifecycle,
        not the adapter.
    """

    async def request_approval(
        self,
        *,
        action: Action,
        approvers: list[ApproverRef],
        tenant: TenantId,
    ) -> ApprovalHandle:
        """Dispatch an approval request and return a handle for polling.

        Raises:
            HITLPortError: the request could not be dispatched.
        """
        ...

    async def poll(self, handle: ApprovalHandle) -> ApprovalDecision:
        """Poll for a decision.

        Returns:
            ApprovalDecision: PENDING | APPROVED | REJECTED | TIMED_OUT. TIMED_OUT is a valid
            terminal outcome the lifecycle treats as REJECTED (fail-closed).

        Raises:
            HITLPortError: the poll backend is unreachable.
        """
        ...
