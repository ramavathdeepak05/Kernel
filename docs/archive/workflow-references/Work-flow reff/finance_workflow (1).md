# Finance Module Workflow
### Full Automation Reference — ALIS OS Module E07
#### Model: AI Executes Everything. Actors Approve.
#### QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential

---

## Document Map

This document covers the full Finance module (E07) of ALIS OS.

**Connected documents:**
- `admissions_workflow.md` — `student.enrolled` triggers fee schedule generation; `student.cancelled` triggers refund workflow
- `academic_operations_workflow.md` — academic calendar blackout dates; fee dues block attendance eligibility
- `examination_workflow.md` — `student_dues_status` read model consumed by hall ticket gate; `student.dues_cleared` event
- `student_services_workflow.md` — scholarship disbursements (SS-4); hostel/library clearances for refunds (SS-1, SS-2)
- `hr_payroll_workflow.md` — payroll inputs consumed from HR (HR-3); payroll outputs (payslips, Form 16) stored back in HR records
- `regulatory_accreditation_workflow.md` — financial statements, expenditure per student, fee compliance for NAAC/NIRF/UGC

**Cross-references to skill files:**
- Edge cases: `references/edge-cases.md` — EC-ADM-05, EC-FIN-01, EC-FIN-02, EC-FIN-03
- Fee versioning: `references/architecture.md` §26
- Tally/Busy export: `references/gaps.md` — Tally / Busy Accounting Export section
- e-Invoice/IRN: `references/gaps.md` — GST e-Invoice / IRN Generation section
- DPDP consent: `references/architecture.md` §22
- Razorpay webhook idempotency: `references/edge-cases.md` EC-ADM-05
- Build sequence: `ALIS_BUILD_PLAN.md` — Sprint 1 (EC-ADM-05), Sprint 1 (fee versioning), Sprint 2 (EC-FIN-01, EC-FIN-02, EC-FIN-03)

---

## Purpose & Design Principles

The Finance Module governs all money movement in the institution — inbound (fees,
donations), outbound (refunds, payroll, vendor payments), internal (budget allocation,
scholarship adjustments), and statutory (GST, TDS, 80G, UGC compliance). It is the
single source of financial truth across the institution.

**Core Design Principle:** AI executes every computation, posting, and alert.
Humans (Actors) only Approve, Reject, or Escalate at defined gates.

**Non-negotiable rules for this module:**
- AI generates every invoice, receipt, payslip, ledger entry, TDS certificate,
  and report — without staff initiation
- Every approval gate has a defined SLA with auto-escalation on breach
- The Finance module is the only module authorised to update the student dues ledger
  and vendor payment records
- Every ledger entry is immutable after posting — **never UPDATE or DELETE a posted entry**
  Use reversal entries instead (see EC-FIN-03)
- The `student_dues_status` read model is updated in real time by every dues-posting
  operation. The Examination module queries this read model, not the event stream.
- All financial data is stored with full audit trail: who approved, when, what amount,
  what reference number
- DPDP Act compliance: financial personal data (bank details, salary, fee history)
  is scoped by role — bank account numbers partially masked in all views except
  Finance Officer. Full access log maintained.

---

## Actors

| Actor | Scope of Authority | Escalation Path |
|---|---|---|
| Finance Officer | All 7 finance domains — primary authority | VC / Management |
| Accounts Staff | Day-to-day entries, receipts, vouchers, payroll processing | Finance Officer |
| Dean / Registrar | Scholarship disbursement approval, refund authorisation, fee waiver sign-off | Finance Officer → VC |
| VC / Management | Budget approval, large expenditure sanction (above threshold), final audit sign-off | Board / Statutory Auditor |
| Vendor / Supplier | Invoice submission, payment status visibility (via vendor portal) | Finance Officer |
| Student | Fee payment, receipt download, dues status, refund tracking (via student portal) | Accounts Staff → Finance Officer |

**MFA requirement:** Finance Officer, Accounts Staff (for payment batch release), and
all roles with access to salary or bank account data must have MFA enabled.
See `references/architecture.md` §23. This is enforced at login — not optional.

---

## Module Overview

| # | Finance Domain | Primary Trigger | Primary Actor | Stages |
|---|---|---|---|---|
| FM-1 | Fee Collection & Receipts | `student.enrolled` | Finance Officer + Student | 8 stages |
| FM-2 | Scholarships & Waivers | `scholarship.awarded` / Dean approval | Finance Officer + Dean | 6 stages |
| FM-3 | Refunds & Cancellations | `student.cancelled` / refund request | Finance Officer + Dean | 7 stages |
| FM-4 | Vendor & Purchase Management | Department purchase requisition | Finance Officer + VC | 9 stages |
| FM-5 | Payroll (Faculty & Staff) | Monthly payroll cycle (configurable) | Finance Officer + Accounts Staff | 8 stages |
| FM-6 | Budget Planning & Tracking | Financial year start / management directive | Finance Officer + VC | 7 stages |
| FM-7 | Financial Reporting & Audits | Monthly / quarterly / annual trigger (auto) | Finance Officer + VC | 6 stages |

---

## Compliance Framework

All seven domains operate within the following compliance requirements.
AI monitors and flags violations automatically.

| Compliance Area | Applies To | Key Requirement | AI Action |
|---|---|---|---|
| **UGC Fee Regulations** | FM-1 | Fee structure published before admissions; no mid-year revision without UGC approval | Auto-publishes fee schedule; flags mid-year revision for VC approval |
| **GST (CGST Act 2017)** | FM-1, FM-4, FM-7 | Core tuition fees exempt; ancillary services taxable; e-Invoice mandatory above ₹5 crore turnover | Classifies each line as EXEMPT or TAXABLE; generates GSTR-1/3B data; triggers IRN generation |
| **TDS (IT Act)** | FM-4, FM-5 | Section-wise deductions; deposit by 7th of following month; quarterly returns | Auto-deducts; generates Form 16/16A; deposits on schedule; files 26Q |
| **80G** | FM-6, FM-7 | Auto-generate receipts for registered institutions | Issues 80G receipts on donation receipt |
| **DPDP Act 2023** | All FM domains | Financial personal data scoped by role; consent logged before collection; erasure supported | Role-based masking; access logs; erasure cascade (anonymises, preserves aggregates) |

---

## Production Hardening Requirements

### Fee Structure Versioning — Go-Live Blocker

**A student admitted in 2022 must be billed under the 2022 fee structure for all
4 years, regardless of changes in 2023, 2024, or 2025.**

This is a legal requirement — multiple Indian universities have faced litigation from
students billed under revised fee structures. Without this, the first annual fee
revision will corrupt every existing student's ledger.

