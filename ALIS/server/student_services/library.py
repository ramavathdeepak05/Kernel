"""E09-S02 — Library Management"""

import logging
import uuid
from datetime import date, datetime, timedelta

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.db_service import execute_query, execute_transaction

from .models import BorrowingCreate, LibraryBookCreate, ReturnBook

logger = logging.getLogger(__name__)

_FINE_PER_DAY = 2.0   # ₹2 per day overdue (configurable via PolicyStore)
_MAX_BORROW   = 3     # max books per borrower at a time


class LibraryService:

    # ── Books ────────────────────────────────────────────────

    @classmethod
    def add_book(cls, org_id: str, req: LibraryBookCreate, actor_id: str) -> dict:
        bid = str(uuid.uuid4())
        execute_transaction([(
            """
            INSERT INTO library_books
                (id, org_id, isbn, title, author, publisher, edition,
                 year_published, category, total_copies, available_copies, location)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (bid, org_id, req.isbn, req.title, req.author, req.publisher,
             req.edition, req.year_published, req.category,
             req.total_copies, req.total_copies, req.location),
        )])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="library_book", entity_id=bid, org_id=org_id,
                     module="E09-S02",
                     metadata={"title": req.title, "copies": req.total_copies})

        return cls.get_book(org_id, bid)

    @classmethod
    def get_book(cls, org_id: str, book_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM library_books WHERE id = %s AND org_id = %s",
            (book_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Book {book_id} not found")
        return dict(rows[0])

    @classmethod
    def search(cls, org_id: str, query: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT *, ts_rank(to_tsvector('english', title || ' ' || author), plainto_tsquery('english', %s)) AS rank
            FROM library_books
            WHERE org_id = %s AND is_active = TRUE
              AND to_tsvector('english', title || ' ' || author) @@ plainto_tsquery('english', %s)
            ORDER BY rank DESC
            LIMIT 30
            """,
            (query, org_id, query),
        )
        return [dict(r) for r in rows]

    @classmethod
    def list_books(cls, org_id: str, category: str | None = None,
                    available_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM library_books WHERE org_id = %s AND is_active = TRUE"
        params: list = [org_id]
        if category:
            sql += " AND category = %s"
            params.append(category)
        if available_only:
            sql += " AND available_copies > 0"
        sql += " ORDER BY title"
        return [dict(r) for r in execute_query(sql, params)]

    # ── Borrowings ───────────────────────────────────────────

    @classmethod
    def issue_book(cls, org_id: str, req: BorrowingCreate, actor_id: str) -> dict:
        # Check availability
        book_rows = execute_query(
            "SELECT * FROM library_books WHERE id = %s AND org_id = %s AND is_active = TRUE",
            (req.book_id, org_id),
        )
        if not book_rows:
            raise NotFoundError(f"Book {req.book_id} not found")
        book = dict(book_rows[0])
        if int(book["available_copies"]) <= 0:
            raise BusinessRuleViolation(message=f"No copies of '{book['title']}' available")

        # Check borrower limit
        active_borrows = execute_query(
            "SELECT COUNT(*) AS cnt FROM library_borrowings WHERE borrower_id = %s AND org_id = %s AND status = 'BORROWED'",
            (req.borrower_id, org_id),
        )
        if int(active_borrows[0]["cnt"] or 0) >= _MAX_BORROW:
            raise BusinessRuleViolation(
                message=f"Borrower already has {_MAX_BORROW} books. Return one to borrow more."
            )

        # Check no unpaid fines
        unpaid = execute_query(
            "SELECT SUM(fine_amount) AS total FROM library_borrowings WHERE borrower_id = %s AND org_id = %s AND fine_paid = FALSE AND fine_amount > 0",
            (req.borrower_id, org_id),
        )
        if float(unpaid[0]["total"] or 0) > 0:
            raise BusinessRuleViolation(
                message="Clear outstanding library fines before borrowing"
            )

        iid = str(uuid.uuid4())
        execute_transaction([
            (
                """
                INSERT INTO library_borrowings
                    (id, org_id, book_id, borrower_id, borrower_type, issued_date, due_date, issued_by)
                VALUES (%s,%s,%s,%s,%s,CURRENT_DATE,%s,%s)
                """,
                (iid, org_id, req.book_id, req.borrower_id,
                 req.borrower_type.value, req.due_date, actor_id),
            ),
            (
                "UPDATE library_books SET available_copies = available_copies - 1 WHERE id = %s",
                (req.book_id,),
            ),
        ])

        AuditLog.log(action=AuditAction.CREATE, actor_id=actor_id, actor_type="human",
                     entity_type="library_borrowing", entity_id=iid, org_id=org_id,
                     module="E09-S02",
                     metadata={"book_id": req.book_id, "borrower_id": req.borrower_id})

        return cls.get_borrowing(org_id, iid)

    @classmethod
    def return_book(cls, org_id: str, borrowing_id: str,
                     req: ReturnBook, actor_id: str) -> dict:
        rows = execute_query(
            "SELECT * FROM library_borrowings WHERE id = %s AND org_id = %s",
            (borrowing_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Borrowing {borrowing_id} not found")
        borrow = dict(rows[0])

        if borrow["status"] == "RETURNED":
            raise BusinessRuleViolation(message="Book already returned")

        # Compute fine
        due_date = borrow["due_date"]
        if isinstance(due_date, str):
            due_date = datetime.strptime(due_date, "%Y-%m-%d").date()
        today = date.today()
        fine = 0.0
        if today > due_date:
            overdue_days = (today - due_date).days
            fine = round(overdue_days * _FINE_PER_DAY, 2)

        execute_transaction([
            (
                """
                UPDATE library_borrowings
                SET returned_date = CURRENT_DATE, status = 'RETURNED',
                    fine_amount = %s, fine_paid = %s
                WHERE id = %s AND org_id = %s
                """,
                (fine, req.fine_paid or fine == 0, borrowing_id, org_id),
            ),
            (
                "UPDATE library_books SET available_copies = available_copies + 1 WHERE id = %s",
                (str(borrow["book_id"]),),
            ),
        ])

        return cls.get_borrowing(org_id, borrowing_id)

    @classmethod
    def mark_overdue(cls, org_id: str) -> int:
        rows = execute_query(
            """
            UPDATE library_borrowings
            SET status = 'OVERDUE',
                fine_amount = (CURRENT_DATE - due_date) * %s
            WHERE org_id = %s AND status = 'BORROWED' AND due_date < CURRENT_DATE
            RETURNING id
            """,
            (_FINE_PER_DAY, org_id),
        )
        return len(rows)

    @classmethod
    def get_borrowing(cls, org_id: str, borrowing_id: str) -> dict:
        rows = execute_query(
            """
            SELECT lb.*, b.title, b.author, b.isbn
            FROM library_borrowings lb
            JOIN library_books b ON b.id = lb.book_id
            WHERE lb.id = %s AND lb.org_id = %s
            """,
            (borrowing_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Borrowing {borrowing_id} not found")
        return dict(rows[0])

    @classmethod
    def list_for_borrower(cls, org_id: str, borrower_id: str,
                           status: str | None = None) -> list[dict]:
        sql = """
            SELECT lb.*, b.title, b.author
            FROM library_borrowings lb
            JOIN library_books b ON b.id = lb.book_id
            WHERE lb.borrower_id = %s AND lb.org_id = %s
        """
        params: list = [borrower_id, org_id]
        if status:
            sql += " AND lb.status = %s"
            params.append(status)
        sql += " ORDER BY lb.issued_date DESC"
        return [dict(r) for r in execute_query(sql, params)]

    @classmethod
    def list_overdue(cls, org_id: str) -> list[dict]:
        rows = execute_query(
            """
            SELECT lb.*, b.title, b.author, u.name AS borrower_name, u.email
            FROM library_borrowings lb
            JOIN library_books b ON b.id = lb.book_id
            JOIN users u ON u.id = lb.borrower_id
            WHERE lb.org_id = %s AND lb.status IN ('BORROWED','OVERDUE')
              AND lb.due_date < CURRENT_DATE
            ORDER BY lb.due_date
            """,
            (org_id,),
        )
        return [dict(r) for r in rows]

    @classmethod
    def summary(cls, org_id: str) -> dict:
        rows = execute_query(
            """
            SELECT
                COUNT(*) AS total_titles,
                SUM(total_copies) AS total_copies,
                SUM(available_copies) AS available_copies
            FROM library_books WHERE org_id = %s AND is_active = TRUE
            """,
            (org_id,),
        )
        stats = dict(rows[0]) if rows else {}
        active = execute_query(
            "SELECT COUNT(*) AS cnt FROM library_borrowings WHERE org_id = %s AND status = 'BORROWED'",
            (org_id,),
        )
        stats["currently_borrowed"] = int(active[0]["cnt"] or 0) if active else 0
        return stats
