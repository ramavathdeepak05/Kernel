from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from core.errors import HITLPortError
from core.hitl.model import ApprovalRecord
from core.hitl.store import ApprovalStore
from core.types import Action, ActorId, ApprovalDecision, ApprovalHandle, ApproverRef, TenantId

log = logging.getLogger("quaicu.hitl")


class InProcessHITLPort:
    """
    Programmatic HITL port for sovereign tier and testing.

    Usage:
        port = InProcessHITLPort(timeout_seconds=3600)
        handle = await port.request_approval(action=..., approvers=..., tenant=...)
        decision = await port.poll(handle)

        await port.approve(handle.id, approver_actor_id=ActorId("bob"))
        await port.reject(handle.id, approver_actor_id=ActorId("carol"))
    """

    def __init__(
        self,
        timeout_seconds: int = 86400,
        store: ApprovalStore | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._store = store or ApprovalStore()

    # ── HITLPort protocol ────────────────────────────────────────────────────

    async def request_approval(
        self,
        *,
        action: Action,
        approvers: list[ApproverRef],
        tenant: TenantId,
    ) -> ApprovalHandle:
        handle_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        record = ApprovalRecord(
            handle_id=handle_id,
            action_id=action.id,
            tenant=tenant,
            required_approvers=tuple(approvers),
            requested_at=now,
            expires_at=now + timedelta(seconds=self._timeout_seconds) if self._timeout_seconds > 0 else None,
        )
        self._store.put(record)
        log.info(
            "HITL request created: handle=%s action=%s approvers=%s",
            handle_id,
            action.id,
            approvers,
        )
        return ApprovalHandle(id=handle_id, tenant=tenant, created_at=now)

    async def poll(self, handle: ApprovalHandle) -> ApprovalDecision:
        record = self._store.get(handle.id)
        if record is None:
            raise HITLPortError(
                f"ApprovalHandle {handle.id!r} not found.",
                detail={"handle_id": handle.id},
            )
        if record.decision is not ApprovalDecision.PENDING:
            return record.decision
        if record.is_expired(datetime.now(UTC)):
            timed_out = record.with_decision(ApprovalDecision.TIMED_OUT)
            self._store.update(timed_out)
            log.info("HITL timed out: handle=%s action=%s", handle.id, record.action_id)
            return ApprovalDecision.TIMED_OUT
        return ApprovalDecision.PENDING

    # ── External control (admin / test surface) ──────────────────────────────

    async def approve(self, handle_id: str, *, approver_actor_id: ActorId) -> None:
        record = self._store.get(handle_id)
        if record is None:
            raise HITLPortError(f"Handle {handle_id!r} not found.")
        if record.decision is not ApprovalDecision.PENDING:
            raise HITLPortError(
                f"Handle {handle_id!r} already decided: {record.decision.value}."
            )
        if record.is_expired(datetime.now(UTC)):
            raise HITLPortError(f"Handle {handle_id!r} has expired.")
        self._assert_authorized(approver_actor_id, record.required_approvers)
        approved = record.with_decision(
            ApprovalDecision.APPROVED, decided_by=approver_actor_id
        )
        self._store.update(approved)
        log.info("HITL approved: handle=%s by=%s", handle_id, approver_actor_id)

    async def reject(self, handle_id: str, *, approver_actor_id: ActorId) -> None:
        record = self._store.get(handle_id)
        if record is None:
            raise HITLPortError(f"Handle {handle_id!r} not found.")
        if record.decision is not ApprovalDecision.PENDING:
            raise HITLPortError(
                f"Handle {handle_id!r} already decided: {record.decision.value}."
            )
        self._assert_authorized(approver_actor_id, record.required_approvers)
        rejected = record.with_decision(
            ApprovalDecision.REJECTED, decided_by=approver_actor_id
        )
        self._store.update(rejected)
        log.info("HITL rejected: handle=%s by=%s", handle_id, approver_actor_id)

    async def force_expire(self, handle_id: str) -> None:
        record = self._store.get(handle_id)
        if record is None:
            raise HITLPortError(f"Handle {handle_id!r} not found.")
        if record.decision is ApprovalDecision.PENDING:
            timed_out = record.with_decision(ApprovalDecision.TIMED_OUT)
            self._store.update(timed_out)

    def get_record(self, handle_id: str) -> ApprovalRecord | None:
        return self._store.get(handle_id)

    # ── Authority ────────────────────────────────────────────────────────────

    def _assert_authorized(
        self, actor_id: ActorId, required: tuple[ApproverRef, ...]
    ) -> None:
        user_refs = [r for r in required if str(r).startswith("user:")]
        if user_refs:
            actor_ref = ApproverRef(f"user:{actor_id}")
            if actor_ref not in user_refs:
                raise HITLPortError(
                    f"Actor {actor_id!r} is not authorized. Required user refs: {user_refs}",
                    detail={
                        "actor_id": str(actor_id),
                        "required": [str(r) for r in required],
                    },
                )
