---
name: alis-audit-certifications
description: |
  ALIS regular audit and certification procedures. Use when implementing audit chain verification,
  generating compliance reports, enforcing model change governance, implementing appeal replay guarantee,
  running retention audit reports, or preparing for regulatory certification. Covers AuditLedger chain
  verification, Legal Addendum clauses (§18–§27), model version governance, prompt version tracking,
  policy version tracking, appeal replay, AI governance certification, human override logging.
  Trigger keywords: audit, certification, compliance, audit chain, chain verification, integrity check,
  audit report, model governance, model version, appeal replay, human override log, AI governance,
  legal addendum, policy version, prompt version, regulatory, SOC, ISO, NAAC, accreditation, audit log.
---

# ALIS Audit & Certifications

You are the ALIS Compliance & Certification Expert. ALIS must be continuously auditable and
certifiable under institutional and regulatory standards.

## Audit Chain Integrity Verification

The audit ledger is SHA-256 hash-chained per tenant. Verify it regularly:

```python
from server.core.audit import AuditLedger

# Verify the full hash chain for a tenant
result = AuditLedger.verify_chain_integrity(tenant_id=org_id)
# {
#   "valid": True,
#   "total_entries": 12450,
#   "first_invalid_id": None,
#   "message": "All 12450 entries verified successfully."
# }

if not result["valid"]:
    # Alert security team — chain tampered with
    # result["first_invalid_id"] — first broken link
    raise SecurityIncidentError(f"Audit chain breach at entry {result['first_invalid_id']}")
```

Run this check:
- At application startup (lightweight — first 100 entries only for speed)
- Daily via Celery Beat (full chain)
- Before any regulatory audit or export

## Audit Log Export for Regulators

```python
# JSON export (full chain for a tenant)
json_export = AuditLedger.export_ledger(
    tenant_id=org_id,
    fmt="json",
    start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    end_time=datetime(2026, 3, 31, tzinfo=timezone.utc),
)

# CSV export (for spreadsheet review)
csv_export = AuditLedger.export_ledger(
    tenant_id=org_id,
    fmt="csv",
)
```

Exported fields: `id, tenant_id, actor_id, actor_role, action, entity_type, entity_id, metadata, timestamp, previous_hash, hash`.
Chain hash is included — regulator can independently verify integrity.

## Retention Audit Report

```python
from server.core.retention_policy import RetentionAuditReport

report = RetentionAuditReport.generate(tenant_id=org_id)
# Includes: retention_matrix, archival_summary, deletion_summary
# Use for: NAAC data governance review, GDPR compliance, internal audit
```

## Legal Addendum Compliance (§18–§27)

### §18 — Non-Delegation Clause

AI outputs are advisory only. Verify in code:
- No AI response has `state_impact != "DRAFT"` in production
- All final decisions (grade publish, fee waiver approval, admissions offer) have human actor in audit trail
- AI Gateway rejects `state_impact` values of `FINAL`, `COMMIT`, `OVERRIDE`

Audit query to confirm:
```python
rows = AuditLedger.query(
    tenant_id=org_id,
    action=AuditAction.AGENT_DECISION,
    limit=500,
)
# Verify: all AGENT_DECISION entries have corresponding STATE_TRANSITION by a human actor
```

### §19 — Human Override Logging

Every human accept/reject/modify of an AI recommendation MUST log:

```python
AuditLedger.log(
    action=AuditAction.OVERRIDE_EXECUTED,
    actor_id=staff_actor_id,
    actor_role=actor_role,
    entity_type="ApplicationDecision",
    entity_id=application_id,
    tenant_id=org_id,
    metadata={
        "ai_recommendation": ai_response.recommendation,
        "ai_confidence": ai_response.confidence,
        "ai_confidence_tier": ai_response.confidence_tier,
        "human_decision": "APPROVED",   # Accept / Reject / Modify
        "reason_code": "MERIT_OVERRIDE",
        "ai_output_snapshot": ai_response.dict(),
    },
)
```

### §20 — Appeal Replay Guarantee

For academic, financial, or disciplinary disputes, the system must replay the AI evaluation
using the exact historical versions:

```python
from server.core.prompt_registry import PromptRegistry
from server.core.model_registry import ModelRegistry

# All AI invocations log model_version + prompt_version + policy_version in metadata
# On appeal, retrieve the historical invocation from audit_ledger
historical_entry = AuditLedger.query(
    tenant_id=org_id,
    entity_id=application_id,
    action=AuditAction.AGENT_DECISION,
    limit=1,
)[0]

# Replay uses historical versions — NOT current versions
historical_prompt = PromptRegistry.get_by_version(
    historical_entry.metadata["prompt_id"],
    historical_entry.metadata["prompt_version"],
)
# Never re-run with current model — historical determinism is mandatory
```

Implement an `AppealReplayService` that:
1. Retrieves historical `model_version`, `prompt_version`, `policy_version` from audit
2. Fetches the historical prompt text
3. Re-runs inference with locked model version
4. Returns historical AI output + confidence for display — never overwrites stored decision

### §21 — Model Change Governance

