"""Enterprise license — public surface of `core/license` (ADR-0009)."""

from __future__ import annotations

from core.license.model import License
from core.license.validator import (
    load_public_key,
    sign_license,
    verify_license,
)

__all__ = [
    "License",
    "load_public_key",
    "sign_license",
    "verify_license",
]
