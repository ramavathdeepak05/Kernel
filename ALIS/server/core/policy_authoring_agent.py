"""PAA — Policy Authoring Agent (§10b)

LLM-assisted policy DSL drafting.
ALWAYS produces DRAFT status — human reviewer must APPROVE before activation.
Never directly modifies institution_policies — inserts a new row with status='DRAFT'.
SUPER_ADMIN only.
"""

from __future__ import annotations

import json as _json
import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx
from server.core.domain_events import DomainEvent, DomainEventBus
from server.core.exceptions import BusinessRuleViolation, NotFoundError
from server.core.llm_router import LLMTaskClass, get_model_for_task
from server.db_service import execute_query, execute_transaction

logger = logging.getLogger(__name__)

event_bus = DomainEventBus()


@dataclass
class PolicyDraftResult:
    """Result of a PAA draft operation.

    status is always 'DRAFT' at creation time — activation requires
    an explicit approve_draft() call by a SUPER_ADMIN reviewer.
    """

    draft_id: str
    policy_key: str
    policy_type: str  # INTEGER | DECIMAL | BOOLEAN | STRING | JSON
    current_value: str | None
    current_version: int | None
    proposed_value: str
    justification: str
    confidence: float  # LLM confidence 0.0–1.0
    status: str  # always "DRAFT" at creation
    created_by: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "policy_key": self.policy_key,
            "policy_type": self.policy_type,
            "current_value": self.current_value,
            "current_version": self.current_version,
            "proposed_value": self.proposed_value,
            "justification": self.justification,
            "confidence": self.confidence,
            "status": self.status,
            "created_by": self.created_by,
        }


