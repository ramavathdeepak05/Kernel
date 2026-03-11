"""E09 — Student Services Event Handlers

Subscribes to:
  - LibraryOverdue     → notify borrower (fired by beat task)
  - CrisisSessionLogged → alert designated coordinator (future)
"""

import logging

from server.core.domain_events import DomainEventBus

logger = logging.getLogger(__name__)


def on_library_overdue(event: dict) -> None:
    payload     = event.get("payload", {})
    org_id      = event.get("org_id")
    borrower_id = payload.get("borrower_id")
    book_title  = payload.get("book_title")

    if not (org_id and borrower_id):
        return

    try:
        from server.db_service import execute_query
        from server.core.notifications.service import NotificationDispatcher

        user_rows = execute_query(
            "SELECT name, email FROM users WHERE id = %s", (borrower_id,)
        )
        if not user_rows:
            return
        user = user_rows[0]
        NotificationDispatcher.dispatch(
            template_key="library_overdue",
            recipient_id=borrower_id,
            recipient_email=user["email"],
            context={
                "borrower_name": user["name"],
                "book_title": book_title,
                "fine_per_day": payload.get("fine_per_day", 2),
            },
            org_id=org_id,
        )
    except Exception as exc:
        logger.warning("E09: LibraryOverdue notification failed (non-fatal): %s", exc)


def register_all() -> None:
    DomainEventBus.subscribe("LibraryOverdue", on_library_overdue)
    logger.info("E09 event handlers registered")
