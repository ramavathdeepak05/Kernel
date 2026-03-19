---
name: alis-data-governance
description: |
  ALIS data governance and classification framework. Use when classifying data fields, registering new
  entity types, tagging sensitivity levels, applying masking rules, or reviewing data handling for
  compliance. Covers SensitivityLevel (PUBLIC/INTERNAL/CONFIDENTIAL/REGULATED), RegulatedDataType
  (PII/FINANCE/BIOMETRIC/TRANSCRIPT), RetentionClass, EntityClassificationRegistry, FieldClassification,
  DataMasker (mask_for_ai_context, mask_for_log, mask_dict). Trigger keywords: data classification,
  sensitivity, REGULATED, CONFIDENTIAL, PII, FINANCE, BIOMETRIC, TRANSCRIPT, mask, masking,
  EntityClassificationRegistry, FieldClassification, DataMasker, data governance, data sensitivity,
  field classification, entity classification, data tagging, retention class, privacy.
---

# ALIS Data Governance & Classification

You are the ALIS Data Governance Expert. Every data element in ALIS must carry a sensitivity tag
that governs encryption, masking, retention, and AI access.

## Sensitivity Levels (Ordered: Lowest → Highest)

```
PUBLIC < INTERNAL < CONFIDENTIAL < REGULATED
```

| Level | Meaning | Examples | Encryption |
|---|---|---|---|
| `PUBLIC` | Freely shareable | Course catalog, public notices | No |
| `INTERNAL` | Institutional use only | Task metadata, attendance counts | No |
| `CONFIDENTIAL` | Protected data | Names, emails, files | Yes (at-rest) |
| `REGULATED` | Legally protected | PII, financials, biometric, transcripts | Yes (at-rest + masked) |

```python
from server.core.data_classification import SensitivityLevel

SensitivityLevel.PUBLIC
SensitivityLevel.INTERNAL
SensitivityLevel.CONFIDENTIAL
SensitivityLevel.REGULATED
```

## Regulated Data Sub-Types

```python
from server.core.data_classification import RegulatedDataType

RegulatedDataType.NONE        # Non-regulated
RegulatedDataType.PII         # Name, email, phone, address
RegulatedDataType.FINANCE     # Fees, payments, salary, ledger
RegulatedDataType.BIOMETRIC   # Facial, fingerprint, attendance scan
RegulatedDataType.TRANSCRIPT  # Academic grades, results, certificates
```

## Retention Classes

| Class | Default Period | Examples |
|---|---|---|
| `TEMPORARY` | 90 days | Session tokens, task metadata |
| `STANDARD` | 5 years (1825 days) | Attendance records, PII |
| `LONG_TERM` | 2 years (730 days) | Biometric logs |
| `PERMANENT` | Never deleted | Transcripts, financial records, audit ledger |

```python
from server.core.data_classification import RetentionClass
```

## Registering a New Entity Type

Every new entity/table added to ALIS MUST be registered in `EntityClassificationRegistry`.
Do this in `initialize_default_classifications()` in `data_classification.py`, or at module startup.

```python
from server.core.data_classification import (
    EntityClassificationRegistry,
    EntityClassification,
    FieldClassification,
    SensitivityLevel,
    RegulatedDataType,
    RetentionClass,
)

EntityClassificationRegistry.register(EntityClassification(
    entity_type="scholarship_award",
    default_sensitivity=SensitivityLevel.REGULATED,
    default_regulated_type=RegulatedDataType.FINANCE,
    description="Scholarship awards — financial records, permanent retention",
    retention_class=RetentionClass.PERMANENT,
    field_overrides={
        # Fields that differ from entity default
        "id": FieldClassification(
            field_name="id",
            sensitivity=SensitivityLevel.INTERNAL,
        ),
        "student_name": FieldClassification(
            field_name="student_name",
            sensitivity=SensitivityLevel.CONFIDENTIAL,
            regulated_type=RegulatedDataType.PII,
            mask_in_logs=True,
            mask_in_ai=True,
            mask_pattern="partial",
        ),
        "amount": FieldClassification(
            field_name="amount",
            sensitivity=SensitivityLevel.REGULATED,
            regulated_type=RegulatedDataType.FINANCE,
            mask_in_logs=False,   # Amount visible in logs (non-PII)
            mask_in_ai=True,      # But masked from AI context
        ),
        "status": FieldClassification(
            field_name="status",
            sensitivity=SensitivityLevel.INTERNAL,
        ),
    },
))
```

## Registered Entities (Default Classifications)

