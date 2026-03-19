"""Finance — Tally XML + Busy CSV Export

Exports finance data for external accounting software.
Feature flags: finance.tally_export, finance.busy_export (R11)
Format templates from document_engine or hardcoded XML/CSV structure (R9 — use configurable format)
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import date
from typing import List, Optional
from xml.sax.saxutils import escape as xml_escape

from server.core.exceptions import BusinessRuleViolation
from server.db_service import execute_query

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_feature_flag(org_id: str, flag_key: str) -> bool:
    """Return True if the feature flag is enabled for this tenant."""
    rows = execute_query(
        """
        SELECT flag_value
        FROM tenant_feature_flags
        WHERE org_id = %s AND flag_key = %s
        LIMIT 1
        """,
        (org_id, flag_key),
    )
    if not rows:
        return False
    return str(rows[0]["flag_value"]).lower() == "true"


def _query_invoices(org_id: str, from_date: date, to_date: date) -> List[dict]:
    return execute_query(
        """
        SELECT si.invoice_number,
               si.student_id,
               si.total_amount,
               si.created_at,
               si.irn,
               p.amount        AS paid_amount,
               p.payment_method,
               p.transaction_ref
        FROM student_invoices si
        LEFT JOIN fee_payments p ON p.invoice_id = si.id
        WHERE si.org_id = %s
          AND si.created_at BETWEEN %s AND %s
        ORDER BY si.created_at
        """,
        (org_id, from_date, to_date),
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class TallyExportService:

    @classmethod
    def export_tally_xml(
        cls,
        org_id: str,
        from_date: date,
        to_date: date,
        actor_id: str,
    ) -> bytes:
        """
        Generate a Tally-compatible XML (TALLYMESSAGE / Receipt voucher format).
        Raises BusinessRuleViolation if feature flag finance.tally_export is not enabled.
        Returns UTF-8 encoded XML bytes.
        """
        if not _check_feature_flag(org_id, "finance.tally_export"):
            raise BusinessRuleViolation(
                "Tally export is not enabled",
                code="FINANCE_TALLY_EXPORT_DISABLED",
            )

        rows = _query_invoices(org_id, from_date, to_date)

        vouchers_xml = []
        for r in rows:
            # Skip rows with no payment (LEFT JOIN may yield NULL paid_amount)
            if r["paid_amount"] is None:
                continue

            txn_date = ""
            if r["created_at"]:
                dt = r["created_at"]
                if hasattr(dt, "strftime"):
                    txn_date = dt.strftime("%Y%m%d")
                else:
                    txn_date = str(dt).replace("-", "")[:8]

            inv_number = xml_escape(str(r["invoice_number"] or ""))
            amount = str(r["paid_amount"])

            vouchers_xml.append(
                f"""          <TALLYMESSAGE>
            <VOUCHER VCHTYPE="Receipt" ACTION="Create">
              <DATE>{txn_date}</DATE>
              <NARRATION>{inv_number}</NARRATION>
              <AMOUNT>{amount}</AMOUNT>
              <LEDGERENTRIES.LIST>
                <LEDGERNAME>Student Fees</LEDGERNAME>
                <AMOUNT>{amount}</AMOUNT>
              </LEDGERENTRIES.LIST>
            </VOUCHER>
          </TALLYMESSAGE>"""
            )

        vouchers_block = "\n".join(vouchers_xml)

        xml_body = f"""<?xml version="1.0" encoding="UTF-8"?>
<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Import Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <IMPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Vouchers</REPORTNAME>
      </REQUESTDESC>
      <REQUESTDATA>
{vouchers_block}
      </REQUESTDATA>
    </IMPORTDATA>
  </BODY>
</ENVELOPE>
"""
        logger.info(
            "tally_export | org=%s from=%s to=%s vouchers=%d actor=%s",
            org_id, from_date, to_date, len(vouchers_xml), actor_id,
        )
        return xml_body.encode("utf-8")

    @classmethod
    def export_busy_csv(
        cls,
        org_id: str,
        from_date: date,
        to_date: date,
        actor_id: str,
    ) -> bytes:
        """
        Generate a Busy Accounting-compatible CSV.
        Raises BusinessRuleViolation if feature flag finance.busy_export is not enabled.
        Returns UTF-8 encoded CSV bytes.

        Columns: Date, VoucherNo, Party, Amount, Narration, PaymentMode
        """
        if not _check_feature_flag(org_id, "finance.busy_export"):
            raise BusinessRuleViolation(
                "Busy export is not enabled",
                code="FINANCE_BUSY_EXPORT_DISABLED",
            )

        rows = _query_invoices(org_id, from_date, to_date)

        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["Date", "VoucherNo", "Party", "Amount", "Narration", "PaymentMode"],
            lineterminator="\r\n",
        )
        writer.writeheader()

        for r in rows:
            if r["paid_amount"] is None:
                continue

            txn_date = ""
            if r["created_at"]:
                dt = r["created_at"]
                if hasattr(dt, "strftime"):
                    txn_date = dt.strftime("%d/%m/%Y")
                else:
                    raw = str(r["created_at"])[:10]
                    parts = raw.split("-")
                    txn_date = "/".join(reversed(parts)) if len(parts) == 3 else raw

            writer.writerow({
                "Date": txn_date,
                "VoucherNo": r["invoice_number"] or "",
                "Party": str(r["student_id"] or ""),
                "Amount": str(r["paid_amount"]),
                "Narration": r["invoice_number"] or "",
                "PaymentMode": r["payment_method"] or "",
            })

        csv_content = output.getvalue()
        logger.info(
            "busy_export | org=%s from=%s to=%s actor=%s",
            org_id, from_date, to_date, actor_id,
        )
        return csv_content.encode("utf-8")
