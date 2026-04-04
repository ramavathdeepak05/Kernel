"""
FM-7 — GST & TDS Return Generation

Implements:
- GSTR-1 (outward supplies) generation from invoices
- GSTR-3B (monthly summary) generation
- TDS Return 26Q (non-salary) from vendor payments
- TDS Return 24Q (salary) from payroll
- Form 16/16A generation stubs

All returns are generated as JSON data structures that can be
exported to CSV/JSON format compatible with the GST/IT portals.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import uuid4

from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


class GSTReturnService:
    """Generates GST return data from invoice records."""

    @classmethod
    def generate_gstr1(cls, org_id: str, month: int, year: int) -> Dict[str, Any]:
        """
        GSTR-1: Outward supplies (B2B, B2C, exports).
        Compiled from all invoices issued in the given month.
        """
        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"

        # B2B invoices (to registered businesses — have GSTIN)
        b2b = execute_query(
            """
            SELECT i.invoice_number, i.invoice_date, i.gstin_recipient,
                   i.taxable_amount, i.cgst, i.sgst, i.igst, i.total_amount,
                   i.place_of_supply
            FROM invoices i
            WHERE i.org_id = %s AND i.invoice_date >= %s AND i.invoice_date < %s
            AND i.gstin_recipient IS NOT NULL AND i.gstin_recipient != ''
            AND i.status = 'ISSUED'
            ORDER BY i.invoice_date
            """,
            (org_id, start_date, end_date),
            tenant_id=org_id,
        )

        # B2C invoices (to unregistered — no GSTIN)
        b2c = execute_query(
            """
            SELECT i.invoice_number, i.invoice_date,
                   i.taxable_amount, i.cgst, i.sgst, i.igst, i.total_amount,
                   i.place_of_supply
            FROM invoices i
            WHERE i.org_id = %s AND i.invoice_date >= %s AND i.invoice_date < %s
            AND (i.gstin_recipient IS NULL OR i.gstin_recipient = '')
            AND i.status = 'ISSUED'
            ORDER BY i.invoice_date
            """,
            (org_id, start_date, end_date),
            tenant_id=org_id,
        )

        total_taxable = sum(float(r.get("taxable_amount", 0)) for r in b2b) + \
                        sum(float(r.get("taxable_amount", 0)) for r in b2c)
        total_tax = sum(float(r.get("cgst", 0)) + float(r.get("sgst", 0)) + float(r.get("igst", 0))
                        for r in b2b) + \
                   sum(float(r.get("cgst", 0)) + float(r.get("sgst", 0)) + float(r.get("igst", 0))
                        for r in b2c)

        return {
            "return_type": "GSTR-1",
            "period": f"{month:02d}/{year}",
            "org_id": org_id,
            "b2b_invoices": [dict(r) for r in b2b],
            "b2c_invoices": [dict(r) for r in b2c],
            "b2b_count": len(b2b),
            "b2c_count": len(b2c),
            "total_taxable_value": total_taxable,
            "total_tax": total_tax,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def generate_gstr3b(cls, org_id: str, month: int, year: int) -> Dict[str, Any]:
        """
        GSTR-3B: Monthly summary return.
        Aggregates outward + inward supplies, ITC, and net tax payable.
        """
        gstr1 = cls.generate_gstr1(org_id, month, year)

        # Input Tax Credit (ITC) from purchase invoices
        start_date = f"{year}-{month:02d}-01"
        end_date = f"{year}-{month + 1:02d}-01" if month < 12 else f"{year + 1}-01-01"

        itc_rows = execute_query(
            """
            SELECT COALESCE(SUM(cgst), 0) AS itc_cgst,
                   COALESCE(SUM(sgst), 0) AS itc_sgst,
                   COALESCE(SUM(igst), 0) AS itc_igst
            FROM purchase_invoices
            WHERE org_id = %s AND invoice_date >= %s AND invoice_date < %s
            AND itc_eligible = TRUE
            """,
            (org_id, start_date, end_date),
            tenant_id=org_id,
        )
        itc = itc_rows[0] if itc_rows else {"itc_cgst": 0, "itc_sgst": 0, "itc_igst": 0}

        outward_cgst = sum(float(r.get("cgst", 0)) for r in gstr1["b2b_invoices"]) + \
                       sum(float(r.get("cgst", 0)) for r in gstr1["b2c_invoices"])
        outward_sgst = sum(float(r.get("sgst", 0)) for r in gstr1["b2b_invoices"]) + \
                       sum(float(r.get("sgst", 0)) for r in gstr1["b2c_invoices"])
        outward_igst = sum(float(r.get("igst", 0)) for r in gstr1["b2b_invoices"]) + \
                       sum(float(r.get("igst", 0)) for r in gstr1["b2c_invoices"])

        net_cgst = outward_cgst - float(itc["itc_cgst"])
        net_sgst = outward_sgst - float(itc["itc_sgst"])
        net_igst = outward_igst - float(itc["itc_igst"])

        return {
            "return_type": "GSTR-3B",
            "period": f"{month:02d}/{year}",
            "org_id": org_id,
            "outward_supplies": {
                "taxable_value": gstr1["total_taxable_value"],
                "cgst": outward_cgst, "sgst": outward_sgst, "igst": outward_igst,
            },
            "input_tax_credit": {
                "cgst": float(itc["itc_cgst"]),
                "sgst": float(itc["itc_sgst"]),
                "igst": float(itc["itc_igst"]),
            },
            "net_tax_payable": {
                "cgst": max(net_cgst, 0), "sgst": max(net_sgst, 0), "igst": max(net_igst, 0),
                "total": max(net_cgst, 0) + max(net_sgst, 0) + max(net_igst, 0),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


class TDSReturnService:
    """Generates TDS return data from payment records."""

    @classmethod
    def generate_26q(cls, org_id: str, quarter: int, financial_year: str) -> Dict[str, Any]:
        """
        Form 26Q: TDS on non-salary payments (vendor payments, professional fees, rent).
        Quarter: 1=Apr-Jun, 2=Jul-Sep, 3=Oct-Dec, 4=Jan-Mar.
        """
        fy_start = int(financial_year.split("-")[0])
        quarter_months = {
            1: (4, 6), 2: (7, 9), 3: (10, 12), 4: (1, 3),
        }
        start_m, end_m = quarter_months[quarter]
        start_year = fy_start if quarter <= 3 else fy_start + 1
        end_year = start_year if start_m <= end_m else start_year + 1

        start_date = f"{start_year}-{start_m:02d}-01"
        if end_m == 12:
            end_date = f"{end_year + 1}-01-01"
        else:
            end_date = f"{end_year}-{end_m + 1:02d}-01"

        deductions = execute_query(
            """
            SELECT v.name AS deductee_name, v.pan AS deductee_pan,
                   td.tds_section, td.gross_amount, td.tds_rate, td.tds_amount,
                   td.payment_date, td.challan_number
            FROM tds_deductions td
            JOIN vendors v ON v.id = td.vendor_id AND v.org_id = td.org_id
            WHERE td.org_id = %s AND td.payment_date >= %s AND td.payment_date < %s
            AND td.deduction_type = 'NON_SALARY'
            ORDER BY td.payment_date
            """,
            (org_id, start_date, end_date),
            tenant_id=org_id,
        )

        total_tds = sum(float(r.get("tds_amount", 0)) for r in deductions)

        return {
            "form": "26Q",
            "quarter": quarter,
            "financial_year": financial_year,
            "org_id": org_id,
            "deductions": [dict(r) for r in deductions],
            "deduction_count": len(deductions),
            "total_tds_deducted": total_tds,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    def generate_24q(cls, org_id: str, quarter: int, financial_year: str) -> Dict[str, Any]:
        """
        Form 24Q: TDS on salary payments.
        Compiled from payroll records.
        """
        fy_start = int(financial_year.split("-")[0])
        quarter_months = {1: (4, 6), 2: (7, 9), 3: (10, 12), 4: (1, 3)}
        start_m, end_m = quarter_months[quarter]
        start_year = fy_start if quarter <= 3 else fy_start + 1
        end_year = start_year if start_m <= end_m else start_year + 1
        start_date = f"{start_year}-{start_m:02d}-01"
        end_date = f"{end_year}-{end_m + 1:02d}-01" if end_m < 12 else f"{end_year + 1}-01-01"

        deductions = execute_query(
            """
            SELECT s.employee_name, s.pan, s.gross_salary,
                   s.tds_deducted, s.pay_period, s.challan_number
            FROM salary_tds_records s
            WHERE s.org_id = %s AND s.pay_period >= %s AND s.pay_period < %s
            ORDER BY s.pay_period, s.employee_name
            """,
            (org_id, start_date, end_date),
            tenant_id=org_id,
        )

        total_tds = sum(float(r.get("tds_deducted", 0)) for r in deductions)

        return {
            "form": "24Q",
            "quarter": quarter,
            "financial_year": financial_year,
            "org_id": org_id,
            "deductions": [dict(r) for r in deductions],
            "deduction_count": len(deductions),
            "total_tds_deducted": total_tds,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
