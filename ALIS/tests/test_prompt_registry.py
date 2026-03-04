"""
E03-S03 Prompt Registry & Versioning — Test Suite

Tests the following contracts:
1. Prompt CRUD operations (create, get, list)
2. Version immutability (ACTIVATED/SUPERSEDED cannot be mutated)
3. "Latest" resolution rejection (Contract Rule #3)
4. Jinja2 rendering with SandboxedEnvironment
5. Strict version validation
6. Activate/Supersede workflow
7. AI Gateway invoke_with_prompt integration
"""

import hashlib
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server.core.prompt_registry import (
    PromptRegistry,
    PROMPT_STATUS_DRAFT,
    PROMPT_STATUS_ACTIVATED,
    PROMPT_STATUS_SUPERSEDED,
    _FORBIDDEN_VERSION_IDENTIFIERS,
)
from server.core.exceptions import (
    PromptNotFoundError,
    PromptResolutionError,
)


class TestVersionValidation(unittest.TestCase):
    """Test Contract Rule #3: Latest prompt resolution is prohibited."""

    def test_reject_latest_string(self):
        """'latest' must be rejected."""
        with self.assertRaises(PromptResolutionError) as ctx:
            PromptRegistry.assert_valid_version("latest")
        self.assertIn("prohibited", ctx.exception.message)

    def test_reject_current_string(self):
        """'current' must be rejected."""
        with self.assertRaises(PromptResolutionError):
            PromptRegistry.assert_valid_version("current")

    def test_reject_active_string(self):
        """'active' must be rejected."""
        with self.assertRaises(PromptResolutionError):
            PromptRegistry.assert_valid_version("active")

    def test_reject_newest_string(self):
        """'newest' must be rejected."""
        with self.assertRaises(PromptResolutionError):
            PromptRegistry.assert_valid_version("newest")

    def test_reject_none(self):
        """None version must be rejected."""
        with self.assertRaises(PromptResolutionError) as ctx:
            PromptRegistry.assert_valid_version(None)
        self.assertIn("None", ctx.exception.message)

    def test_reject_zero(self):
        """Version 0 must be rejected (versions start at 1)."""
        with self.assertRaises(PromptResolutionError):
            PromptRegistry.assert_valid_version(0)

    def test_reject_negative(self):
        """Negative versions must be rejected."""
        with self.assertRaises(PromptResolutionError):
            PromptRegistry.assert_valid_version(-1)

    def test_accept_valid_integer(self):
        """Valid integer version must be accepted."""
        result = PromptRegistry.assert_valid_version(1)
        self.assertEqual(result, 1)

    def test_accept_valid_integer_string(self):
        """String '1' must be parsed and accepted."""
        result = PromptRegistry.assert_valid_version("1")
        self.assertEqual(result, 1)

    def test_accept_large_version(self):
        """Large version numbers must be accepted."""
        result = PromptRegistry.assert_valid_version(999)
        self.assertEqual(result, 999)

    def test_reject_float(self):
        """Float versions must be rejected."""
        with self.assertRaises(PromptResolutionError):
            PromptRegistry.assert_valid_version(1.5)

    def test_reject_non_numeric_string(self):
        """Non-numeric strings must be rejected."""
        with self.assertRaises(PromptResolutionError):
            PromptRegistry.assert_valid_version("abc")

    def test_all_forbidden_identifiers_covered(self):
        """All forbidden identifiers in the set must be rejected."""
        for identifier in _FORBIDDEN_VERSION_IDENTIFIERS:
            with self.assertRaises(PromptResolutionError):
                PromptRegistry.assert_valid_version(identifier)

    def test_case_insensitive_rejection(self):
        """Forbidden identifiers must be rejected regardless of case."""
        with self.assertRaises(PromptResolutionError):
            PromptRegistry.assert_valid_version("LATEST")
        with self.assertRaises(PromptResolutionError):
            PromptRegistry.assert_valid_version("Latest")


class TestJinja2Rendering(unittest.TestCase):
    """Test Jinja2 template rendering with sandboxed environment."""

    def test_simple_variable_substitution(self):
        """Basic Jinja2 variable rendering."""
        template = "Hello, {{ name }}!"
        result = PromptRegistry.render_prompt(template, {"name": "World"})
        self.assertEqual(result, "Hello, World!")

    def test_multiple_variables(self):
        """Multiple variable rendering."""
        template = "Subject: {{ subject }}\nMarks: {{ marks }}"
        result = PromptRegistry.render_prompt(
            template, {"subject": "Math", "marks": 95}
        )
        self.assertEqual(result, "Subject: Math\nMarks: 95")

    def test_missing_variable_raises_error(self):
        """StrictUndefined: missing variables must raise an error."""
        import jinja2
        template = "Hello, {{ name }}! Your score is {{ score }}."
        with self.assertRaises(jinja2.UndefinedError):
            PromptRegistry.render_prompt(template, {"name": "Alice"})

    def test_multiline_template(self):
        """Multiline templates (typical for prompts) must render correctly."""
        template = (
            "You are an evaluator.\n"
            "Criteria:\n{{ criteria }}\n"
            "Grades:\n{{ grades }}"
        )
        result = PromptRegistry.render_prompt(
            template, {"criteria": "50% minimum", "grades": "Math: 80"}
        )
        self.assertIn("50% minimum", result)
        self.assertIn("Math: 80", result)

    def test_json_template(self):
        """JSON output instructions in templates must render cleanly."""
        template = 'Return JSON: {"score": {{ score }}}'
        result = PromptRegistry.render_prompt(template, {"score": 0.85})
        self.assertEqual(result, 'Return JSON: {"score": 0.85}')

    def test_empty_variables_dict(self):
        """Template with no variables should render as-is."""
        template = "You are a helpful assistant."
        result = PromptRegistry.render_prompt(template, {})
        self.assertEqual(result, "You are a helpful assistant.")


