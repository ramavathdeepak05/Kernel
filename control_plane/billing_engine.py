"""
Billing Engine — S4

Computes monthly invoices from tenant usage data and plan configuration.

Design:
  - One Invoice per tenant per calendar month
  - Line items: base subscription + per-dimension overage
  - Tax placeholder: 0% (institutions provide GST details separately; tax engine S9)
  - Idempotent: calling compute() twice for the same period returns the same
    invoice (upserts on (tenant_id, period) with status preservation)

Invocation:
  - Beat task: runs on the 1st of each month at 02:00 UTC
  - Admin API: POST /admin/billing/invoices/generate (for recompute/preview)
  - Data plane: POST /billing/usage sends events; invoice is computed separately
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import List, Optional

from control_plane.billing_models import (
    PLAN_CONFIGS,
    Invoice,
    InvoiceLineItem,
    PlanConfig,
    UsageSummary,
)
from control_plane.usage_store import UsageStore

logger = logging.getLogger(__name__)


_CENT = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


class BillingEngine:
    """
    Computes and persists monthly invoices for all active tenants.
    """

    def __init__(self, usage_store: Optional[UsageStore] = None) -> None:
        self._store = usage_store or UsageStore()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_invoice(
        self,
        tenant_id: str,
        plan: str,
        period: str,
        persist: bool = True,
    ) -> Invoice:
        """
        Compute the invoice for `tenant_id` in `period` ("YYYY-MM").

        Args:
            tenant_id:  Tenant UUID string
            plan:       Plan name — starter | growth | enterprise
            period:     Billing period in YYYY-MM format
            persist:    If True, upsert the invoice into cp_invoices

        Returns:
            Fully computed Invoice (status="draft" unless previously issued/paid).
        """
        plan_cfg = PLAN_CONFIGS.get(plan, PLAN_CONFIGS["starter"])
        summary = self._store.get_summary(tenant_id, period)
        period_start, period_end = _period_dates(period)

        line_items = self._build_line_items(plan_cfg, summary)
        subtotal = _round(sum(li.amount for li in line_items))
        tax = Decimal("0.00")   # GST computed separately in S9
        total = subtotal + tax

        invoice = Invoice(
            tenant_id=tenant_id,
            period=period,
            period_start=period_start,
            period_end=period_end,
            plan=plan,
            line_items=line_items,
            subtotal=subtotal,
            tax=tax,
            total=total,
            status="draft",
        )

        if persist:
            invoice = self._upsert_invoice(invoice)

        return invoice

    def compute_all_active(self, period: str) -> List[Invoice]:
        """
        Compute invoices for every active tenant for the given period.
        Returns the list of computed invoices.
        """
        from control_plane import db

        tenants = db.query(
            "SELECT tenant_id, plan FROM cp_tenants WHERE status = 'active'"
        )
        invoices = []
        for row in tenants:
            try:
                inv = self.compute_invoice(
                    tenant_id=str(row["tenant_id"]),
                    plan=row["plan"],
                    period=period,
                    persist=True,
                )
                invoices.append(inv)
            except Exception as exc:
                logger.exception(
                    "Invoice computation failed for tenant=%s period=%s: %s",
                    row["tenant_id"], period, exc,
                )
        return invoices

    def get_invoice(self, tenant_id: str, period: str) -> Optional[Invoice]:
        """Retrieve a stored invoice by tenant + period."""
        from control_plane import db

        rows = db.query(
            """
            SELECT id, tenant_id, period, period_start, period_end, plan,
                   line_items, subtotal, tax, total, currency, status,
                   created_at, issued_at
            FROM cp_invoices
            WHERE tenant_id = %s AND period = %s
            """,
            (tenant_id, period),
        )
        if not rows:
            return None
        return _row_to_invoice(rows[0])

    def list_invoices(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[List[Invoice], int]:
        """List invoices with optional filters. Returns (invoices, total_count)."""
        from control_plane import db

        conditions = []
        params: list = []
        if tenant_id:
            conditions.append("tenant_id = %s")
            params.append(tenant_id)
        if status:
            conditions.append("status = %s")
            params.append(status)

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        count_rows = db.query(
            f"SELECT COUNT(*) AS n FROM cp_invoices {where}", tuple(params)
        )
        total = count_rows[0]["n"] if count_rows else 0

        params += [limit, offset]
        rows = db.query(
            f"""
            SELECT id, tenant_id, period, period_start, period_end, plan,
                   line_items, subtotal, tax, total, currency, status,
                   created_at, issued_at
            FROM cp_invoices
            {where}
            ORDER BY period DESC, tenant_id
            LIMIT %s OFFSET %s
            """,
            tuple(params),
        )
        return [_row_to_invoice(r) for r in rows], total

    def mark_issued(self, tenant_id: str, period: str) -> bool:
        """Transition invoice status draft → issued."""
        from control_plane import db

        db.execute(
            """
            UPDATE cp_invoices
            SET status = 'issued', issued_at = NOW()
            WHERE tenant_id = %s AND period = %s AND status = 'draft'
            """,
            (tenant_id, period),
        )
        return True

    def mark_paid(self, tenant_id: str, period: str) -> bool:
        """Transition invoice status issued → paid."""
        from control_plane import db

        db.execute(
            """
            UPDATE cp_invoices
            SET status = 'paid'
            WHERE tenant_id = %s AND period = %s AND status = 'issued'
            """,
            (tenant_id, period),
        )
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_line_items(
        self, plan: PlanConfig, usage: UsageSummary
    ) -> List[InvoiceLineItem]:
        items: List[InvoiceLineItem] = []

        # 1. Base subscription
        items.append(InvoiceLineItem(
            description=f"{plan.name.title()} plan — monthly subscription",
            quantity=Decimal("1"),
            unit_price=plan.monthly_price_usd,
            amount=_round(plan.monthly_price_usd),
        ))

        # 2. Token overage
        token_overage = max(0, usage.ai_tokens - plan.token_quota)
        if token_overage > 0:
            units = Decimal(token_overage) / Decimal("1000")
            amount = _round(units * plan.overage_token_per_1k)
            items.append(InvoiceLineItem(
                description=f"AI token overage ({token_overage:,} tokens)",
                quantity=_round(units),
                unit_price=plan.overage_token_per_1k,
                amount=amount,
            ))

        # 3. API call overage
        call_overage = max(0, usage.api_calls - plan.api_call_quota)
        if call_overage > 0:
            units = Decimal(call_overage) / Decimal("1000")
            amount = _round(units * plan.overage_api_per_1k)
            items.append(InvoiceLineItem(
                description=f"API call overage ({call_overage:,} calls)",
                quantity=_round(units),
                unit_price=plan.overage_api_per_1k,
                amount=amount,
            ))

        # 4. Storage overage
        storage_overage = max(Decimal("0"), usage.storage_gb - Decimal(plan.storage_gb_quota))
        if storage_overage > 0:
            amount = _round(storage_overage * plan.overage_storage_gb)
            items.append(InvoiceLineItem(
                description=f"Storage overage ({storage_overage} GB)",
                quantity=storage_overage,
                unit_price=plan.overage_storage_gb,
                amount=amount,
            ))

        # 5. Active user overage
        user_overage = max(0, usage.active_users - plan.active_user_quota)
        if user_overage > 0:
            amount = _round(Decimal(user_overage) * plan.overage_user)
            items.append(InvoiceLineItem(
                description=f"Active user overage ({user_overage} users)",
                quantity=Decimal(user_overage),
                unit_price=plan.overage_user,
                amount=amount,
            ))

        return items

    def _upsert_invoice(self, invoice: Invoice) -> Invoice:
        """
        Insert or update the invoice in cp_invoices.

        On conflict (tenant_id, period):
          - If existing status is draft → overwrite line_items + amounts
          - If existing status is issued/paid → leave amounts as-is, return existing
        """
        import json
        from control_plane import db

        line_items_json = json.dumps([li.model_dump(mode="json") for li in invoice.line_items])

        # Check if invoice already exists
        existing = db.query(
            "SELECT id, status FROM cp_invoices WHERE tenant_id = %s AND period = %s",
            (invoice.tenant_id, invoice.period),
        )

        if not existing:
            db.execute(
                """
                INSERT INTO cp_invoices
                    (tenant_id, period, period_start, period_end, plan,
                     line_items, subtotal, tax, total, currency, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    invoice.tenant_id, invoice.period,
                    invoice.period_start, invoice.period_end,
                    invoice.plan, line_items_json,
                    str(invoice.subtotal), str(invoice.tax), str(invoice.total),
                    invoice.currency, invoice.status,
                ),
            )
        elif existing[0]["status"] == "draft":
            # Recompute — overwrite draft
            db.execute(
                """
                UPDATE cp_invoices
                SET line_items=%s, subtotal=%s, tax=%s, total=%s, plan=%s
                WHERE tenant_id=%s AND period=%s
                """,
                (
                    line_items_json, str(invoice.subtotal), str(invoice.tax),
                    str(invoice.total), invoice.plan,
                    invoice.tenant_id, invoice.period,
                ),
            )
        # else: issued/paid — do not overwrite

        # Return persisted record with id
        return self.get_invoice(invoice.tenant_id, invoice.period) or invoice


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _period_dates(period: str) -> tuple[date, date]:
    """Return (first day of month, last day of month) for "YYYY-MM"."""
    year, month = int(period[:4]), int(period[5:7])
    start = date(year, month, 1)
    # Last day: first of next month minus 1 day
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _row_to_invoice(row: dict) -> Invoice:
    import json

    raw = row.get("line_items", "[]")
    line_items_data = json.loads(raw) if isinstance(raw, str) else raw
    line_items = [InvoiceLineItem(**li) for li in line_items_data]

    return Invoice(
        id=row.get("id"),
        tenant_id=str(row["tenant_id"]),
        period=row["period"],
        period_start=row["period_start"],
        period_end=row["period_end"],
        plan=row["plan"],
        line_items=line_items,
        subtotal=Decimal(str(row["subtotal"])),
        tax=Decimal(str(row["tax"])),
        total=Decimal(str(row["total"])),
        currency=row.get("currency", "USD"),
        status=row.get("status", "draft"),
        created_at=row.get("created_at"),
        issued_at=row.get("issued_at"),
    )
