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

from delivery.api.app import create_app
from delivery.sdk.kernel import Kernel

_config_path = os.getenv("KERNEL_CONFIG", "kernel.toml")
kernel = Kernel.from_config(_config_path)
app = create_app(kernel)


def main() -> None:
    """CLI entry point: ``quaicu-kernel`` command."""
    import uvicorn

    host = os.getenv("KERNEL_HOST", "0.0.0.0")
    port = int(os.getenv("KERNEL_PORT", "7000"))
    uvicorn.run("delivery.entrypoint:app", host=host, port=port, workers=1)
