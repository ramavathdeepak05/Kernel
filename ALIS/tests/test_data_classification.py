"""
Unit Tests for ALIS Data Classification & Sensitivity Model - E00-S01

Tests:
1. Sensitivity Level Enums & Ordering
2. Entity Classification Registry
3. Data Masker (email, phone, name, generic, full)
4. AI Context Scrubbing
5. Log Masking
6. Entity Sensitivity Tagging (BaseEntity, User, etc.)
7. Encryption Required Helper
8. Integration with Existing Models
"""

import pytest
from datetime import datetime

from server.core.data_classification import (
    SensitivityLevel,
    RegulatedDataType,
    FieldClassification,
    EntityClassification,
    EntityClassificationRegistry,
    DataMasker,
    encryption_required,
    sensitivity_gte,
    initialize_default_classifications,
)
from server.core.models import (
    BaseEntity, User, Organization, NotificationLog, Task,
    ActorType, UserStatus, TaskPriority,
)
from server.core.audit import AuditLog, AuditAction


# --- Fixtures ---

@pytest.fixture(autouse=True)
def reset_services():
    """Reset all services before each test."""
    EntityClassificationRegistry._reset()
    AuditLog._entries = []
    initialize_default_classifications()
    yield


# ===========================================================
# TEST CLASS 1: SENSITIVITY LEVELS
# ===========================================================

class TestSensitivityLevels:
    """Tests for SensitivityLevel enum and ordering."""

    def test_enum_values_exist(self):
        """Test that all four sensitivity levels are defined."""
        assert SensitivityLevel.PUBLIC == "PUBLIC"
        assert SensitivityLevel.INTERNAL == "INTERNAL"
        assert SensitivityLevel.CONFIDENTIAL == "CONFIDENTIAL"
        assert SensitivityLevel.REGULATED == "REGULATED"

    def test_sensitivity_ordering(self):
        """Test that sensitivity levels are properly ordered."""
        assert sensitivity_gte(SensitivityLevel.REGULATED, SensitivityLevel.PUBLIC)
        assert sensitivity_gte(SensitivityLevel.CONFIDENTIAL, SensitivityLevel.INTERNAL)
        assert sensitivity_gte(SensitivityLevel.INTERNAL, SensitivityLevel.PUBLIC)
        assert sensitivity_gte(SensitivityLevel.REGULATED, SensitivityLevel.CONFIDENTIAL)

    def test_sensitivity_equality(self):
        """Test that same levels are gte each other."""
        assert sensitivity_gte(SensitivityLevel.CONFIDENTIAL, SensitivityLevel.CONFIDENTIAL)
        assert sensitivity_gte(SensitivityLevel.PUBLIC, SensitivityLevel.PUBLIC)

    def test_lower_not_gte_higher(self):
        """Test that lower levels are NOT gte higher levels."""
        assert not sensitivity_gte(SensitivityLevel.PUBLIC, SensitivityLevel.INTERNAL)
        assert not sensitivity_gte(SensitivityLevel.INTERNAL, SensitivityLevel.CONFIDENTIAL)
        assert not sensitivity_gte(SensitivityLevel.CONFIDENTIAL, SensitivityLevel.REGULATED)

    def test_regulated_data_types(self):
        """Test that all regulated data sub-types are defined."""
        assert RegulatedDataType.NONE == "NONE"
        assert RegulatedDataType.PII == "PII"
        assert RegulatedDataType.FINANCE == "FINANCE"
        assert RegulatedDataType.BIOMETRIC == "BIOMETRIC"
        assert RegulatedDataType.TRANSCRIPT == "TRANSCRIPT"


# ===========================================================
# TEST CLASS 2: ENTITY CLASSIFICATION REGISTRY
# ===========================================================

