"""
Unit Tests for File Storage & Versioning Service (E02-S05)

Tests:
- File upload (v1 creation)
- File update (v2 creation, immutability of v1)
- Retrieval (latest vs specific version)
- Integrity check (hash verification)
- RBAC enforcement (mocked roles)
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add server to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))

from fs_service import (
    FileStorageService,
    FileMetadata,
    FileVersion,
    FileNotFoundError,
    VersionNotFoundError,
    AccessDeniedError,
    _FileMetadataStore,
)
from core.rbac import Role, AccessResult


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_storage_dir():
    """Create a temporary storage directory for tests."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def file_service(temp_storage_dir):
    """Create a FileStorageService with temp storage."""
    # Clear in-memory store before each test
    _FileMetadataStore.clear()
    return FileStorageService(storage_dir=temp_storage_dir)


@pytest.fixture
def mock_rbac_allow():
    """Mock RBAC to always allow access."""
    with patch("fs_service.verify_access") as mock:
        mock.return_value = AccessResult(allowed=True)
        yield mock


@pytest.fixture
def sample_file_content():
    """Sample file content for testing."""
    return b"This is a test document for ALIS E02-S05."


@pytest.fixture
def sample_context():
    """Sample RBAC context."""
    return {"role": Role.FACULTY}


# =============================================================================
# UPLOAD TESTS
# =============================================================================

class TestFileUpload:
    """Tests for file upload functionality."""
    
    def test_upload_creates_v1(
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
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
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
    ):
        """Uploaded file should have correct SHA-256 hash."""
        import hashlib
        expected_hash = hashlib.sha256(sample_file_content).hexdigest()
        
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        
        assert metadata.versions[0].file_hash == expected_hash
    
    def test_upload_stores_size(
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
    ):
        """Uploaded file should have correct size."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        
        assert metadata.versions[0].size_bytes == len(sample_file_content)
    
    def test_upload_creates_physical_file(
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
    ):
        """Upload should create physical file on disk."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        
        storage_path = Path(metadata.versions[0].storage_path)
        assert storage_path.exists()
        assert storage_path.read_bytes() == sample_file_content


# =============================================================================
# UPDATE (VERSIONING) TESTS
# =============================================================================

class TestFileUpdate:
    """Tests for file update/versioning functionality."""
    
    def test_update_creates_v2(
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
    ):
        """Updating a file should create version 2."""
        # Upload v1
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        
        # Update to v2
        new_content = b"Updated content for version 2"
        new_version = file_service.update_file(
            file_id=metadata.file_id,
            file_content=new_content,
            updated_by="user_001",
            context=sample_context,
        )
        
        assert new_version.version == 2
        
        # Check metadata is updated
        updated_metadata = file_service.get_metadata(
            metadata.file_id, "user_001", sample_context
        )
        assert updated_metadata.current_version == 2
        assert len(updated_metadata.versions) == 2
    
    def test_update_preserves_v1_immutability(
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
    ):
        """Updating should NOT modify the original v1 file."""
        # Upload v1
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        v1_path = Path(metadata.versions[0].storage_path)
        v1_hash = metadata.versions[0].file_hash
        
        # Update to v2
        new_content = b"Completely different content"
        file_service.update_file(
            file_id=metadata.file_id,
            file_content=new_content,
            updated_by="user_001",
            context=sample_context,
        )
        
        # Verify v1 is unchanged
        assert v1_path.exists()
        assert v1_path.read_bytes() == sample_file_content
        
        # Verify v1 can still be retrieved with original content
        v1_content = file_service.get_file(
            metadata.file_id, "user_001", sample_context, version=1
        )
        assert v1_content == sample_file_content
    
    def test_update_nonexistent_file_raises_error(
        self, file_service, mock_rbac_allow, sample_context
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
    """Tests for file retrieval functionality."""
    
    def test_get_file_returns_latest_by_default(
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
    ):
        """get_file() without version should return latest."""
        # Upload v1
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        
        # Update to v2
        v2_content = b"Version 2 content"
        file_service.update_file(
            file_id=metadata.file_id,
            file_content=v2_content,
            updated_by="user_001",
            context=sample_context,
        )
        
        # Get without version (should return v2)
        content = file_service.get_file(
            metadata.file_id, "user_001", sample_context
        )
        
        assert content == v2_content
    
    def test_get_file_specific_version(
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
    ):
        """get_file() with version should return that specific version."""
        # Upload v1
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        
        # Update to v2
        file_service.update_file(
            file_id=metadata.file_id,
            file_content=b"Version 2",
            updated_by="user_001",
            context=sample_context,
        )
        
        # Get v1 specifically
        v1_content = file_service.get_file(
            metadata.file_id, "user_001", sample_context, version=1
        )
        
        assert v1_content == sample_file_content
    
    def test_get_nonexistent_version_raises_error(
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
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
    """Tests for file integrity verification."""
    
    def test_verify_integrity_valid_file(
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
    ):
        """verify_integrity should return True for valid file."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        
        assert file_service.verify_integrity(metadata.file_id) is True
    
    def test_verify_integrity_tampered_file(
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
    ):
        """verify_integrity should return False for tampered file."""
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        
        # Tamper with the file
        storage_path = Path(metadata.versions[0].storage_path)
        storage_path.write_bytes(b"TAMPERED CONTENT")
        
        assert file_service.verify_integrity(metadata.file_id) is False


# =============================================================================
# RBAC TESTS
# =============================================================================

class TestRBAC:
    """Tests for RBAC enforcement."""
    
    def test_upload_denied_when_rbac_fails(
        self, file_service, sample_file_content
    ):
        """Upload should raise AccessDeniedError when RBAC denies."""
        with patch("fs_service.verify_access") as mock:
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
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
    ):
        """get_file should raise AccessDeniedError when RBAC denies."""
        # First upload with allowed RBAC
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        
        # Now try to read with denied RBAC
        with patch("fs_service.verify_access") as mock:
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
    """Tests for listing file versions."""
    
    def test_list_versions_returns_all(
        self, file_service, mock_rbac_allow, sample_file_content, sample_context
    ):
        """list_versions should return all versions."""
        # Upload v1
        metadata = file_service.upload_file(
            file_content=sample_file_content,
            filename="test.txt",
            owner_id="user_001",
            context=sample_context,
        )
        
        # Create v2 and v3
        file_service.update_file(
            metadata.file_id, b"v2", "user_001", sample_context
        )
        file_service.update_file(
            metadata.file_id, b"v3", "user_001", sample_context
        )
        
        versions = file_service.list_versions(
            metadata.file_id, "user_001", sample_context
        )
        
        assert len(versions) == 3
        assert [v.version for v in versions] == [1, 2, 3]
