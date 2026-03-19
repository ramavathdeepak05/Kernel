---
name: alis-data-management
description: |
  ALIS comprehensive data management processes — retention, archival, legal deletion, and data lifecycle.
  Use when implementing or reviewing data lifecycle processes, retention schedules, archival jobs,
  hard-delete workflows, or retention audit reports. Covers RetentionPolicy, ArchivalService,
  RetentionService, DeletionRequest, RetentionMatrix, RetentionAuditReport, and data minimization.
  Trigger keywords: data retention, retention policy, archival, archive, hard delete, legal deletion,
  data lifecycle, retention period, DeletionRequest, ArchivalService, RetentionService, retention matrix,
  retention audit, data minimization, expiry, purge, PERMANENT, TEMPORARY, STANDARD, LONG_TERM.
---

# ALIS Comprehensive Data Management

You are the ALIS Data Lifecycle Expert. Every entity in ALIS has a retention class that determines
how long it lives before archival or legal deletion.

## Data Lifecycle States

```
ACTIVE → (retention period elapsed) → ARCHIVED → (legal workflow) → HARD_DELETED
                                                                   (PERMANENT entities never deleted)
```

- `ACTIVE`: Normal operational state
- `ARCHIVED`: Soft-archived — read-only, not surfaced in normal queries (status = 'ARCHIVED')
- `HARD_DELETED`: Physical DB row removed — only for non-permanent, REGULATED data, SUPER_ADMIN only

## Retention Matrix (Source of Truth)

Retention periods are defined by `EntityClassification.retention_class` in `data_classification.py`:

| Retention Class | Default Days | Auto-Archival | Hard-Delete Eligible |
|---|---|---|---|
| `TEMPORARY` | 90 days | Yes | Yes (after archival) |
| `STANDARD` | 1825 days (5 yr) | Yes | Yes (after archival) |
| `LONG_TERM` | 730 days (2 yr) | Yes | Yes (after archival) |
| `PERMANENT` | Never | No | No (prohibited) |

```python
from server.core.retention_policy import RetentionMatrix

# Get retention info for an entity type
info = RetentionMatrix.get_retention_info("user")
# {
#   "entity_type": "user",
#   "retention_class": "STANDARD",
#   "retention_days": 1825,
#   "is_permanent": False,
#   "regulated_type": "PII",
#   "sensitivity": "CONFIDENTIAL"
# }

# Get full matrix for compliance reporting
matrix = RetentionMatrix.get_full_matrix()
```

## Scheduled Archival Job

Run periodically (daily via Celery Beat or cron) to archive records past their retention period.

```python
from server.core.retention_policy import ArchivalService, ArchivalStatus
from server.db_service import execute_query

# 1. Fetch active records for a module
records = execute_query(
    """
    SELECT id AS entity_id, 'user' AS entity_type, created_at, status
    FROM users
    WHERE org_id = %s AND status = 'ACTIVE'
    """,
    (org_id,)
)

# 2. Run archival evaluation
results = ArchivalService.run_archival_job(
    tenant_id=org_id,
    records=records,
    dry_run=False,  # Set True to preview without committing
)

# 3. Process results
for record in results:
    if record.status == ArchivalStatus.ARCHIVED:
        # Physically update the DB row
        execute_transaction([
            ("UPDATE users SET status = 'ARCHIVED' WHERE id = %s AND org_id = %s",
             (record.entity_id, org_id)),
        ])
    elif record.status == ArchivalStatus.FAILED:
        logger.error("Archival failed: %s/%s — %s",
                     record.entity_type, record.entity_id, record.reason)
    elif record.status == ArchivalStatus.SKIPPED_PERMANENT:
        pass  # Expected for PERMANENT entities — no action needed
```

## Legal Hard-Delete Workflow

Hard deletion is only permitted for:
1. Non-PERMANENT entities
2. By `SUPER_ADMIN` role
3. With a written justification
4. After a pre-deletion audit snapshot is logged

