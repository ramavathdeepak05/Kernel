---
name: monitoring-observability
description: "Monitoring and observability strategy, implementation, and troubleshooting. Use this skill whenever the user mentions monitoring, observability, metrics, logs, traces, alerting, SLOs, Prometheus, Grafana, Datadog, Loki, or OpenTelemetry. Triggers include designing metrics strategy (Four Golden Signals, RED/USE), setting up Prometheus/Grafana/Loki, creating alerts or dashboards, calculating SLOs and error budgets, instrumenting with OpenTelemetry, analyzing performance issues, choosing between monitoring tools, optimizing Datadog costs, migrating to open-source stack, and setting up distributed tracing. QUAICU kernel — OpenTelemetry with the exact span names and attributes from core/telemetry.py (quaicu.lifecycle.*, quaicu.ledger.seal), tenant_id on every signal, no PII or prompt content in telemetry, critical alerts for ledger tamper and fail-open. Triggers — QUAICU, lifecycle span, ledger tamper alert, fail-open, OTel attributes, quaicu.telemetry."
---

# Monitoring & Observability

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific observability choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.**

### Invariants — never violated
- Use OpenTelemetry with the EXACT span names and attributes from `core/telemetry.py` (e.g. `quaicu.lifecycle.evaluate`, `quaicu.ledger.seal`). Do not invent ad-hoc names.
- Every span/metric/log carries `quaicu.tenant_id` and (where applicable) `quaicu.action_id`. NEVER emit PII or raw prompt content into telemetry.
- Telemetry is best-effort and NEVER changes a governance decision. But a missing prompt LOG is fail-closed — that is the gateway's responsibility, not telemetry's. Do not conflate the two.
- Stack is Prometheus + Grafana + Loki + OTel collector (open-source) so sovereign deploys have no proprietary-only dependency.

### Must-have signals
| Signal | Example |
|---|---|
| Counter | `quaicu.actions.proposed/denied/completed` |
| Histogram | `quaicu.lifecycle.step.duration_ms`, `quaicu.ledger.seal.duration_ms` |
| Gauge | `quaicu.actions.pending_approval` |
| Critical alert | ledger tamper / consistency-proof failure; fail-open detected; seal-failure rate |

### Tie-break rules
- Log prompt text to Loki for debugging? → never; PII/prompt content stays out of telemetry.
- Block an action because a span failed to export? → no; telemetry is best-effort (prompt logging ≠ telemetry).

### Self-check
- [ ] Span names/attributes match core/telemetry.py exactly.
- [ ] tenant_id on every signal; no PII/prompt content emitted.
- [ ] Critical alerts cover ledger tamper + fail-open + seal failures.
- [ ] Open-source stack (Prometheus/Grafana/Loki/OTel).

---

## Core Workflow: Observability Implementation

Use this decision tree to determine your starting point:

```
Are you setting up monitoring from scratch?
├─ YES → Start with "1. Design Metrics Strategy"
└─ NO → Do you have an existing issue?
    ├─ YES → Go to "9. Troubleshooting & Analysis"
    └─ NO → Are you improving existing monitoring?
        ├─ Alerts → Go to "3. Alert Design"
        ├─ Dashboards → Go to "4. Dashboard & Visualization"
        ├─ SLOs → Go to "5. SLO & Error Budgets"
        ├─ Tool selection → Read references/tool_comparison.md
        └─ Using Datadog? High costs? → Go to "7. Datadog Cost Optimization & Migration"
```

---

## 1. Design Metrics Strategy

### Start with The Four Golden Signals

Every service should monitor: **Latency** (p50/p95/p99), **Traffic** (req/s), **Errors** (failure rate), **Saturation** (resource utilization).

**RED Method** (request-driven): Rate, Errors, Duration | **USE Method** (infrastructure): Utilization, Saturation, Errors

**Quick Start - Web Application Example**:
```promql
# Rate (requests/sec)
sum(rate(http_requests_total[5m]))

# Errors (error rate %)
sum(rate(http_requests_total{status=~"5.."}[5m]))
  /
sum(rate(http_requests_total[5m])) * 100

# Duration (p95 latency)
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)
```

