"""E13 — Dynamic Process Engine Models

Step config schemas (stored in process_steps.config as JSONB):

  FORM:
    { "fields": [{ "name": str, "label": str, "type": "text|number|date|select|checkbox",
                   "options": [...], "required": bool, "validation": {...} }] }

  APPROVAL:
    { "reviewers": ["user_id", ...],   -- static reviewer list
      "reviewer_role": "REGISTRAR",    -- OR dynamic: pick by role
      "quorum": 1,                     -- number of approvals needed
      "timeout_hours": 48,
      "on_timeout": "ESCALATE|AUTO_APPROVE|AUTO_REJECT" }

  CONDITION:
    { "expression": "context.cgpa >= 7.0",   -- Python-safe eval against context dict
      "pass_label": "Eligible",
      "fail_label": "Not Eligible" }

  NOTIFICATION:
    { "template_key": "admission_confirmed",
      "recipient_field": "context.student_email",  -- dot-path into context
      "channel": "EMAIL|SMS|IN_APP" }

  AI_EVALUATION:
    { "prompt_template": "Evaluate this application: ${context}",
      "output_field": "ai_score",         -- write result into context under this key
      "expected_schema": { ... }          -- JSON schema for AI response
      "pass_condition": "context.ai_score >= 0.7" }

  AUTO_ACTION:
    { "action": "update_application_status",  -- registered action name
      "params": { "status": "APPROVED" }       -- static params merged with context
    }
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StepType(str, Enum):
    FORM = "FORM"
    APPROVAL = "APPROVAL"
    CONDITION = "CONDITION"
    NOTIFICATION = "NOTIFICATION"
    AI_EVALUATION = "AI_EVALUATION"
    AUTO_ACTION = "AUTO_ACTION"


class ProcessStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


# --- Request models ---


class StepCreate(BaseModel):
    name: str
    step_type: StepType
    config: dict[str, Any] = Field(default_factory=dict)
    on_pass_step: int | None = None
    on_fail_step: int | None = None
    is_required: bool = True


class ProcessDefinitionCreate(BaseModel):
    name: str
    description: str | None = None
    trigger_event: str | None = None
    trigger_filter: dict[str, Any] = Field(default_factory=dict)
    context_schema: dict[str, Any] = Field(default_factory=dict)
    steps: list[StepCreate] = Field(default_factory=list)


class ProcessDefinitionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    trigger_event: str | None = None
    trigger_filter: dict[str, Any] | None = None
    is_active: bool | None = None


class ProcessLaunchRequest(BaseModel):
    process_id: str
    entity_type: str | None = None
    entity_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class FormSubmission(BaseModel):
    form_data: dict[str, Any]


class FormField(BaseModel):
    name: str
    label: str
    type: str = "text"  # text | number | date | select | checkbox | textarea
    options: list[str] = Field(default_factory=list)
    required: bool = True
    validation: dict[str, Any] = Field(default_factory=dict)
    default: Any = None
    help_text: str | None = None