```sql
-- Replace any existing fee_master table approach with this schema

CREATE TABLE fee_structures (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL,
    program_id        UUID NOT NULL,
    intake_year       INTEGER NOT NULL,
    valid_for_batches INTEGER[],              -- e.g. [2022, 2023]
    fee_heads         JSONB NOT NULL,         -- itemised breakdown
    total_annual      DECIMAL(12,2) NOT NULL,
    approved_by       UUID NOT NULL,          -- VC who approved
    published_at      TIMESTAMPTZ NOT NULL,   -- immutable after this point
    is_locked         BOOLEAN DEFAULT false,  -- true = cannot be modified
    created_at        TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, program_id, intake_year)
);

-- Immutable record — one per student at enrollment time
CREATE TABLE student_fee_assignments (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL,
    student_id       UUID NOT NULL UNIQUE,
    fee_structure_id UUID NOT NULL REFERENCES fee_structures(id),
    assigned_at      TIMESTAMPTZ DEFAULT now()
    -- No UPDATE ever. Enforced via PostgreSQL trigger.
);

-- Trigger: locks fee_structure the moment the first student is enrolled under it
CREATE OR REPLACE FUNCTION lock_fee_structure_on_enrollment()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE fee_structures SET is_locked = true
    WHERE id = NEW.fee_structure_id AND tenant_id = NEW.tenant_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER lock_fee_on_first_enrollment
AFTER INSERT ON student_fee_assignments
FOR EACH ROW EXECUTE FUNCTION lock_fee_structure_on_enrollment();
```

```python
class FeeStructureService:
    async def update_fee_structure(self, structure_id: UUID, updates: dict, tenant_id: str):
        structure = await get_fee_structure(structure_id, tenant_id)
        if structure.is_locked:
            raise FeeStructureLockedError(
                f"Fee structure for intake year {structure.intake_year} is locked. "
                "A student is already enrolled under it. "
                "Create a new structure for the next intake year instead."
            )
        # Proceed with update
```

**Event handler for `student.enrolled` in FM-1:**
On enrollment, the handler looks up the `fee_structures` row for
`(program_id, intake_year)` and creates a `student_fee_assignments` record.
All future fee schedules for this student are generated from that locked structure —
never from a live query of the current fee table.

### `student_dues_status` Read Model

The Examination module queries this read model at hall-ticket generation time.
The Finance module is responsible for keeping it current.

```python
class StudentDuesStatus(BaseModel):
    student_id: UUID
    tenant_id: UUID
    total_outstanding: Decimal      # sum of all unpaid invoices
    pending_library_fines: Decimal  # posted from SS-2
    pending_hostel_dues: Decimal    # posted from SS-1
    pending_exam_fees: Decimal      # posted from E06
    last_updated_at: datetime

# Updated by Finance on every:
# - Invoice generated
# - Payment received
# - Fine posted (from any module)
# - Exemption granted or expired (from EC-FIN-01)
```

Every dues-posting operation across all modules (library fine, hostel damage,
exam fee) must call `update_dues_status(student_id, tenant_id)` after posting.
This read model is the single source of truth for exam eligibility checks.

### Payment Webhook Idempotency — P0

All Razorpay webhook processing must be idempotent. See EC-ADM-05 below for the
full implementation. The core requirement:

```sql
CREATE TABLE payment_webhook_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    razorpay_payment_id TEXT NOT NULL UNIQUE,  -- idempotency key
    event_type          TEXT NOT NULL,
    processed_at        TIMESTAMPTZ NOT NULL,
    payload             JSONB NOT NULL
);
```

Before processing any webhook: check `payment_webhook_log` for the
`razorpay_payment_id`. If already present, skip. If not present, process and
insert. On startup: replay any unprocessed payments from the last 24 hours
by polling the Razorpay API.

### DPDP Act — Finance Data

The Finance module handles sensitive financial personal data. Three requirements:

**1. Consent logging:** Every fee payment, salary record, and bank account capture
must log a `consent_records` entry via E21 before writing data.
`purpose = 'financial_data'`, `legal_basis = 'legitimate_interest'` for fee records;
`legal_basis = 'legal_obligation'` for payroll (statutory requirement).

**2. Role-based masking:** Bank account numbers shown as `XXXX XXXX 1234` in all
views except Finance Officer. Salary details visible only to Finance Officer + HR
Officer + the employee themselves.

**3. Erasure cascade:** When a student exercises DPDP right to erasure, the Finance
module anonymises PII fields (student name, bank account, contact) while preserving
aggregate financial records (total fees collected, scholarship amounts) needed for
NAAC/NIRF/UGC statutory reporting. Legal holds — active fee disputes, pending
refunds — block erasure until resolved.
See `references/architecture.md` §22 for the `DataErasureWorkflow`.

---

## FM-1: Fee Collection & Receipts

**Trigger:** `student.enrolled` event. AI immediately generates the fee schedule
for that student's program, batch, and category. No staff action required.

**The fee schedule is generated from the locked `student_fee_assignments` record —
never from a live query of the current fee table.** This is the fee versioning
guarantee.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 1.1 | Fee Schedule Generation | On `student.enrolled`, pulls locked fee structure from `student_fee_assignments`. Applies category-based concessions (SC/ST, EWS, management quota, NRI). Computes semester-wise breakup. Classifies each head as GST-exempt or taxable. | Finance Officer reviews fee schedule for new programs / batch year. Approves master fee table before each admission cycle (UGC compliance). | Fee schedule per student. Published to student portal. `fee_schedule.generated` event. | Instant on enrollment |
| 1.2 | Invoice Generation | At each fee due date, auto-generates itemised invoice. Applies scholarship credits already awarded. Computes net payable. Attaches GST breakup. Generates IRN if institution is above ₹5 crore turnover threshold (see e-Invoice section below). | No action required. | Invoice visible in student portal. Email + SMS + WhatsApp. Invoice ID assigned. | Per fee calendar (auto) |
| 1.3 | Payment Gateway Integration | Student initiates payment via Razorpay. AI handles session creation, callback processing, failure retry logic. Idempotent webhook processing via `payment_webhook_log` table. UTR dispute portal available if webhook drops (EC-ADM-05). | Finance Officer approves partial payment plans on request. | Payment captured. Receipt auto-generated. `fee.paid` event fired. | Real-time |
| 1.4 | Receipt Issuance & Posting | Auto-generates digitally signed PDF receipt (sequential receipt number, date, amount, mode). Posts to student ledger. Updates `student_dues_status` read model immediately. Sends receipt to student email + portal. | No action required. | Receipt issued. Ledger updated. Read model updated. Dues balance reduced. | Instant post-payment |
| 1.5 | Defaulter Management | Daily batch: identifies overdue fees. Checks `student_fee_exemptions` table before escalating (EC-FIN-01). Checks `FeePaymentComponent` promissory records before escalating (EC-FIN-02). Sends escalating reminders: Day 1 (SMS+Email) → Day 7 (Parent alert) → Day 15 (HOD notification) → Day 30 (Dean alert + portal restriction). | Finance Officer reviews defaulter list weekly. Dean approves portal restriction for persistent defaulters. | Defaulter status updated. Escalation communications sent. | Daily batch (auto) |
| 1.6 | Late Fee Computation | Payment received after due date and grace period: auto-calculates late fee per day. Adds to next invoice. | Finance Officer approves late fee waiver on documented request. | Late fee added to ledger. Student notified. Waiver logged with approver. | Same day as late payment |
| 1.7 | Demand Draft / Offline Payment | Accounts Staff records DD or cash payment. AI verifies instrument details. Posts to ledger on clearance confirmation. Updates `student_dues_status` read model. | Accounts Staff enters offline payment details. Finance Officer spot-checks weekly. | Offline payment posted. Receipt generated. Read model updated. | 1 business day |
| 1.8 | Reconciliation | Daily: auto-reconciles Razorpay settlement reports against ledger postings. Flags mismatches. Generates daily reconciliation report. | Finance Officer reviews and resolves mismatches. | Reconciliation report generated. `reconciliation.complete` event. | Daily overnight batch |

