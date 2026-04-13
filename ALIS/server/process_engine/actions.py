"""E13 — AUTO_ACTION registry.

Actions are named callables that can be invoked from AUTO_ACTION steps.
Register new actions with @ActionRegistry.register("action_name").
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from server.db_service import execute_transaction

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, Callable[..., Any]] = {}


class ActionRegistry:
    @staticmethod
    def register(name: str):
        """Decorator to register an action."""

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            _REGISTRY[name] = fn
            return fn

        return decorator

    @staticmethod
    def execute(
        name: str, params: dict[str, Any], org_id: str
    ) -> dict[str, Any] | None:
        fn = _REGISTRY.get(name)
        if not fn:
            raise ValueError(
                f"Unknown AUTO_ACTION: '{name}'. Registered: {list(_REGISTRY)}"
            )
        return fn(params=params, org_id=org_id)

    @staticmethod
    def list_actions() -> list:
        return list(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Built-in actions
# ---------------------------------------------------------------------------


@ActionRegistry.register("update_application_status")
def _update_application_status(params: dict[str, Any], org_id: str) -> dict[str, Any]:
    application_id = params.get("application_id")
    status = params.get("status")
    if not application_id or not status:
        raise ValueError("update_application_status requires application_id and status")
    from server.db_service import execute_transaction

    execute_transaction(
        [
            (
                "UPDATE applicants SET status = %s WHERE id = %s AND org_id = %s",
                (status, application_id, org_id),
            )
        ]
    )
    return {"application_id": application_id, "new_status": status}


@ActionRegistry.register("send_notification")
def _send_notification(params: dict[str, Any], org_id: str) -> dict[str, Any]:
    from server.core.notifications.service import NotificationDispatcher

    result = NotificationDispatcher.dispatch(
        template_key=params.get("template_key", ""),
        recipient_id=str(params.get("recipient_id", "system")),
        recipient_email=str(params.get("recipient_email", "")),
        context=params,
        org_id=org_id,
    )
    return result or {}


@ActionRegistry.register("update_student_status")
def _update_student_status(params: dict[str, Any], org_id: str) -> dict[str, Any]:
    student_id = params.get("student_id")
    status = params.get("status")
    if not student_id or not status:
        raise ValueError("update_student_status requires student_id and status")
    from server.db_service import execute_transaction

    execute_transaction(
        [
            (
                "UPDATE students SET status = %s WHERE id = %s AND org_id = %s",
                (status, student_id, org_id),
            )
        ]
    )
    return {"student_id": student_id, "new_status": status}


@ActionRegistry.register("create_fee_invoice")
def _create_fee_invoice(params: dict[str, Any], org_id: str) -> dict[str, Any]:
    rows = execute_transaction(
        [
            (
                """
        INSERT INTO fee_invoices (org_id, student_id, fee_structure_id, due_date, amount, status)
        VALUES (%s, %s, %s, %s, %s, 'UNPAID')
        RETURNING id
        """,
                (
                    org_id,
                    params.get("student_id"),
                    params.get("fee_structure_id"),
                    params.get("due_date"),
                    params.get("amount", 0),
                ),
            )
        ],
        tenant_id=org_id,
    )
    return {"invoice_id": str(rows[0]["id"])} if rows else {}
