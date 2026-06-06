---
name: temporal-golang-pro
description: "Use when building durable distributed systems with Temporal Go SDK. Covers deterministic workflow rules, mTLS worker configs, and advanced patterns. QUAICU kernel — the Temporal WorkflowPort adapter for the K·06 Process Engine; deterministic workflows with all non-determinism behind recorded activities, HITL signal with fail-closed timeout, config-selected alongside the Postgres state-machine adapter. Triggers — WorkflowPort, K·06, process engine, durable workflow, recorded activity, deterministic replay, HITL signal."
risk: safe
source: self
date_added: "2026-02-27"
---

# Temporal Go SDK (temporal-golang-pro)

## ⚡ QUAICU Decision Contract — READ THIS FIRST (when used for the QUAICU kernel)

> Makes the QUAICU-specific workflow choices mechanical so a small/low-token model matches a top model at max effort.
> **For QUAICU work, this block overrides the general guidance below.** Missing rule → HALT the workflow.

### Invariants — never violated
- The kernel reaches Temporal only through `WorkflowPort`. Temporal is ONE adapter (`adapters/workflow/temporal`); the Postgres state-machine is the default/MVP adapter. NEVER import the Temporal SDK in `core/`.
- Workflow code is deterministic. Every non-deterministic op (model call, time, random, external read) goes in an ACTIVITY. On replay, recorded results are reused, never recomputed.
- HITL is a workflow signal; a HITL timeout resolves to REJECTED (fail-closed). NEVER auto-approve on timeout.
- Adapter selection is config-driven (`kernel.toml`); never branch on adapter type in `core/`.
- Rollback/compensation runs through the governed lifecycle (saga), not as an out-of-band side effect.

### Decision table
| Situation | Do exactly this |
|---|---|
| Need time/random/IO in a workflow | move to an activity; record the result |
| HITL approval | `@workflow.signal`; timeout → REJECTED |
| Activity fails transiently | retry policy on the activity; workflow stays pure |
| Activity fails terminally | propagate → action HALTED |
| Default engine for sovereign/MVP | Postgres state-machine, not Temporal |

### Tie-break rules
- Workflow body vs activity? → non-deterministic or side-effecting → activity. Workflow stays pure.
- Unknown/unreachable state? → HALT, never assume completed/approved.

### Self-check
- [ ] core/ uses WorkflowPort only; no Temporal SDK import in core/.
- [ ] No clock/random/IO in workflow bodies — all in recorded activities.
- [ ] HITL signal timeout → rejected.
- [ ] Adapter chosen by config; Postgres adapter is the default.

## Overview

Expert-level guide for building resilient, scalable, and deterministic distributed systems using the Temporal Go SDK. This skill transforms vague orchestration requirements into production-grade Go implementations, focusing on durable execution, strict determinism, and enterprise-scale worker configuration.

## When to Use This Skill

- **Designing Distributed Systems**: When building microservices that require durable state and reliable orchestration.
- **Implementing Complex Workflows**: Using the Go SDK to handle long-running processes (days/months) or complex Saga patterns.
- **Optimizing Performance**: When workers need fine-tuned concurrency, mTLS security, or custom interceptors.
- **Ensuring Reliability**: Implementing idempotent activities, graceful error handling, and sophisticated retry policies.
- **Maintenance & Evolution**: Versioning running workflows or performing zero-downtime worker updates.

## Do not use this skill when

- Using Temporal with other SDKs (Python, Java, TypeScript) - refer to their specific `-pro` skills.
- The task is a simple request/response without durability or coordination needs.
- High-level design without implementation (use `workflow-orchestration-patterns`).

## Step-by-Step Guide

1.  **Gather Context**: Proactively ask for:
    - Target **Temporal Cluster** (Cloud vs. Self-hosted) and **Namespace**.
    - **Task Queue** names and expected throughput.
    - **Security requirements** (mTLS paths, authentication).
    - **Failure modes** and desired retry/timeout policies.
2.  **Verify Determinism**: Before suggesting workflow code, verify against these **5 Rules**:
    - No native Go concurrency (goroutines).
    - No native time (`time.Now`, `time.Sleep`).
    - No non-deterministic map iteration (must sort keys).
    - No direct external I/O or network calls.
    - No non-deterministic random numbers.
