"""
ALIS Prompt Registry — E03-S03

MODULE: Platform Core (E03 — AI Gateway & Agents)
LAYER: Layer 2 (Agentic Decisions) + Layer 4 (Invariant Enforcement)
ENTITY: PromptRegistry

This module implements the centralized prompt registry for ALIS.
All AI prompts MUST be stored, versioned, and retrieved through this
registry. Inline/hardcoded prompts in agents or modules are PROHIBITED.

Rendering uses Jinja2 templates. Variables are injected at invocation time
by the AI Gateway before passing the rendered prompt to the LLM.

Must Align With:
- AI Invocation Contract (Rule #3): "Latest prompt resolution is prohibited."
- E03-S03 Acceptance Criteria:
    - [x] Prompt templates stored centrally
    - [x] Versioned prompts
    - [x] Prompt metadata (purpose, scope)
    - [x] No inline prompts inside modules
    - [x] Audit trail on prompt changes

Hard Constraints:
- Prompts in ACTIVATED or SUPERSEDED status are immutable (DB triggers).
- Hard deletion of prompts is blocked (DB trigger).
- All mutations are audit-logged with actor identity.
- "latest" version resolution is explicitly rejected.

Usage:
    # Create a new prompt version (DRAFT status):
    prompt = PromptRegistry.create_prompt(
        name="eligibility.extract_grades",
        content="You are an academic document analyzer...\\n{{ marksheet_text }}",
        description="Extracts grades from marksheet OCR text.",
        actor_id="admin-001",
        actor_role="ADMIN",
        tenant_id="tenant-abc",
    )

    # Activate a draft:
    PromptRegistry.activate_version(
        name="eligibility.extract_grades", version=2,
        actor_id="admin-001", actor_role="ADMIN", tenant_id="tenant-abc",
    )

    # Fetch a specific version (used by AI Gateway):
    prompt = PromptRegistry.get_prompt(
        name="eligibility.extract_grades",
        version=1,
        tenant_id="tenant-abc",
    )

    # Render with runtime variables:
    rendered = PromptRegistry.render_prompt(
        prompt["content"], {"marksheet_text": "..."}
    )
"""

import hashlib
import logging
from typing import Dict, Any, Optional, List
from uuid import uuid4

import jinja2
from jinja2.sandbox import SandboxedEnvironment

from .audit import AuditLog, AuditAction
from .exceptions import PromptNotFoundError, PromptResolutionError

logger = logging.getLogger(__name__)


# =============================================================================
# PROMPT STATUS CONSTANTS
# =============================================================================

PROMPT_STATUS_DRAFT = "DRAFT"
PROMPT_STATUS_ACTIVATED = "ACTIVATED"
PROMPT_STATUS_SUPERSEDED = "SUPERSEDED"

# Forbidden version identifiers (Contract Rule #3)
_FORBIDDEN_VERSION_IDENTIFIERS = {"latest", "current", "active", "newest"}


# =============================================================================
# JINJA2 SANDBOXED ENVIRONMENT
# =============================================================================

# Use SandboxedEnvironment to prevent template authors from executing
# arbitrary Python code inside Jinja2 templates.
_jinja_env = SandboxedEnvironment(
    undefined=jinja2.StrictUndefined,  # Fail loudly on missing variables
    autoescape=False,  # Prompts are plain text, not HTML
)


# =============================================================================
# PROMPT REGISTRY SERVICE
# =============================================================================