### GST Treatment — Fee Heads

| Fee Head | GST Status | Rate | Basis |
|---|---|---|---|
| Tuition Fee (UGC-recognised program) | EXEMPT | 0% | Notification 12/2017-CT(R), Entry 66 |
| Examination Fee | EXEMPT | 0% | Core educational service |
| Development / Infrastructure Fee | EXEMPT | 0% | Part of educational service |
| Hostel Fee (institution-run) | EXEMPT | 0% | Part of educational service |
| Hostel Fee (third-party managed) | TAXABLE | 18% | Commercial accommodation |
| Transport Fee (institution bus) | TAXABLE | 5% | Transportation service |
| Canteen / Mess (third-party) | TAXABLE | 18% | Catering service |
| Library Fine | TAXABLE | 18% | Penalty — ancillary service |
| Late Fee | TAXABLE | 18% | Ancillary charge |
| Alumni Donation (80G registered) | EXEMPT (80G) | 0% | If institution registered u/s 80G |

### GST e-Invoice / IRN Generation (new — FM-1 extension)

From April 2025, institutions above ₹5 crore annual turnover must generate
Invoice Reference Numbers (IRNs) for all B2B transactions via the NIC GST portal.

**Schema addition to `invoices` table:**

```sql
ALTER TABLE invoices
    ADD COLUMN irn               TEXT UNIQUE,
    ADD COLUMN irn_generated_at  TIMESTAMPTZ,
    ADD COLUMN qr_code_data      TEXT,
    ADD COLUMN einvoice_ack_number TEXT,
    ADD COLUMN einvoice_status   TEXT DEFAULT 'NOT_APPLICABLE'
        CHECK (einvoice_status IN (
            'NOT_APPLICABLE',  -- B2C or below threshold
            'PENDING',         -- B2B, threshold crossed, not yet generated
            'GENERATED',       -- IRN assigned
            'CANCELLED'        -- cancelled within 24 hours
        ));
```

**e-Invoice service:**

```python
class EInvoiceService:
    async def generate_irn(self, invoice_id: UUID, tenant_id: UUID) -> str | None:
        invoice = await get_invoice(invoice_id, tenant_id)
        tenant = await get_tenant_gstin(tenant_id)

        if not self._is_einvoice_applicable(invoice, tenant):
            return None  # B2C or below threshold — skip

        payload = {
            "Version": "1.1",
            "TranDtls": {"TaxSch": "GST", "SupTyp": "B2B", "RegRev": "N"},
            "DocDtls": {
                "Typ": "INV",
                "No": invoice.invoice_number,
                "Dt": invoice.invoice_date.strftime("%d/%m/%Y"),
            },
            "SellerDtls": {
                "Gstin": tenant.gstin, "TrdNm": tenant.legal_name,
                "Addr1": tenant.address, "Loc": tenant.city,
                "Pin": tenant.pincode, "Stcd": tenant.state_code,
            },
            "BuyerDtls": {
                "Gstin": invoice.buyer_gstin or "URP",
                "TrdNm": invoice.buyer_name,
                "Pos": invoice.place_of_supply_code,
                "Addr1": invoice.buyer_address,
                "Stcd": invoice.buyer_state_code,
            },
            "ValDtls": {
                "AssVal": str(invoice.taxable_amount),
                "CgstVal": str(invoice.cgst_amount),
                "SgstVal": str(invoice.sgst_amount),
                "TotInvVal": str(invoice.total_amount),
            },
        }

        response = await nic_einvoice_api.generate_irn(
            payload, tenant.gstin, tenant.gstin_auth_token
        )

        await execute_transaction([(
            """UPDATE invoices
               SET irn = $1, irn_generated_at = now(),
                   qr_code_data = $2, einvoice_ack_number = $3,
                   einvoice_status = 'GENERATED'
               WHERE id = $4 AND tenant_id = $5""",
            [response.irn, response.signed_qr_code, response.ack_number,
             str(invoice_id), str(tenant_id)]
        )])
        return response.irn

    def _is_einvoice_applicable(self, invoice, tenant) -> bool:
        return (
            invoice.buyer_gstin is not None        # B2B only
            and tenant.annual_turnover >= 5_00_00_000  # ≥ ₹5 crore
            and invoice.is_gst_taxable              # taxable supply
        )
```

**Feature flag:** `finance.einvoice_enabled` — off by default. Enable when institution
crosses the turnover threshold.

### Accounting Export — Tally / Busy (new — FM-1 extension)

Accounts teams use Tally or Busy and will not abandon them. ALIS must produce
clean exports — not replace these tools.

**Tally XML export (TallyPrime format):**

```python
class TallyExportService:
    async def export_fee_collections(
        self, tenant_id: UUID, date_from: date, date_to: date
    ) -> str:
        collections = await get_fee_collections(tenant_id, date_from, date_to)

        root = ET.Element("ENVELOPE")
        ET.SubElement(ET.SubElement(root, "HEADER"), "TALLYREQUEST").text = "Import Data"

        request_data = ET.SubElement(
            ET.SubElement(ET.SubElement(root, "BODY"), "IMPORTDATA"), "REQUESTDATA"
        )
        ET.SubElement(
            ET.SubElement(
                ET.SubElement(request_data.getparent(), "REQUESTDESC"),
                "REPORTNAME"
            ),
            "REPORTNAME"
        ).text = "Vouchers"

        for c in collections:
            v = ET.SubElement(ET.SubElement(request_data, "TALLYMESSAGE"), "VOUCHER")
            ET.SubElement(v, "DATE").text = c.date.strftime("%Y%m%d")
            ET.SubElement(v, "VOUCHERTYPENAME").text = "Receipt"
            ET.SubElement(v, "NARRATION").text = (
                f"Fee receipt {c.receipt_number} - {c.student_name}"
            )
            debit = ET.SubElement(v, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(debit, "LEDGERNAME").text = c.payment_mode_ledger
            ET.SubElement(debit, "ISDEEMEDPOSITIVE").text = "Yes"
            ET.SubElement(debit, "AMOUNT").text = f"-{c.amount}"
            credit = ET.SubElement(v, "ALLLEDGERENTRIES.LIST")
            ET.SubElement(credit, "LEDGERNAME").text = c.fee_head_ledger
            ET.SubElement(credit, "ISDEEMEDPOSITIVE").text = "No"
            ET.SubElement(credit, "AMOUNT").text = str(c.amount)

        return ET.tostring(root, encoding="unicode", xml_declaration=True)

    async def export_payroll_vouchers(self, tenant_id: UUID, payroll_month: str) -> str:
        """Same pattern — one receipt voucher per employee salary credit."""
        ...
```

**Busy export** is a CSV format with the same underlying data, different formatter.
Both are available from the Finance Officer's reports screen.

**Feature flags:** `finance.tally_export`, `finance.busy_export` — enable per
institution based on which accounting software they use.

**API endpoints:**
```
GET /api/v1/finance/export/tally?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD&type=fee_collections
GET /api/v1/finance/export/tally?type=payroll&month=YYYY-MM
GET /api/v1/finance/export/busy?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
```

### EC-ADM-05 — Razorpay Webhook Drop (P0 — Sprint 1)

