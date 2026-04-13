"""
ALIS Commenting & Activity Feed Service - E02-S07

MODULE: Shared Services (E02)
LAYER: Service / Infrastructure
ENTITY: ActivityFeed / Comment

This module implements the generic commenting and activity feed system.
 It supports:
- Append-only activity logging
- Threaded comments
- RBAC-based visibility filtering
- Soft-hiding of comments (moderation)
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from server.core.audit import AuditAction, AuditLedger
from server.core.rbac import Role
from server.db_service import execute_query, execute_transaction

# --- Models ---


class ActivityType(str, Enum):
    """Types of entries in the activity feed."""

    STATUS_CHANGE = "status_change"
    COMMENT = "comment"
    SYSTEM_EVENT = "system_event"
    ALERT = "alert"


class ActivityEntry(BaseModel):
    """Represents a single activity event."""

    id: int
    entity_type: str
    entity_id: str
    activity_type: ActivityType
    description: str
    metadata: dict[str, Any] = {}
    actor_id: str
    actor_role: str
    created_at: datetime


class Comment(BaseModel):
    """Represents a user comment."""

    id: int
    entity_type: str
    entity_id: str
    content: str
    parent_id: int | None = None
    actor_id: str
    actor_role: str
    is_hidden: bool = False
    created_at: datetime


class FeedItem(BaseModel):
    """Unified feed item (can be an activity or a comment)."""

    type: str = Field(..., description="'activity' or 'comment'")
    data: ActivityEntry | Comment
    sort_time: datetime


# --- Core Logic ---


def log_activity(
    entity_type: str,
    entity_id: str,
    activity_type: ActivityType,
    description: str,
    actor_id: str,
    actor_role: Role,
    visible_to_roles: list[Role],
    metadata: dict[str, Any] | None = None,
) -> int:
    """
    Log a system or user activity.

    Args:
        visible_to_roles: List of roles allowed to see this activity.
                          If empty, it might be visible to no one (or all, depending on policy).
                          ALIS Default: Explicit allow list required.
    """
    role_strs = [r.value for r in visible_to_roles]
    meta_json = json.dumps(metadata) if metadata else "{}"

    sql = """
    INSERT INTO activity_feed
    (entity_type, entity_id, activity_type, description, actor_id, actor_role, visible_to_roles, metadata)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    RETURNING id
    """

    rows = execute_transaction(
        [
            (
                sql,
                (
                    entity_type,
                    entity_id,
                    activity_type.value,
                    description,
                    actor_id,
                    actor_role.value,
                    role_strs,
                    meta_json,
                ),
            )
        ]
    )

    entry_id = rows[0]["id"] if rows else -1
    if entry_id != -1:
        AuditLedger.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_role=actor_role.value,
            entity_type="activity_feed",
            entity_id=str(entry_id),
            tenant_id="",
            metadata={"source": "log_activity"},
        )
    return entry_id


def add_comment(
    entity_type: str,
    entity_id: str,
    content: str,
    actor_id: str,
    actor_role: Role,
    visible_to_roles: list[Role],
    parent_id: int | None = None,
) -> int:
    """
    Add a comment to an entity.
    """
    role_strs = [r.value for r in visible_to_roles]

    sql = """
    INSERT INTO comments
    (entity_type, entity_id, content, parent_id, actor_id, actor_role, visible_to_roles)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    RETURNING id
    """

    rows = execute_transaction(
        [
            (
                sql,
                (
                    entity_type,
                    entity_id,
                    content,
                    parent_id,
                    actor_id,
                    actor_role.value,
                    role_strs,
                ),
            )
        ]
    )

    if rows:
        comment_id_val = rows[0]["id"]
        AuditLedger.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_role=actor_role.value,
            entity_type="comment",
            entity_id=str(comment_id_val),
            tenant_id="",
            metadata={"source": "add_comment"},
        )
        return comment_id_val
    return -1


def get_feed(
    entity_type: str,
    entity_id: str,
    viewer_role: Role,
    limit: int = 50,
    offset: int = 0,
) -> list[FeedItem]:
    """
    Retrieve the combined activity and comment feed for an entity,
    filtered by the viewer's role.
    """
    role_str = viewer_role.value

    # We use a UNION query to fetch both activities and comments, sorted by time.
    # We verify RBAC: viewer_role must be in visible_to_roles array.

    sql = """
    SELECT
        'activity' as type,
        id,
        entity_type,
        entity_id,
        activity_type as subtype, -- Maps to ActivityType
        description as content,
        metadata,
        actor_id,
        actor_role,
        created_at,
        NULL::int as parent_id,
        FALSE as is_hidden
    FROM activity_feed
    WHERE entity_type = %s
      AND entity_id = %s
      AND %s = ANY(visible_to_roles)

    UNION ALL

    SELECT
        'comment' as type,
        id,
        entity_type,
        entity_id,
        NULL as subtype,
        content,
        NULL as metadata,
        actor_id,
        actor_role,
        created_at,
        parent_id,
        is_hidden
    FROM comments
    WHERE entity_type = %s
      AND entity_id = %s
      AND %s = ANY(visible_to_roles)
      AND is_hidden = FALSE

    ORDER BY created_at DESC
    LIMIT %s OFFSET %s
    """

    rows = execute_query(
        sql,
        (
            entity_type,
            entity_id,
            role_str,
            entity_type,
            entity_id,
            role_str,
            limit,
            offset,
        ),
    )

    feed = []
    for row in rows:
        if row["type"] == "activity":
            entry = ActivityEntry(
                id=row["id"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                activity_type=ActivityType(row["subtype"]),
                description=row["content"],
                metadata=row["metadata"] if row["metadata"] else {},
                actor_id=row["actor_id"],
                actor_role=row["actor_role"],
                created_at=row["created_at"],
            )
            feed.append(
                FeedItem(type="activity", data=entry, sort_time=row["created_at"])
            )
        else:
            comment = Comment(
                id=row["id"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                content=row["content"],
                parent_id=row["parent_id"],
                actor_id=row["actor_id"],
                actor_role=row["actor_role"],
                is_hidden=row["is_hidden"],
                created_at=row["created_at"],
            )
            feed.append(
                FeedItem(type="comment", data=comment, sort_time=row["created_at"])
            )

    return feed


def hide_comment(comment_id: int, actor_role: Role) -> bool:
    """
    Soft-delete a comment.
    Only implicit verification here. In a real app, strict ownership/admin checks
    would happen in the Layer 5/RBAC middleware before calling this.
    """
    sql = "UPDATE comments SET is_hidden = TRUE WHERE id = %s"
    execute_transaction([(sql, (comment_id,))])

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id="system",
        actor_role="system",
        entity_type="hide_comment",
        entity_id="",
        tenant_id="",
        metadata={"source": "hide_comment"},
    )
    return True
