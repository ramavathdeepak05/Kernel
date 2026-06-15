"""Entitlement persistence adapters (ADR-0009 / WS-C).

`PostgresEntitlementRepository` is the durable backend for `core.entitlements.EntitlementStore`, so
customer plans (and billing-driven tier flips) survive a restart.
"""

from adapters.entitlements.postgres import PostgresEntitlementRepository

__all__ = ["PostgresEntitlementRepository"]