class PolicyAuthoringAgent:
    """LLM-assisted policy authoring for ALIS institutions.

    All drafts are inserted with status='DRAFT'.  No approved policy row is
    ever mutated directly — a new versioned row is created and must pass
    through the approve_draft / reject_draft lifecycle before becoming active.

    QUAICU_ONLY policies (§4.4) cannot be drafted through this interface.
    They require QUAICU engineering intervention.
    """

    # Policies governed at the platform level — §4.4 of Engineering Build Guidelines
    _QUAICU_ONLY_PREFIXES: list[str] = [
        "audit_ledger_retention",
        "tenant_isolation",
        "dpdp_compliance_mode",
    ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_current_policy(
        self, org_id: str, policy_key: str
    ) -> dict[str, Any] | None:
        """Return the latest APPROVED policy row, or None if not set."""
        rows = execute_query(
            """
            SELECT id, policy_value, version, policy_type, description
            FROM institution_policies
            WHERE org_id = %s AND policy_key = %s AND status = 'APPROVED'
            ORDER BY version DESC
            LIMIT 1
            """,
            (org_id, policy_key),
        )
        return rows[0] if rows else None

    def _call_llm(
        self,
        policy_key: str,
        current_value: str | None,
        policy_type: str | None,
        plain_english_description: str,
    ) -> dict[str, Any]:
        """Call Ollama and parse the JSON draft response.

        Falls back to a safe empty draft if the LLM is unavailable or
        returns unparseable output — the caller must surface confidence=0.0
        to the reviewer.
        """
        model = get_model_for_task(LLMTaskClass.REASONING)

        prompt = (
            "You are an ALIS institution policy expert. Generate a policy value for the given key.\n"
            f"Policy key: {policy_key}\n"
            f"Current value: {current_value or 'not set'}\n"
            f"Policy type: {policy_type or 'unknown'}\n\n"
            f"Admin's request: {plain_english_description}\n\n"
            "Return JSON only:\n"
            '{"proposed_value": "...", "policy_type": "INTEGER|DECIMAL|BOOLEAN|STRING|JSON", '
            '"justification": "...", "confidence": 0.0}\n\n'
            "Rules:\n"
            "- INTEGER: whole number only\n"
            "- DECIMAL: number with decimals\n"
            '- BOOLEAN: "true" or "false" only\n'
            "- JSON: valid JSON array or object\n"
            "- STRING: plain text\n"
            "- proposed_value MUST be a string representation\n"
            "- confidence 0.0-1.0 based on how clear the request is"
        )

        try:
            from server.core.settings import settings as _settings

            resp = httpx.post(
                f"{_settings.ollama_base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=30,
            )
            raw = resp.json().get("response", "{}")
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            draft_json: dict[str, Any] = _json.loads(match.group()) if match else {}
        except Exception as exc:
            logger.warning("PAA LLM call failed: %s", exc)
            draft_json = {
                "proposed_value": "",
                "policy_type": "STRING",
                "justification": "LLM unavailable",
                "confidence": 0.0,
            }

        return draft_json

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def draft_policy(
        self,
        org_id: str,
        policy_key: str,
        plain_english_description: str,
        actor_id: str,
    ) -> dict[str, Any]:
        """Generate an LLM-assisted policy draft.

        Inserts a new institution_policies row with status='DRAFT'.
        The draft must be approved via approve_draft() before it becomes
        active.  Fires policy.ai_draft_created domain event.

        Args:
            org_id: Institution tenant identifier.
            policy_key: The dot-namespaced policy key to draft (e.g.
                ``admissions.max_seats``).
            plain_english_description: Free-text admin instruction.
            actor_id: User ID of the SUPER_ADMIN initiating the draft.

        Returns:
            PolicyDraftResult as a plain dict.
        """
        # §4.4 — QUAICU_ONLY guard: these policies cannot be changed through ALIS
        for prefix in self._QUAICU_ONLY_PREFIXES:
            if policy_key.startswith(prefix):
                raise BusinessRuleViolation(
                    f"Policy '{policy_key}' is governed at the platform level and cannot "
                    "be changed through ALIS. Please contact QUAICU support."
                )

        current = self._get_current_policy(org_id, policy_key)
        current_value: str | None = current["policy_value"] if current else None
        current_version: int | None = int(current["version"]) if current else None
        current_type: str | None = current["policy_type"] if current else None

        draft_json = self._call_llm(
            policy_key,
            current_value,
            current_type,
            plain_english_description,
        )

        proposed_value: str = str(draft_json.get("proposed_value", ""))
        policy_type: str = draft_json.get("policy_type") or current_type or "STRING"
        justification: str = draft_json.get("justification", "")
        confidence: float = float(draft_json.get("confidence", 0.0))

        new_version = (current_version or 0) + 1
        draft_id = str(uuid4())
        description = f"AI DRAFT: {plain_english_description[:200]}"

        execute_transaction(
            [
                (
                    """
                    INSERT INTO institution_policies
                        (id, org_id, policy_key, policy_value, policy_type,
                         description, version, status, created_by)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'DRAFT', %s)
                    """,
                    (
                        draft_id,
                        org_id,
                        policy_key,
                        proposed_value,
                        policy_type,
                        description,
                        new_version,
                        actor_id,
                    ),
                )
            ]
        )

        event = DomainEvent(
            event_type="policy.ai_draft_created",
            org_id=org_id,
            payload={
                "policy_key": policy_key,
                "draft_id": draft_id,
                "confidence": confidence,
            },
        )
        await event_bus.publish(event)

        result = PolicyDraftResult(
            draft_id=draft_id,
            policy_key=policy_key,
            policy_type=policy_type,
            current_value=current_value,
            current_version=current_version,
            proposed_value=proposed_value,
            justification=justification,
            confidence=confidence,
            status="DRAFT",
            created_by=actor_id,
        )
        return result.to_dict()

    def list_drafts(self, org_id: str) -> list[dict[str, Any]]:
        """Return all pending DRAFT policy rows for the given org."""
        return execute_query(
            """
            SELECT id AS draft_id, policy_key, policy_value, policy_type,
                   description, version, status, created_by, created_at
            FROM institution_policies
            WHERE org_id = %s AND status = 'DRAFT'
            ORDER BY created_at DESC
            """,
            (org_id,),
        )

    async def approve_draft(
        self,
        draft_id: str,
        org_id: str,
        actor_id: str,
        justification: str,
    ) -> dict[str, Any]:
        """Approve a DRAFT policy, making it the active version.

        Updates status to APPROVED and appends the reviewer's justification
        to the description.  Fires policy.draft_approved domain event.

        Args:
            draft_id: UUID of the draft row.
            org_id: Institution tenant identifier.
            actor_id: Reviewer user ID.
            justification: Human rationale for approval.

        Returns:
            Updated policy row as a plain dict.

        Raises:
            NotFoundError: Draft not found or not in DRAFT status.
        """
        rows = execute_query(
            """
            SELECT id, policy_key, policy_value, policy_type, description,
                   version, status, created_by
            FROM institution_policies
            WHERE id = %s AND org_id = %s
            """,
            (draft_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Policy draft {draft_id} not found")

        draft = rows[0]
        if draft["status"] != "DRAFT":
            raise BusinessRuleViolation(
                f"Policy {draft_id} is not in DRAFT status (current: {draft['status']})"
            )

        updated_description = (
            f"{draft['description']} | APPROVED by {actor_id}: {justification[:200]}"
        )

        execute_transaction(
            [
                (
                    """
                    UPDATE institution_policies
                    SET status = 'APPROVED',
                        description = %s,
                        updated_at = NOW()
                    WHERE id = %s AND org_id = %s
                    """,
                    (updated_description, draft_id, org_id),
                )
            ]
        )

        event = DomainEvent(
            event_type="policy.draft_approved",
            org_id=org_id,
            payload={
                "draft_id": draft_id,
                "policy_key": draft["policy_key"],
                "approved_by": actor_id,
            },
        )
        await event_bus.publish(event)

        return {
            "draft_id": draft_id,
            "policy_key": draft["policy_key"],
            "policy_value": draft["policy_value"],
            "policy_type": draft["policy_type"],
            "version": draft["version"],
            "status": "APPROVED",
            "approved_by": actor_id,
            "justification": justification,
        }

    async def reject_draft(
        self,
        draft_id: str,
        org_id: str,
        actor_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Reject and delete a DRAFT policy row.

        Removes the draft from institution_policies — rejected drafts do not
        stay in the table.  Fires policy.draft_rejected domain event.

        Args:
            draft_id: UUID of the draft row.
            org_id: Institution tenant identifier.
            actor_id: Reviewer user ID.
            reason: Human rationale for rejection (stored in event payload).

        Returns:
            ``{"draft_id": ..., "status": "REJECTED"}``

        Raises:
            NotFoundError: Draft not found.
        """
        rows = execute_query(
            """
            SELECT id, policy_key, status
            FROM institution_policies
            WHERE id = %s AND org_id = %s
            """,
            (draft_id, org_id),
        )
        if not rows:
            raise NotFoundError(f"Policy draft {draft_id} not found")

        draft = rows[0]
        if draft["status"] != "DRAFT":
            raise BusinessRuleViolation(
                f"Policy {draft_id} is not in DRAFT status (current: {draft['status']})"
            )

        execute_transaction(
            [
                (
                    "DELETE FROM institution_policies WHERE id = %s AND org_id = %s",
                    (draft_id, org_id),
                )
            ]
        )

        event = DomainEvent(
            event_type="policy.draft_rejected",
            org_id=org_id,
            payload={
                "draft_id": draft_id,
                "policy_key": draft["policy_key"],
                "rejected_by": actor_id,
                "reason": reason,
            },
        )
        await event_bus.publish(event)

        return {"draft_id": draft_id, "status": "REJECTED"}


# Module-level singleton — import and use directly.
policy_authoring_agent = PolicyAuthoringAgent()
