"""QUAICU kernel error hierarchy — FROZEN contract surface.

Every exception raised in `core/` is a typed subclass of `QUAICUError`. Never `raise Exception(...)`,
never invent a parallel error tree, never catch-and-continue. Each error carries a stable `code`
string used for structured logging and OpenTelemetry attributes.

This file is FROZEN. To add a new error type, place it under the correct existing parent. To change a
parent's shape or an existing `code`, escalate to the orchestrator and record an ADR (see AGENTS.md §3).

Source of truth: build spec §1/§8 and the `quaicu-kernel-arch` skill.
"""

from __future__ import annotations

from typing import Any


class QUAICUError(Exception):
    """Root of all kernel errors. All kernel code catches or raises subtypes of this."""

    code: str = "QUAICU_ERROR"

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.detail: dict[str, Any] = detail or {}


# ── Architecture / wiring errors ──────────────────────────────────────────────


class ArchitectureViolationError(QUAICUError):
    """A frozen ADR is violated at runtime (misconfigured wiring)."""

    code = "ARCH_VIOLATION"


class DomainImportError(ArchitectureViolationError):
    """A domain concept was detected in core/ at runtime (CI should catch this first)."""

    code = "DOMAIN_IMPORT"


class PortContractError(ArchitectureViolationError):
    """A port implementation returned None or an invalid value where it must raise."""

    code = "PORT_CONTRACT"


# ── Lifecycle errors ───────────────────────────────────────────────────────────


class LifecycleError(QUAICUError):
    """Base for all lifecycle-spine errors."""

    code = "LIFECYCLE_ERROR"


class LifecycleDeniedError(LifecycleError):
    """Action denied at evaluate or gate. Terminal — do not retry."""

    code = "LIFECYCLE_DENIED"


class LifecycleHaltedError(LifecycleError):
    """Action halted due to an internal error. May be retryable depending on cause."""

    code = "LIFECYCLE_HALTED"


class LifecycleIdempotencyError(LifecycleError):
    """Idempotency key already processed. Return the existing action state."""

    code = "LIFECYCLE_IDEMPOTENT"


class LifecycleBypassAttemptError(LifecycleError):
    """Code attempted to execute without going through evaluate + gate. F-04 violation."""

    code = "LIFECYCLE_BYPASS"


class LifecycleInvalidTransitionError(LifecycleError):
    """State-machine transition not permitted from the current state."""

    code = "LIFECYCLE_INVALID_TRANSITION"


# ── Policy engine errors (K·01) ─────────────────────────────────────────────────


class PolicyError(QUAICUError):
    """Base for all policy-engine errors."""

    code = "POLICY_ERROR"


class PolicyEvaluationError(PolicyError):
    """CEL evaluation failed or returned an unexpected type. Treated as no-match → DENY."""

    code = "POLICY_EVAL_FAILED"


class PolicyCompileError(PolicyError):
    """CEL expression failed to compile during authoring."""

    code = "POLICY_COMPILE_ERROR"


class PolicyActivationError(PolicyError):
    """Policy cannot be activated — preconditions (impact report, reviewer, compile) not met."""

    code = "POLICY_ACTIVATION_BLOCKED"


class PolicyTransitionError(PolicyError):
    """Invalid policy lifecycle transition: re-registering an ACTIVATED/DEPRECATED version, or
    submitting a non-DRAFT policy for review. (Activation has its own PolicyActivationError.)"""

    code = "POLICY_TRANSITION_INVALID"


class PolicyConflictError(PolicyError):
    """Conflict resolution produced an undefined result (should never happen — totality bug)."""

    code = "POLICY_CONFLICT_UNDEFINED"


class PolicyNotFoundError(PolicyError):
    """No policy governs this action type. Resolution: fail-closed DENY."""

    code = "POLICY_NOT_FOUND"


class PolicyPersistenceError(PolicyError):
    """A durable policy-store operation (load/save/update) failed.

    Raised by a PolicyRepository adapter so a persistence fault on the policy write path surfaces
    to the caller (management API) rather than silently leaving the durable store inconsistent.
    """

    code = "POLICY_PERSISTENCE_ERROR"


# ── Ledger errors (K·02) ────────────────────────────────────────────────────────


class LedgerError(QUAICUError):
    """Base for all TrustLedger errors."""

    code = "LEDGER_ERROR"


class LedgerSealError(LedgerError):
    """Ledger seal failed. Action must be HALTED — never marked EXECUTED/COMPLETED."""

    code = "LEDGER_SEAL_FAILED"


