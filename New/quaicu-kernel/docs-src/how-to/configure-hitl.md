# Configure HITL (Human-in-the-Loop)

!!! info "Coming soon"
    This guide is being written. It covers the `HITLPort` interface, the in-memory adapter (dev), the email/Slack adapters (production), and the fail-closed timeout guarantee (timeout → DENY, never auto-approve).

**Key invariant:** The HITL gate never auto-approves on timeout. A timed-out approval → `REJECTED`. This is non-negotiable and non-configurable.
