from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import UTC, datetime

from core.types import ActionId, ActorId, ApprovalDecision, ApproverRef, TenantId


@dataclass(frozen=True)
class ApprovalRecord:
    """Full record of a HITL approval request, including WHO decided (resolves the open ADR)."""

    handle_id: str
    action_id: ActionId
    tenant: TenantId
    required_approvers: tuple[ApproverRef, ...]
    requested_at: datetime
    decision: ApprovalDecision = ApprovalDecision.PENDING
    decided_by: ActorId | None = None
    decided_at: datetime | None = None
    expires_at: datetime | None = None

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at

    def with_decision(
        self,
        decision: ApprovalDecision,
        decided_by: ActorId | None = None,
        decided_at: datetime | None = None,
    ) -> ApprovalRecord:
        return dataclasses.replace(
            self,
            decision=decision,
            decided_by=decided_by,
            decided_at=decided_at or datetime.now(UTC),
        )
