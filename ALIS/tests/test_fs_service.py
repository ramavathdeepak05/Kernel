"""
Unit Tests for File Storage & Versioning Service (E02-S05)

Tests:
- File upload (v1 creation)
- File update (v2 creation, immutability of v1)
- Retrieval (latest vs specific version)
- Integrity check (hash verification)
- RBAC enforcement (mocked roles)
"""

import hashlib
import pytest
from io import BytesIO
from unittest.mock import patch, MagicMock

from server.fs_service import (
    FileStorageService,
    FileMetadata,
    FileVersion,
    FileNotFoundError,
    VersionNotFoundError,
    AccessDeniedError,
    _FileMetadataStore,
)
from server.core.rbac import Role, AccessResult


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def clear_store():
    """Clear in-memory metadata store before each test."""
    _FileMetadataStore.clear()
    yield
    _FileMetadataStore.clear()


@pytest.fixture
def mock_minio():
    """Mock the MinIO client returned by FileStorageService._minio()."""
    mock_client = MagicMock()
    # get_object returns an object whose .read() returns bytes
    mock_response = MagicMock()
    mock_client.get_object.return_value = mock_response
    with patch.object(FileStorageService, "_minio", return_value=mock_client), \
         patch.object(FileStorageService, "_ensure_bucket"):
        yield mock_client


@pytest.fixture
def mock_rbac_allow():
    """Mock RBAC to always allow access."""
    with patch("server.fs_service.verify_access") as mock:
        mock.return_value = AccessResult(allowed=True)
        yield mock


@pytest.fixture
def file_service():
    """Return a FileStorageService instance (no args — MinIO config from settings)."""
    return FileStorageService()


@pytest.fixture
def sample_file_content():
    return b"This is a test document for ALIS E02-S05."


@pytest.fixture
def sample_context():
    return {"role": Role.FACULTY}


# =============================================================================
# UPLOAD TESTS
# =============================================================================

