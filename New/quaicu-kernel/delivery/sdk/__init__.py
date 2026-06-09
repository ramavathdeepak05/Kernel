"""QUAICU Kernel Python SDK.

Primary exports:
  - ``Kernel`` — holds all port adapters; the entry point for SDK users.
  - ``governed`` — decorator factory exposed on a ``Kernel`` instance.

Usage::

    from delivery.sdk import Kernel

    kernel = Kernel.from_config("kernel.toml")

    @kernel.governed(policy="ciro.ifrs9.stage_transition")
    async def reclassify_loan(loan_id: str, from_stage: int, to_stage: int, *, actor):
        await ledger_db.update_stage(loan_id, to_stage)
"""

from delivery.sdk.kernel import Kernel

__all__ = ["Kernel"]
