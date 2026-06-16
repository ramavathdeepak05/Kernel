"""QUAICU Kernel — uvicorn application entrypoint.

Loads a ``Kernel`` from the TOML config file specified by the ``KERNEL_CONFIG``
environment variable (default: ``kernel.toml`` in the current working directory),
then builds the FastAPI app with ``create_app(kernel)``.

Usage::

    # development
    uvicorn delivery.entrypoint:app --reload --port 7000

    # production (Docker CMD)
    uvicorn delivery.entrypoint:app --host 0.0.0.0 --port 7000 --workers 1

The ``main()`` function is the CLI entry point registered as ``quaicu-kernel``
in ``[project.scripts]``.
"""

from __future__ import annotations

import os
import tomllib

from delivery.api.app import create_app
from delivery.sdk.billing_config import build_billing
from delivery.sdk.entitlements_config import build_entitlement_store
from delivery.sdk.kernel import Kernel
from delivery.sdk.metering_config import build_usage_meter

_config_path = os.getenv("KERNEL_CONFIG", "kernel.toml")
kernel = Kernel.from_config(_config_path)

# Enable billing (Stripe/Razorpay → tier flips + self-serve checkout) only when the config declares a
# [billing] section. The shared EntitlementStore is what a verified webhook mutates and what the
# entitlements/rate-limit edge reads — one source of truth for plans. Absent [billing], the kernel
# serves exactly as before (billing routes 503; no entitlement_store ⇒ entitlements report unlimited).
with open(_config_path, "rb") as _f:
    _config = tomllib.load(_f)

# Per-tenant, per-UTC-day usage counter — activates daily-quota enforcement (max_actions_per_day) and
# the admin usage snapshot whenever an entitlement source resolves a plan. Shared Redis meter when
# [metering].redis_url / REDIS_URL is set (exact cross-replica counts), else in-process.
_meter = build_usage_meter(_config)

if "billing" in _config:
    # Durable when [entitlements]/[storage] supplies a DSN, else in-memory. The store is hydrated
    # from its repository in create_app's lifespan, so a billing-driven tier flip survives a restart.
    _entitlements = build_entitlement_store(_config)
    _billing_adapters, _billing_engine = build_billing(_config, _entitlements)
    app = create_app(
        kernel,
        entitlement_store=_entitlements,
        usage_meter=_meter,
        billing_adapters=_billing_adapters,
        billing_engine=_billing_engine,
    )
else:
    app = create_app(kernel, usage_meter=_meter)


def main() -> None:
    """CLI entry point: ``quaicu-kernel`` command."""
    import uvicorn

    host = os.getenv("KERNEL_HOST", "0.0.0.0")
    port = int(os.getenv("KERNEL_PORT", "7000"))
    uvicorn.run("delivery.entrypoint:app", host=host, port=port, workers=1)