**Deep dive**: `references/metrics_design.md` — metric types, cardinality, naming conventions, dashboard design

### Querying Metrics Directly

Query Prometheus and CloudWatch metrics using CLI/curl:

```bash
# Query Prometheus instant value
curl -s 'http://localhost:9090/api/v1/query?query=rate(http_requests_total[5m])' | jq .

# Query Prometheus over a time range (last 1h, 15s step)
curl -s 'http://localhost:9090/api/v1/query_range?query=rate(http_requests_total[5m])&start='$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ)'&end='$(date -u +%Y-%m-%dT%H:%M:%SZ)'&step=15s' | jq .

# Query CloudWatch metrics (e.g., EC2 CPU over last 1 hour)
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=i-1234567890abcdef0 \
  --start-time $(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 300 \
  --statistics Average Maximum
```

---

## 2. Log Aggregation & Analysis

### Structured Logging Checklist

Every log entry should include: timestamp (ISO 8601), log level, message, service name, request ID (for tracing).

**Example structured log (JSON)**:
```json
{
  "timestamp": "2024-10-28T14:32:15Z",
  "level": "error",
  "message": "Payment processing failed",
  "service": "payment-service",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_id": "user123",
  "order_id": "ORD-456",
  "error_type": "GatewayTimeout",
  "duration_ms": 5000
}
```

### Log Analysis

Analyze logs for errors, patterns, and anomalies:

```bash
# Analyze log file for patterns
python3 scripts/log_analyzer.py application.log

# Show error lines with context
python3 scripts/log_analyzer.py application.log --show-errors

# Extract stack traces
python3 scripts/log_analyzer.py application.log --show-traces
```

**→ Script**: [scripts/log_analyzer.py](scripts/log_analyzer.py)

**Deep dive**: `references/logging_guide.md` — structured logging, aggregation patterns (ELK, Loki, CloudWatch), PII redaction, sampling

---

## 3. Alert Design

### Alert Design Principles

1. **Actionable** - If you can't act on it, don't alert
2. **Symptom-based** - Alert on user experience, not components
3. **SLO-tied** - Connect to business impact
4. **Low noise** - Only page for critical issues

### Alert Severity Levels

| Severity | Response Time | Example |
|----------|--------------|---------|
| **Critical** | Page immediately | Service down, SLO violation |
| **Warning** | Ticket, review in hours | Elevated error rate, resource warning |
| **Info** | Log for awareness | Deployment completed, scaling event |

### Multi-Window Burn Rate Alerting

Alert when error budget is consumed too quickly:

```yaml
# Fast burn (1h window) - Critical
- alert: ErrorBudgetFastBurn
  expr: |
    (error_rate / 0.001) > 14.4  # 99.9% SLO
  for: 2m
  labels:
    severity: critical

# Slow burn (6h window) - Warning
- alert: ErrorBudgetSlowBurn
  expr: |
    (error_rate / 0.001) > 6  # 99.9% SLO
  for: 30m
  labels:
    severity: warning
```

### Alert Quality Checker

Audit your alert rules against best practices:

```bash
# Check single file
python3 scripts/alert_quality_checker.py alerts.yml

# Check all rules in directory
python3 scripts/alert_quality_checker.py /path/to/prometheus/rules/
```

**Checks**: naming conventions, required labels/annotations, PromQL quality, 'for' clause to prevent flapping.

**→ Script**: [scripts/alert_quality_checker.py](scripts/alert_quality_checker.py)

### Alert Templates

Production-ready alert rule templates:

**→ Templates**:
- [assets/templates/prometheus-alerts/webapp-alerts.yml](assets/templates/prometheus-alerts/webapp-alerts.yml) - Web application alerts
- [assets/templates/prometheus-alerts/kubernetes-alerts.yml](assets/templates/prometheus-alerts/kubernetes-alerts.yml) - Kubernetes alerts

**Deep dive**: `references/alerting_best_practices.md` — alert design patterns, routing, inhibition rules, runbook structure, on-call practices