3.  **Implement Incrementally**: Start with shared Protobuf/Data classes, then Activities, then Workflows, and finally Workers.
4.  **Leverage Resources**: If the implementation requires advanced patterns (Sagas, Interceptors, Replay Testing), explicitly refer to the implementation playbook and testing strategies.

## Capabilities

### Go SDK Implementation

- **Worker Management**: Deep knowledge of `worker.Options`, including `MaxConcurrentActivityTaskPollers`, `WorkerStopTimeout`, and `StickyScheduleToStartTimeout`.
- **Interceptors**: Implementing Client, Worker, and Workflow interceptors for cross-cutting concerns (logging, tracing, auth).
- **Custom Data Converters**: Integrating Protobuf, encrypted payloads, or custom JSON marshaling.

### Advanced Workflow Patterns

- **Durable Concurrency**: Using `workflow.Go`, `workflow.Channel`, and `workflow.Selector` instead of native primitives.
- **Versioning**: Implementing safe code evolution using `workflow.GetVersion` and `workflow.GetReplaySafeLogger`.
- **Large-scale Processing**: Pattern for `ContinueAsNew` to manage history size limits (defaults: 50MB or 50K events).
- **Child Workflows**: Managing lifecycle, cancellation, and parent-child signal propagation.

### Testing & Observability

- **Testsuite Mastery**: Using `WorkflowTestSuite` for unit and functional testing with deterministic time control.
- **Mocking**: Sophisticated activity and child workflow mocking strategies.
- **Replay Testing**: Validating code changes against production event histories.
- **Metrics**: Configuring Prometheus/OpenTelemetry exporters for worker performance tracking.

## Examples

### Example 1: Versioned Workflow (Deterministic)

```go
// Note: imports omitted. Requires 'go.temporal.io/sdk/workflow', 'go.temporal.io/sdk/temporal', and 'time'.
func SubscriptionWorkflow(ctx workflow.Context, userID string) error {
    // 1. Versioning for logic evolution (v1 = DefaultVersion)
    v := workflow.GetVersion(ctx, "billing_logic", workflow.DefaultVersion, 2)

    for i := 0; i < 12; i++ {
        ao := workflow.ActivityOptions{
            StartToCloseTimeout: 5 * time.Minute,
            RetryPolicy: &temporal.RetryPolicy{MaximumAttempts: 3},
        }
        ctx = workflow.WithActivityOptions(ctx, ao)

        // 2. Activity Execution (Always handle errors)
        err := workflow.ExecuteActivity(ctx, ChargePaymentActivity, userID).Get(ctx, nil)
        if err != nil {
            workflow.GetLogger(ctx).Error("Payment failed", "Error", err)
            return err
        }

        // 3. Durable Sleep (Time-skipping safe)
        sleepDuration := 30 * 24 * time.Hour
        if v >= 2 {
            sleepDuration = 28 * 24 * time.Hour
        }

        if err := workflow.Sleep(ctx, sleepDuration); err != nil {
            return err
        }
    }
    return nil
}
```

### Example 2: Full mTLS Worker Setup

```go
func RunSecureWorker() error {
    // 1. Load Client Certificate and Key
    cert, err := tls.LoadX509KeyPair("client.pem", "client.key")
    if err != nil {
        return fmt.Errorf("failed to load client keys: %w", err)
    }

    // 2. Load CA Certificate for Server verification (Proper mTLS)
    caPem, err := os.ReadFile("ca.pem")
    if err != nil {
        return fmt.Errorf("failed to read CA cert: %w", err)
    }
    certPool := x509.NewCertPool()
    if !certPool.AppendCertsFromPEM(caPem) {
        return fmt.Errorf("failed to parse CA cert")
    }

    // 3. Dial Cluster with full TLS config
    c, err := client.Dial(client.Options{
        HostPort:  "temporal.example.com:7233",
        Namespace: "production",
        ConnectionOptions: client.ConnectionOptions{
            TLS: &tls.Config{
                Certificates: []tls.Certificate{cert},
                RootCAs:      certPool,
            },
        },
    })
    if err != nil {
        return fmt.Errorf("failed to dial temporal: %w", err)
    }
    defer c.Close()

    w := worker.New(c, "payment-queue", worker.Options{})
    w.RegisterWorkflow(SubscriptionWorkflow)

    if err := w.Run(worker.InterruptCh()); err != nil {
        return fmt.Errorf("worker run failed: %w", err)
    }
    return nil
}
```