class PromptRegistry:
    """
    Centralized, versioned prompt registry for all ALIS AI operations.

    This class provides static methods for CRUD operations on prompts.
    It enforces:
    - Tenant isolation (via db_service tenant-scoped queries)
    - Version immutability (via DB triggers)
    - Audit trail (via AuditLog)
    - Strict version resolution (no "latest" allowed)
    """

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    @staticmethod
    def create_prompt(
        name: str,
        content: str,
        actor_id: str,
        actor_role: str,
        tenant_id: str,
        description: str = "",
        fmt: str = "jinja2",
    ) -> Dict[str, Any]:
        """
        Create a new prompt version in DRAFT status.

        The version is auto-incremented: it finds the highest existing
        version for this (tenant_id, name) and adds 1.

        Args:
            name: Prompt identifier (e.g., "eligibility.extract_grades")
            content: Jinja2 template string
            actor_id: ID of the actor creating the prompt
            actor_role: Role of the actor (e.g., "ADMIN")
            tenant_id: Tenant ID for scoping
            description: Human-readable description of the prompt
            fmt: Template format (default "jinja2")

        Returns:
            Dict with the created prompt record fields.
        """
        from server.db_service import execute_query, execute_transaction

        # Compute content hash for integrity
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Determine next version number
        existing = execute_query(
            "SELECT COALESCE(MAX(version), 0) as max_version "
            "FROM prompt_registry WHERE name = %s AND tenant_id = %s",
            (name, tenant_id),
            tenant_id=tenant_id,
        )
        next_version = (existing[0]["max_version"] if existing else 0) + 1

        prompt_id = f"prompt-{name}-v{next_version}-{uuid4().hex[:8]}"

        execute_transaction(
            [
                (
                    """
                    INSERT INTO prompt_registry
                        (id, tenant_id, name, version, content, format,
                         description, status, content_hash,
                         created_by, created_by_role)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        prompt_id, tenant_id, name, next_version,
                        content, fmt, description,
                        PROMPT_STATUS_DRAFT, content_hash,
                        actor_id, actor_role,
                    ),
                )
            ],
            tenant_id=tenant_id,
        )

        # Audit log
        AuditLog.log(
            action=AuditAction.PROMPT_CREATED,
            actor_id=actor_id,
            actor_role=actor_role,
            entity_type="prompt_registry",
            entity_id=prompt_id,
            tenant_id=tenant_id,
            metadata={
                "prompt_name": name,
                "version": next_version,
                "content_hash": content_hash,
                "format": fmt,
            },
        )

        logger.info(
            "E03-S03: Prompt '%s' v%d created [tenant=%s, actor=%s]",
            name, next_version, tenant_id, actor_id,
        )

        return {
            "id": prompt_id,
            "tenant_id": tenant_id,
            "name": name,
            "version": next_version,
            "content": content,
            "format": fmt,
            "description": description,
            "status": PROMPT_STATUS_DRAFT,
            "content_hash": content_hash,
            "created_by": actor_id,
            "created_by_role": actor_role,
        }

    # ------------------------------------------------------------------
    # ACTIVATE
    # ------------------------------------------------------------------

    @staticmethod
    def activate_version(
        name: str,
        version: int,
        actor_id: str,
        actor_role: str,
        tenant_id: str,
    ) -> None:
        """
        Activate a specific prompt version.

        This will:
        1. Mark the currently ACTIVATED version (if any) as SUPERSEDED.
        2. Mark the specified DRAFT version as ACTIVATED.

        Both operations happen in a single transaction.

        Args:
            name: Prompt identifier
            version: Version number to activate
            actor_id: ID of the actor performing activation
            actor_role: Role of the actor
            tenant_id: Tenant scope

        Raises:
            PromptNotFoundError: If the specified version does not exist
                                  or is not in DRAFT status.
        """
        from server.db_service import execute_query, execute_transaction

        # Verify the target version exists and is in DRAFT
        target = execute_query(
            "SELECT id, status FROM prompt_registry "
            "WHERE name = %s AND version = %s AND tenant_id = %s",
            (name, version, tenant_id),
            tenant_id=tenant_id,
        )

        if not target:
            raise PromptNotFoundError(
                message=(
                    f"Prompt '{name}' version {version} not found "
                    f"[tenant={tenant_id}]"
                ),
                details={"name": name, "version": version},
            )

        if target[0]["status"] != PROMPT_STATUS_DRAFT:
            raise PromptResolutionError(
                message=(
                    f"Prompt '{name}' version {version} is in "
                    f"'{target[0]['status']}' status — only DRAFT "
                    f"prompts can be activated."
                ),
                details={
                    "name": name,
                    "version": version,
                    "current_status": target[0]["status"],
                },
            )

        target_id = target[0]["id"]

        # Build transaction queries
        queries = []

        # Step 1: Supersede currently active version (if any)
        current_active = execute_query(
            "SELECT id, version FROM prompt_registry "
            "WHERE name = %s AND status = %s AND tenant_id = %s",
            (name, PROMPT_STATUS_ACTIVATED, tenant_id),
            tenant_id=tenant_id,
        )

        if current_active:
            old_id = current_active[0]["id"]
            old_version = current_active[0]["version"]
            queries.append((
                "UPDATE prompt_registry SET status = %s, "
                "updated_at = NOW() WHERE id = %s AND tenant_id = %s",
                (PROMPT_STATUS_SUPERSEDED, old_id, tenant_id),
            ))

            # Audit: supersede old version
            AuditLog.log(
                action=AuditAction.PROMPT_SUPERSEDED,
                actor_id=actor_id,
                actor_role=actor_role,
                entity_type="prompt_registry",
                entity_id=old_id,
                tenant_id=tenant_id,
                metadata={
                    "prompt_name": name,
                    "version": old_version,
                    "superseded_by_version": version,
                },
            )

        # Step 2: Activate the target version
        queries.append((
            "UPDATE prompt_registry SET status = %s, "
            "activated_by = %s, activated_at = NOW(), "
            "updated_at = NOW() WHERE id = %s AND tenant_id = %s",
            (PROMPT_STATUS_ACTIVATED, actor_id, target_id, tenant_id),
        ))

        execute_transaction(queries, tenant_id=tenant_id)

        # Audit: activate new version
        AuditLog.log(
            action=AuditAction.PROMPT_ACTIVATED,
            actor_id=actor_id,
            actor_role=actor_role,
            entity_type="prompt_registry",
            entity_id=target_id,
            tenant_id=tenant_id,
            metadata={
                "prompt_name": name,
                "version": version,
            },
        )

        logger.info(
            "E03-S03: Prompt '%s' v%d activated [tenant=%s, actor=%s]",
            name, version, tenant_id, actor_id,
        )

    # ------------------------------------------------------------------
    # GET (Strict Version Resolution)
    # ------------------------------------------------------------------

    @staticmethod
    def get_prompt(
        name: str,
        version: int,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """
        Fetch a specific prompt version.

        Contract Rule #3: "Latest prompt resolution is prohibited."
        This method requires an explicit integer version. Any attempt
        to resolve dynamically is blocked upstream.

        Args:
            name: Prompt identifier
            version: Explicit version number (integer)
            tenant_id: Tenant scope

        Returns:
            Dict with prompt fields (id, name, version, content, format,
            description, status, content_hash, created_by, etc.)

        Raises:
            PromptNotFoundError: If prompt not found
        """
        from server.db_service import execute_query

        rows = execute_query(
            "SELECT id, tenant_id, name, version, content, format, "
            "description, status, content_hash, created_by, "
            "created_by_role, activated_by, created_at, activated_at "
            "FROM prompt_registry "
            "WHERE name = %s AND version = %s AND tenant_id = %s",
            (name, version, tenant_id),
            tenant_id=tenant_id,
        )

        if not rows:
            raise PromptNotFoundError(
                message=(
                    f"Prompt '{name}' version {version} not found "
                    f"[tenant={tenant_id}]"
                ),
                details={"name": name, "version": version},
            )

        return dict(rows[0])

    # ------------------------------------------------------------------
    # GET ACTIVE (Convenience — returns the ACTIVATED version)
    # ------------------------------------------------------------------

    @staticmethod
    def get_active_prompt(
        name: str,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """
        Fetch the currently ACTIVATED version of a prompt.

        This is a convenience method for system-internal use (e.g., agent
        registries that know which prompt they need but want the current
        active version). The returned dict always includes the explicit
        version number so that it can be passed to the AI Gateway for
        contract-compliant invocation logging.

        Args:
            name: Prompt identifier
            tenant_id: Tenant scope

        Returns:
            Dict with all prompt fields including 'version'.

        Raises:
            PromptNotFoundError: If no ACTIVATED version exists.
        """
        from server.db_service import execute_query

        rows = execute_query(
            "SELECT id, tenant_id, name, version, content, format, "
            "description, status, content_hash, created_by, "
            "created_by_role, activated_by, created_at, activated_at "
            "FROM prompt_registry "
            "WHERE name = %s AND status = %s AND tenant_id = %s",
            (name, PROMPT_STATUS_ACTIVATED, tenant_id),
            tenant_id=tenant_id,
        )

        if not rows:
            raise PromptNotFoundError(
                message=(
                    f"No ACTIVATED version of prompt '{name}' found "
                    f"[tenant={tenant_id}]"
                ),
                details={"name": name, "status": "ACTIVATED"},
            )

        return dict(rows[0])

    # ------------------------------------------------------------------
    # LIST (All versions for a prompt name)
    # ------------------------------------------------------------------

    @staticmethod
    def list_versions(
        name: str,
        tenant_id: str,
    ) -> List[Dict[str, Any]]:
        """
        List all versions of a prompt (ordered by version descending).

        Args:
            name: Prompt identifier
            tenant_id: Tenant scope

        Returns:
            List of prompt version dicts.
        """
        from server.db_service import execute_query

        rows = execute_query(
            "SELECT id, tenant_id, name, version, format, "
            "description, status, content_hash, created_by, "
            "created_by_role, activated_by, created_at, activated_at "
            "FROM prompt_registry "
            "WHERE name = %s AND tenant_id = %s "
            "ORDER BY version DESC",
            (name, tenant_id),
            tenant_id=tenant_id,
        )

        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # RENDER (Jinja2 Template Rendering)
    # ------------------------------------------------------------------

    @staticmethod
    def render_prompt(
        template_content: str,
        variables: Dict[str, Any],
    ) -> str:
        """
        Render a Jinja2 prompt template with the given variables.

        Uses a SandboxedEnvironment to prevent arbitrary code execution
        inside templates. StrictUndefined ensures all expected variables
        are provided — missing variables raise an error immediately
        rather than producing silent empty strings.

        Args:
            template_content: Jinja2 template string
            variables: Dict of runtime variables to inject

        Returns:
            Rendered prompt string ready for LLM invocation.

        Raises:
            jinja2.UndefinedError: If a required variable is missing.
            jinja2.TemplateSyntaxError: If the template is malformed.
        """
        template = _jinja_env.from_string(template_content)
        return template.render(**variables)

    # ------------------------------------------------------------------
    # STRICT VERSION GUARD (Contract Rule #3)
    # ------------------------------------------------------------------

    @staticmethod
    def assert_valid_version(version: Any) -> int:
        """
        Validate that a version identifier is an explicit integer.

        Per AI Invocation Contract Rule #3:
        "Latest prompt resolution is prohibited."

        Args:
            version: The version value to validate.

        Returns:
            The validated integer version.

        Raises:
            PromptResolutionError: If version is "latest", None, or
                                    otherwise non-explicit.
        """
        if version is None:
            raise PromptResolutionError(
                message=(
                    "Prompt version must be explicitly specified. "
                    "'None' is not allowed (E03-S03 Contract Rule #3)."
                ),
            )

        if isinstance(version, str):
            if version.lower().strip() in _FORBIDDEN_VERSION_IDENTIFIERS:
                raise PromptResolutionError(
                    message=(
                        f"Prompt version '{version}' is prohibited. "
                        f"Latest prompt resolution is not allowed "
                        f"(E03-S03 Contract Rule #3)."
                    ),
                    details={"requested_version": version},
                )
            # Try to parse as integer
            try:
                return int(version)
            except ValueError:
                raise PromptResolutionError(
                    message=(
                        f"Prompt version '{version}' is not a valid "
                        f"integer version identifier."
                    ),
                    details={"requested_version": version},
                )

        if isinstance(version, int):
            if version < 1:
                raise PromptResolutionError(
                    message=(
                        f"Prompt version must be >= 1, got {version}."
                    ),
                )
            return version

        raise PromptResolutionError(
            message=(
                f"Prompt version must be an integer, "
                f"got {type(version).__name__}."
            ),
        )