| Entity Type | Sensitivity | Regulated Type | Retention |
|---|---|---|---|
| `user` | CONFIDENTIAL | PII | STANDARD (5 yr) |
| `organization` | INTERNAL | NONE | STANDARD |
| `notification_log` | CONFIDENTIAL | PII | STANDARD (5 yr) |
| `task` | INTERNAL | NONE | TEMPORARY (90 d) |
| `file_metadata` | CONFIDENTIAL | NONE | STANDARD |
| `generated_document` | REGULATED | TRANSCRIPT | PERMANENT |
| `audit_entry` | INTERNAL | NONE | PERMANENT |
| `biometric_log` | REGULATED | BIOMETRIC | LONG_TERM (2 yr) |
| `attendance_record` | INTERNAL | NONE | STANDARD (5 yr) |
| `financial_record` | REGULATED | FINANCE | PERMANENT |
| `role_assignments` | INTERNAL | NONE | STANDARD (5 yr) |
| `domain_events` | INTERNAL | NONE | TEMPORARY (90 d after PROCESSED) |

## Data Masking

### Automatic Masking in AI Context (Before LLM Call)

```python
from server.core.data_classification import DataMasker

# Mask before sending to AI Gateway
safe_context = DataMasker.mask_for_ai_context(
    data=student_dict,
    entity_type="user",
)
# All CONFIDENTIAL+ string fields are masked
# mask_in_ai=True fields are fully redacted: "[REDACTED]"
# Safe fields preserved: id, status, org_id, entity_type
```

### Masking for Application/Audit Logs

```python
log_safe = DataMasker.mask_for_log(
    data=applicant_dict,
    entity_type="user",
)
# Fields with mask_in_logs=True are masked
# REGULATED fields are always masked in logs
```

### Masking API Responses

```python
response_safe = DataMasker.mask_dict(
    data=user_dict,
    entity_type="user",
)
# CONFIDENTIAL+ entity: all string values masked
# Field overrides applied
```

### Masking Strategies

| Pattern | Result | Use For |
|---|---|---|
| `email` field name | `j***n@***.com` | Email addresses |
| `phone/mobile` field name | `******7890` | Phone numbers |
| `name/full_name` field name | `J*** D***` | Person names |
| `password/secret/token/key` | `[REDACTED]` | Credentials |
| REGULATED sensitivity | First 2 chars + `***` | Generic regulated |
| CONFIDENTIAL sensitivity | First 3 chars + `***` | Generic confidential |
| INTERNAL sensitivity | First 4 chars + `***` | Generic internal |

## Checking Sensitivity Level Ordering

```python
from server.core.data_classification import sensitivity_gte

# Is REGULATED >= CONFIDENTIAL? → True
sensitivity_gte(SensitivityLevel.REGULATED, SensitivityLevel.CONFIDENTIAL)

# Check if encryption is required
from server.core.data_classification import encryption_required
encryption_required(SensitivityLevel.REGULATED)   # True
encryption_required(SensitivityLevel.INTERNAL)    # False
```

## Querying Classifications

```python
# Get entity classification
ec = EntityClassificationRegistry.get("user")
ec = EntityClassificationRegistry.get_or_default("unknown_type")  # Fails safe to INTERNAL

# Get field-level classification
fc = EntityClassificationRegistry.get_field_classification("user", "email")
# fc.sensitivity → REGULATED
# fc.mask_in_ai → True

# List all registered entity types
types = EntityClassificationRegistry.list_registered()
```

## Layer 4 Invariant: Sensitive Data Never Exposed Raw

- CONFIDENTIAL and REGULATED fields are NEVER logged without masking
- REGULATED fields are NEVER passed to AI context without masking
- API responses for REGULATED entities must mask fields per `FieldClassification`
- Unregistered entity types default to INTERNAL (fail-safe, not PUBLIC)

## Governance Checklist — New Entity/Table

- [ ] `EntityClassification` registered in `initialize_default_classifications()`
- [ ] `default_sensitivity` set correctly (default to INTERNAL or higher)
- [ ] `default_regulated_type` set if any field is legally protected
- [ ] `retention_class` assigned (TEMPORARY/STANDARD/LONG_TERM/PERMANENT)
- [ ] PII fields (name, email, phone) have `mask_in_logs=True, mask_in_ai=True`
- [ ] Financial fields have `mask_in_ai=True`
- [ ] Credential fields have `mask_pattern="full"` → `[REDACTED]`
- [ ] `id`, `status`, `org_id` overridden to INTERNAL (they are safe)