### Runbook Template

Create comprehensive runbooks for your alerts:

**→ Template**: [assets/templates/runbooks/incident-runbook-template.md](assets/templates/runbooks/incident-runbook-template.md)

---

## 4. Dashboard & Visualization

### Dashboard Design Principles

1. **Top-down layout**: Most important metrics first
2. **Color coding**: Red (critical), yellow (warning), green (healthy)
3. **Consistent time windows**: All panels use same time range
4. **Limit panels**: 8-12 panels per dashboard maximum
5. **Include context**: Show related metrics together

**Recommended layout**: Overall Health (single stats) -> Request Rate & Errors -> Latency Distribution -> Resource Usage

### Generate Grafana Dashboards

Automatically generate dashboards from templates:

```bash
# Web application dashboard
python3 scripts/dashboard_generator.py webapp \
  --title "My API Dashboard" \
  --service my_api \
  --output dashboard.json

# Kubernetes dashboard
python3 scripts/dashboard_generator.py kubernetes \
  --title "K8s Production" \
  --namespace production \
  --output k8s-dashboard.json

# Database dashboard
python3 scripts/dashboard_generator.py database \
  --title "PostgreSQL" \
  --db-type postgres \
  --instance db.example.com:5432 \
  --output db-dashboard.json
```

**Supports**: Web applications, Kubernetes, Databases (PostgreSQL, MySQL).

**→ Script**: [scripts/dashboard_generator.py](scripts/dashboard_generator.py)

---

## 5. SLO & Error Budgets

### SLO Fundamentals

SLI (measurement), SLO (target), Error Budget (allowed failure = 100% - SLO). See `references/slo_sla_guide.md` for full definitions.

### Common SLO Targets

| Availability | Downtime/Month | Use Case |
|--------------|----------------|----------|
| **99%** | 7.2 hours | Internal tools |
| **99.9%** | 43.2 minutes | Standard production |
| **99.95%** | 21.6 minutes | Critical services |
| **99.99%** | 4.3 minutes | High availability |

### SLO Calculator

Calculate compliance, error budgets, and burn rates:

```bash
# Show SLO reference table
python3 scripts/slo_calculator.py --table

# Calculate availability SLO
python3 scripts/slo_calculator.py availability \
  --slo 99.9 \
  --total-requests 1000000 \
  --failed-requests 1500 \
  --period-days 30

# Calculate burn rate
python3 scripts/slo_calculator.py burn-rate \
  --slo 99.9 \
  --errors 50 \
  --requests 10000 \
  --window-hours 1
```

**→ Script**: [scripts/slo_calculator.py](scripts/slo_calculator.py)

**Deep dive**: `references/slo_sla_guide.md` — choosing SLIs, setting targets, error budget policies, burn rate alerting, SLA contracts

---

## 6. Distributed Tracing

### When to Use Tracing

Use distributed tracing when you need to:
- Debug performance issues across services
- Understand request flow through microservices
- Identify bottlenecks in distributed systems
- Find N+1 query problems

### OpenTelemetry Implementation

**Python example**:
```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("process_order")
def process_order(order_id):
    span = trace.get_current_span()
    span.set_attribute("order.id", order_id)

    try:
        result = payment_service.charge(order_id)
        span.set_attribute("payment.status", "success")
        return result
    except Exception as e:
        span.set_status(trace.Status(trace.StatusCode.ERROR))
        span.record_exception(e)
        raise
```

### Sampling Strategies

- **Development**: 100% (ALWAYS_ON)
- **Staging**: 50-100%
- **Production**: 1-10% (or error-based sampling)

**Error-based sampling** (always sample errors, 1% of successes):
```python
class ErrorSampler(Sampler):
    def should_sample(self, parent_context, trace_id, name, **kwargs):
        attributes = kwargs.get('attributes', {})

        if attributes.get('error', False):
            return Decision.RECORD_AND_SAMPLE

        if trace_id & 0xFF < 3:  # ~1%
            return Decision.RECORD_AND_SAMPLE

        return Decision.DROP
```

