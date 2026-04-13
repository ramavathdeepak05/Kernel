"""Multi-campus / Group Entity Model (§30)

Campus provisioning for group institutions.
Each campus = own RLS tenant (org_id).
Group admin can view aggregate reports across campuses.
Feature flag: platform.multi_campus_enabled
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any
from uuid import uuid4

from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

event_bus = DomainEventBus()


class EntityType(str, Enum):
    """Organisation structural classification."""

    STANDALONE = "STANDALONE"
    CAMPUS = "CAMPUS"
    GROUP = "GROUP"


class CampusService:
    """Provisioning and management of multi-campus group institutions.

    Each campus receives its own org_id for full RLS tenant isolation.
    A GROUP organisation acts as the administrative umbrella; it has no
    direct students — only CAMPUS children do.

    Feature flag ``platform.multi_campus_enabled`` must be 'true' on the
    group org before any campus operations are permitted.
    """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check_multi_campus_enabled(self, org_id: str) -> None:
        """Raise BusinessRuleViolation if the multi-campus flag is off."""
        rows = execute_query(
            """
            SELECT flag_value
            FROM tenant_feature_flags
            WHERE org_id = %s AND flag_key = 'platform.multi_campus_enabled'
            """,
            (org_id,),
        )
        flag_value = rows[0]["flag_value"] if rows else None
        if flag_value != "true":
            raise BusinessRuleViolation("Multi-campus feature is not enabled")

    def _get_entity_type(self, org_id: str) -> str | None:
        rows = execute_query(
            "SELECT entity_type FROM organizations WHERE id = %s",
            (org_id,),
        )
        return rows[0]["entity_type"] if rows else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def provision_campus(
        self,
        group_org_id: str,
        campus_code: str,
        campus_name: str,
        city: str,
        state: str,
        address: str | None = None,
        pincode: str | None = None,
        phone: str | None = None,
        principal_user_id: str | None = None,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Provision a new campus under a GROUP organisation.

        Creates a fresh CAMPUS org (own org_id / RLS tenant) and a
        corresponding campus_entities row.  Fires campus.provisioned event.

        Args:
            group_org_id: The GROUP org this campus belongs to.
            campus_code: Short identifier, e.g. "DELHI-01".
            campus_name: Human-readable name shown in the UI.
            city: City of the campus.
            state: State / province of the campus.
            address: Optional street address.
            pincode: Optional postal code.
            phone: Optional contact number.
            principal_user_id: Optional user appointed as campus principal.
            actor_id: User ID of the GROUP admin performing the action.

        Returns:
            ``{campus_org_id, campus_code, campus_name, group_org_id}``

        Raises:
            BusinessRuleViolation: Feature flag off, or parent not GROUP.
        """
        self._check_multi_campus_enabled(group_org_id)

        entity_type = self._get_entity_type(group_org_id)
        if entity_type != EntityType.GROUP:
            raise BusinessRuleViolation(
                "Parent organization must have entity_type=GROUP"
            )

        campus_org_id = str(uuid4())
        campus_entity_id = str(uuid4())

        execute_transaction(
            [
                # New isolated tenant org for the campus
                (
                    """
                    INSERT INTO organizations
                        (id, name, type, status, entity_type, parent_org_id, created_at)
                    VALUES (%s, %s, 'UNIVERSITY', 'ACTIVE', 'CAMPUS', %s, NOW())
                    """,
                    (campus_org_id, campus_name, group_org_id),
                ),
                # Campus metadata row
                (
                    """
                    INSERT INTO campus_entities
                        (id, org_id, campus_code, campus_name, address, city,
                         state, pincode, phone, principal_user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        campus_entity_id,
                        campus_org_id,
                        campus_code,
                        campus_name,
                        address,
                        city,
                        state,
                        pincode,
                        phone,
                        principal_user_id,
                    ),
                ),
            ]
        )

        event = DomainEvent(
            event_type="campus.provisioned",
            org_id=group_org_id,
            payload={
                "campus_org_id": campus_org_id,
                "campus_code": campus_code,
                "group_org_id": group_org_id,
            },
        )
        await event_bus.publish(event)

        return {
            "campus_org_id": campus_org_id,
            "campus_code": campus_code,
            "campus_name": campus_name,
            "group_org_id": group_org_id,
        }

    def assign_user_to_campus(
        self,
        user_id: str,
        campus_org_id: str,
        role_scope: str,
        assigned_by: str,
    ) -> dict[str, Any]:
        """Assign a user to a campus with a scoped role.

        Uses INSERT … ON CONFLICT DO UPDATE so the call is idempotent — a
        repeated assignment simply updates role_scope and assigned_by.

        Args:
            user_id: UUID of the user to assign.
            campus_org_id: Org ID of the target CAMPUS.
            role_scope: Role label scoped to this campus, e.g. "REGISTRAR".
            assigned_by: User ID of the GROUP admin performing the assignment.

        Returns:
            Assignment record as a plain dict.
        """
        assignment_id = str(uuid4())

        execute_transaction(
            [
                (
                    """
                    INSERT INTO campus_user_assignments
                        (id, user_id, campus_org_id, role_scope, assigned_by, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (user_id, campus_org_id)
                    DO UPDATE SET
                        role_scope  = EXCLUDED.role_scope,
                        assigned_by = EXCLUDED.assigned_by,
                        updated_at  = NOW()
                    """,
                    (assignment_id, user_id, campus_org_id, role_scope, assigned_by),
                )
            ]
        )

        return {
            "assignment_id": assignment_id,
            "user_id": user_id,
            "campus_org_id": campus_org_id,
            "role_scope": role_scope,
            "assigned_by": assigned_by,
        }

    async def get_group_summary(
        self, group_org_id: str, actor_id: str
    ) -> dict[str, Any]:
        """Return aggregate metrics for all campuses under a GROUP.

        Fetches per-campus student and faculty counts in a single loop.
        The feature flag is checked on entry so unauthorised GROUP orgs cannot
        access cross-tenant data.

        Args:
            group_org_id: The GROUP org to summarise.
            actor_id: Requesting user's ID (for audit).

        Returns:
            ``{group_org_id, campus_count, campuses: [...]}``, where each
            campus entry includes ``student_count`` and ``faculty_count``.
        """
        self._check_multi_campus_enabled(group_org_id)

        campuses = execute_query(
            """
            SELECT o.id, o.name, ce.campus_code, ce.city, ce.is_active
            FROM organizations o
            JOIN campus_entities ce ON ce.org_id = o.id
            WHERE o.parent_org_id = %s AND o.entity_type = 'CAMPUS'
            ORDER BY ce.campus_code
            """,
            (group_org_id,),
        )

        enriched: list[dict[str, Any]] = []
        for campus in campuses:
            campus_org_id = campus["id"]

            student_rows = execute_query(
                "SELECT COUNT(*) AS cnt FROM students WHERE org_id = %s",
                (campus_org_id,),
            )
            faculty_rows = execute_query(
                """
                SELECT COUNT(*) AS cnt
                FROM users
                WHERE org_id = %s AND role IN ('FACULTY', 'PROFESSOR')
                """,
                (campus_org_id,),
            )

            enriched.append(
                {
                    "campus_org_id": campus_org_id,
                    "name": campus["name"],
                    "campus_code": campus["campus_code"],
                    "city": campus["city"],
                    "is_active": campus.get("is_active", True),
                    "student_count": int(student_rows[0]["cnt"] if student_rows else 0),
                    "faculty_count": int(faculty_rows[0]["cnt"] if faculty_rows else 0),
                }
            )

        return {
            "group_org_id": group_org_id,
            "campus_count": len(enriched),
            "campuses": enriched,
        }

    def promote_to_group(self, org_id: str, actor_id: str) -> dict[str, Any]:
        """Promote a STANDALONE organisation to GROUP status.

        Once promoted the org can provision CAMPUS children via
        provision_campus().  The operation is irreversible — GROUP orgs
        cannot be demoted back to STANDALONE.

        Args:
            org_id: The STANDALONE org to promote.
            actor_id: SUPER_ADMIN user performing the action.

        Returns:
            Updated organisation record.

        Raises:
            BusinessRuleViolation: Org is not STANDALONE (already GROUP or
                CAMPUS).
        """
        entity_type = self._get_entity_type(org_id)
        if entity_type != EntityType.STANDALONE:
            raise BusinessRuleViolation(
                f"Organization must be STANDALONE to promote to GROUP "
                f"(current entity_type: {entity_type})"
            )

        execute_transaction(
            [
                (
                    """
                    UPDATE organizations
                    SET entity_type = 'GROUP', updated_at = NOW()
                    WHERE id = %s AND entity_type = 'STANDALONE'
                    """,
                    (org_id,),
                )
            ]
        )

        rows = execute_query(
            "SELECT id, name, type, status, entity_type FROM organizations WHERE id = %s",
            (org_id,),
        )
        return rows[0] if rows else {"id": org_id, "entity_type": "GROUP"}

    def list_campuses(self, group_org_id: str) -> list[dict[str, Any]]:
        """Return all CAMPUS orgs under the given GROUP.

        Args:
            group_org_id: The GROUP org whose campuses to list.

        Returns:
            List of campus records including campus_entities metadata.
        """
        return execute_query(
            """
            SELECT o.id AS campus_org_id, o.name, o.status,
                   ce.campus_code, ce.campus_name, ce.city, ce.state,
                   ce.phone, ce.is_active, ce.principal_user_id
            FROM organizations o
            JOIN campus_entities ce ON ce.org_id = o.id
            WHERE o.parent_org_id = %s AND o.entity_type = 'CAMPUS'
            ORDER BY ce.campus_code
            """,
            (group_org_id,),
        )


# Module-level singleton.
campus_service = CampusService()
