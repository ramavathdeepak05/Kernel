"""E08 — HR Event Handlers

Subscribes to:
  - LeaveRequested    → notify HOD / approver
  - LeaveApproved     → notify staff
  - LeaveRejected     → notify staff
"""

import logging

from server.core.domain_events import DomainEventBus

logger = logging.getLogger(__name__)


def on_leave_requested(event: dict) -> None:
    payload  = event.get("payload", {})
    org_id   = event.get("org_id")
    staff_id = payload.get("staff_id")

    if not (org_id and staff_id):
        return

    try:
        from server.db_service import execute_query
        from server.core.notifications.service import NotificationDispatcher

        # Find HOD / reporting manager
        staff_rows = execute_query(
            """
            SELECT sp.reporting_to, u.name AS staff_name, sp.department
            FROM staff_profiles sp
            JOIN users u ON u.id = sp.user_id
            WHERE sp.id = %s AND sp.org_id = %s
            """,
            (staff_id, org_id),
        )
        if not staff_rows:
            return

        staff = dict(staff_rows[0])
        approver_id = staff.get("reporting_to")
        if not approver_id:
            return

        approver_rows = execute_query(
            "SELECT name, email FROM users WHERE id = %s", (str(approver_id),)
        )
        if not approver_rows:
            return

        approver = approver_rows[0]
        NotificationDispatcher.dispatch(
            template_key="leave_request_pending",
            recipient_id=str(approver_id),
            recipient_email=approver["email"],
            context={
                "approver_name": approver["name"],
                "staff_name":    staff["staff_name"],
                "department":    staff["department"],
                "days":          payload.get("days"),
                "leave_type":    payload.get("leave_type"),
            },
            org_id=org_id,
        )
    except Exception as exc:
        logger.warning("E08: LeaveRequested notification failed (non-fatal): %s", exc)


def register_all() -> None:
    DomainEventBus.subscribe("LeaveRequested", on_leave_requested)
    logger.info("E08 event handlers registered")
