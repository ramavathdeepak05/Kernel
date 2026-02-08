"""
ALIS Core Schema - Pydantic Models for API I/O

This module contains Pydantic models for request/response validation.
Separate from core models to maintain clean separation.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from .models import ActorType, UserStatus, OrganizationStatus, TaskStatus, TaskPriority


# --- Task Schemas (E02-S08) ---

class TaskCreate(BaseModel):
    """Schema for creating a new task."""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    
    # Assignment (One is required)
    assignee_id: Optional[str] = None
    assignee_role: Optional[str] = None
    
    due_date: Optional[datetime] = None
    
    # Context
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None


class TaskUpdate(BaseModel):
    """Schema for updating a task."""
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[TaskPriority] = None
    due_date: Optional[datetime] = None
    status: Optional[TaskStatus] = None


class TaskRead(BaseModel):
    """Schema for reading a task."""
    id: str
    title: str
    description: Optional[str]
    priority: TaskPriority
    status: TaskStatus
    assignee_id: Optional[str]
    assignee_role: Optional[str]
    due_date: Optional[datetime]
    completed_at: Optional[datetime]
    entity_type: Optional[str]
    entity_id: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]


# --- User Schemas ---

class UserCreate(BaseModel):
    """Schema for creating a new user."""
    username: str = Field(..., min_length=3, max_length=64)
    email: Optional[str] = None
    display_name: Optional[str] = None
    actor_type: ActorType = ActorType.HUMAN
    org_id: Optional[str] = None


class UserRead(BaseModel):
    """Schema for reading user data."""
    id: str
    username: str
    email: Optional[str]
    display_name: Optional[str]
    actor_type: ActorType
    status: UserStatus
    org_id: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]


class UserUpdate(BaseModel):
    """Schema for updating user data (partial)."""
    email: Optional[str] = None
    display_name: Optional[str] = None
    status: Optional[UserStatus] = None


# --- Organization Schemas ---

class OrganizationCreate(BaseModel):
    """Schema for creating a new organization."""
    name: str = Field(..., min_length=2, max_length=256)
    code: str = Field(..., min_length=2, max_length=32)
    parent_id: Optional[str] = None


class OrganizationRead(BaseModel):
    """Schema for reading organization data."""
    id: str
    name: str
    code: str
    parent_id: Optional[str]
    status: OrganizationStatus
    created_at: datetime
    updated_at: Optional[datetime]
