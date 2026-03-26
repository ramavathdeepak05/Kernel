"""E14 — Regulatory & Accreditation Module

Pure event consumer — no mutations to source module data.
Aggregates regulatory_metrics from all domain events.

Supported frameworks:
  NAAC | NIRF | AISHE | UGC | NBA | INTERNAL

Reference: ALIS-skills/references/architecture.md §5, §15, §20
"""
from __future__ import annotations