**Trigger:** Student pays fee on deadline day. Payment leaves their bank account.
The Razorpay webhook to ALIS fails (network timeout, server restart, queue overflow).
ALIS ledger shows `UNPAID`. Exam module blocks hall ticket.

**What breaks:** Student has paid but is treated as defaulter. No self-service path.
Finance staff have no structured tool to resolve without risking double-posting.

**Fix Part 1: Idempotent webhook processing**

```python
async def process_razorpay_webhook(payload: dict, tenant_id: UUID):
    payment_id = payload["payload"]["payment"]["entity"]["id"]

    # Check idempotency — never process the same payment twice
    existing = await execute_query(
        "SELECT id FROM payment_webhook_log WHERE razorpay_payment_id = $1",
        [payment_id]
    )
    if existing:
        return  # Already processed — idempotent skip

    # Process the payment
    await post_payment_to_ledger(payload, tenant_id)
    await update_dues_status(payload["student_id"], tenant_id)

    # Record in idempotency log
    await execute_transaction([(
        """INSERT INTO payment_webhook_log
           (id, tenant_id, razorpay_payment_id, event_type, processed_at, payload)
           VALUES ($1, $2, $3, $4, now(), $5)""",
        [str(uuid4()), str(tenant_id), payment_id,
         payload["event"], json.dumps(payload)]
    )])
```

On startup: ALIS polls the Razorpay API for all payments in the last 24 hours and
replays any that are not in `payment_webhook_log`. This is the safety net.

**Fix Part 2: UTR reconciliation portal**

```python
@workflow.defn
class PaymentDisputeWorkflow:
    @workflow.run
    async def run(self, dispute: PaymentDisputeRequest):
        # Lift restriction for 48 hours while we verify
        await workflow.execute_activity(
            lift_restriction_temporarily,
            args=[dispute.student_id, dispute.tenant_id, timedelta(hours=48)]
        )

        # Query Razorpay directly — bypass the webhook
        payment = await workflow.execute_activity(
            query_razorpay_by_utr,
            args=[dispute.utr_number, dispute.order_id]
        )

        if payment.status == "captured":
            # Confirmed — post to ledger permanently
            await workflow.execute_activity(
                post_payment_to_ledger,
                args=[payment, dispute.student_id, dispute.tenant_id]
            )
            await workflow.execute_activity(
                lift_restriction_permanently,
                args=[dispute.student_id, dispute.tenant_id]
            )
        else:
            # Not found — restore restriction after 48h, alert Finance Officer
            await workflow.sleep(timedelta(hours=48))
            await workflow.execute_activity(
                restore_restriction_with_finance_alert,
                args=[dispute.student_id, dispute.tenant_id]
            )
```

Student portal shows: "Submit your UTR / transaction reference. We will verify with
your bank and lift the restriction within 2 hours."

---

## FM-2: Scholarships & Waivers

**Trigger:** `scholarship.awarded` event from SS-4 (Student Services), OR Dean
approves a fee waiver directly, OR management grants a category-based concession.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 2.1 | Award Ingestion | Receives `scholarship.awarded` event. Reads amount, type (full/partial, tuition-only/all-heads), duration (one-time/annual/full program), source (institutional/government/private). | No action — auto-ingested. | Scholarship record created. Linked to student ID. | Instant |
| 2.2 | Ledger Credit Computation | Computes credit per semester. Applies to applicable fee heads per scholarship rules. Calculates revised net payable. Updates `student_dues_status` read model. | Finance Officer reviews for new scholarship types. | Revised fee schedule. Student notified of reduced dues. | Same day |
| 2.3 | Fee Waiver Processing | For institutional waivers: applies percentage or fixed amount. Posts `WAIVER_CREDIT` ledger entry (never modifies existing invoice). | Dean / Registrar approves waiver. Finance Officer countersigns for waivers above ₹50,000 (configurable). | Waiver posted. Approval record stored with authoriser, date, amount. | 2 business days |
| 2.4 | Government DBT Tracking | For NSP and state portal scholarships: monitors DBT credit via API or manual confirmation. Reconciles against student account. Flags delays. Creates `AWAITING_GOVT_DBT` exemption record (EC-FIN-01). | Finance Officer confirms receipt and posts on DBT credit. | DBT credit posted. `scholarship.disbursed` event. Student notified. | Per government cycle |
| 2.5 | 80G Receipt Issuance | For private donations: auto-generates 80G receipt (sequential number, donor name, PAN, amount, purpose, institution registration number). | Finance Officer countersigns above ₹1 lakh (configurable). | 80G receipt issued and archived. Donation register updated. | Same day |
| 2.6 | Renewal & Suspension | Semester end: checks scholarship holder's academic performance against retention criteria. Auto-generates renewal or suspension letter. Adjusts next semester fee schedule. | Finance Officer + Dean review suspension cases. Dean approves reinstatement. | Fee schedule updated. Renewal / suspension letter sent. `scholarship.renewal_status` event. | 5 business days before semester fee due |

### EC-FIN-01 — Government DBT Scholarship Delay (P1 — Sprint 2)

**Trigger:** Student relies on a state scholarship promised in August but disbursed
in March. Daily defaulter batch flags them from September onward. Hall ticket blocked.

**What breaks:** Student who has done nothing wrong is treated as defaulter for
7 months. Exam access blocked. Severe distress and legitimate grievance.

**Fix: `student_fee_exemptions` table with explicit defaulter pause**

```sql
CREATE TABLE student_fee_exemptions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL,
    student_id       UUID NOT NULL,
    exemption_type   TEXT NOT NULL
        CHECK (exemption_type IN (
            'AWAITING_GOVT_DBT',
            'AWAITING_BANK_LOAN',
            'AWAITING_NGO_GRANT',
            'PAYMENT_DISPUTE',
            'SCHOLARSHIP_ESCROW',
            'MANAGEMENT_WAIVER'
        )),
    expected_date    DATE,
    amount_expected  DECIMAL(12,2),
    reference_number TEXT,                -- scholarship ID / loan sanction letter
    approved_by      UUID NOT NULL,       -- Finance Officer who approved
    valid_until      DATE NOT NULL,       -- exemption expires on this date
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT now()
);
```

**Defaulter detection check (Celery Beat daily job):**

```python
async def is_student_exempted(student_id: UUID, tenant_id: UUID) -> bool:
    exemption = await execute_query(
        """SELECT id FROM student_fee_exemptions
           WHERE student_id = $1 AND tenant_id = $2
           AND valid_until >= CURRENT_DATE""",
        [str(student_id), str(tenant_id)]
    )
    return len(exemption) > 0

# In the defaulter detection loop:
if await is_student_exempted(student.id, tenant_id):
    continue  # Skip — exemption active. Log skip reason for audit.
```

**Exam eligibility gate (in Examination module):**
The eligibility check must read: `dues_cleared OR is_exempted`.
The `student_dues_status` read model carries an `exemption_active` boolean
populated by this module.

**Important:** The exemption does NOT waive the fee. It pauses escalation only.
When DBT credit arrives, Finance closes the exemption. If credit never arrives,
the student remains responsible.

**Feature flag:** `finance.government_dbt_exemption` — always enabled for Indian institutions.

---

## FM-3: Refunds & Cancellations

**Trigger:** `student.cancelled` event from Admissions, OR student submits a refund
request post-enrollment, OR institution cancels a program.

