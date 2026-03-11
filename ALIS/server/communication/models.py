"""E10 — Communication Hub Models"""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NotifChannel(str, Enum):
    EMAIL  = "EMAIL"
    SMS    = "SMS"
    IN_APP = "IN_APP"
    ALL    = "ALL"


class TargetAudience(str, Enum):
    ALL     = "ALL"
    STUDENTS = "STUDENTS"
    STAFF   = "STAFF"
    FACULTY = "FACULTY"
    PARENTS = "PARENTS"


class Priority(str, Enum):
    LOW    = "LOW"
    NORMAL = "NORMAL"
    HIGH   = "HIGH"
    URGENT = "URGENT"


# --- Request models ---

class TemplateCreate(BaseModel):
    key:     str = Field(..., pattern=r'^[a-z0-9_]+$')
    name:    str
    subject: Optional[str] = None
    body:    str
    channel: NotifChannel = NotifChannel.EMAIL


class TemplateUpdate(BaseModel):
    name:    Optional[str] = None
    subject: Optional[str] = None
    body:    Optional[str] = None
    is_active: Optional[bool] = None


class AnnouncementCreate(BaseModel):
    title:           str
    body:            str
    target_audience: TargetAudience = TargetAudience.ALL
    priority:        Priority = Priority.NORMAL
    expires_at:      Optional[str] = None  # ISO 8601


class BulkMessageCreate(BaseModel):
    title:         str
    message:       str
    channel:       NotifChannel = NotifChannel.EMAIL
    target_filter: Dict[str, Any] = Field(default_factory=dict)
    # target_filter examples:
    #   {"role": "STUDENT"}
    #   {"role": "STUDENT", "program_id": "uuid"}
    #   {"academic_year": "2025-26", "semester": 3}
