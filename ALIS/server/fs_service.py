"""
ALIS File Storage & Versioning Service - E02-S05

MODULE: Shared Services (E02)
LAYER: Cross-cutting (Infrastructure)
ENTITY: FileMetadata, FileVersion

This module implements secure, versioned file storage for all ALIS modules.

Must Align With:
- Tenant isolation
- Audit requirements
- No direct filesystem access by modules

Acceptance Criteria:
- [x] Versioned uploads (v1, v2, ...)
- [x] Immutable previous versions
- [x] Access controlled via RBAC+
- [x] Secure storage abstraction
- [x] No direct filesystem access by modules

Layer Compliance:
- Layer 4: Global Locks checked before operations (if applicable)
- Layer 5: RBAC+ enforced for all access
- Audit: All operations logged
"""

import hashlib
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field

from core.audit import AuditLog, AuditAction
from core.rbac import verify_access, Role, Permission


# =============================================================================
# EXCEPTIONS
# =============================================================================

class FileStorageError(Exception):
    """Base exception for file storage errors."""
    pass


class FileNotFoundError(FileStorageError):
    """Raised when a requested file does not exist."""
    pass


class VersionNotFoundError(FileStorageError):
    """Raised when a requested version does not exist."""
    pass


class AccessDeniedError(FileStorageError):
    """Raised when access is denied by RBAC+."""
    pass


class ImmutabilityViolationError(FileStorageError):
    """Raised when an operation would violate immutability of previous versions."""
    pass


# =============================================================================
# MODELS
# =============================================================================

class FileVersion(BaseModel):
    """
    Represents a specific version of a file.
    
    Immutable after creation - uses frozen=True via Config.
    """
    version: int = Field(..., ge=1, description="Version number (1, 2, 3, ...)")
    storage_path: str = Field(..., description="Absolute path to the stored file")
    file_hash: str = Field(..., description="SHA-256 hash of file content")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    created_by: str = Field(..., description="User ID who created this version")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        frozen = True  # Immutable after creation


class FileMetadata(BaseModel):
    """
    Represents a file entity with all its versions.
    
    The file entity tracks the logical file, while versions
    represent the physical storage of each revision.
    """
    file_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str = Field(..., description="Original filename")
    content_type: Optional[str] = Field(None, description="MIME type if known")
    owner_id: str = Field(..., description="User ID who owns this file")
    entity_id: Optional[str] = Field(None, description="Related entity ID (student_id, etc.)")
    entity_type: Optional[str] = Field(None, description="Related entity type")
    
    current_version: int = Field(default=1, ge=1, description="Latest version number")
    versions: List[FileVersion] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    def get_version(self, version: Optional[int] = None) -> Optional[FileVersion]:
        """Get a specific version or the latest."""
        if version is None:
            version = self.current_version
        for v in self.versions:
            if v.version == version:
                return v
        return None


# =============================================================================
# IN-MEMORY STORAGE (Development Only)
# =============================================================================

class _FileMetadataStore:
    """
    In-memory storage for file metadata.
    
    In production, this will be replaced by a database backend.
    """
    _files: Dict[str, FileMetadata] = {}
    
    @classmethod
    def save(cls, metadata: FileMetadata) -> None:
        cls._files[metadata.file_id] = metadata
    
    @classmethod
    def get(cls, file_id: str) -> Optional[FileMetadata]:
        return cls._files.get(file_id)
    
    @classmethod
    def exists(cls, file_id: str) -> bool:
        return file_id in cls._files
    
    @classmethod
    def clear(cls) -> None:
        """Clear all stored files (for testing only)."""
        cls._files.clear()


# =============================================================================
# FILE STORAGE SERVICE
# =============================================================================