class TestEntityClassificationRegistry:
    """Tests for the EntityClassificationRegistry."""

    def test_default_registrations_loaded(self):
        """Test that initialize_default_classifications populates the registry."""
        registered = EntityClassificationRegistry.list_registered()
        assert "user" in registered
        assert "organization" in registered
        assert "notification_log" in registered
        assert "task" in registered
        assert "file_metadata" in registered
        assert "generated_document" in registered
        assert "audit_entry" in registered

    def test_user_classification(self):
        """Test that User is classified as CONFIDENTIAL/PII."""
        ec = EntityClassificationRegistry.get("user")
        assert ec is not None
        assert ec.default_sensitivity == SensitivityLevel.CONFIDENTIAL
        assert ec.default_regulated_type == RegulatedDataType.PII

    def test_organization_classification(self):
        """Test that Organization is classified as INTERNAL."""
        ec = EntityClassificationRegistry.get("organization")
        assert ec is not None
        assert ec.default_sensitivity == SensitivityLevel.INTERNAL

    def test_generated_document_classification(self):
        """Test that GeneratedDocument is REGULATED/TRANSCRIPT."""
        ec = EntityClassificationRegistry.get("generated_document")
        assert ec is not None
        assert ec.default_sensitivity == SensitivityLevel.REGULATED
        assert ec.default_regulated_type == RegulatedDataType.TRANSCRIPT

    def test_field_overrides_exist(self):
        """Test that User has field-level overrides for email, username, etc."""
        ec = EntityClassificationRegistry.get("user")
        assert "email" in ec.field_overrides
        assert "username" in ec.field_overrides
        assert "display_name" in ec.field_overrides
        assert ec.field_overrides["email"].sensitivity == SensitivityLevel.REGULATED
        assert ec.field_overrides["email"].mask_in_ai is True

    def test_get_or_default_for_unknown(self):
        """Test that unregistered entities get INTERNAL default."""
        ec = EntityClassificationRegistry.get_or_default("unknown_entity")
        assert ec.default_sensitivity == SensitivityLevel.INTERNAL
        assert ec.description == "Unregistered entity — defaulting to INTERNAL"

    def test_get_field_classification(self):
        """Test retrieving field-level classification."""
        fc = EntityClassificationRegistry.get_field_classification("user", "email")
        assert fc.sensitivity == SensitivityLevel.REGULATED
        assert fc.regulated_type == RegulatedDataType.PII
        assert fc.mask_in_ai is True

    def test_get_field_classification_default(self):
        """Test that fields without overrides inherit entity default."""
        fc = EntityClassificationRegistry.get_field_classification("user", "created_at")
        assert fc.sensitivity == SensitivityLevel.CONFIDENTIAL  # Inherits entity default

    def test_custom_registration(self):
        """Test registering a custom entity classification."""
        EntityClassificationRegistry.register(EntityClassification(
            entity_type="custom_entity",
            default_sensitivity=SensitivityLevel.REGULATED,
            default_regulated_type=RegulatedDataType.FINANCE,
            description="Test entity",
        ))
        ec = EntityClassificationRegistry.get("custom_entity")
        assert ec is not None
        assert ec.default_sensitivity == SensitivityLevel.REGULATED


# ===========================================================
# TEST CLASS 3: DATA MASKER — CORE FUNCTIONS
# ===========================================================

class TestDataMaskerCore:
    """Tests for core masking functions."""

    def test_mask_email(self):
        """Test email masking preserves structure."""
        result = DataMasker.mask_email("john.doe@example.com")
        assert "@" in result
        assert result.startswith("j")
        assert "***" not in result or result != "john.doe@example.com"
        assert result != "john.doe@example.com"  # Must be different

    def test_mask_email_short_local(self):
        """Test email masking with short local part."""
        result = DataMasker.mask_email("ab@test.com")
        assert "@" in result
        assert result != "ab@test.com"

    def test_mask_email_invalid(self):
        """Test email masking with invalid input."""
        assert DataMasker.mask_email("") == "***"
        assert DataMasker.mask_email("noatsign") == "***"

    def test_mask_phone(self):
        """Test phone masking keeps last 4 digits."""
        result = DataMasker.mask_phone("+91 9876543210")
        assert result.endswith("3210")
        assert "*" in result

    def test_mask_phone_short(self):
        """Test phone masking with short numbers."""
        assert DataMasker.mask_phone("1234") == "***"

    def test_mask_name(self):
        """Test name masking keeps first initial."""
        result = DataMasker.mask_name("John Doe")
        assert result.startswith("J")
        assert "D" in result
        assert result != "John Doe"

    def test_mask_name_empty(self):
        """Test name masking with empty input."""
        assert DataMasker.mask_name("") == "***"

    def test_mask_generic(self):
        """Test generic partial masking."""
        result = DataMasker.mask_generic("SENSITIVE_DATA", keep_chars=3)
        assert result.startswith("SEN")
        assert "*" in result
        assert len(result) == len("SENSITIVE_DATA")

    def test_mask_full(self):
        """Test full redaction."""
        assert DataMasker.mask_full("anything") == "[REDACTED]"

    def test_mask_value_public_passthrough(self):
        """Test that PUBLIC values are never masked."""
        result = DataMasker.mask_value("email", "test@test.com", SensitivityLevel.PUBLIC)
        assert result == "test@test.com"

    def test_mask_value_none_passthrough(self):
        """Test that None values return None."""
        assert DataMasker.mask_value("email", None, SensitivityLevel.REGULATED) is None

    def test_mask_value_secret_always_redacted(self):
        """Test that password/secret/token fields are fully redacted."""
        assert DataMasker.mask_value("password", "mypassword", SensitivityLevel.INTERNAL) == "[REDACTED]"
        assert DataMasker.mask_value("secret_key", "abc123", SensitivityLevel.INTERNAL) == "[REDACTED]"
        assert DataMasker.mask_value("api_token", "tok_123", SensitivityLevel.INTERNAL) == "[REDACTED]"
        assert DataMasker.mask_value("biometric_hash", "hash", SensitivityLevel.REGULATED) == "[REDACTED]"


