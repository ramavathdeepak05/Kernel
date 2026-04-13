"""E11 — Reporting & Analytics Models"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ReportModule(str, Enum):
    ADMISSIONS = "admissions"
    ACADEMICS = "academics"
    EXAMINATIONS = "examinations"
    FINANCE = "finance"
    HR = "hr"
    SERVICES = "services"


class ExportFormat(str, Enum):
    CSV = "CSV"
    XLSX = "XLSX"
    PDF = "PDF"


class SavedReportCreate(BaseModel):
    name: str
    description: str | None = None
    module: ReportModule
    filters: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)


class ExportRequest(BaseModel):
    report_type: str  # "admissions" | "grades" | "fee_collection" | etc.
    format: ExportFormat = ExportFormat.CSV
    filters: dict[str, Any] = Field(default_factory=dict)