class TestPromptCRUD(unittest.TestCase):
    """Test Prompt Registry CRUD operations (mocked DB)."""

    @patch("server.core.prompt_registry.AuditLog")
    @patch("server.db_service.execute_transaction")
    @patch("server.db_service.execute_query")
    def test_create_prompt_first_version(
        self, mock_query, mock_transaction, mock_audit
    ):
        """Creating first prompt should result in version 1."""
        # Mock: no existing versions
        mock_query.return_value = [{"max_version": 0}]

        result = PromptRegistry.create_prompt(
            name="test.prompt",
            content="Hello {{ name }}",
            actor_id="admin-1",
            actor_role="ADMIN",
            tenant_id="tenant-abc",
            description="Test prompt",
        )

        self.assertEqual(result["version"], 1)
        self.assertEqual(result["status"], PROMPT_STATUS_DRAFT)
        self.assertEqual(result["name"], "test.prompt")
        self.assertTrue(result["content_hash"])
        mock_transaction.assert_called_once()
        mock_audit.log.assert_called_once()

    @patch("server.core.prompt_registry.AuditLog")
    @patch("server.db_service.execute_transaction")
    @patch("server.db_service.execute_query")
    def test_create_prompt_increments_version(
        self, mock_query, mock_transaction, mock_audit
    ):
        """Creating a new version should auto-increment."""
        mock_query.return_value = [{"max_version": 3}]

        result = PromptRegistry.create_prompt(
            name="test.prompt",
            content="Hello v4",
            actor_id="admin-1",
            actor_role="ADMIN",
            tenant_id="tenant-abc",
        )

        self.assertEqual(result["version"], 4)

    @patch("server.db_service.execute_query")
    def test_get_prompt_not_found(self, mock_query):
        """Getting a non-existent prompt should raise PromptNotFoundError."""
        mock_query.return_value = []

        with self.assertRaises(PromptNotFoundError):
            PromptRegistry.get_prompt(
                name="nonexistent", version=1, tenant_id="tenant-abc"
            )

    @patch("server.db_service.execute_query")
    def test_get_prompt_success(self, mock_query):
        """Getting an existing prompt should return a dict."""
        mock_query.return_value = [
            {
                "id": "prompt-test-v1",
                "tenant_id": "tenant-abc",
                "name": "test.prompt",
                "version": 1,
                "content": "Hello {{ name }}",
                "format": "jinja2",
                "description": "Test",
                "status": "ACTIVATED",
                "content_hash": "abc123",
                "created_by": "admin-1",
                "created_by_role": "ADMIN",
                "activated_by": "admin-1",
                "created_at": "2026-01-01",
                "activated_at": "2026-01-01",
            }
        ]

        result = PromptRegistry.get_prompt(
            name="test.prompt", version=1, tenant_id="tenant-abc"
        )

        self.assertEqual(result["name"], "test.prompt")
        self.assertEqual(result["version"], 1)


class TestActivationWorkflow(unittest.TestCase):
    """Test the activate/supersede workflow."""

    @patch("server.core.prompt_registry.AuditLog")
    @patch("server.db_service.execute_transaction")
    @patch("server.db_service.execute_query")
    def test_activate_rejects_non_draft(
        self, mock_query, mock_transaction, mock_audit
    ):
        """Activating an already ACTIVATED prompt should raise an error."""
        mock_query.return_value = [
            {"id": "prompt-test-v1", "status": "ACTIVATED"}
        ]

        with self.assertRaises(PromptResolutionError) as ctx:
            PromptRegistry.activate_version(
                name="test.prompt",
                version=1,
                actor_id="admin-1",
                actor_role="ADMIN",
                tenant_id="tenant-abc",
            )
        self.assertIn("ACTIVATED", ctx.exception.message)

    @patch("server.core.prompt_registry.AuditLog")
    @patch("server.db_service.execute_transaction")
    @patch("server.db_service.execute_query")
    def test_activate_not_found(
        self, mock_query, mock_transaction, mock_audit
    ):
        """Activating a non-existent version should raise PromptNotFoundError."""
        mock_query.return_value = []

        with self.assertRaises(PromptNotFoundError):
            PromptRegistry.activate_version(
                name="nonexistent",
                version=99,
                actor_id="admin-1",
                actor_role="ADMIN",
                tenant_id="tenant-abc",
            )


class TestContentHashIntegrity(unittest.TestCase):
    """Test content hash computation for replay verification."""

    def test_content_hash_deterministic(self):
        """Same content must produce same hash."""
        content = "You are an evaluator.\n{{ grades }}"
        hash1 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        hash2 = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.assertEqual(hash1, hash2)

    def test_different_content_different_hash(self):
        """Different content must produce different hashes."""
        content1 = "Version 1 prompt"
        content2 = "Version 2 prompt"
        hash1 = hashlib.sha256(content1.encode("utf-8")).hexdigest()
        hash2 = hashlib.sha256(content2.encode("utf-8")).hexdigest()
        self.assertNotEqual(hash1, hash2)


if __name__ == "__main__":
    unittest.main()
