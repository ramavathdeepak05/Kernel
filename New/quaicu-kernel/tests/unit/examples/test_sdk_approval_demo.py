"""D2-3 DoD: the SDK approval example must run green (allow/deny/approve/self-approval-block)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_DEMO = Path(__file__).resolve().parents[3] / "examples" / "sdk-approval-demo" / "demo.py"


def _load_demo():
    spec = importlib.util.spec_from_file_location("sdk_approval_demo", _DEMO)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def test_sdk_approval_demo_runs_to_completion():
    demo = _load_demo()
    assert await demo.main() == 0