**UGC Refund Policy (mandatory — not configurable):**

| Scenario | Refund Entitlement | Timeline |
|---|---|---|
| Cancellation 15+ days before program start | Full fee minus ₹1,000 processing fee | Within 15 days of request |
| Cancellation 14 days to program start | Full fee minus ₹1,000 | Within 15 days |
| Cancellation within 30 days of start | 80% of tuition | Within 15 days |
| Cancellation 30–60 days after start | 50% of tuition | Within 15 days |
| Cancellation after 60 days of start | No refund on tuition; hostel security deposit returned | Within 30 days |
| Institution cancels program / seat | Full refund + interest | Within 15 days |

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 3.1 | Refund Request Intake | Receives cancellation request or `student.cancelled` event. Assigns Refund ID. Collects: reason, bank details, supporting documents. | No action — auto-captured. | Refund ID issued. Auto-acknowledgement within 1 hour. | 1 hour (auto-ack) |
| 3.2 | Eligibility & Amount Computation | Computes refund per UGC policy (date-of-request logic). Deducts outstanding dues, non-refundable processing fee (₹1,000). | Finance Officer reviews for edge cases (scholarship holders, mid-year transfers). | Refund eligibility report. Computed amount confirmed. | Same day |
| 3.3 | Clearance Check | Verifies: Library (`library.cleared`), Hostel (`hostel.cleared`), Exams (no hall ticket issued for upcoming exam). Flags pending clearances to student. | Student clears pending dues / returns. Staff confirms clearance. | Clearance status confirmed or pending items listed. | 3 business days |
| 3.4 | Refund Approval | Drafts approval note: student ID, program, dates, fees paid, eligible refund, deductions, net refund. Routes to Dean. | Dean / Registrar approves. Finance Officer countersigns above ₹10,000 (configurable). | Refund approved. Approval record stored. | 3 business days (within UGC 15-day clock) |
| 3.5 | Bank Verification & NEFT | Verifies bank account details (IFSC, account number). Initiates NEFT via bank API or generates payment advice. | Accounts Staff confirms bank details. Finance Officer authorises NEFT batch. | Payment initiated. UTR recorded. `refund.initiated` event. | 1 business day post-approval |
| 3.6 | Credit Confirmation & Receipt | Monitors bank credit confirmation. Generates refund receipt (Refund ID, amount, UTR, date). Sends to student. | No action required. | Refund receipt issued. `refund.completed` event. Portal updated. | Within 15 days total (UGC mandate) |
| 3.7 | Ledger Reversal & Reporting | Posts `PAYMENT_REVERSAL` ledger entry (never modifies original). Updates seat counter in Admissions (if pre-enrollment). Adds to monthly refund summary. | Finance Officer reviews monthly refund report. | Ledger updated. Seat released (if applicable). | Same day as credit confirmation |

### EC-FIN-03 — Retroactive Scholarship Revocation (P1 — Sprint 2)

**Trigger:** Student received merit scholarship in Semester 1. In Semester 3, a
major disciplinary violation is confirmed. Management revokes the scholarship
retroactively to Semester 1. The naive approach — updating posted ledger entries —
violates accounting controls.

**What breaks:** Modifying a closed accounting period is an audit control violation.
Student will dispute the amount. Audit trail is destroyed.

**Fix: Reversal Ledger Entry — never mutate closed periods**

```python
class LedgerEntryType(str, Enum):
    FEE_CHARGE          = "fee_charge"
    PAYMENT_RECEIVED    = "payment_received"
    SCHOLARSHIP_CREDIT  = "scholarship_credit"
    SCHOLARSHIP_REVERSAL = "scholarship_reversal"   # never edits original
    LATE_FEE_CHARGE     = "late_fee_charge"
    WAIVER_CREDIT       = "waiver_credit"
    WAIVER_REVERSAL     = "waiver_reversal"
    PAYMENT_REVERSAL    = "payment_reversal"        # for refunds

# To revoke Semester 1 scholarship:
# WRONG: UPDATE ledger SET amount = 0 WHERE type = 'SCHOLARSHIP_CREDIT'
# RIGHT: INSERT new entry type = 'SCHOLARSHIP_REVERSAL', amount = original_amount

class ScholarshipRevocationRecord(BaseModel):
    original_scholarship_credit_id: UUID  # entry being reversed
    reversal_entry_id: UUID               # new reversal entry
    revocation_reason: str
    effective_from: date                  # which semester it applies from
    total_amount_reversed: Decimal
    approved_by_dean: UUID
    approved_by_finance_officer: UUID     # dual authorization required
    dispute_window_closes_at: datetime    # 30 days from revocation
    disputed: bool = False
```

**Student receives an itemised statement** showing original credits and reversals
as separate line items — transparent and auditable. A 30-day dispute window opens
automatically where the student can challenge the revocation through the grievance
module (SS-5).

---

## FM-4: Vendor & Purchase Management

**Trigger:** Department raises a Purchase Requisition (PR) via the admin portal.

**Purchase Approval Thresholds (configurable):**

| Purchase Value | Approval Required | Process |
|---|---|---|
| Up to ₹10,000 | Accounts Staff | Direct purchase — petty cash |
| ₹10,001 – ₹1,00,000 | Finance Officer | 3 competitive quotations |
| ₹1,00,001 – ₹10,00,000 | Finance Officer + Dean | Minimum 3 quotations + comparative |
| Above ₹10,00,000 | Finance Officer + Dean + VC | Formal tender (RFP/RFQ) mandatory |

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 4.1 | Purchase Requisition (PR) | Validates: budget head exists, funds available, no duplicate PR. | Department Head countersigns. | PR ID assigned. Budget hold placed. `pr.submitted` event. | Same day |
| 4.2 | Vendor & Quotation | Routes RFQ to empanelled vendors. Collects and organises comparative statement. For new vendors: initiates onboarding (GSTIN, PAN, bank details, TDS category). | Finance Officer reviews, identifies preferred vendor. | Comparative statement generated. Vendor shortlisted. | 5 business days |
| 4.3 | Purchase Order Generation | AI drafts PO: vendor details, item/service, quantity, rate, delivery date, payment terms, TDS applicability, GST treatment, institution GSTIN. Flags ITC eligibility. | Finance Officer approves and e-signs. Dean / VC co-signs per threshold. | PO issued to vendor. `po.issued` event. | 2 business days post-quotation |
| 4.4 | Delivery & GRN | On vendor delivery: generates GRN template. Matches delivered items against PO. Flags shortages, substitutions, quality deviations. | Receiving department verifies delivery. Signs GRN. | GRN recorded. `grn.completed` event. Invoice matching enabled. | Day of delivery |
| 4.5 | Invoice Processing & 3-Way Match | Receives vendor invoice. Auto-matches against PO and GRN (3-way match). Flags discrepancies. Extracts GST details for ITC claim. | Finance Officer resolves discrepancies. Approves matched invoice. | Invoice matched. ITC amount computed. TDS amount computed. | 3 business days |
| 4.6 | TDS Deduction & Compliance | Identifies TDS applicability per section. Deducts from payment. Generates Form 16A. Schedules TDS deposit (7th of following month). Files 26Q quarterly. | Finance Officer reviews TDS for new vendor categories. | TDS deducted. Form 16A queued. 26Q data compiled. | 7th of month |
| 4.7 | Payment Processing | Generates NEFT/RTGS payment advice for net amount (invoice minus TDS). Schedules per agreed terms. | Finance Officer authorises payment batch. VC approves advances above ₹5 lakh. | Payment initiated. UTR recorded. `vendor.paid` event. | Per payment terms |
| 4.8 | Vendor Performance Tracking | Tracks delivery timeliness, quality, invoice accuracy per vendor quarterly. Computes performance score. Flags poor performers. | Finance Officer + Dean review quarterly vendor report. | Vendor scorecard updated. Low-performers flagged. | Quarterly (auto) |
| 4.9 | GST ITC Reconciliation | Monthly: reconciles ITC claimed against GSTR-2B. Flags mismatches. Generates GSTR-3B data. | Finance Officer reviews ITC reconciliation. Resolves vendor mismatches. | GSTR-3B data ready. Monthly GST reconciliation report. | 15th of following month |