### OTel Collector Configuration

**→ Template**: [assets/templates/otel-config/collector-config.yaml](assets/templates/otel-config/collector-config.yaml) — OTLP/Prometheus/host metrics receivers, batching, tail sampling, multiple exporters (Tempo, Jaeger, Loki, Prometheus, CloudWatch, Datadog)

**Deep dive**: `references/tracing_guide.md` — OTel instrumentation (Python, Node.js, Go, Java), context propagation, backend comparison, analysis patterns

---

## 7. Datadog Cost Optimization & Migration

### Scenario 1: I'm Using Datadog and Costs Are Too High

Check usage directly in the Datadog UI at **Plan & Usage > Usage Summary**, or query the API:

```bash
# Get Datadog usage summary for the current month (requires DD_API_KEY and DD_APP_KEY)
curl -s -X GET "https://api.datadoghq.com/api/v1/usage/summary?start_month=$(date -u +%Y-%m)" \
  -H "DD-API-KEY: ${DD_API_KEY}" \
  -H "DD-APPLICATION-KEY: ${DD_APP_KEY}" | jq .

# Get hourly usage for hosts (identify peak usage)
curl -s -X GET "https://api.datadoghq.com/api/v1/usage/hosts?start_hr=$(date -u -v-24H +%Y-%m-%dT%H)" \
  -H "DD-API-KEY: ${DD_API_KEY}" \
  -H "DD-APPLICATION-KEY: ${DD_APP_KEY}" | jq .
```

#### Common Cost Optimization Strategies

- **Custom Metrics** (20-40% savings): Remove high-cardinality tags, delete unused metrics, aggregate before sending
- **Log Management** (30-50% savings): Sample high-volume services, exclude debug logs in prod, archive to S3 after 7 days
- **APM** (15-25% savings): Reduce trace sampling (10% to 5%), remove APM from non-critical services
- **Infrastructure** (10-20% savings): Use container-based pricing, remove agents from ephemeral instances, consolidate staging

### Scenario 2: Migrating Away from Datadog

Migration to open-source stack (Prometheus + Grafana, Loki, Tempo/Jaeger, Alertmanager). Estimated savings: 60-77%.

#### Migration Strategy

- **Phase 1** (Month 1-2): Deploy open-source stack in parallel, migrate metrics first, validate accuracy
- **Phase 2** (Month 2-3): Convert dashboards to Grafana, translate alert rules (DQL to PromQL), train team
- **Phase 3** (Month 3-4): Set up Loki for logs, deploy Tempo/Jaeger for traces, update instrumentation
- **Phase 4** (Month 4-5): Confirm all functionality migrated, decommission Datadog

**Full migration guide**: `references/datadog_migration.md` | **Query translation**: `references/dql_promql_translation.md`

---

## 8. Tool Selection & Comparison

| Solution | Monthly Cost (100 hosts) | Best For |
|----------|-------------------------|----------|
| Prometheus + Loki + Tempo | $1,500 | Kubernetes, budget-conscious, ops-capable teams |
| Grafana Cloud | $3,000 | Open-source stack, low ops overhead |
| Datadog | $8,000 | Ease of use, full observability out of the box |
| ELK Stack | $4,000 | Heavy log analysis, powerful search |
| CloudWatch | $2,000 | Single AWS provider, simple needs |

**Deep dive**: `references/tool_comparison.md` — full comparison of metrics, logging, tracing, and full-stack platforms

---

## 9. Troubleshooting & Analysis

### Health Check Validation

Validate health check endpoints using `curl`:

```bash
# Check endpoint returns 200 and measure response time
curl -sf -o /dev/null -w "status:%{http_code} time:%{time_total}s\n" https://api.example.com/health

# Get full response body (check for JSON 'status' field, version info)
curl -sf https://api.example.com/health | jq .

# Check multiple endpoints in sequence
for ep in /health /readiness /liveness; do
  printf "%-20s " "$ep"
  curl -sf -o /dev/null -w "status:%{http_code} time:%{time_total}s\n" "https://api.example.com${ep}"
done
```

