"""
Counsellor Management Service — P0-S10

Manages counsellor accounts (users with role=COUNSELLOR) and triggers
the PGVector embedding ETL whenever a counsellor profile is created or updated.

The embedding powers E04-S05 auto-assignment (vector similarity search).
Full HR management of counsellors moves to E08 in a later phase.
"""

from __future__ import annotations

import logging
import uuid

from server.core.audit import AuditAction, AuditLog
from server.core.exceptions import NotFoundError
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)


def _build_profile_text(
    name: str, specializations: list[str], bio: str, programs: list[str]
) -> str:
    """
    Combine counsellor fields into a single string for embedding.
    Keep it human-readable — the model was trained on natural language.
    """
    parts = [f"Counsellor: {name}."]
    if specializations:
        parts.append(f"Specializations: {', '.join(specializations)}.")
    if programs:
        parts.append(f"Programs: {', '.join(programs)}.")
    if bio:
        parts.append(f"Bio: {bio}")
    return " ".join(parts)


class CounsellorService:
    """CRUD for counsellor profiles + embedding ETL trigger."""

    @classmethod
    def create(
        cls,
        org_id: str,
        name: str,
        email: str,
        specializations: list[str],
        programs: list[str],
        bio: str = "",
        phone: str | None = None,
        actor_id: str = "system",
    ) -> dict:
        """
        Create a counsellor user account and queue the embedding ETL.

        Returns the created user row as a dict.
        """
        counsellor_id = str(uuid.uuid4())
        metadata = {
            "specializations": specializations,
            "programs": programs,
            "bio": bio,
        }

        import json

        execute_transaction(
            [
                (
                    """
                INSERT INTO users
                    (id, org_id, email, phone, name, role, status, metadata)
                VALUES (%s, %s, %s, %s, %s, 'COUNSELLOR', 'ACTIVE', %s)
                """,
                    (counsellor_id, org_id, email, phone, name, json.dumps(metadata)),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="counsellor",
            entity_id=counsellor_id,
            org_id=org_id,
            module="P0-S10",
            metadata={"name": name, "email": email, "specializations": specializations},
        )

        # Trigger embedding ETL asynchronously
        cls._queue_embedding(
            org_id, counsellor_id, name, specializations, bio, programs
        )

        return {
            "id": counsellor_id,
            "org_id": org_id,
            "name": name,
            "email": email,
            "role": "COUNSELLOR",
            "status": "ACTIVE",
            "metadata": metadata,
        }

    @classmethod
    def update_profile(
        cls,
        org_id: str,
        counsellor_id: str,
        specializations: list[str] | None = None,
        programs: list[str] | None = None,
        bio: str | None = None,
        actor_id: str = "system",
    ) -> dict:
        """
        Update a counsellor's metadata and re-index their embedding.
        """
        rows = execute_query(
            "SELECT name, metadata FROM users WHERE id = %s AND org_id = %s AND role = 'COUNSELLOR'",
            (counsellor_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Counsellor {counsellor_id} not found in org {org_id}")

        row = rows[0]
        current_meta = row.get("metadata") or {}
        updated_meta = {
            "specializations": specializations
            if specializations is not None
            else current_meta.get("specializations", []),
            "programs": programs
            if programs is not None
            else current_meta.get("programs", []),
            "bio": bio if bio is not None else current_meta.get("bio", ""),
        }

        import json

        execute_transaction(
            [
                (
                    "UPDATE users SET metadata = %s, updated_at = NOW() WHERE id = %s AND org_id = %s",
                    (json.dumps(updated_meta), counsellor_id, org_id),
                )
            ]
        )

        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=actor_id,
            actor_type="human",
            entity_type="counsellor",
            entity_id=counsellor_id,
            org_id=org_id,
            module="P0-S10",
            metadata={"updated_fields": list(updated_meta.keys())},
        )

        cls._queue_embedding(
            org_id,
            counsellor_id,
            row["name"],
            updated_meta["specializations"],
            updated_meta["bio"],
            updated_meta["programs"],
        )

        return {"id": counsellor_id, "metadata": updated_meta}

    @classmethod
    def list_counsellors(cls, org_id: str) -> list[dict]:
        """List all active counsellors for an org."""
        return execute_query(
            """
            SELECT id, name, email, phone, status, metadata, created_at
            FROM users
            WHERE org_id = %s AND role = 'COUNSELLOR' AND status = 'ACTIVE'
            ORDER BY name
            """,
            (org_id,),
        )

    @classmethod
    def get(cls, org_id: str, counsellor_id: str) -> dict:
        rows = execute_query(
            "SELECT id, name, email, phone, status, metadata, created_at FROM users WHERE id = %s AND org_id = %s AND role = 'COUNSELLOR'",
            (counsellor_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Counsellor {counsellor_id} not found")
        return rows[0]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @classmethod
    def _queue_embedding(
        cls,
        org_id: str,
        counsellor_id: str,
        name: str,
        specializations: list[str],
        bio: str,
        programs: list[str],
    ) -> None:
        profile_text = _build_profile_text(name, specializations, bio, programs)
        try:
            from server.tasks.ai_tasks import upsert_counsellor_embedding

            upsert_counsellor_embedding.delay(org_id, counsellor_id, profile_text)
            logger.info("P0-S10: Queued embedding ETL for counsellor %s", counsellor_id)
        except Exception as exc:
            # Non-fatal — vector search will fall back to load-balanced assignment
            logger.warning("P0-S10: Could not queue embedding ETL: %s", exc)
