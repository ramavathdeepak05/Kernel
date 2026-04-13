"""E10 — Communication Hub Models"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NotifChannel(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"
    IN_APP = "IN_APP"
    ALL = "ALL"


class TargetAudience(str, Enum):
    ALL = "ALL"
    STUDENTS = "STUDENTS"
    STAFF = "STAFF"
    FACULTY = "FACULTY"
    PARENTS = "PARENTS"


class Priority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


# --- Request models ---


class TemplateCreate(BaseModel):
    key: str = Field(..., pattern=r"^[a-z0-9_]+$")
    name: str
    subject: str | None = None
    body: str
    channel: NotifChannel = NotifChannel.EMAIL


class TemplateUpdate(BaseModel):
    name: str | None = None
    subject: str | None = None
    body: str | None = None
    is_active: bool | None = None
    whatsapp_template_id: str | None = None  # MSG91 DLT registered template ID


class AnnouncementCreate(BaseModel):
    title: str
    body: str
    target_audience: TargetAudience = TargetAudience.ALL
    priority: Priority = Priority.NORMAL
    expires_at: str | None = None  # ISO 8601


class BulkMessageCreate(BaseModel):
    title: str
    message: str
    channel: NotifChannel = NotifChannel.EMAIL
    target_filter: dict[str, Any] = Field(default_factory=dict)
    # target_filter examples:
    #   {"role": "STUDENT"}
    #   {"role": "STUDENT", "program_id": "uuid"}
    #   {"academic_year": "2025-26", "semester": 3}