# ===========================================================
# TEST CLASS 4: DATA MASKER — DICT MASKING
# ===========================================================

class TestDataMaskerDict:
    """Tests for dictionary-level masking."""

    def test_mask_dict_user(self):
        """Test masking a user dictionary."""
        user_data = {
            "id": "user-001",
            "username": "johndoe",
            "email": "john@example.com",
            "display_name": "John Doe",
            "status": "ACTIVE",
        }
        result = DataMasker.mask_dict(user_data, "user")

        # Email should be masked (field override: mask_in_logs=True)
        assert result["email"] != "john@example.com"
        # Username should be masked (field override: mask_in_logs=True)
        assert result["username"] != "johndoe"
        # Display name should be masked
        assert result["display_name"] != "John Doe"

    def test_mask_dict_organization(self):
        """Test masking an organization dictionary (INTERNAL — light treatment)."""
        org_data = {
            "id": "org-001",
            "name": "Test University",
            "code": "TU",
            "status": "ACTIVE",
        }
        result = DataMasker.mask_dict(org_data, "organization")

        # Organization name is PUBLIC per override — should not be masked
        # Name field has PUBLIC override in the registry
        assert result["name"] == "Test University"
        assert result["code"] == "TU"

    def test_mask_dict_notification_log(self):
        """Test masking notification log with recipient address."""
        notif_data = {
            "recipient_address": "student@university.edu",
            "recipient_id": "stu-001",
            "template_id": "welcome_email",
        }
        result = DataMasker.mask_dict(notif_data, "notification_log")
        assert result["recipient_address"] != "student@university.edu"
        assert result["recipient_id"] != "stu-001"


# ===========================================================
# TEST CLASS 5: AI CONTEXT SCRUBBING
# ===========================================================

class TestAIMasking:
    """Tests for AI context masking (most aggressive)."""

    def test_ai_context_masks_user_pii(self):
        """Test that AI context hides user PII completely."""
        user_data = {
            "id": "user-001",
            "username": "johndoe",
            "email": "john@example.com",
            "display_name": "John Doe",
            "status": "ACTIVE",
            "org_id": "org-001",
        }
        result = DataMasker.mask_for_ai_context(user_data, "user")

        # Safe fields preserved
        assert result["id"] == "user-001"
        assert result["status"] == "ACTIVE"
        assert result["org_id"] == "org-001"

        # PII fields masked/redacted
        assert result["email"] == "[REDACTED]"
        assert result["username"] == "[REDACTED]"
        assert result["display_name"] == "[REDACTED]"

    def test_ai_context_preserves_safe_fields(self):
        """Test that entity_type, id, status pass through to AI."""
        data = {
            "id": "task-001",
            "status": "PENDING",
            "entity_type": "approval_request",
            "title": "Review document",
        }
        result = DataMasker.mask_for_ai_context(data, "task")
        assert result["id"] == "task-001"
        assert result["status"] == "PENDING"
        assert result["entity_type"] == "approval_request"


# ===========================================================
# TEST CLASS 6: LOG MASKING
# ===========================================================

class TestLogMasking:
    """Tests for log-safe masking."""

    def test_log_masks_user_email(self):
        """Test that user email is masked in logs."""
        user_data = {
            "id": "user-001",
            "email": "private@email.com",
            "username": "private_user",
            "status": "ACTIVE",
        }
        result = DataMasker.mask_for_log(user_data, "user")
        assert result["email"] != "private@email.com"
        assert result["username"] != "private_user"
        # Status is not marked mask_in_logs — should pass through
        assert result["status"] == "ACTIVE"

    def test_log_preserves_non_sensitive(self):
        """Test that non-sensitive fields are not masked in logs."""
        org_data = {
            "name": "Public University",
            "code": "PU",
            "status": "ACTIVE",
        }
        result = DataMasker.mask_for_log(org_data, "organization")
        assert result["name"] == "Public University"
        assert result["code"] == "PU"