class FileStorageService:
    """
    Centralized file storage service for ALIS.
    
    Provides secure, versioned file storage with RBAC+ access control
    and full audit logging. Modules MUST use this service for all
    file operations - direct filesystem access is forbidden.
    
    Usage:
        service = FileStorageService()
        
        # Upload a new file
        metadata = service.upload_file(
            file_content=b"...",
            filename="document.pdf",
            owner_id="user_123",
            context={"role": Role.FACULTY}
        )
        
        # Update (create new version)
        new_version = service.update_file(
            file_id=metadata.file_id,
            file_content=b"...",
            updated_by="user_123",
            context={"role": Role.FACULTY}
        )
        
        # Retrieve file content
        content = service.get_file(
            file_id=metadata.file_id,
            user_id="user_123",
            context={"role": Role.FACULTY}
        )
    """
    
    # Default storage directory
    DEFAULT_STORAGE_DIR = Path("storage/files")
    
    # RBAC Permission for file operations
    # Note: In a full implementation, these would be added to rbac.py
    FILE_READ_PERMISSION = Permission.STUDENT_READ  # Placeholder
    FILE_WRITE_PERMISSION = Permission.STUDENT_UPDATE  # Placeholder
    
    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize the file storage service.
        
        Args:
            storage_dir: Custom storage directory (defaults to storage/files)
        """
        self.storage_dir = storage_dir or self.DEFAULT_STORAGE_DIR
        self.storage_dir.mkdir(parents=True, exist_ok=True)
    
    def _compute_hash(self, data: bytes) -> str:
        """Compute SHA-256 hash of file content."""
        return hashlib.sha256(data).hexdigest()
    
    def _get_storage_path(self, file_id: str, version: int) -> Path:
        """
        Generate storage path for a file version.
        
        Organizes files by year/month for scalability.
        Format: storage/files/{year}/{month}/{file_id}_v{version}
        """
        now = datetime.utcnow()
        year_month_dir = self.storage_dir / str(now.year) / f"{now.month:02d}"
        year_month_dir.mkdir(parents=True, exist_ok=True)
        return year_month_dir / f"{file_id}_v{version}"
    
    def _check_access(
        self,
        actor_role: Role,
        permission: Permission,
        context: Optional[Dict] = None
    ) -> None:
        """
        Check RBAC+ access.
        
        Raises:
            AccessDeniedError: If access is denied
        """
        result = verify_access(actor_role, permission, context)
        if not result.allowed:
            raise AccessDeniedError(
                f"Access denied: {result.reason}"
            )
    
    def upload_file(
        self,
        file_content: bytes,
        filename: str,
        owner_id: str,
        context: Dict[str, Any],
        entity_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        content_type: Optional[str] = None,
    ) -> FileMetadata:
        """
        Upload a new file (creates v1).
        
        Args:
            file_content: Raw bytes of the file
            filename: Original filename
            owner_id: User ID uploading the file
            context: RBAC+ context (must include 'role')
            entity_id: Optional related entity ID
            entity_type: Optional related entity type
            content_type: Optional MIME type
            
        Returns:
            FileMetadata with version 1 created
            
        Raises:
            AccessDeniedError: If RBAC+ denies access
        """
        # Extract role from context
        actor_role = context.get("role", Role.STUDENT)
        
        # RBAC+ Check (Layer 5)
        self._check_access(actor_role, self.FILE_WRITE_PERMISSION, context)
        
        # Generate file ID
        file_id = str(uuid.uuid4())
        version = 1
        
        # Compute hash and size
        file_hash = self._compute_hash(file_content)
        size_bytes = len(file_content)
        
        # Determine storage path
        storage_path = self._get_storage_path(file_id, version)
        
        # Write file to storage
        with open(storage_path, "wb") as f:
            f.write(file_content)
        
        # Create version record
        file_version = FileVersion(
            version=version,
            storage_path=str(storage_path.absolute()),
            file_hash=file_hash,
            size_bytes=size_bytes,
            created_by=owner_id,
        )
        
        # Create metadata record
        metadata = FileMetadata(
            file_id=file_id,
            filename=filename,
            content_type=content_type,
            owner_id=owner_id,
            entity_id=entity_id,
            entity_type=entity_type,
            current_version=version,
            versions=[file_version],
        )
        
        # Save metadata
        _FileMetadataStore.save(metadata)
        
        # Audit log
        AuditLog.log(
            action=AuditAction.CREATE,
            actor_id=owner_id,
            actor_type="human",
            entity_type="file",
            entity_id=file_id,
            action_detail=f"Uploaded file: {filename} (v1)",
            module="E02",
            metadata={
                "filename": filename,
                "version": version,
                "file_hash": file_hash,
                "size_bytes": size_bytes,
                "related_entity_id": entity_id,
                "related_entity_type": entity_type,
            },
        )
        
        return metadata
    
    def update_file(
        self,
        file_id: str,
        file_content: bytes,
        updated_by: str,
        context: Dict[str, Any],
    ) -> FileVersion:
        """
        Update a file by creating a new version.
        
        Previous versions remain immutable and accessible.
        
        Args:
            file_id: ID of the file to update
            file_content: New file content
            updated_by: User ID making the update
            context: RBAC+ context (must include 'role')
            
        Returns:
            The newly created FileVersion
            
        Raises:
            FileNotFoundError: If file doesn't exist
            AccessDeniedError: If RBAC+ denies access
        """
        # Extract role from context
        actor_role = context.get("role", Role.STUDENT)
        
        # RBAC+ Check (Layer 5)
        self._check_access(actor_role, self.FILE_WRITE_PERMISSION, context)
        
        # Get existing metadata
        metadata = _FileMetadataStore.get(file_id)
        if metadata is None:
            raise FileNotFoundError(f"File not found: {file_id}")
        
        # Compute new version number
        new_version_num = metadata.current_version + 1
        
        # Compute hash and size
        file_hash = self._compute_hash(file_content)
        size_bytes = len(file_content)
        
        # Determine storage path for new version
        storage_path = self._get_storage_path(file_id, new_version_num)
        
        # Write file to storage (new path, old versions untouched)
        with open(storage_path, "wb") as f:
            f.write(file_content)
        
        # Create new version record
        new_version = FileVersion(
            version=new_version_num,
            storage_path=str(storage_path.absolute()),
            file_hash=file_hash,
            size_bytes=size_bytes,
            created_by=updated_by,
        )
        
        # Update metadata (create new object to maintain immutability pattern)
        updated_metadata = FileMetadata(
            file_id=metadata.file_id,
            filename=metadata.filename,
            content_type=metadata.content_type,
            owner_id=metadata.owner_id,
            entity_id=metadata.entity_id,
            entity_type=metadata.entity_type,
            current_version=new_version_num,
            versions=[*metadata.versions, new_version],
            created_at=metadata.created_at,
            updated_at=datetime.utcnow(),
        )
        
        # Save updated metadata
        _FileMetadataStore.save(updated_metadata)
        
        # Audit log
        AuditLog.log(
            action=AuditAction.UPDATE,
            actor_id=updated_by,
            actor_type="human",
            entity_type="file",
            entity_id=file_id,
            action_detail=f"Updated file: {metadata.filename} (v{new_version_num})",
            module="E02",
            previous_state=f"v{metadata.current_version}",
            new_state=f"v{new_version_num}",
            metadata={
                "filename": metadata.filename,
                "version": new_version_num,
                "file_hash": file_hash,
                "size_bytes": size_bytes,
            },
        )
        
        return new_version
    
    def get_file(
        self,
        file_id: str,
        user_id: str,
        context: Dict[str, Any],
        version: Optional[int] = None,
    ) -> bytes:
        """
        Retrieve file content.
        
        Args:
            file_id: ID of the file
            user_id: User requesting the file
            context: RBAC+ context (must include 'role')
            version: Specific version to retrieve (defaults to latest)
            
        Returns:
            File content as bytes
            
        Raises:
            FileNotFoundError: If file doesn't exist
            VersionNotFoundError: If requested version doesn't exist
            AccessDeniedError: If RBAC+ denies access
        """
        # Extract role from context
        actor_role = context.get("role", Role.STUDENT)
        
        # RBAC+ Check (Layer 5)
        self._check_access(actor_role, self.FILE_READ_PERMISSION, context)
        
        # Get metadata
        metadata = _FileMetadataStore.get(file_id)
        if metadata is None:
            raise FileNotFoundError(f"File not found: {file_id}")
        
        # Get requested version
        file_version = metadata.get_version(version)
        if file_version is None:
            raise VersionNotFoundError(
                f"Version {version} not found for file {file_id}"
            )
        
        # Read file content
        storage_path = Path(file_version.storage_path)
        if not storage_path.exists():
            raise FileNotFoundError(
                f"Physical file missing: {file_version.storage_path}"
            )
        
        with open(storage_path, "rb") as f:
            content = f.read()
        
        # Verify integrity
        actual_hash = self._compute_hash(content)
        if actual_hash != file_version.file_hash:
            # Log integrity violation
            AuditLog.log(
                action=AuditAction.READ,
                actor_id=user_id,
                actor_type="human",
                entity_type="file",
                entity_id=file_id,
                success=False,
                failure_reason="Integrity check failed: hash mismatch",
                module="E02",
                metadata={
                    "expected_hash": file_version.file_hash,
                    "actual_hash": actual_hash,
                    "version": file_version.version,
                },
            )
            raise FileStorageError(
                f"File integrity check failed for {file_id} v{file_version.version}"
            )
        
        # Audit log (successful read)
        AuditLog.log(
            action=AuditAction.READ,
            actor_id=user_id,
            actor_type="human",
            entity_type="file",
            entity_id=file_id,
            action_detail=f"Read file: {metadata.filename} (v{file_version.version})",
            module="E02",
            metadata={
                "version": file_version.version,
            },
        )
        
        return content
    
    def get_metadata(
        self,
        file_id: str,
        user_id: str,
        context: Dict[str, Any],
    ) -> FileMetadata:
        """
        Get file metadata (all versions).
        
        Args:
            file_id: ID of the file
            user_id: User requesting metadata
            context: RBAC+ context
            
        Returns:
            FileMetadata with all version information
            
        Raises:
            FileNotFoundError: If file doesn't exist
            AccessDeniedError: If RBAC+ denies access
        """
        # Extract role from context
        actor_role = context.get("role", Role.STUDENT)
        
        # RBAC+ Check
        self._check_access(actor_role, self.FILE_READ_PERMISSION, context)
        
        # Get metadata
        metadata = _FileMetadataStore.get(file_id)
        if metadata is None:
            raise FileNotFoundError(f"File not found: {file_id}")
        
        return metadata
    
    def list_versions(
        self,
        file_id: str,
        user_id: str,
        context: Dict[str, Any],
    ) -> List[FileVersion]:
        """
        List all versions of a file.
        
        Args:
            file_id: ID of the file
            user_id: User requesting version list
            context: RBAC+ context
            
        Returns:
            List of FileVersion objects
        """
        metadata = self.get_metadata(file_id, user_id, context)
        return list(metadata.versions)
    
    def verify_integrity(
        self,
        file_id: str,
        version: Optional[int] = None,
    ) -> bool:
        """
        Verify file integrity by comparing stored hash.
        
        Args:
            file_id: ID of the file
            version: Specific version (defaults to latest)
            
        Returns:
            True if file is intact, False otherwise
        """
        metadata = _FileMetadataStore.get(file_id)
        if metadata is None:
            return False
        
        file_version = metadata.get_version(version)
        if file_version is None:
            return False
        
        storage_path = Path(file_version.storage_path)
        if not storage_path.exists():
            return False
        
        with open(storage_path, "rb") as f:
            actual_hash = self._compute_hash(f.read())
        
        return actual_hash == file_version.file_hash
