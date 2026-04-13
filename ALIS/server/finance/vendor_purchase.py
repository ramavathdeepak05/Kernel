"""
FM-4 — Vendor & Purchase Management

Implements:
- Vendor registration and approval
- Purchase Order (PO) lifecycle: DRAFT → APPROVED → GRN_PENDING → INVOICE_MATCHED → PAID
- 3-way match: PO vs. GRN vs. Vendor Invoice
- TDS deduction per section (194J 10%, 194C 1-2%, 194H 5%, 194I 10%)
- GST ITC tracking on purchases

State Machine:
    PO: DRAFT → SUBMITTED → APPROVED → GRN_PENDING → INVOICE_MATCHED → PAYMENT_PENDING → PAID → CLOSED
    Vendor: PENDING → APPROVED → ACTIVE → SUSPENDED → BLACKLISTED

Roles:
- Requester (Faculty/HOD): create PO
- Finance Officer: approve PO, process payment
- Admin/Registrar: approve vendors, approve high-value POs
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from server.core.audit import AuditAction, AuditLog
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


# =============================================================================
# Enums
# =============================================================================


class VendorStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    BLACKLISTED = "BLACKLISTED"


class POStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    GRN_PENDING = "GRN_PENDING"
    INVOICE_MATCHED = "INVOICE_MATCHED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


PO_TRANSITIONS = {
    POStatus.DRAFT: {POStatus.SUBMITTED, POStatus.CANCELLED},
    POStatus.SUBMITTED: {POStatus.APPROVED, POStatus.CANCELLED},
    POStatus.APPROVED: {POStatus.GRN_PENDING, POStatus.CANCELLED},
    POStatus.GRN_PENDING: {POStatus.INVOICE_MATCHED},
    POStatus.INVOICE_MATCHED: {POStatus.PAYMENT_PENDING},
    POStatus.PAYMENT_PENDING: {POStatus.PAID},
    POStatus.PAID: {POStatus.CLOSED},
    POStatus.CLOSED: set(),
    POStatus.CANCELLED: set(),
}


# TDS rates per section
TDS_RATES = {
    "194C_INDIVIDUAL": 0.01,  # Contractor (individual/HUF) — 1%
    "194C_OTHERS": 0.02,  # Contractor (others) — 2%
    "194J_PROFESSIONAL": 0.10,  # Professional services — 10%
    "194J_TECHNICAL": 0.02,  # Technical services — 2%
    "194H_COMMISSION": 0.05,  # Commission/brokerage — 5%
    "194I_RENT_LAND": 0.10,  # Rent (land/building) — 10%
    "194I_RENT_EQUIPMENT": 0.02,  # Rent (equipment) — 2%
    "194IA_PROPERTY": 0.01,  # Property purchase — 1%
}


# =============================================================================
# Vendor Service
# =============================================================================


class VendorService:
    @classmethod
    def register(
        cls, org_id: str, data: dict[str, Any], actor_id: str
    ) -> dict[str, Any]:
        """Register a new vendor (starts as PENDING, requires approval)."""
        vendor_id = str(uuid4())
        now = datetime.now(timezone.utc)
        execute_transaction(
            [
                (
                    """
                INSERT INTO vendors
                    (id, org_id, name, gstin, pan, address, contact_email,
                     contact_phone, bank_account, bank_ifsc, tds_section,
                     status, created_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        vendor_id,
                        org_id,
                        data["name"],
                        data.get("gstin", ""),
                        data.get("pan", ""),
                        data.get("address", ""),
                        data.get("contact_email", ""),
                        data.get("contact_phone", ""),
                        data.get("bank_account", ""),
                        data.get("bank_ifsc", ""),
                        data.get("tds_section", "194C_OTHERS"),
                        VendorStatus.PENDING.value,
                        actor_id,
                        now,
                    ),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_role="admin",
            entity_type="vendor",
            entity_id=vendor_id,
            tenant_id=org_id,
            metadata={"name": data["name"], "gstin": data.get("gstin", "")},
        )
        return {"id": vendor_id, "status": VendorStatus.PENDING.value}

    @classmethod
    def approve(cls, org_id: str, vendor_id: str, actor_id: str) -> dict[str, Any]:
        execute_transaction(
            [
                (
                    "UPDATE vendors SET status = %s, approved_by = %s, approved_at = NOW() "
                    "WHERE id = %s AND org_id = %s AND status = %s",
                    (
                        VendorStatus.ACTIVE.value,
                        actor_id,
                        vendor_id,
                        org_id,
                        VendorStatus.PENDING.value,
                    ),
                )
            ],
            tenant_id=org_id,
        )
        return {"id": vendor_id, "status": VendorStatus.ACTIVE.value}

    @classmethod
    def list_vendors(
        cls, org_id: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        if status:
            rows = execute_query(
                "SELECT id, name, gstin, pan, status, contact_email FROM vendors "
                "WHERE org_id = %s AND status = %s ORDER BY name",
                (org_id, status),
                tenant_id=org_id,
            )
        else:
            rows = execute_query(
                "SELECT id, name, gstin, pan, status, contact_email FROM vendors "
                "WHERE org_id = %s ORDER BY name",
                (org_id,),
                tenant_id=org_id,
            )
        return [dict(r) for r in rows]


# =============================================================================
# Purchase Order Service
# =============================================================================


class PurchaseOrderService:
    @classmethod
    def create(cls, org_id: str, data: dict[str, Any], actor_id: str) -> dict[str, Any]:
        po_id = str(uuid4())
        po_number = (
            f"PO-{datetime.now(timezone.utc).strftime('%Y')}-{po_id[:6].upper()}"
        )
        now = datetime.now(timezone.utc)

        execute_transaction(
            [
                (
                    """
                INSERT INTO purchase_orders
                    (id, org_id, po_number, vendor_id, department, description,
                     line_items, subtotal, gst_amount, total_amount, budget_head,
                     status, requested_by, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s)
                """,
                    (
                        po_id,
                        org_id,
                        po_number,
                        data["vendor_id"],
                        data.get("department", ""),
                        data.get("description", ""),
                        _json_str(data.get("line_items", [])),
                        data.get("subtotal", 0),
                        data.get("gst_amount", 0),
                        data.get("total_amount", 0),
                        data.get("budget_head", ""),
                        POStatus.DRAFT.value,
                        actor_id,
                        now,
                    ),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_role="requester",
            entity_type="purchase_order",
            entity_id=po_id,
            tenant_id=org_id,
            metadata={"po_number": po_number, "vendor_id": data["vendor_id"]},
        )
        return {"id": po_id, "po_number": po_number, "status": POStatus.DRAFT.value}

    @classmethod
    def advance_status(
        cls, org_id: str, po_id: str, target: str, actor_id: str
    ) -> dict[str, Any]:
        """Move PO to next status (validates transition)."""
        rows = execute_query(
            "SELECT status FROM purchase_orders WHERE id = %s AND org_id = %s",
            (po_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise ValueError(f"PO {po_id} not found")
        current = POStatus(rows[0]["status"])
        target_status = POStatus(target)
        if target_status not in PO_TRANSITIONS.get(current, set()):
            raise ValueError(
                f"Invalid PO transition: {current.value} → {target_status.value}"
            )

        execute_transaction(
            [
                (
                    "UPDATE purchase_orders SET status = %s, updated_at = NOW() WHERE id = %s AND org_id = %s",
                    (target_status.value, po_id, org_id),
                )
            ],
            tenant_id=org_id,
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_role="finance",
            entity_type="purchase_order",
            entity_id=po_id,
            tenant_id=org_id,
            metadata={"from": current.value, "to": target_status.value},
        )
        return {"id": po_id, "status": target_status.value}

    @classmethod
    def three_way_match(
        cls,
        org_id: str,
        po_id: str,
        grn_amount: float,
        invoice_amount: float,
    ) -> dict[str, Any]:
        """
        3-way match: PO amount vs GRN amount vs Vendor Invoice amount.
        Tolerance: 2% or ₹500 (whichever is higher).
        """
        rows = execute_query(
            "SELECT total_amount FROM purchase_orders WHERE id = %s AND org_id = %s",
            (po_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise ValueError(f"PO {po_id} not found")

        po_amount = float(rows[0]["total_amount"])
        tolerance = max(po_amount * 0.02, 500.0)

        match_result = {
            "po_amount": po_amount,
            "grn_amount": grn_amount,
            "invoice_amount": invoice_amount,
            "tolerance": tolerance,
            "po_grn_match": abs(po_amount - grn_amount) <= tolerance,
            "po_invoice_match": abs(po_amount - invoice_amount) <= tolerance,
            "grn_invoice_match": abs(grn_amount - invoice_amount) <= tolerance,
        }
        match_result["all_matched"] = all(
            [
                match_result["po_grn_match"],
                match_result["po_invoice_match"],
                match_result["grn_invoice_match"],
            ]
        )
        return match_result

    @classmethod
    def compute_tds(cls, org_id: str, vendor_id: str, amount: float) -> dict[str, Any]:
        """Compute TDS deduction for a vendor payment."""
        rows = execute_query(
            "SELECT tds_section, pan FROM vendors WHERE id = %s AND org_id = %s",
            (vendor_id, org_id),
            tenant_id=org_id,
        )
        if not rows:
            raise ValueError(f"Vendor {vendor_id} not found")

        section = rows[0].get("tds_section", "194C_OTHERS")
        rate = TDS_RATES.get(section, 0.02)
        has_pan = bool(rows[0].get("pan"))

        # No PAN → higher rate (20% per IT Act)
        if not has_pan:
            rate = 0.20

        tds_amount = round(amount * rate, 2)
        net_payable = round(amount - tds_amount, 2)

        return {
            "gross_amount": amount,
            "tds_section": section,
            "tds_rate": rate,
            "tds_amount": tds_amount,
            "net_payable": net_payable,
            "pan_available": has_pan,
        }

    @classmethod
    def list_orders(
        cls, org_id: str, status: str | None = None
    ) -> list[dict[str, Any]]:
        if status:
            rows = execute_query(
                "SELECT id, po_number, vendor_id, total_amount, status, created_at "
                "FROM purchase_orders WHERE org_id = %s AND status = %s ORDER BY created_at DESC",
                (org_id, status),
                tenant_id=org_id,
            )
        else:
            rows = execute_query(
                "SELECT id, po_number, vendor_id, total_amount, status, created_at "
                "FROM purchase_orders WHERE org_id = %s ORDER BY created_at DESC",
                (org_id,),
                tenant_id=org_id,
            )
        return [dict(r) for r in rows]


def _json_str(obj: Any) -> str:
    import json

    return json.dumps(obj)
