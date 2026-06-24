"""Managed PII-masking adapters implementing `core.ports.masking.MaskingPort` (W6-3)."""

from __future__ import annotations

from adapters.masking.gcp_dlp import CloudDLPMaskingAdapter, MaskingDependencyError

__all__ = ["CloudDLPMaskingAdapter", "MaskingDependencyError"]