Model upgrades affect all three LLM tiers independently. Each tier has a `LLMTaskClass` and maps to
a different default model (`EXTRACTION` 1.5b / `GENERATION` 7b / `REASONING` 14b). A governance
event is required per tier upgrade — a single approval cannot cover multiple tiers.

Model upgrades require:

```python
from server.core.model_registry import ModelRegistry
from server.core.llm_router import LLMTaskClass

# Register new model version — specify which task class tier this applies to
ModelRegistry.register_version(
    model_name="qwen2.5:1.5b-instruct-q8_0",
    version="v2",
    task_class=LLMTaskClass.EXTRACTION,   # EXTRACTION | GENERATION | REASONING
    effective_from=datetime(2026, 4, 1, tzinfo=timezone.utc),
    approved_by=super_admin_id,
    validation_report_url="...",
)

AuditLedger.log(
    action=AuditAction.CONFIG_CHANGE,
    actor_id=super_admin_id,
    actor_role="super_admin",
    entity_type="ModelVersion",
    entity_id="qwen2.5:1.5b-v2",
    tenant_id=org_id,
    metadata={
        "change_type": "model_upgrade",
        "old_version": "v1",
        "new_version": "v2",
        "effective_from": "2026-04-01T00:00:00Z",
    },
)
```

Model changes CANNOT:
- Retroactively affect historical decisions
- Modify archived outputs
- Recompute past grades automatically
- Take effect mid-academic-cycle without explicit approval + notification

### §22 — Academic Integrity Protection

For grading agents, every invocation logs:

```python
metadata={
    "grading_rubric_id": rubric_id,
    "rubric_version": rubric_version,
    "policy_thresholds": {"pass_mark": 40, "distinction": 75},
    "input_scoring_matrix": {course: marks},
    "model_version": model_version,
    "prompt_version": prompt_version,
}
```

Mid-semester grading model updates are prohibited unless:
- Explicitly approved by DEAN or SUPER_ADMIN
- Logged to audit ledger with justification
- Effective from next cycle only (never retroactive)

## Audit Action Coverage Matrix

| Critical Operation | Required Audit Action |
|---|---|
| User login | `LOGIN` |
| Any state mutation | `UPDATE` or `STATE_TRANSITION` |
| AI agent run | `AGENT_EXECUTION` + `AGENT_DECISION` |
| Domain event dispatched | `UPDATE` on `domain_events` (PENDING→PROCESSING→PROCESSED) |
| Stuck domain event reset | `UPDATE` on `domain_events` (PROCESSING→PENDING, via Beat task) |
| Human override | `OVERRIDE_EXECUTED` |
| Key generation/rotation | `CREATE`/`UPDATE` on `tenant_key` |
| Hard delete | `HARD_DELETE` |
| Lockdown activate/deactivate | `LOCKDOWN_ACTIVATED`/`LOCKDOWN_DEACTIVATED` |
| Config change | `CONFIG_CHANGE` |
| Model upgrade | `CONFIG_CHANGE` (subtype: model_upgrade) |
| Consent grant/withdrawal | `CREATE`/`UPDATE` on `consent_record` |
| Policy governance | `POLICY_DRAFTED`/`APPROVED`/`ACTIVATED` |

## Certification Readiness Checklist

### NAAC / UGC (Indian Higher Education)
- [ ] Audit ledger exportable in CSV/JSON for academic year
- [ ] Student data with PERMANENT retention (transcripts, financial)
- [ ] All grade modifications have human actor + reason in audit
- [ ] AI used only advisory — final grades require human sign-off

### GDPR / PDPB (Data Protection)
- [ ] Consent records with purpose + lawful basis
- [ ] Subject access request export capability
- [ ] Right to erasure workflow (withdrawal → archive → hard delete)
- [ ] Retention matrix documented and enforced
- [ ] Biometric data: explicit consent + 2-year max retention

### ISO 27001 (Information Security)
- [ ] Encryption at rest for CONFIDENTIAL/REGULATED fields
- [ ] Key rotation procedure documented and audited
- [ ] Incident response plan tested (LockdownManager)
- [ ] Access control: RBAC + ABAC + tenant isolation verified
- [ ] No cloud data egress (all local: Ollama, PostgreSQL, MinIO)

### SOC 2 Type II (Service Organizations)
- [ ] Audit chain integrity verifiable independently
- [ ] All access to REGULATED data is logged
- [ ] Session management with token expiry
- [ ] Lockdown mode with documented RTO

## Daily/Weekly Automated Audit Tasks (Celery Beat)

```python
beat_schedule = {
    "daily-audit-chain-verify": {
        "task": "server.tasks.audit.verify_chain_integrity",
        "schedule": crontab(hour=1, minute=0),  # 1 AM daily
    },
    "weekly-retention-audit-report": {
        "task": "server.tasks.retention.generate_audit_report",
        "schedule": crontab(day_of_week=0, hour=3),  # Sunday 3 AM
    },
    "daily-consent-expiry": {
        "task": "server.tasks.retention.expire_old_consents",
        "schedule": crontab(hour=2, minute=30),
    },
}
```