### TDS Rate Reference (FY 2025-26)

| Section | Payment Type | Rate | Threshold |
|---|---|---|---|
| 194J | Professional services | 10% | ₹50,000/year |
| 194J | Technical services | 2% | ₹50,000/year |
| 194I | Rent (land/building) | 10% | ₹2,40,000/year |
| 194C | Contractor payments | 1% (individual) / 2% (company) | ₹30,000/txn or ₹1,00,000/year |
| 194H | Commission / brokerage | 5% | ₹15,000/year |
| 192 | Salary | Per tax slab | Above exemption limit |

### EC-FIN-02 — Fragmented Multi-Source Fee Payment (P1 — Sprint 2)

**Trigger:** A student's ₹2,00,000 annual fee is paid via ₹10,000 UPI +
₹50,000 Demand Draft + ₹1,40,000 bank education loan in tranches. The system
sees partial payments and flags a defaulter.

**What breaks:** A fully compliant student is treated as a defaulter because
the bank tranche schedule doesn't align with the institution's fee calendar.

**Fix: Promissory / Escrow Ledger with explicit third-party fund tracking**

```python
class FeePaymentComponent(BaseModel):
    invoice_id: UUID
    component_type: str  # 'direct_payment'|'dd'|'loan_tranche'|'scholarship'|'promissory'
    amount: Decimal
    payment_reference: str | None
    expected_date: date | None        # for promissory components
    received: bool
    received_at: datetime | None
    posted_by: UUID | None            # Finance staff who confirmed receipt

# Invoice is considered PAID when:
#   sum(received=True components) >= invoice_amount
#
# Defaulter escalation is PAUSED when:
#   sum(ALL components including promissory) >= invoice_amount
#   AND (expected_date + grace_days) has not passed
```

Finance staff create promissory components by logging the bank loan sanction
letter number, expected disbursement schedule, and tranche amounts. This pauses
defaulter escalation until `expected_date + 15 days` (configurable).

The `student_dues_status` read model carries a `promissory_cover_active` boolean
so the Examination module can correctly reflect exemption status.

---

## FM-5: Payroll (Faculty & Staff)

**Trigger:** Monthly payroll cycle — configurable date (default: 25th of each month
for processing; 1st of following month for disbursement). AI initiates automatically.

**Boundary with HR Module (HR-3):** HR owns attendance and LOP computation.
Finance owns salary computation, deductions, and disbursement. Data flows via
the `payroll.inputs_ready` event.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 5.1 | Payroll Inputs Collection | Pulls from HR module: active employees, designation, grade, LOP days, approved leaves. Pulls from Attendance module. Flags data gaps to Accounts Staff. | Accounts Staff resolves flagged gaps (missing attendance, new joinee data). | Payroll input sheet compiled. `payroll.inputs_ready` event consumed. | 20th of month |
| 5.2 | Gross Salary Computation | Computes gross: Basic + HRA + DA + Allowances. Applies LOP deductions (Gross/30 × LOP days). Applies OT additions if applicable. | No action required. | Gross salary computed for all active employees. | 22nd of month |
| 5.3 | Statutory Deductions | Computes: PF (12% employee + 13% employer including admin charges). ESI (0.75% employee + 3.25% employer, salary ≤ ₹21,000). PT (per Telangana: ₹200/month above ₹15,000). TDS Sec 192 per declared regime. | Finance Officer reviews TDS for employees who changed tax regime. | Deduction amounts computed. | 23rd of month |
| 5.4 | Net Pay Computation | Net = Gross − PF − ESI − PT − TDS − Loan repayment − Advance recovery. Generates payslip PDF per employee. | No action required. | Payslip PDFs generated. Sent to employee email + HR portal. Stored in employee digital file (HR-2). | 24th of month |
| 5.5 | Payroll Approval | Generates summary: total headcount, gross, deductions, net, employer contributions. Routes to Finance Officer. | Finance Officer approves payroll. VC countersigns if total exceeds threshold. | Payroll approved. `payroll.approved` event. Bank NEFT file generated. | 25th of month |
| 5.6 | Salary Disbursement | Initiates NEFT batch via bank API or generates bank-formatted salary file. Records UTR per transaction. Updates salary disbursement register. | Finance Officer releases NEFT batch / uploads bank file. | Salary credited. `salary.disbursed` event. | 1st of following month |
| 5.7 | Statutory Deposits | Schedules: PF deposit — 15th of following month. ESI deposit — 15th. PT — monthly per Telangana schedule. TDS Sec 192 — 7th of following month. | Finance Officer authorises each statutory deposit. | Challan numbers recorded. Deposit confirmation archived. | Per statutory due dates |
| 5.8 | Annual Form 16 | At financial year end: computes annual TDS per employee. Reconciles with 24Q. Generates Form 16 (Part A from TRACES + Part B computed by AI). Distributes to employees by June 15. | Finance Officer reviews and countersigns batch. | Form 16 issued to all employees. Stored in employee digital file (HR-2). | June 15 (statutory deadline) |

**Payroll Compliance Calendar:**

| Obligation | Due Date | Section |
|---|---|---|
| TDS on Salary deposit | 7th of following month | Sec 192 |
| PF deposit | 15th of following month | EPF Act |
| ESI deposit | 15th of following month | ESI Act |
| PT (Telangana) | Monthly per state schedule | State PT Act |
| TDS Return (24Q) | 31 Jul / 31 Oct / 31 Jan / 31 May | IT Act |
| Form 16 issuance | June 15 | IT Act |

---

## FM-6: Budget Planning & Tracking

