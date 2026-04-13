"""
Re-export shim — PolicyStore has been promoted to server.core.policy_store
so all modules (academics, examinations, hr, etc.) can import it without
creating cross-module dependency violations (§12.4 R05).

This shim preserves backward compatibility for existing admissions-internal
imports (admissions_router, tasks, etc.).
"""

from __future__ import annotations

from server.core.policy_store import PolicyKey, PolicyStore  # noqa: F401

__all__ = ["PolicyKey", "PolicyStore"]
