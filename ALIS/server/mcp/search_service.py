"""
ALIS Search Service - E02-S06: Global Search & Indexing

MODULE: Shared Services (E02)
LAYER: Service / Infrastructure
ENTITY: SearchIndex

This module implements the Global Search capability using PostgreSQL Full-Text Search.
It acts as the single entry point for all search operations across ALIS.

Must Align With:
- "Permission-aware search results" (Acceptance Criteria)
- "No raw DB search from modules" (Dependency Rule)
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel
from server.core.audit import AuditAction, AuditLedger
from server.core.rbac import Role
from server.db_service import execute_query, execute_transaction

# --- Models ---


class SearchEntityType(str, Enum):
    """Supported entity types for indexing."""

    USER = "user"
    COURSE = "course"
    DOCUMENT = "document"
    WORKFLOW = "workflow"
    STUDENT = "student"


class SearchResult(BaseModel):
    """Standardized search result object."""

    entity_type: str
    entity_id: str
    snippet: str
    relevance: float
    metadata: dict[str, Any]


# --- Core Logic ---


def index_entity(
    entity_type: SearchEntityType,
    entity_id: str,
    content: str,
    metadata: dict[str, Any],
    roles_allowed: list[Role],
) -> None:
    """
    Index an entity for search.

    Args:
        entity_type: Type of entity (User, Course, etc.)
        entity_id: Unique ID of the entity
        content: Text content to index (will be converted to tsvector)
        metadata: Additional JSON metadata for result display/filtering
        roles_allowed: List of roles permitted to view this entity in search results
    """
    # Upsert logic: Delete existing entry for this entity first to ensure clean update
    delete_query = "DELETE FROM search_index WHERE entity_type = %s AND entity_id = %s"

    # Convert roles to strings for storage
    roles_str = [r.value for r in roles_allowed]

    insert_query = """
    INSERT INTO search_index (entity_type, entity_id, content, metadata, search_vector, roles_allowed)
    VALUES (%s, %s, %s, %s, to_tsvector('english', %s), %s)
    """

    execute_transaction(
        [
            (delete_query, (entity_type.value, entity_id)),
            (
                insert_query,
                (
                    entity_type.value,
                    entity_id,
                    content,
                    json.dumps(metadata),
                    content,
                    roles_str,
                ),
            ),
        ]
    )

    AuditLedger.log(
        action=AuditAction.UPDATE,
        actor_id="system",
        actor_role="system",
        entity_type="index_entity",
        entity_id=entity_id,
        tenant_id="",
        metadata={"source": "index_entity"},
    )


def search(
    query: str, actor_role: Role, limit: int = 20, offset: int = 0
) -> list[SearchResult]:
    """
    Execute a global search with RBAC enforcement.

    Args:
        query: Search query string
        actor_role: Role of the user performing the search
        limit: Max results to return
        offset: Pagination offset

    Returns:
        List of SearchResult objects
    """
    # SQL query enforcing RBAC at the database level using the @> array operator
    # 'roles_allowed' column contains the list of roles that can see the record.
    # The query checks if the actor's role is in that list.

    sql = """
    SELECT
        entity_type,
        entity_id,
        ts_headline('english', content, to_tsquery('english', %s)) as snippet,
        ts_rank(search_vector, to_tsquery('english', %s)) as relevance,
        metadata
    FROM search_index
    WHERE
        search_vector @@ to_tsquery('english', %s)
        AND %s = ANY(roles_allowed)
    ORDER BY relevance DESC
    LIMIT %s OFFSET %s
    """

    # Format query for tsquery (simple 'AND' behavior for spaces)
    formatted_query = " & ".join(query.split())

    rows = execute_query(
        sql,
        (
            formatted_query,
            formatted_query,
            formatted_query,
            actor_role.value,
            limit,
            offset,
        ),
    )

    results = []
    for row in rows:
        results.append(
            SearchResult(
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                snippet=row["snippet"],
                relevance=row["relevance"],
                metadata=row["metadata"]
                if isinstance(row["metadata"], dict)
                else json.loads(row["metadata"]),
            )
        )

    return results


def reindex_all():
    """
    Stub for a full re-indexing job.
    In a real implementation, this would iterate over all entity tables and call index_entity.
    """
    pass


def delete_index(entity_type: SearchEntityType, entity_id: str):
    """Remove an entity from the search index."""
    sql = "DELETE FROM search_index WHERE entity_type = %s AND entity_id = %s"
    execute_transaction([(sql, (entity_type.value, entity_id))])

    AuditLedger.log(
        action=AuditAction.DELETE,
        actor_id="system",
        actor_role="system",
        entity_type="index",
        entity_id=entity_id,
        tenant_id="",
        metadata={"source": "delete_index"},
    )
