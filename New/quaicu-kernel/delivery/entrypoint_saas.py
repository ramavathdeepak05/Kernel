"""QUAICU Kernel — shared SaaS-plane uvicorn entrypoint (ADR-0009).

Builds a `TieredKernelProvider` that routes each request to the kernel its tenant's commercial tier is
served by, from a plane-descriptor TOML pointed to by ``KERNEL_CONFIG_SAAS`` (default:
``kernel.saas.toml`` in the cwd). The single-kernel/dedicated entrypoint is ``delivery/entrypoint.py``.

Usage::

    # development
    KERNEL_CONFIG_SAAS=kernel.saas.toml uvicorn delivery.entrypoint_saas:app --reload --port 7000

    # production (Docker / CLI)
    quaicu-kernel-saas

The app build lives in ``delivery/sdk/saas_app.build_saas_app`` (pure / testable); this module only
loads the config and exposes ``app`` + the ``quaicu-kernel-saas`` CLI entry point.
"""

from __future__ import annotations

import os
import tomllib

from delivery.sdk.saas_app import build_saas_app

_config_path = os.getenv("KERNEL_CONFIG_SAAS", "kernel.saas.toml")
with open(_config_path, "rb") as _f:
    _config = tomllib.load(_f)

app = build_saas_app(_config)


def main() -> None:
    """CLI entry point: ``quaicu-kernel-saas`` command."""
    import uvicorn

    host = os.getenv("KERNEL_HOST", "0.0.0.0")
    port = int(os.getenv("KERNEL_PORT", "7000"))
    # KERNEL_WORKERS mirrors the Docker CMD: the shared plane is all-durable (D0-5/D4-1), so
    # horizontal workers are safe; the in-memory dev profile should keep the default of 1.
    workers = int(os.getenv("KERNEL_WORKERS", "1"))
    uvicorn.run("delivery.entrypoint_saas:app", host=host, port=port, workers=workers)