**What to verify**: 200 status, response time < 1s, JSON format with `status` field, version/build info, dependency checks, no caching headers (`Cache-Control: no-cache`).

### Common Troubleshooting Workflows

**High Latency**: Check dashboards for spike -> query traces for slow ops -> check DB slow queries -> check external APIs -> review deployments -> check resource utilization

**High Error Rate**: Check error logs -> identify affected endpoints -> check dependency health -> review deployments -> check resource limits -> verify configuration

**Service Down**: Check pods/instances running -> check health endpoint -> review deployments -> check resource availability -> check network -> review startup logs

---

## Quick Reference Commands

### Prometheus Queries

```promql
# Request rate
sum(rate(http_requests_total[5m]))

# Error rate
sum(rate(http_requests_total{status=~"5.."}[5m]))
  /
sum(rate(http_requests_total[5m])) * 100

# P95 latency
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
)

# CPU usage
100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Memory usage
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100
```

See `references/quick_commands.md` for Kubernetes, Elasticsearch, Loki, and CloudWatch query references.

---

## Resources Summary

**Scripts**: `alert_quality_checker.py` | `dashboard_generator.py` | `log_analyzer.py` | `slo_calculator.py`

**References**: `metrics_design.md` | `alerting_best_practices.md` | `logging_guide.md` | `tracing_guide.md` | `slo_sla_guide.md` | `tool_comparison.md` | `datadog_migration.md` | `dql_promql_translation.md`

**Templates**: `prometheus-alerts/webapp-alerts.yml` | `prometheus-alerts/kubernetes-alerts.yml` | `otel-config/collector-config.yaml` | `runbooks/incident-runbook-template.md`

---

## QUAICU-Specific Application

### OTel Instrumentation Map

Every step of the governed action lifecycle emits a span. The span name follows the convention `<subsystem>.<operation>`. All spans carry `tenant_id` and `action_id` as attributes — these are the join keys for correlating traces, metrics, and logs across a governed action.

```python
# core/observability.py
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from opentelemetry.semconv.trace import SpanAttributes

tracer = trace.get_tracer("quaicu.kernel", schema_url="https://opentelemetry.io/schemas/1.24.0")

# ── Lifecycle spans ───────────────────────────────────────────────────────────
# Each span name maps directly to the lifecycle step in the spec.

SPAN_LIFECYCLE_PROPOSE  = "lifecycle.propose"    # action enters the kernel
SPAN_LIFECYCLE_EVALUATE = "lifecycle.evaluate"   # K·01 policy eval + K·04/K·08-K·11 assurance
SPAN_LIFECYCLE_GATE     = "lifecycle.gate"       # K·03 HITL checkpoint
SPAN_LIFECYCLE_EXECUTE  = "lifecycle.execute"    # K·06 state transition
SPAN_LIFECYCLE_SEAL     = "lifecycle.seal"       # K·02 Merkle ledger append
SPAN_LIFECYCLE_EMIT     = "lifecycle.emit"       # K·07 event publication

# ── Layer spans ───────────────────────────────────────────────────────────────
SPAN_GATEWAY_GENERATE   = "gateway.generate"     # K·05 model call (child of lifecycle.execute)
SPAN_LEDGER_SEAL        = "ledger.seal"          # Merkle append + proof generation

# Required attributes on every kernel span
ATTR_TENANT_ID     = "quaicu.tenant_id"
ATTR_ACTION_ID     = "quaicu.action_id"
ATTR_ACTION_TYPE   = "quaicu.action_type"
ATTR_DECISION      = "quaicu.decision"           # ALLOWED | DENIED | PENDING | SEALED
ATTR_POLICY_ID     = "quaicu.policy_id"
ATTR_POLICY_VERSION = "quaicu.policy_version"
ATTR_LEDGER_SEQ    = "quaicu.ledger_seq"         # set on lifecycle.seal and ledger.seal
ATTR_MODEL_REF     = "quaicu.model_ref"          # set on gateway.generate
ATTR_MODEL_COST_USD = "quaicu.model_cost_usd"    # set on gateway.generate
```

