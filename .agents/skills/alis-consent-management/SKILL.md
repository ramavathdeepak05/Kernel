---
name: alis-consent-management
description: |
  ALIS consent management patterns for data collection, processing, and withdrawal. Use when implementing
  consent capture, consent auditing, withdrawal workflows, data subject rights, or reviewing any feature
  that collects or processes personal data from students, staff, or alumni. Covers consent collection
  before PII storage, consent audit trail via AuditLedger, withdrawal enforcement via RetentionService,
  purpose limitation, data subject access requests. Trigger keywords: consent, GDPR, data subject,
  privacy, opt-in, opt-out, withdrawal, consent form, consent record, data collection, purpose,
  lawful basis, right to access, right to erasure, data subject request, privacy notice, consent log.
---

# ALIS Consent Management

You are the ALIS Privacy & Consent Expert. ALIS handles student PII, financial records, biometric
data, and academic transcripts — all requiring explicit consent where legally mandated.

## Core Principle

> **No REGULATED or CONFIDENTIAL data is stored without a lawful basis.**
> For student PII, the lawful basis is either:
> (a) **Contractual necessity** — data required to deliver the educational service, or
> (b) **Explicit consent** — for optional data (biometrics, marketing, alumni tracking)

## Consent Data Model

Consent records are stored in a dedicated table. Add this in a migration if not present:

```sql
CREATE TABLE IF NOT EXISTS consent_records (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES organisations(id),
    subject_id      UUID NOT NULL,         -- User/Student/Staff ID
    subject_type    TEXT NOT NULL,         -- "student", "staff", "alumni"
    purpose         TEXT NOT NULL,         -- What data is collected for
    data_categories JSONB NOT NULL,        -- Which sensitivity categories
    lawful_basis    TEXT NOT NULL,         -- "consent", "contract", "legal_obligation"
    status          TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE / WITHDRAWN / EXPIRED
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,           -- NULL = no expiry
    withdrawn_at    TIMESTAMPTZ,
    withdrawn_by    UUID,
    ip_address      TEXT,                  -- Where consent was recorded
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
```

## Recording Consent

Consent MUST be recorded before storing any optional PII or REGULATED data:

```python
from server.db_service import execute_transaction
from server.core.audit import AuditLedger, AuditAction
from uuid import uuid4
from datetime import datetime, timezone

def record_consent(
    org_id: str,
    subject_id: str,
    subject_type: str,  # "student", "staff", "alumni"
    purpose: str,
    data_categories: list,
    lawful_basis: str,  # "consent", "contract", "legal_obligation"
    actor_id: str,
    ip_address: str = None,
    expires_at: datetime = None,
) -> str:
    consent_id = str(uuid4())

    execute_transaction([
        ("""
        INSERT INTO consent_records
            (id, org_id, subject_id, subject_type, purpose, data_categories,
             lawful_basis, status, granted_at, expires_at, ip_address)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'ACTIVE', NOW(), %s, %s)
        """, (
            consent_id, org_id, subject_id, subject_type, purpose,
            json.dumps(data_categories), lawful_basis, expires_at, ip_address,
        )),
    ])

    # Audit log (mandatory)
    AuditLedger.log(
        action=AuditAction.CREATE,
        actor_id=actor_id,
        actor_role="system",
        entity_type="consent_record",
        entity_id=consent_id,
        tenant_id=org_id,
        metadata={
            "subject_id": subject_id,
            "subject_type": subject_type,
            "purpose": purpose,
            "data_categories": data_categories,
            "lawful_basis": lawful_basis,
        },
    )
    return consent_id
```

## Consent Purposes Reference

Use consistent purpose strings across the system:

| Purpose Key | Description | Lawful Basis |
|---|---|---|
| `enrollment_processing` | Admissions and enrollment data | `contract` |
| `academic_records` | Marks, grades, transcripts | `legal_obligation` |
| `financial_processing` | Fee collection and payments | `contract` |
| `attendance_tracking` | Daily attendance records | `contract` |
| `biometric_attendance` | Facial/fingerprint attendance | `consent` |
| `communication_email` | Institutional email notifications | `contract` |
| `communication_sms` | SMS alerts | `consent` |
| `alumni_tracking` | Alumni profile and placement data | `consent` |
| `marketing_communications` | Newsletters, event invitations | `consent` |
| `research_participation` | Academic research data use | `consent` |

## Consent Validation Before Data Collection