class TestFileUpload:

    def test_upload_creates_v1(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """Uploading a new file should create version 1."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test_document.pdf",
            owner_id="user_001",
            context=sample_context,
        )

        assert metadata.file_id is not None
        assert metadata.filename == "test_document.pdf"
        assert metadata.owner_id == "user_001"
        assert metadata.current_version == 1
        assert len(metadata.versions) == 1
        assert metadata.versions[0].version == 1

    def test_upload_stores_hash(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """Uploaded file should have correct SHA-256 hash."""
        expected_hash = hashlib.sha256(sample_file_content).hexdigest()

        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )

        assert metadata.versions[0].file_hash == expected_hash

    def test_upload_stores_size(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """Uploaded file should have correct size."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )

        assert metadata.versions[0].size_bytes == len(sample_file_content)

    def test_upload_calls_minio_put(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """Upload should call MinIO put_object with the correct bucket."""
        from server.core.settings import settings

        file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )

        assert mock_minio.put_object.called
        call_args = mock_minio.put_object.call_args
        assert call_args[0][0] == settings.minio_bucket


# =============================================================================
# UPDATE (VERSIONING) TESTS
# =============================================================================

class TestFileUpdate:

    def test_update_creates_v2(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """Updating a file should create version 2."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )

        new_content = b"Updated content for version 2"
        new_version = file_service.update_file(
            file_id=metadata.file_id,
            file_content=new_content,
            updated_by="user_001",
            context=sample_context,
        )

        assert new_version.version == 2

        updated_metadata = file_service.get_metadata(
            metadata.file_id, "user_001", sample_context
        )
        assert updated_metadata.current_version == 2
        assert len(updated_metadata.versions) == 2

    def test_update_preserves_v1_hash(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """Updating should NOT change the stored v1 hash (immutability)."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        v1_hash = metadata.versions[0].file_hash

        file_service.update_file(
            file_id=metadata.file_id,
            file_content=b"Completely different content",
            updated_by="user_001",
            context=sample_context,
        )

        updated_metadata = file_service.get_metadata(
            metadata.file_id, "user_001", sample_context
        )
        # v1 entry must be unchanged
        assert updated_metadata.versions[0].file_hash == v1_hash
        assert updated_metadata.versions[0].version == 1

    def test_update_nonexistent_file_raises_error(
        self, file_service, mock_minio, mock_rbac_allow, sample_context
    ):
        """Updating a non-existent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            file_service.update_file(
                file_id="nonexistent_id",
                file_content=b"content",
                updated_by="user_001",
                context=sample_context,
            )


# =============================================================================
# RETRIEVAL TESTS
# =============================================================================

class TestFileRetrieval:

    def _setup_minio_read(self, mock_minio, content: bytes):
        """Configure mock_minio.get_object to return the given bytes."""
        mock_response = MagicMock()
        mock_response.read.return_value = content
        mock_minio.get_object.return_value = mock_response

    def test_get_file_returns_latest_by_default(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """get_file() without version should return latest content."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )

        v2_content = b"Version 2 content"
        file_service.update_file(
            file_id=metadata.file_id,
            file_content=v2_content,
            updated_by="user_001",
            context=sample_context,
        )

        # MinIO should return v2 content when called
        self._setup_minio_read(mock_minio, v2_content)

        content = file_service.get_file(
            metadata.file_id, "user_001", sample_context
        )
        assert content == v2_content

    def test_get_file_specific_version(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """get_file() with version=1 should return v1 content."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        file_service.update_file(
            file_id=metadata.file_id,
            file_content=b"Version 2",
            updated_by="user_001",
            context=sample_context,
        )

        self._setup_minio_read(mock_minio, sample_file_content)

        v1_content = file_service.get_file(
            metadata.file_id, "user_001", sample_context, version=1
        )
        assert v1_content == sample_file_content

    def test_get_nonexistent_version_raises_error(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """Requesting a version that doesn't exist should raise VersionNotFoundError."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )

        with pytest.raises(VersionNotFoundError):
            file_service.get_file(
                metadata.file_id, "user_001", sample_context, version=999
            )


# =============================================================================
# INTEGRITY TESTS
# =============================================================================

class TestIntegrity:

    def test_verify_integrity_valid_file(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """verify_integrity should return True when MinIO content matches stored hash."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )

        # Simulate MinIO returning the original content
        mock_response = MagicMock()
        mock_response.read.return_value = sample_file_content
        mock_minio.get_object.return_value = mock_response

        assert file_service.verify_integrity(metadata.file_id) is True

    def test_verify_integrity_tampered_file(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """verify_integrity should return False when MinIO content hash differs."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )

        # Simulate MinIO returning tampered content
        mock_response = MagicMock()
        mock_response.read.return_value = b"TAMPERED CONTENT"
        mock_minio.get_object.return_value = mock_response

        assert file_service.verify_integrity(metadata.file_id) is False


# =============================================================================
# RBAC TESTS
# =============================================================================

class TestRBAC:

    def test_upload_denied_when_rbac_fails(
        self, file_service, mock_minio, sample_file_content
    ):
        """Upload should raise AccessDeniedError when RBAC denies."""
        with patch("server.fs_service.verify_access") as mock:
            mock.return_value = AccessResult(
                allowed=False,
                reason="No permission for file write"
            )

            with pytest.raises(AccessDeniedError):
                file_service.upload_file(
                    file_content=sample_file_content,
                    filename="test.txt",
                    owner_id="user_001",
                    context={"role": Role.STUDENT},
                )

    def test_get_file_denied_when_rbac_fails(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """get_file should raise AccessDeniedError when RBAC denies."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )

        with patch("server.fs_service.verify_access") as mock:
            mock.return_value = AccessResult(
                allowed=False,
                reason="No permission for file read"
            )

            with pytest.raises(AccessDeniedError):
                file_service.get_file(
                    metadata.file_id, "user_002", {"role": Role.STUDENT}
                )


# =============================================================================
# LIST VERSIONS TESTS
# =============================================================================

class TestListVersions:

    def test_list_versions_returns_all(
        self, file_service, mock_minio, mock_rbac_allow, sample_file_content, sample_context
    ):
        """list_versions should return all versions in order."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )

        file_service.update_file(metadata.file_id, b"v2", "user_001", sample_context)
        file_service.update_file(metadata.file_id, b"v3", "user_001", sample_context)

        versions = file_service.list_versions(
            metadata.file_id, "user_001", sample_context
        )

        assert len(versions) == 3
        assert [v.version for v in versions] == [1, 2, 3]