**Trigger:** Financial year start (April 1), OR VC directive for mid-year revision,
OR new program launch requiring budget allocation.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 6.1 | Budget Template Generation | At FY start: generates department-wise templates pre-filled with prior year actuals, enrollment projections, inflation adjustments. Sends to each HOD. | HOD fills in requirements and submits. | Templates distributed. Submission deadline set (15 days after FY start). | FY start (auto) |
| 6.2 | Budget Consolidation | Consolidates all submissions. Categorises: Personnel / Academic / Infrastructure / Admin / Statutory / Capital. Computes projected income vs. expenditure. Flags deficit. | Finance Officer reviews. Highlights major variances vs. prior year. | Consolidated budget draft. Income-expenditure projection. | 10 days after submission deadline |
| 6.3 | Budget Review & Negotiation | Generates comparison: current request vs. prior year actuals vs. prior year budget. Highlights departments with > 20% increase request. Schedules review meetings. | Finance Officer + Dean negotiate with HODs. Management Committee reviews. | Negotiated figures recorded per round. Audit trail of changes. | 15-day negotiation window |
| 6.4 | Budget Approval | Drafts final document: income heads, expenditure heads, surplus/deficit projection. | VC / Management Committee approves. Board ratification above threshold. | Annual budget approved. `budget.approved` event. Budget figures loaded into system. | Before April 30 |
| 6.5 | Budget Allocation to Departments | Auto-allocates approved amounts to each department and cost centre. Creates budget ledger accounts. Enables PRs only against approved heads (FM-4 validation). | Finance Officer confirms allocation mapping. | Budget allocated. Departments notified. PR system unlocked for the year. | 2 days post-approval |
| 6.6 | Monthly Budget vs. Actual | Monthly: compares actual income and expenditure against budget. Computes variance. Flags head where actual exceeds budget by > 10%. Flags income shortfalls > 5%. | Finance Officer reviews. Dean reviews income shortfalls. VC notified of > 20% overrun. | Monthly variance report. `budget.variance_alert` event for significant deviations. | 5th of following month |
| 6.7 | Revised Estimates & Supplementary | Mid-year: if actuals significantly deviate, generates Revised Estimates automatically. For supplementary requests: generates justification template. | Dean proposes RE. VC / Management Committee approves. | Revised budget figures loaded. System limits updated. Board communicated. | Within 30 days of VC directive |

---

## FM-7: Financial Reporting & Audits

**Trigger:** Monthly / quarterly / annual triggers (fully automated). Audit trigger on VC directive.

| # | Stage | AI Executes | Human Approves / Acts | Output / Event | SLA |
|---|---|---|---|---|---|
| 7.1 | Monthly MIS Report | 5th of every month: auto-generates fee collection summary, outstanding dues, refunds, payroll cost, vendor payments, budget vs. actuals, cash position. Distributes to Finance Officer, Dean, VC. | VC reviews and raises queries. Finance Officer responds. | Monthly MIS distributed. Queries logged and resolved. | 5th of month (auto) |
| 7.2 | GST Return Data | Monthly: compiles outward supply data (GSTR-1). Compiles ITC data (GSTR-3B). Reconciles with GSTR-2B. Generates draft returns. | Finance Officer reviews and files on GST portal. | GSTR-1 filed (11th). GSTR-3B filed (20th). | Before GST deadlines |
| 7.3 | TDS Return Preparation | Quarterly: compiles 26Q (non-salary) and 24Q (salary) TDS deductions. Matches against challan deposits. Generates Form 16A for vendors (15 days after Q4 filing). | Finance Officer authorises TDS return filing. | Quarterly TDS return filed. Form 16A / 16 issued. | 31 Jul / 31 Oct / 31 Jan / 31 May |
| 7.4 | Annual Financial Statements | March 31: auto-generates Income & Expenditure Account, Balance Sheet, Receipts & Payments Account, Schedules. Applies accounting principles for educational trusts. | Finance Officer reviews draft. Statutory Auditor receives for audit. | Draft annual accounts. `annual_accounts.draft` event. | By April 30 |
| 7.5 | Statutory Audit Support | Compiles audit pack: all vouchers (digitally stored), bank reconciliation, TDS records, GST returns, payroll registers, vendor contracts, student fee ledgers, scholarship records. Responds to auditor data requests within 2 business days. | Finance Officer coordinates with auditor. VC signs management representation letter. | Audit pack submitted. Observations addressed. Final audited accounts produced. | Per auditor timeline |
| 7.6 | Regulatory & NAAC Reporting | Compiles financial data for UGC Annual Returns, NAAC criteria (financial sustainability, expenditure on academics vs. administration), NIRF (expenditure per student). Auto-populates report templates. | Finance Officer reviews. VC signs off. Dean signs NAAC financial criteria. | UGC Annual Return financial section complete. NAAC and NIRF data ready. | Per regulatory deadlines |

**Statutory Filing Calendar:**

| Filing | Due Date | Form |
|---|---|---|
| GSTR-1 (monthly) | 11th of following month | CGST Act |
| GSTR-3B (monthly) | 20th of following month | CGST Act |
| GSTR-9 (annual) | December 31 | CGST Act |
| TDS Return (26Q / 24Q) | 31 Jul / 31 Oct / 31 Jan / 31 May | IT Act |
| Form 16 / 16A | 15 days after Q4 TDS return | IT Act |
| PF Monthly ECR | 15th of following month | EPF Act |
| ESI Monthly Return | 15th of following month | ESI Act |
| UGC Annual Return | As notified | UGC Regulations |
| NIRF Data Submission | January (annual) | MHRD directive |
| Statutory Audit Completion | September 30 (typically) | Companies Act / Trust Act |

---

## Cross-Module Integration Map

| Event | Fired By | Consumed By | Payload / Purpose |
|---|---|---|---|
| `student.enrolled` | Admissions | FM-1 Fee Collection | Student ID, program, batch, category, hostel_opted — triggers fee schedule generation from locked fee_structure |
| `fee.paid` | FM-1 | Admissions | Payment confirmation — releases seat confirmation |
| `student.dues_cleared` | FM-1 | Exams (signal only — module queries read model) | Clearance signal — Exams re-queries `student_dues_status` at generation time |
| `student.financial_flag` | FM-1 | SS-4 Scholarships | Financial hardship signal — triggers scholarship eligibility check |
| `scholarship.awarded` | SS-4 | FM-2 Scholarships | Award details — triggers ledger credit |
| `scholarship.disbursed` | FM-2 | SS-4 Scholarships | Disbursement confirmation — updates scholarship status |
| `student.cancelled` | Admissions | FM-3 Refunds | Cancellation trigger — initiates refund workflow |
| `refund.completed` | FM-3 | Admissions | Refund confirmation — seat released back to pool |
| `hostel.cleared` | SS-1 Hostel | FM-3 Refunds | Clearance — enables security deposit refund |
| `library.cleared` | SS-2 Library | FM-3 Refunds | Clearance — prerequisite for full refund |
| `pr.submitted` | FM-4 Vendor | FM-6 Budget | Budget hold placed on PR submission |
| `po.issued` | FM-4 Vendor | Vendor Portal | PO dispatched to vendor |
| `vendor.paid` | FM-4 Vendor | FM-7 Reporting | Payment record — included in monthly MIS |
| `salary.disbursed` | FM-5 Payroll | HR Module | Payroll confirmation — updates employment records |
| `budget.approved` | FM-6 Budget | FM-4 Vendor | Unlocks PR system for the financial year |
| `budget.variance_alert` | FM-6 Budget | Dean + VC Dashboard | Significant deviation — management attention |
| `annual_accounts.draft` | FM-7 Reporting | Statutory Auditor | Annual accounts ready for audit |

---

## SLA & Escalation Matrix