### Example 3: Selector & Signal Integration

```go
func ApprovalWorkflow(ctx workflow.Context) (string, error) {
    var approved bool
    signalCh := workflow.GetSignalChannel(ctx, "approval-signal")

    // Use Selector to wait for multiple async events
    s := workflow.NewSelector(ctx)
    s.AddReceive(signalCh, func(c workflow.ReceiveChannel, _ bool) {
        c.Receive(ctx, &approved)
    })

    // Add 72-hour timeout timer
    s.AddReceive(workflow.NewTimer(ctx, 72*time.Hour).GetChannel(), func(c workflow.ReceiveChannel, _ bool) {
        approved = false
    })

    s.Select(ctx)

    if !approved {
        return "rejected", nil
    }
    return "approved", nil
}
```

## Best Practices

- ✅ **Do:** Always handle errors from `ExecuteActivity` and `client.Dial`.
- ✅ **Do:** Use `workflow.Go` and `workflow.Channel` for concurrency.
- ✅ **Do:** Sort map keys before iteration to maintain determinism.
- ✅ **Do:** Use `activity.RecordHeartbeat` for activities lasting > 1 minute.
- ✅ **Do:** Test logic compatibility using `replayer.ReplayWorkflowHistoryFromJSON`.
- ❌ **Don't:** Swallow errors with `_` or `log.Fatal` in production workers.
- ❌ **Don't:** Perform direct Network/Disk I/O inside a Workflow function.
- ❌ **Don't:** Rely on native `time.Now()` or `rand.Int()`.
- ❌ **Don't:** Apply this to simple cron jobs that don't require durability.

## Troubleshooting

- **Panic: Determinism Mismatch**: Usually caused by logic changes without `workflow.GetVersion` or non-deterministic code (e.g., native maps).
- **Error: History Size Exceeded**: History limit reached (default 50K events). Ensure `ContinueAsNew` is implemented.
- **Worker Hang**: Check `WorkerStopTimeout` and ensure all activities handle context cancellation.

## Limitations

- Does not cover Temporal Cloud UI navigation or TLS certificate provisioning workflows.
- Does not cover Temporal Java, Python, or TypeScript SDKs; refer to their dedicated `-pro` skills.
- Assumes Temporal Server v1.20+ and Go SDK v1.25+; older SDK versions may have different APIs.
- Does not cover experimental Temporal features (e.g., Nexus, Multi-cluster Replication).
- Does not address global namespace configuration or multi-region failover setup.
- Does not cover Temporal Worker versioning via the `worker-versioning` feature flag (experimental).

## Resources