class LedgerPersistenceError(LedgerError):
    """A durable ledger-store operation (append/load/save) failed.

    Raised by a LedgerRepository adapter. `TrustLedger.seal` maps it to a fail-closed seal failure
    (the action HALTs) so the durable transparency log and the in-memory tree never diverge.
    """

    code = "LEDGER_PERSISTENCE_ERROR"


class LedgerProofError(LedgerError):
    """Merkle inclusion/consistency proof verification failed."""

    code = "LEDGER_PROOF_INVALID"


class LedgerTamperError(LedgerError):
    """Consistency proof detected tampering — critical, alert immediately."""

    code = "LEDGER_TAMPERED"


class LedgerClockSkewError(LedgerError):
    """Monotonic sequence violated — possible clock skew on this node."""

    code = "LEDGER_CLOCK_SKEW"


# ── Consent errors (K·04) ───────────────────────────────────────────────────────


class ConsentError(QUAICUError):
    """Base for all DPDP consent errors."""

    code = "CONSENT_ERROR"


class ConsentDeniedError(ConsentError):
    """Consent missing, expired, or withdrawn → DENY (fail-closed)."""

    code = "CONSENT_DENIED"


# ── AI Gateway errors (K·05) ────────────────────────────────────────────────────


class GatewayError(QUAICUError):
    """Base for all AI Gateway errors."""

    code = "GATEWAY_ERROR"


class GatewayDeniedError(GatewayError):
    """No policy-approved model available for this action/tenant. Fail-closed — no fallback."""

    code = "GATEWAY_DENIED"


class GatewayLoggingError(GatewayError):
    """Prompt call could not be logged. The call must not proceed (an unlogged call is ungoverned)."""

    code = "GATEWAY_LOGGING_FAILED"


class GatewayBudgetExceededError(GatewayError):
    """Per-tenant cost budget exhausted; default behavior is block (DENY)."""

    code = "GATEWAY_BUDGET_EXCEEDED"


class GatewayMaskingError(GatewayError):
    """PII masking failed; the prompt must not be transmitted."""

    code = "GATEWAY_MASKING_FAILED"


# ── Model Registry errors (K·08) ─────────────────────────────────────────────


class RegistryError(QUAICUError):
    """Base for all Model Registry errors."""

    code = "REGISTRY_ERROR"


class ModelNotPermittedError(RegistryError):
    """Model is not in the tenant's allowlist. Fail-closed — no fallback to an unapproved model."""

    code = "REGISTRY_MODEL_NOT_PERMITTED"


class ModelNotFoundError(RegistryError):
    """Model not registered in the kernel."""

    code = "REGISTRY_MODEL_NOT_FOUND"


# ── Port / adapter errors ─────────────────────────────────────────────────────


class PortError(QUAICUError):
    """Base for all port-adapter errors."""

    code = "PORT_ERROR"


class PortTimeoutError(PortError):
    """Port call timed out. Resolution: fail-closed."""

    code = "PORT_TIMEOUT"


class PortUnavailableError(PortError):
    """Port (service behind the adapter) is unreachable. Resolution: fail-closed."""

    code = "PORT_UNAVAILABLE"


class InferencePortError(PortError):
    """InferencePort adapter error (model unavailable, unapproved, or logging failed)."""

    code = "PORT_INFERENCE_ERROR"


class HITLPortError(PortError):
    """HITLPort adapter error (approver unreachable, dispatch failed)."""

    code = "PORT_HITL_ERROR"


class IdentityPortError(PortError):
    """IdentityPort adapter error (identity unresolvable, token invalid)."""

    code = "PORT_IDENTITY_ERROR"


class StoragePortError(PortError):
    """StoragePort adapter error (commit failed, write conflict)."""

    code = "PORT_STORAGE_ERROR"


class WorkflowPortError(PortError):
    """WorkflowPort adapter error (start/signal/state failed)."""

    code = "PORT_WORKFLOW_ERROR"


# ── Tenant isolation errors ───────────────────────────────────────────────────


class TenantError(QUAICUError):
    """Base for all tenant-boundary errors."""

    code = "TENANT_ERROR"


class TenantCrossContaminationError(TenantError):
    """Data from another tenant was observed — critical, halt everything, alert."""

    code = "TENANT_CROSS_CONTAMINATION"