# ===========================================================
# TEST CLASS 7: ENCRYPTION REQUIRED
# ===========================================================

class TestEncryptionRequired:
    """Tests for the encryption_required() helper."""

    def test_public_no_encryption(self):
        """PUBLIC data does not require encryption."""
        assert encryption_required(SensitivityLevel.PUBLIC) is False

    def test_internal_no_encryption(self):
        """INTERNAL data does not require encryption."""
        assert encryption_required(SensitivityLevel.INTERNAL) is False

    def test_confidential_requires_encryption(self):
        """CONFIDENTIAL data MUST be encrypted at rest."""
        assert encryption_required(SensitivityLevel.CONFIDENTIAL) is True

    def test_regulated_requires_encryption(self):
        """REGULATED data MUST be encrypted at rest."""
        assert encryption_required(SensitivityLevel.REGULATED) is True


# ===========================================================
# TEST CLASS 8: ENTITY SENSITIVITY TAGGING
# ===========================================================

class TestEntitySensitivityTag:
    """Tests for sensitivity metadata on model entities."""

    def test_base_entity_default(self):
        """Test that BaseEntity defaults to INTERNAL/NONE."""
        entity = BaseEntity()
        assert entity.sensitivity_level == SensitivityLevel.INTERNAL
        assert entity.regulated_data_type == RegulatedDataType.NONE

    def test_user_sensitivity(self):
        """Test that User defaults to CONFIDENTIAL/PII."""
        user = User(username="test_user")
        assert user.sensitivity_level == SensitivityLevel.CONFIDENTIAL
        assert user.regulated_data_type == RegulatedDataType.PII

    def test_organization_inherits_default(self):
        """Test that Organization inherits INTERNAL from BaseEntity."""
        org = Organization(name="Test Org", code="TO")
        assert org.sensitivity_level == SensitivityLevel.INTERNAL
        assert org.regulated_data_type == RegulatedDataType.NONE

    def test_notification_log_sensitivity(self):
        """Test that NotificationLog is CONFIDENTIAL/PII."""
        log = NotificationLog(
            recipient_id="user-001",
            recipient_address="test@test.com",
            template_id="tpl-001",
        )
        assert log.sensitivity_level == SensitivityLevel.CONFIDENTIAL
        assert log.regulated_data_type == RegulatedDataType.PII

    def test_task_inherits_default(self):
        """Test that Task inherits INTERNAL from BaseEntity."""
        task = Task(title="Review application")
        assert task.sensitivity_level == SensitivityLevel.INTERNAL
        assert task.regulated_data_type == RegulatedDataType.NONE

    def test_sensitivity_survives_serialization(self):
        """Test that sensitivity metadata is included in model dict."""
        user = User(username="test_user")
        data = user.model_dump()
        assert "sensitivity_level" in data
        assert data["sensitivity_level"] == SensitivityLevel.CONFIDENTIAL
        assert "regulated_data_type" in data
        assert data["regulated_data_type"] == RegulatedDataType.PII


# ===========================================================
# TEST CLASS 9: AUDIT ACTION COVERAGE
# ===========================================================

class TestAuditActions:
    """Tests for data classification audit actions."""

    def test_classification_audit_actions_exist(self):
        """Test that E00-S01 audit actions are defined."""
        assert AuditAction.DATA_CLASSIFIED == "data_classified"
        assert AuditAction.SENSITIVITY_CHANGED == "sensitivity_changed"
        assert AuditAction.SENSITIVE_ACCESS == "sensitive_access"

    def test_can_log_classification_event(self):
        """Test logging a data classification audit entry."""
        entry = AuditLog.log(
            action=AuditAction.DATA_CLASSIFIED,
            actor_id="system",
            actor_type="system",
            entity_type="user",
            entity_id="user-001",
            action_detail="Entity classified as CONFIDENTIAL/PII",
            metadata={"sensitivity": "CONFIDENTIAL", "regulated_type": "PII"},
        )
        assert entry.action == AuditAction.DATA_CLASSIFIED
        assert entry.entity_type == "user"

        entries = AuditLog.query(action=AuditAction.DATA_CLASSIFIED)
        assert len(entries) == 1