```python
from server.db_service import execute_query

def has_active_consent(org_id: str, subject_id: str, purpose: str) -> bool:
    """Check if subject has active, non-expired consent for a given purpose."""
    rows = execute_query(
        """
        SELECT id FROM consent_records
        WHERE org_id = %s
          AND subject_id = %s
          AND purpose = %s
          AND status = 'ACTIVE'
          AND (expires_at IS NULL OR expires_at > NOW())
        LIMIT 1
        """,
        (org_id, subject_id, purpose),
    )
    return len(rows) > 0

# Before collecting biometric data
if not has_active_consent(org_id, student_id, "biometric_attendance"):
    raise PermissionDeniedError("Biometric consent not granted by student")
```

## Consent Withdrawal (Right to Withdraw)

```python
from datetime import datetime, timezone

def withdraw_consent(
    org_id: str,
    subject_id: str,
    purpose: str,
    actor_id: str,
    actor_role: str,
) -> None:
    now = datetime.now(timezone.utc)

    execute_transaction([
        ("""
        UPDATE consent_records
        SET status = 'WITHDRAWN',
            withdrawn_at = %s,
            withdrawn_by = %s
        WHERE org_id = %s
          AND subject_id = %s
          AND purpose = %s
          AND status = 'ACTIVE'
        """, (now, actor_id, org_id, subject_id, purpose)),
    ])

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id=actor_id,
        actor_role=actor_role,
        entity_type="consent_record",
        entity_id=subject_id,
        tenant_id=org_id,
        metadata={"purpose": purpose, "action": "withdrawn", "withdrawn_at": now.isoformat()},
    )

    # If biometric consent withdrawn — immediately archive biometric data
    if purpose == "biometric_attendance":
        execute_transaction([
            ("""
            UPDATE biometric_logs
            SET status = 'ARCHIVED'
            WHERE org_id = %s AND student_id = %s AND status = 'ACTIVE'
            """, (org_id, subject_id)),
        ])
```

## Data Subject Rights Implementation

### Right to Access (SAR — Subject Access Request)

```python
# Collect all data for a subject across all modules
def generate_data_export(org_id: str, subject_id: str, requestor_id: str) -> dict:
    # Gather from each module table
    # Mask credentials and secrets before export
    # Return structured JSON — never binary blobs
    # Log the access event
    AuditLedger.log(
        action=AuditAction.SENSITIVE_ACCESS,
        actor_id=requestor_id,
        entity_type="data_subject_export",
        entity_id=subject_id,
        tenant_id=org_id,
        metadata={"purpose": "subject_access_request"},
    )
```

### Right to Erasure (GDPR Article 17)

```python
from server.core.retention_policy import RetentionService

# Withdraw all consents first
for purpose in ["biometric_attendance", "alumni_tracking", "marketing_communications"]:
    withdraw_consent(org_id, subject_id, purpose, actor_id, "super_admin")

# Then request hard delete for consent-based REGULATED data
# (Contract/legal_obligation data cannot be erased before retention period)
RetentionService.request_hard_delete(
    entity_type="biometric_log",
    entity_id=log_id,
    tenant_id=org_id,
    actor_id=actor_id,
    actor_role="super_admin",
    justification="GDPR Article 17 erasure request — consent withdrawn",
    entity_snapshot={"subject_id": subject_id},
)
```

## Consent Audit Trail

All consent events are audited using `AuditAction`:
- Grant → `AuditAction.CREATE` on `consent_record`
- Withdrawal → `AuditAction.UPDATE` on `consent_record`
- Expiry → `AuditAction.ARCHIVE` on `consent_record` (via Celery job)
- SAR → `AuditAction.SENSITIVE_ACCESS`

The `AuditLedger` is hash-chained and append-only — consent history is tamper-evident.

## Consent Expiry (Celery Job)

```python
# In server/tasks/retention.py
@celery_app.task
def expire_old_consents():
    """Mark consents past their expiry date as EXPIRED."""
    from server.db_service import execute_transaction
    execute_transaction([
        ("""
        UPDATE consent_records
        SET status = 'EXPIRED'
        WHERE status = 'ACTIVE'
          AND expires_at IS NOT NULL
          AND expires_at < NOW()
        """, ()),
    ])
```

## Consent Checklist — New Feature

- [ ] Identify what data is collected and its sensitivity level
- [ ] Determine lawful basis (contract / consent / legal_obligation)
- [ ] If basis is `consent`: implement consent capture UI + `record_consent()`
- [ ] Add `has_active_consent()` check before storing optional data
- [ ] Implement withdrawal endpoint + `withdraw_consent()`
- [ ] Implement cascade: withdrawal triggers archival of related data
- [ ] Register `consent_record` entity type in `EntityClassificationRegistry`
- [ ] Add consent expiry to Celery Beat schedule
- [ ] Test: data cannot be collected after withdrawal
- [ ] Audit trail present for grant, withdrawal, and expiry events