class TenantNotFoundError(TenantError):
    """Requested tenant does not exist or is not provisioned/ACTIVE."""

    code = "TENANT_NOT_FOUND"


class TenantIsolationError(TenantError):
    """The token's tenant does not match the requested tenant. Reject (403)."""

    code = "TENANT_ISOLATION"


# ── Entitlement / tiering errors (ADR-0009) ────────────────────────────────────


class EntitlementError(QUAICUError):
    """Base for all plan/tier entitlement errors."""

    code = "ENTITLEMENT_ERROR"


class PlanNotFoundError(EntitlementError):
    """No CustomerPlan is provisioned for the tenant. Fail-closed (treat as no entitlements)."""

    code = "PLAN_NOT_FOUND"


class FeatureNotEntitledError(EntitlementError):
    """The tenant's tier does not permit this feature, adapter, or governance profile. Reject (403)."""

    code = "FEATURE_NOT_ENTITLED"


class QuotaExceededError(EntitlementError):
    """The tenant has exceeded a plan quota (e.g. max policies, action rate). Reject (429)."""

    code = "QUOTA_EXCEEDED"


class EntitlementPersistenceError(EntitlementError):
    """A durable entitlement-store operation (load/save/set) failed.

    Raised by an EntitlementRepository adapter so a persistence fault on the plan write path (e.g. a
    billing-driven tier flip) surfaces rather than silently leaving the durable plan store
    inconsistent. Mirrors `PolicyPersistenceError` / `LedgerPersistenceError`.
    """

    code = "ENTITLEMENT_PERSISTENCE_ERROR"


# ── License errors (ADR-0009 — Enterprise dedicated deployments) ───────────────


class LicenseError(QUAICUError):
    """Base for offline Enterprise license validation errors."""

    code = "LICENSE_ERROR"


class LicenseInvalidError(LicenseError):
    """The license token is missing, malformed, expired, or its signature does not verify.

    An ENTERPRISE-config kernel MUST refuse to boot when this is raised (fail-closed)."""

    code = "LICENSE_INVALID"


# ── Account / provisioning errors (ADR-0010) ───────────────────────────────────


class AccountError(QUAICUError):
    """Base for tenant-account / provisioning errors."""

    code = "ACCOUNT_ERROR"


class AccountExistsError(AccountError):
    """Signup attempted with an email that already owns an account. Reject (409)."""

    code = "ACCOUNT_EXISTS"


class AccountNotFoundError(AccountError):
    """Requested account does not exist."""

    code = "ACCOUNT_NOT_FOUND"


class ApiKeyInvalidError(AccountError):
    """An API key is missing, malformed, unknown, or revoked. Reject (401)."""

    code = "API_KEY_INVALID"


# ── Billing errors (WS-C — Stripe / Razorpay → tier flips) ─────────────────────


class BillingError(QUAICUError):
    """Base for billing/webhook errors."""

    code = "BILLING_ERROR"


class WebhookVerificationError(BillingError):
    """A billing webhook's signature is missing, malformed, stale, or does not verify.

    Fail-closed: an unverifiable webhook MUST NOT mutate a tenant's plan. Reject (400)."""

    code = "WEBHOOK_VERIFICATION_FAILED"


class BillingEventError(BillingError):
    """A verified webhook could not be mapped to a plan change (unknown plan id, missing tenant).

    Reject (422); the signature was valid but the payload is not actionable."""

    code = "BILLING_EVENT_UNMAPPABLE"


class CheckoutError(BillingError):
    """Could not create a provider checkout/subscription (outbound payment initiation).

    Covers a misconfigured adapter (no API key / unmapped tier) and a provider that rejected the
    request. Distinct from the inbound webhook errors above — this is the kernel calling *out*."""

    code = "CHECKOUT_FAILED"


# ── Erasure / crypto-shredding errors (WS-G — GDPR right to erasure) ────────────


class ErasureError(QUAICUError):
    """Base for crypto-shredding / right-to-erasure errors."""

    code = "ERASURE_ERROR"


class SubjectErasedError(ErasureError):
    """The data subject's key was crypto-shredded; the ciphertext is permanently irrecoverable.

    Raised on any attempt to decrypt PII for an erased subject. This is the *intended* terminal
    state of a GDPR erasure — not a fault. Surfaced as 410 Gone."""

    code = "SUBJECT_ERASED"


class CipherTokenError(ErasureError):
    """A PII cipher token is malformed or its key is unknown. Fail-closed."""

    code = "CIPHER_TOKEN_INVALID"