#### Span instrumentation pattern

```python
# core/lifecycle/spine.py (illustrative)
async def propose(action: Action, tenant_id: str) -> ActionHandle:
    with tracer.start_as_current_span(
        SPAN_LIFECYCLE_PROPOSE,
        kind=SpanKind.SERVER,
        attributes={
            ATTR_TENANT_ID:   tenant_id,
            ATTR_ACTION_TYPE: action.type,
        },
    ) as span:
        try:
            handle = await _create_action_record(action, tenant_id)
            span.set_attribute(ATTR_ACTION_ID, handle.action_id)
            return handle
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(trace.Status(trace.StatusCode.ERROR))
            raise  # fail-closed: re-raise, never swallow

async def evaluate(handle: ActionHandle, tenant_id: str) -> EvaluationResult:
    with tracer.start_as_current_span(
        SPAN_LIFECYCLE_EVALUATE,
        attributes={
            ATTR_TENANT_ID: tenant_id,
            ATTR_ACTION_ID: handle.action_id,
        },
    ) as span:
        result = await _policy_engine.evaluate(handle)
        span.set_attribute(ATTR_DECISION,        result.decision.value)
        span.set_attribute(ATTR_POLICY_ID,       result.policy_id)
        span.set_attribute(ATTR_POLICY_VERSION,  str(result.policy_version))
        return result
```

### Key Metrics

All metrics use the `quaicu_` prefix. Tenant cardinality is bounded — tenants are not row-level; each tenant is a known customer. Include `tenant_id` as a label on all kernel metrics.

```python
# core/metrics.py
from prometheus_client import Counter, Histogram, Gauge

action_proposed_total = Counter(
    "quaicu_action_proposed_total",
    "Total actions proposed",
    ["tenant_id", "action_type"],
)

action_denied_total = Counter(
    "quaicu_action_denied_total",
    "Total actions denied by policy evaluation",
    ["tenant_id", "action_type", "policy_id"],
)

action_executed_total = Counter(
    "quaicu_action_executed_total",
    "Total actions successfully executed and sealed",
    ["tenant_id", "action_type"],
)

policy_eval_duration = Histogram(
    "quaicu_policy_eval_duration_seconds",
    "Policy evaluation duration (CEL + assurance checks)",
    ["tenant_id", "policy_id"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

ledger_seal_duration = Histogram(
    "quaicu_ledger_seal_duration_seconds",
    "Time to append an entry to the Merkle ledger and generate inclusion proof",
    ["tenant_id"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

hitl_pending_gauge = Gauge(
    "quaicu_hitl_pending_gauge",
    "Number of actions currently awaiting human approval",
    ["tenant_id"],
)

model_call_cost_total = Counter(
    "quaicu_model_call_cost_usd_total",
    "Cumulative model call cost in USD (for chargeback and budget enforcement)",
    ["tenant_id", "model_ref", "action_type"],
)

ledger_seal_failure_total = Counter(
    "quaicu_ledger_seal_failure_total",
    "Ledger seal failures — action was not persisted (fail-closed outcome)",
    ["tenant_id", "reason"],
)
```

### Loki Log Labels

Every log entry emitted by the kernel must carry these labels. Do not put high-cardinality values (action_id, ledger_seq) as Loki labels — put them in the log body as structured fields. Loki labels are for fast stream selection; fields are for log-line filtering.

```python
# core/logging.py
import structlog

def configure_kernel_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ]
    )

# In each request context, bind the stream-level labels:
structlog.contextvars.bind_contextvars(
    tenant_id=tenant_id,        # Loki label — low cardinality
    action_type=action_type,    # Loki label — low cardinality
    decision=decision,          # Loki label: ALLOWED | DENIED | PENDING | SEALED
    # These go in the log body, NOT as Loki labels:
    # action_id=action_id,
    # ledger_seq=ledger_seq,
    # policy_id=policy_id,
)
```

Loki label configuration in Promtail / Alloy:

```yaml
# Loki pipeline stages for quaicu-kernel pods
pipeline_stages:
  - json:
      expressions:
        tenant_id:   tenant_id
        action_type: action_type
        decision:    decision
        level:       level
  - labels:
      tenant_id:
      action_type:
      decision:
      level:
```

### Grafana Governance Overview Dashboard (JSON skeleton)

```json
{
  "title": "QUAICU Governance Overview",
  "uid": "quaicu-governance-overview",
  "tags": ["quaicu", "governance"],
  "refresh": "30s",
  "panels": [
    {
      "id": 1,
      "title": "Actions Proposed / min",
      "type": "stat",
      "gridPos": { "x": 0, "y": 0, "w": 4, "h": 3 },
      "targets": [{
        "expr": "sum(rate(quaicu_action_proposed_total[1m])) by (tenant_id)",
        "legendFormat": "{{tenant_id}}"
      }]
    },
    {
      "id": 2,
      "title": "Deny Rate %",
      "type": "stat",
      "gridPos": { "x": 4, "y": 0, "w": 4, "h": 3 },
      "fieldConfig": {
        "defaults": {
          "thresholds": {
            "steps": [
              { "value": 0,  "color": "green" },
              { "value": 10, "color": "yellow" },
              { "value": 25, "color": "red" }
            ]
          },
          "unit": "percent"
        }
      },
      "targets": [{
        "expr": "100 * sum(rate(quaicu_action_denied_total[5m])) / sum(rate(quaicu_action_proposed_total[5m]))"
      }]
    },
    {
      "id": 3,
      "title": "HITL Pending",
      "type": "stat",
      "gridPos": { "x": 8, "y": 0, "w": 4, "h": 3 },
      "fieldConfig": {
        "defaults": {
          "thresholds": {
            "steps": [
              { "value": 0,  "color": "green" },
              { "value": 10, "color": "yellow" },
              { "value": 50, "color": "red" }
            ]
          }
        }
      },
      "targets": [{
        "expr": "sum(quaicu_hitl_pending_gauge) by (tenant_id)",
        "legendFormat": "{{tenant_id}}"
      }]
    },
    {
      "id": 4,
      "title": "Policy Eval Duration p99 (ms)",
      "type": "timeseries",
      "gridPos": { "x": 0, "y": 3, "w": 12, "h": 6 },
      "targets": [{
        "expr": "histogram_quantile(0.99, sum(rate(quaicu_policy_eval_duration_seconds_bucket[5m])) by (le, tenant_id)) * 1000",
        "legendFormat": "{{tenant_id}} p99"
      }]
    },
    {
      "id": 5,
      "title": "Ledger Seal Duration p99 (ms)",
      "type": "timeseries",
      "gridPos": { "x": 0, "y": 9, "w": 12, "h": 6 },
      "targets": [{
        "expr": "histogram_quantile(0.99, sum(rate(quaicu_ledger_seal_duration_seconds_bucket[5m])) by (le, tenant_id)) * 1000",
        "legendFormat": "{{tenant_id}} p99"
      }]
    },
    {
      "id": 6,
      "title": "Model Call Cost (USD / hour)",
      "type": "timeseries",
      "gridPos": { "x": 0, "y": 15, "w": 12, "h": 6 },
      "targets": [{
        "expr": "sum(rate(quaicu_model_call_cost_usd_total[1h])) by (tenant_id, model_ref)",
        "legendFormat": "{{tenant_id}} / {{model_ref}}"
      }]
    },
    {
      "id": 7,
      "title": "Ledger Seal Failures",
      "type": "timeseries",
      "gridPos": { "x": 0, "y": 21, "w": 12, "h": 4 },
      "fieldConfig": {
        "defaults": {
          "thresholds": { "steps": [{ "value": 0, "color": "green" }, { "value": 1, "color": "red" }] }
        }
      },
      "targets": [{
        "expr": "sum(rate(quaicu_ledger_seal_failure_total[5m])) by (tenant_id, reason)",
        "legendFormat": "{{tenant_id}} / {{reason}}"
      }]
    }
  ]
}
```