- [Implementation Playbook](resources/implementation-playbook.md) - Deep dive into Go SDK patterns.
- [Testing Strategies](resources/testing-strategies.md) - Unit, Replay, and Integration testing for Go.
- [Temporal Go SDK Reference](https://pkg.go.dev/go.temporal.io/sdk)
- [Temporal Go Samples](https://github.com/temporalio/samples-go)

## Related Skills

- `grpc-golang` - Internal transport protocol and Protobuf design.
- `golang-pro` - General Go performance tuning and advanced syntax.
- `workflow-orchestration-patterns` - Language-agnostic orchestration strategy.

---

## QUAICU-Specific Application

This section extends the skill for use within the QUAICU governance kernel build. All patterns here align with the spec at `QUAICU_Kernel_Build_Spec.md`. The Temporal adapter lives at `adapters/workflow/temporal/` and implements `core/ports/workflow.py`'s `WorkflowPort`. Core logic never imports the Temporal SDK directly — only the adapter does.

### GovernedActionWorkflow: The Six Activities

Every governed action flows through exactly these six activities in sequence. No activity may be skipped; a failure at any step cancels the workflow (fail-closed, per Core Invariant F-03 and F-04).

```go
// adapters/workflow/temporal/governed_action_workflow.go

// GovernedActionInput carries all data needed for the full lifecycle.
// All non-deterministic fields (model outputs, resolved actor) are recorded
// here at proposal time and reused on replay — never recomputed.
type GovernedActionInput struct {
    TenantID       string          `json:"tenant_id"`
    ActionID       string          `json:"action_id"`
    ActionType     string          `json:"action_type"`
    Payload        json.RawMessage `json:"payload"`
    ActorRef       string          `json:"actor_ref"`
    IdempotencyKey string          `json:"idempotency_key"`
}

type GovernedActionResult struct {
    Decision   string `json:"decision"` // ALLOWED | DENIED | APPROVED | REJECTED
    LedgerSeq  int64  `json:"ledger_seq"`
    ProofB64   string `json:"proof_b64"`
}

func GovernedActionWorkflow(ctx workflow.Context, input GovernedActionInput) (GovernedActionResult, error) {
    logger := workflow.GetLogger(ctx)

    // ── Activity 1: evaluate ─────────────────────────────────────────────────
    // Runs the Policy Engine (K·01) + consent check (K·04) + assurance signals
    // (K·08–K·11). Returns ALLOW, DENY, or REQUIRE_APPROVAL.
    // Retry: up to 3 attempts with 2s initial interval, 2x backoff.
    // A DENY result is a terminal business outcome — not an error.
    evalOpts := workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
        StartToCloseTimeout: 30 * time.Second,
        RetryPolicy: &temporal.RetryPolicy{
            MaximumAttempts:        3,
            InitialInterval:        2 * time.Second,
            BackoffCoefficient:     2.0,
            NonRetryableErrorTypes: []string{"PolicyDeniedError", "ConsentDeniedError"},
        },
    })
    var evalResult EvaluationResult
    if err := workflow.ExecuteActivity(evalOpts, EvaluateActivity, input).Get(evalOpts, &evalResult); err != nil {
        logger.Error("evaluate activity failed — action DENIED (fail-closed)", "error", err)
        return GovernedActionResult{Decision: "DENIED"}, err
    }
    if evalResult.Decision == "DENY" {
        return GovernedActionResult{Decision: "DENIED"}, nil
    }

    // ── Activity 2: consent_check ────────────────────────────────────────────
    // Separate consent gate (K·04 / DPDP). Called after policy evaluate but
    // before HITL so that a consent failure terminates early without consuming
    // a HITL slot.
    consentOpts := workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
        StartToCloseTimeout: 15 * time.Second,
        RetryPolicy: &temporal.RetryPolicy{
            MaximumAttempts:        3,
            InitialInterval:        1 * time.Second,
            BackoffCoefficient:     2.0,
            NonRetryableErrorTypes: []string{"ConsentMissingError"},
        },
    })
    var consentOK bool
    if err := workflow.ExecuteActivity(consentOpts, ConsentCheckActivity, input).Get(consentOpts, &consentOK); err != nil {
        return GovernedActionResult{Decision: "DENIED"}, err
    }
    if !consentOK {
        return GovernedActionResult{Decision: "DENIED"}, nil
    }

    // ── Activity 3: gate / HITL ──────────────────────────────────────────────
    // Only reached when evalResult.Decision == "REQUIRE_APPROVAL".
    // Issues the approval request via HITLPort, then the workflow suspends
    // waiting for the hitl-decision signal (see HITL signal handler below).
    // If evalResult.Decision == "ALLOW", this activity is a no-op pass-through.
    if evalResult.Decision == "REQUIRE_APPROVAL" {
        gateOpts := workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
            StartToCloseTimeout: 10 * time.Second,
            RetryPolicy:         &temporal.RetryPolicy{MaximumAttempts: 3},
        })
        if err := workflow.ExecuteActivity(gateOpts, RequestHITLActivity, input, evalResult).Get(gateOpts, nil); err != nil {
            return GovernedActionResult{Decision: "DENIED"}, err
        }

        // Suspend: wait for human decision signal or policy-configured timeout.
        hitlSignalCh := workflow.GetSignalChannel(ctx, "hitl-decision")
        timeout := workflow.NewTimer(ctx, evalResult.HITLTimeoutDuration)
        sel := workflow.NewSelector(ctx)

        var hitlDecision HITLDecision
        sel.AddReceive(hitlSignalCh, func(c workflow.ReceiveChannel, _ bool) {
            c.Receive(ctx, &hitlDecision)
        })
        sel.AddFuture(timeout, func(f workflow.Future) {
            // Timeout → fail-closed: treat as rejection
            hitlDecision = HITLDecision{Approved: false, Reason: "timeout"}
        })
        sel.Select(ctx)

        if !hitlDecision.Approved {
            // Cancel workflow cleanly; emit a REJECTED event before returning.
            emitOpts := workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
                StartToCloseTimeout: 10 * time.Second,
                RetryPolicy:         &temporal.RetryPolicy{MaximumAttempts: 3},
            })
            _ = workflow.ExecuteActivity(emitOpts, EmitActivity, input, "REJECTED", nil).Get(emitOpts, nil)
            return GovernedActionResult{Decision: "REJECTED"}, nil
        }
    }

    // ── Activity 4: execute ──────────────────────────────────────────────────
    // The single real state-change step. Only runs after evaluate + gate pass.
    // Idempotency is enforced via input.IdempotencyKey checked inside the activity.
    execOpts := workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
        StartToCloseTimeout: 2 * time.Minute,
        HeartbeatTimeout:    30 * time.Second,
        RetryPolicy: &temporal.RetryPolicy{
            MaximumAttempts:        2,
            InitialInterval:        5 * time.Second,
            BackoffCoefficient:     2.0,
            NonRetryableErrorTypes: []string{"IdempotencyConflictError"},
        },
    })
    var execResult ExecuteResult
    if err := workflow.ExecuteActivity(execOpts, ExecuteActivity, input).Get(execOpts, &execResult); err != nil {
        return GovernedActionResult{Decision: "DENIED"}, err
    }

    // ── Activity 5: seal ─────────────────────────────────────────────────────
    // Writes the completed action to the TrustLedger (K·02) with its RFC 6962
    // Merkle inclusion proof. ZERO retries — the idempotency key stored in the
    // ledger prevents a double-seal. If the seal fails, the workflow errors and
    // Temporal will replay from this point; the activity detects the existing
    // idempotency key and returns success on re-execution without writing again.
    sealOpts := workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
        StartToCloseTimeout: 30 * time.Second,
        RetryPolicy: &temporal.RetryPolicy{
            MaximumAttempts: 1, // No retries — idempotency key is the safety net
        },
    })
    var sealResult SealResult
    if err := workflow.ExecuteActivity(sealOpts, SealActivity, input, execResult).Get(sealOpts, &sealResult); err != nil {
        return GovernedActionResult{Decision: "DENIED"}, err
    }

    // ── Activity 6: emit ─────────────────────────────────────────────────────
    // Publishes the structured governance event (K·07) after the ledger is sealed.
    // The event carries the ledger sequence number and proof reference so
    // consumers can independently verify the action.
    emitOpts := workflow.WithActivityOptions(ctx, workflow.ActivityOptions{
        StartToCloseTimeout: 15 * time.Second,
        RetryPolicy:         &temporal.RetryPolicy{MaximumAttempts: 3},
    })
    if err := workflow.ExecuteActivity(emitOpts, EmitActivity, input, "ALLOWED", &sealResult).Get(emitOpts, nil); err != nil {
        // Emit failure is non-fatal for correctness (the seal already happened)
        // but must be logged and alerted — never silently dropped.
        logger.Error("emit activity failed after seal — event NOT published", "error", err)
    }

    return GovernedActionResult{
        Decision:  "ALLOWED",
        LedgerSeq: sealResult.LedgerSeq,
        ProofB64:  sealResult.ProofB64,
    }, nil
}
```

### HITL Signal Handler Pattern

Signals are the only valid mechanism for injecting a human decision into a suspended workflow. Never poll; never use a side-channel.

```go
// The signal name is the contract between the HITL adapter and the workflow.
// adapters/hitl/ sends this signal via the Temporal client after a human acts.
const HITLDecisionSignal = "hitl-decision"

type HITLDecision struct {
    Approved   bool   `json:"approved"`
    ApproverID string `json:"approver_id"`
    Reason     string `json:"reason"`
    // Timestamp is informational only — workflow logic never branches on wall-clock.
    // Determinism requires that the decision itself (bool) drives branching.
    DecidedAt  string `json:"decided_at"` // ISO-8601, for audit record only
}

// To send the signal from the HITL adapter (outside the workflow):
//
//   err := temporalClient.SignalWorkflow(ctx,
//       workflowID,   // see Workflow ID naming convention below
//       "",           // latest run
//       HITLDecisionSignal,
//       HITLDecision{Approved: true, ApproverID: "user:alice", Reason: "reviewed"},
//   )
```

### Workflow Cancellation for Rejected Actions

When a HITL decision is rejected (or times out), the workflow must:
1. Execute the `emit` activity with decision `REJECTED` — so the event bus and downstream subscribers see the outcome.
2. Return cleanly with `GovernedActionResult{Decision: "REJECTED"}` and a `nil` error.
3. Never call `execute` or `seal` — the action must not reach institutional state or the ledger.

Do NOT use `workflow.RequestCancellation` from within the workflow itself; use the clean return path shown in the `GovernedActionWorkflow` example above. External callers who need to cancel a pending action (e.g., the actor withdraws the proposal) send a `cancel-proposal` signal that triggers the same rejection branch.

### Determinism Rules for QUAICU Workflow Code

The Core Invariant "Determinism" (spec §1) maps directly to Temporal's replay model. Additional rules specific to QUAICU:

| Prohibited in workflow code | Required alternative |
|---|---|
| `time.Now()` | `workflow.Now(ctx)` — returns deterministic replay-safe time |
| `rand.Int()` / `uuid.New()` | Generate in an **activity**; pass result back as return value |
| Direct DB calls | Behind an **activity** (StoragePort adapter) |
| Direct model/inference calls | Behind an **activity** (InferencePort adapter); result recorded in ledger |
| `os.Getenv()` | Pass as workflow input or activity parameter |
| Any `sync.*` primitives | `workflow.Channel`, `workflow.Selector`, `workflow.Go` |

The non-determinism rule from spec §3.13 is enforced here: model calls, external lookups, and time are all performed inside activities whose results are recorded in the Temporal event history and in the ledger sealed entry. Replay never recomputes them.

### Activity Retry Policies Summary

| Activity | Max Attempts | Initial Interval | Backoff | Non-Retryable Errors | Rationale |
|---|---|---|---|---|---|
| `EvaluateActivity` (policy eval) | 3 | 2 s | 2× | `PolicyDeniedError`, `ConsentDeniedError` | Transient infra failures retry; a policy DENY is final |
| `ConsentCheckActivity` | 3 | 1 s | 2× | `ConsentMissingError` | Missing consent is a business terminal; infra errors retry |
| `RequestHITLActivity` | 3 | 2 s | 2× | — | Sending the approval request may hit transient network issues |
| `ExecuteActivity` | 2 | 5 s | 2× | `IdempotencyConflictError` | State change is sensitive; idempotency conflict is final |
| `SealActivity` | **1** (no retry) | — | — | — | Idempotency key in ledger prevents double-seal; Temporal replay handles re-execution safely |
| `EmitActivity` | 3 | 1 s | 2× | — | Post-seal; emit failure is non-fatal for correctness but must not be silently dropped |
| Model call (inside InferencePort activity) | 2 | 3 s | 2× | `ModelUnavailableError` (fail-closed) | Two attempts before failing closed per §3.12 |

### Temporal Worker Configuration for QUAICU

```go
// adapters/workflow/temporal/worker.go

func NewQUAICUWorker(cfg TemporalConfig) (worker.Worker, error) {
    c, err := client.Dial(client.Options{
        HostPort:  cfg.HostPort,
        Namespace: cfg.Namespace, // e.g. "quaicu-production"
        ConnectionOptions: client.ConnectionOptions{
            TLS: loadMTLSConfig(cfg),
        },
        // Interceptor for OpenTelemetry trace propagation across activities
        Interceptors: []interceptor.ClientInterceptor{
            otelinterceptor.NewTracingInterceptor(),
        },
    })
    if err != nil {
        return nil, fmt.Errorf("temporal dial: %w", err)
    }

    w := worker.New(c, QUAICUTaskQueue, worker.Options{
        // Concurrency: governance actions are not throughput-bound; prefer
        // correctness headroom over maximizing parallelism.
        MaxConcurrentActivityExecutionSize:      50,
        MaxConcurrentWorkflowTaskExecutionSize:  20,
        MaxConcurrentActivityTaskPollers:        5,
        MaxConcurrentWorkflowTaskPollers:        5,
        // Give in-flight activities time to finish cleanly on shutdown.
        WorkerStopTimeout: 60 * time.Second,
        // Sticky task queues reduce latency for suspended (HITL) workflows.
        StickyScheduleToStartTimeout: 10 * time.Second,
    })

    w.RegisterWorkflow(GovernedActionWorkflow)
    w.RegisterActivity(&GovernanceActivities{}) // struct-based registration

    return w, nil
}

const QUAICUTaskQueue = "quaicu-governance"
```

### Workflow ID Naming Convention

Workflow IDs must be globally unique per Temporal namespace, human-readable for ops, and carry enough context for the monitoring search attributes.

```
Format:  governed-action/{tenant_id}/{action_id}
Example: governed-action/acme-bank/act_01J3X8K2P9Q7R5S6T4U1V0W2
```

Rules:
- `tenant_id`: the slug from the kernel's tenant registry (e.g. `acme-bank`). Never use an integer or UUID — a slug is readable in Temporal Web.
- `action_id`: a KSORTABLE ID (ULID or similar) generated at proposal time. This becomes the idempotency anchor for the seal activity.
- Re-submitting the same proposal reuses the same `action_id`; Temporal's workflow-ID deduplication (with `WorkflowIDReusePolicy = AllowDuplicateFailedOnly`) ensures a completed or running workflow is not restarted.

```go
workflowID := fmt.Sprintf("governed-action/%s/%s", input.TenantID, input.ActionID)
options := client.StartWorkflowOptions{
    ID:                    workflowID,
    TaskQueue:             QUAICUTaskQueue,
    WorkflowIDReusePolicy: enumspb.WORKFLOW_ID_REUSE_POLICY_ALLOW_DUPLICATE_FAILED_ONLY,
    // Search attributes enable filtering in Temporal Web and Prometheus.
    SearchAttributes: map[string]interface{}{
        "TenantID":   input.TenantID,
        "ActionType": input.ActionType,
        "ActorRef":   input.ActorRef,
    },
}
```

### Search Attributes for Monitoring

Register these custom search attributes on the Temporal namespace (once, via `tctl` or the Admin API):

| Attribute | Type | Purpose |
|---|---|---|
| `TenantID` | Keyword | Filter all workflows for a tenant; tenant isolation audit |
| `ActionType` | Keyword | Filter by governed action type (e.g. `ciro.ifrs9.stage_transition`) |
| `ActorRef` | Keyword | Trace all actions by a given actor |
| `PolicyDecision` | Keyword | `ALLOW` / `DENY` / `REQUIRE_APPROVAL` — SLO dashboards |
| `LedgerSeq` | Int | Correlate workflow run to a specific ledger entry |

These attributes are set by the `EvaluateActivity` upsert (via `workflow.UpsertSearchAttributes`) after the policy decision is known, enabling real-time dashboards without querying the ledger.

### Replay Safety and the Non-Determinism Rule

QUAICU's replay fidelity requirement (spec §3.13, F-09) is satisfied by Temporal's native replay model **only if** all non-deterministic operations are behind activities:

- The `EvaluateActivity` records the policy versions evaluated and the decision; replay uses the recorded result, never re-runs CEL evaluation.
- The `SealActivity` records the Merkle proof; the proof is the replay artifact.
- Model calls (via `InferencePort`) happen inside an activity whose response is sealed to the ledger. Replay never re-calls the model.
- `workflow.Now(ctx)` is used for any time-based branching inside the workflow (e.g. HITL timeout calculation); `time.Now()` is banned.

These guarantees support K·13 (Sandbox counterfactual replay) and K·14 (point-in-time evidence generation) without re-triggering external effects.