| Module | Approval Gate | Approver | SLA | Breach Escalation |
|---|---|---|---|---|
| Fee Collection | Fee schedule approval (per batch) | Finance Officer | Before admissions open | VC notified; admissions paused |
| Fee Collection | Partial payment plan approval | Finance Officer | 2 business days | Escalates to Dean |
| Fee Collection | Late fee waiver | Finance Officer | 3 business days | Auto-rejected with reason |
| Fee Collection | Defaulter portal restriction | Dean | 30 days post-due | Auto-applied if Dean unavailable |
| Scholarships | Waiver approval (above ₹50,000) | Dean + Finance Officer | 2 business days | Escalates to VC |
| Scholarships | DBT exemption creation | Finance Officer | Same day of request | Escalates to Dean |
| Refunds | Refund approval | Dean / Registrar | 3 business days | Escalates to VC; UGC 15-day clock tracked |
| Refunds | NEFT authorisation | Finance Officer | 1 business day post-approval | Auto-escalates to VC |
| Vendor | PR approval (up to ₹1 lakh) | Finance Officer | 2 business days | Escalates to Dean |
| Vendor | PO approval (above ₹10 lakh) | Finance Officer + Dean + VC | 5 business days | Board notified |
| Vendor | Invoice approval | Finance Officer | 3 business days | Escalates to Dean |
| Vendor | TDS deposit | Accounts Staff (auto-scheduled) | 7th of following month | Finance Officer alerted 3 days before |
| Payroll | Payroll approval | Finance Officer | 25th of month | Escalates to VC; disbursement held |
| Payroll | NEFT release | Finance Officer | 25th of month | VC releases directly |
| Budget | Annual budget approval | VC / Management Committee | April 30 | Board notified; interim budget limit applied |
| Budget | Supplementary budget | VC | 30 days of request | Board approval sought |
| Reporting | GST return filing | Finance Officer | Per statutory deadline | VC alerted 5 days before |
| Reporting | Audit sign-off | VC | Per auditor timeline | Board notified |

---

## What Actors Never Do (AI Handles Completely)

**Fee Collection & Scholarships:**
- Generate individual student fee schedules or invoices
- Send fee reminders or defaulter escalation notifications
- Calculate late fees or scholarship credit amounts
- Post payments to student ledgers
- Generate payment receipts with sequential numbers
- Update `student_dues_status` read model after dues changes
- Apply scholarship credits to revised fee schedules
- Issue 80G receipts for donations
- Generate IRN numbers for e-Invoices
- Generate Tally XML or Busy CSV export files

**Refunds & Vendor:**
- Compute refund amounts per UGC policy
- Match vendor invoices against POs and GRNs (3-way match)
- Calculate TDS amounts per vendor category and section
- Generate TDS certificates (Form 16A)
- Schedule TDS deposits and flag upcoming due dates
- Compile GSTR-1 and GSTR-3B data from transaction records
- Track ITC eligibility on vendor invoices

**Payroll & Budget:**
- Pull attendance and LOP data from HR module
- Compute gross salary, PF, ESI, PT, TDS deductions
- Generate payslips for all employees
- Schedule and initiate statutory PF and ESI deposits
- Pre-fill budget templates with prior year actuals
- Compute monthly budget vs. actual variance reports

**Reporting & Compliance:**
- Compile monthly MIS reports and distribute to management
- Generate draft annual financial statements
- Compile audit packs (vouchers, bank statements, TDS records)
- Auto-populate UGC, NAAC, and NIRF financial report templates
- File compliance calendar reminders before each statutory deadline

---

## Notification Map

| Module | Trigger Event | Recipients | Channel |
|---|---|---|---|
| Fee Collection | Fee invoice generated | Student + Parent | Email + SMS + WhatsApp |
| Fee Collection | Payment received | Student | Email (receipt PDF) |
| Fee Collection | Due date reminder (7d / 3d / same day) | Student + Parent | SMS |
| Fee Collection | Payment overdue Day 1 | Student + Parent | Email + SMS |
| Fee Collection | Payment overdue Day 7 | Student + Parent + HOD | Email |
| Fee Collection | Payment overdue Day 30 | Dean + Finance Officer | Dashboard alert |
| Fee Collection | DBT exemption created | Student | Email |
| Fee Collection | DBT exemption expiring (7 days) | Student + Finance Officer | Email |
| Fee Collection | Payment dispute UTR submitted | Student + Finance Officer | Email |
| Scholarships | Scholarship credit applied | Student | Email |
| Scholarships | 80G receipt issued | Donor | Email (PDF) |
| Scholarships | Scholarship suspension warning | Student + Faculty Advisor | Email |
| Refunds | Refund request acknowledged | Student | Email (Refund ID) |
| Refunds | Refund approved — payment initiated | Student | Email + SMS |
| Refunds | Refund credited | Student | SMS |
| Vendor | PO issued | Vendor | Email + vendor portal |
| Vendor | Payment credited | Vendor | Email (UTR) |
| Payroll | Payslip issued | Employee | Email + HR portal |
| Payroll | Salary credited | Employee | SMS |
| Payroll | Form 16 issued | Employee | Email (PDF) |
| Budget | Monthly variance alert | Finance Officer + Dean | Email + dashboard |
| Budget | Budget overrun > 20% | VC | Email + dashboard (urgent) |
| Reporting | Monthly MIS ready | Finance Officer + Dean + VC | Email |
| Reporting | GST filing due in 5 days | Finance Officer | Email + dashboard |
| Reporting | TDS deposit due in 3 days | Accounts Staff + Finance Officer | Email |

---

## Configuration Parameters

| Module | Parameter | Default |
|---|---|---|
| Fee Collection | Payment modes | UPI, Net Banking, Card, DD, Cash |
| Fee Collection | Partial payment allowed | Yes — minimum 50% per semester |
| Fee Collection | Grace period after due date | 7 days |
| Fee Collection | Late fee per day | ₹50/day after grace period |
| Fee Collection | Defaulter restriction threshold | 30 days overdue |
| Fee Collection | e-Invoice turnover threshold | ₹5 crore (statutory — not configurable) |
| Scholarships | Waiver approval threshold | Above ₹50,000 → Dean sign-off |
| Scholarships | 80G auto-issue limit | Up to ₹1 lakh; above → Finance Officer countersigns |
| Scholarships | DBT exemption default validity | 180 days (configurable) |
| Refunds | Non-refundable processing fee | ₹1,000 per UGC mandate (not configurable) |
| Vendor | Petty cash limit | ₹10,000 per transaction |
| Vendor | Formal tender threshold | Above ₹10,00,000 |
| Vendor | Payment terms (standard) | 30 days from invoice approval |
| Vendor | Advance payment VC threshold | Above ₹5,00,000 |
| Payroll | Processing date | 25th of each month |
| Payroll | Disbursement date | 1st of following month |
| Payroll | Tax regime default | New regime (employee can opt old on declaration) |
| Budget | Template submission deadline | 15 days after FY start |
| Budget | Variance alert threshold | > 10% deviation on any head |
| Budget | VC notification threshold | > 20% overrun |
| Reporting | MIS distribution date | 5th of every month |
| Reporting | GST filing advance reminder | 5 days before due date |
| Reporting | TDS deposit advance reminder | 3 days before 7th |

---

*Document version: 2.0 | March 2026*
*Connected to: admissions_workflow.md → academic_operations_workflow.md →*
*examination_workflow.md → student_services_workflow.md → finance_workflow.md →*
*hr_payroll_workflow.md → regulatory_accreditation_workflow.md*
*Full institutional lifecycle: Lead Captured → Graduated → Alumni → Annual Audit*
*QUAICU Pvt. Ltd. | quaicu.org | Hyderabad, India | Confidential*