### Alert Rules

```yaml
# prometheus/rules/quaicu-governance.yml
groups:
  - name: quaicu.governance
    interval: 30s
    rules:

      # ── HITL queue depth ────────────────────────────────────────────────────
      - alert: QUAICUHITLQueueHigh
        expr: |
          quaicu_hitl_pending_gauge > 50
        for: 5m
        labels:
          severity: warning
          team: governance
        annotations:
          summary: "HITL queue depth high for tenant {{ $labels.tenant_id }}"
          description: |
            {{ $value | printf "%.0f" }} actions are pending human approval for tenant
            {{ $labels.tenant_id }}. Governed actions are blocked until resolved.
          runbook_url: "https://docs.quaicu.io/runbooks/hitl-queue-high"

      - alert: QUAICUHITLQueueCritical
        expr: |
          quaicu_hitl_pending_gauge > 200
        for: 2m
        labels:
          severity: critical
          team: governance
        annotations:
          summary: "HITL queue critically high for tenant {{ $labels.tenant_id }}"
          description: |
            {{ $value | printf "%.0f" }} actions pending. Governance throughput is severely
            impacted for tenant {{ $labels.tenant_id }}.

      # ── Deny rate spike ─────────────────────────────────────────────────────
      - alert: QUAICUDenyRateSpike
        expr: |
          (
            sum(rate(quaicu_action_denied_total[5m])) by (tenant_id)
            /
            sum(rate(quaicu_action_proposed_total[5m])) by (tenant_id)
          ) > 0.30
        for: 5m
        labels:
          severity: warning
          team: governance
        annotations:
          summary: "Deny rate spike for tenant {{ $labels.tenant_id }}"
          description: |
            Deny rate is {{ $value | humanizePercentage }} over the last 5 minutes for
            tenant {{ $labels.tenant_id }}. This may indicate a misconfigured policy,
            a changed data distribution, or an upstream issue.

      # ── Ledger seal failure ─────────────────────────────────────────────────
      - alert: QUAICULedgerSealFailure
        expr: |
          sum(rate(quaicu_ledger_seal_failure_total[5m])) by (tenant_id) > 0
        for: 1m
        labels:
          severity: critical
          team: governance
        annotations:
          summary: "Ledger seal failures for tenant {{ $labels.tenant_id }}"
          description: |
            The TrustLedger is failing to seal entries for tenant {{ $labels.tenant_id }}.
            Per fail-closed rules, actions cannot be executed if they cannot be sealed.
            Investigate immediately.
          runbook_url: "https://docs.quaicu.io/runbooks/ledger-seal-failure"

      # ── Policy eval latency ─────────────────────────────────────────────────
      - alert: QUAICUPolicyEvalLatencyHigh
        expr: |
          histogram_quantile(0.99,
            sum(rate(quaicu_policy_eval_duration_seconds_bucket[5m])) by (le, tenant_id)
          ) > 0.5
        for: 5m
        labels:
          severity: warning
          team: governance
        annotations:
          summary: "Policy eval p99 > 500ms for tenant {{ $labels.tenant_id }}"
          description: |
            CEL evaluation is taking {{ $value | humanizeDuration }} at p99 for tenant
            {{ $labels.tenant_id }}. This directly impacts action throughput.
```

### Observability non-negotiables for QUAICU

- Every span must carry `quaicu.tenant_id` and `quaicu.action_id` — without these, correlating a trace to a ledger entry is impossible.
- The `gateway.generate` span must record `quaicu.model_ref` and `quaicu.model_cost_usd` — these are sealed to the ledger as part of K·05 cost governance.
- Ledger seal latency (`ledger.seal` span + `quaicu_ledger_seal_duration_seconds`) is the single most important performance metric for the TrustLedger. Track it at p99, not just average.
- Never sample governance-critical spans (lifecycle.propose, lifecycle.seal) below 100%. These are the forensic record. Sampling applies to application spans, not kernel lifecycle spans.
- HITL pending gauge must be scraped every 15 seconds (not the default 60s) — queue depth affects active governed actions in flight.