```python
from server.core.retention_policy import RetentionService, DeletionStatus

deletion_req = RetentionService.request_hard_delete(
    entity_type="biometric_log",
    entity_id=log_id,
    tenant_id=org_id,
    actor_id=actor_id,
    actor_role="super_admin",         # Must be SUPER_ADMIN — raises PermissionError otherwise
    justification="GDPR erasure request from student ID 12345, received 2026-03-06",
    entity_snapshot={"id": log_id, "student_id": student_id, "created_at": "..."},
)

if deletion_req.status == DeletionStatus.EXECUTED:
    # Now physically delete the DB row
    execute_transaction([
        ("DELETE FROM biometric_logs WHERE id = %s AND org_id = %s",
         (log_id, org_id)),
    ])
elif deletion_req.status == DeletionStatus.REJECTED:
    # Permanent entity or insufficient role — do not delete
    logger.warning("Hard delete rejected: %s", deletion_req.rejection_reason)
```

`RetentionService.request_hard_delete` automatically:
- Verifies `SUPER_ADMIN` role (rejects and audit-logs otherwise)
- Checks entity is not PERMANENT (rejects and audit-logs if so)
- Logs a `HARD_DELETE` entry to the immutable audit ledger with the pre-deletion snapshot
- Raises `RuntimeError` if audit logging fails (deletion cannot proceed without audit trail)

## Hard-Delete Gatekeeping Rules

| Check | Effect |
|---|---|
| Actor role ≠ SUPER_ADMIN | Rejected + audit-logged |
| No justification provided | `ValueError` raised |
| Entity has PERMANENT retention | Rejected + audit-logged |
| Audit log write fails | `RuntimeError` — deletion blocked |

## Entities That Can NEVER Be Deleted

- `audit_entry` (audit_ledger) — PERMANENT, append-only
- `generated_document` (transcripts, certificates) — PERMANENT
- `financial_record` (fees, payments, ledger) — PERMANENT
- Any custom entity registered as `RetentionClass.PERMANENT`

## Retention Audit Report

```python
from server.core.retention_policy import RetentionAuditReport

# Generate for a specific tenant
report = RetentionAuditReport.generate(tenant_id=org_id)
# {
#   "report_generated_at": "2026-03-06T...",
#   "tenant_id": "<org_id>",
#   "retention_matrix": [...],        # Full matrix
#   "archival_summary": {
#     "total_evaluated": 1500,
#     "archived": 120,
#     "skipped_permanent": 450,
#     "failed": 0,
#   },
#   "deletion_summary": {
#     "total_requests": 3,
#     "executed": 2,
#     "rejected": 1,
#   }
# }

# Generate for all tenants
report = RetentionAuditReport.generate()  # tenant_id=None → ALL
```

## Data Minimization Rules

- Collect only what is operationally necessary — no speculative data fields
- TEMPORARY data (session tokens, task metadata): auto-expired after 90 days, never used for analytics
- REGULATED data: never used to train or fine-tune AI models
- AI context: always passed through `DataMasker.mask_for_ai_context()` before LLM call
- Logs: always passed through `DataMasker.mask_for_log()` — no raw PII in application logs
- Reporting module (E11): only aggregates — never exports individual REGULATED records without SUPER_ADMIN

## Celery Beat Schedule for Archival

```python
# In server/worker.py — Beat schedule
beat_schedule = {
    "daily-archival-job": {
        "task": "server.tasks.retention.run_daily_archival",
        "schedule": crontab(hour=2, minute=0),  # 2 AM daily
    },
}
```

## Cross-Module Retention Responsibilities

| Module | Entity Types | Class | Notes |
|---|---|---|---|
| E01 Auth | `user` | STANDARD | PII — 5 yr |
| E03 AI | AI invocation logs | STANDARD | 5 yr |
| E04 Admissions | Applicant records | STANDARD | 5 yr post-decision |
| E06 Examinations | `generated_document` | PERMANENT | Transcripts forever |
| E07 Finance | `financial_record` | PERMANENT | Legal requirement |
| E08 HR | Biometric logs | LONG_TERM | 2 yr only |
| Platform Core | `audit_entry` | PERMANENT | Hash-chained ledger |

## Data Management Checklist

- [ ] New entity type has `EntityClassification` with correct `retention_class`
- [ ] PERMANENT entities have no delete endpoint
- [ ] Hard-delete endpoints require `Permission.HARD_DELETE` + `SUPER_ADMIN` role check
- [ ] Archival job covers all new tables in Celery Beat schedule
- [ ] `RetentionAuditReport` accessible via admin-only API endpoint
- [ ] AI context for retention queries uses `DataMasker.mask_for_ai_context`
- [ ] Deletion request justification validated (non-empty string required)
