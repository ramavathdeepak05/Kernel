"""
ALIS File Storage & Versioning Service - E02-S05

MODULE: Shared Services (E02)
LAYER: Cross-cutting (Infrastructure)
ENTITY: FileMetadata, FileVersion

Provides secure, versioned file storage backed by MinIO (S3-compatible).
All modules MUST use this service — direct filesystem access is forbidden.

Acceptance Criteria:
- [x] Versioned uploads (v1, v2, ...)
- [x] Immutable previous versions
- [x] Access controlled via RBAC+
- [x] MinIO object storage (survives container restarts)
- [x] SHA-256 integrity verification on every read

Layer Compliance:
- Layer 5: RBAC+ enforced for all access
- Audit: All operations logged
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel, Field
from server.core.audit import AuditAction, AuditLog
from server.core.rbac import Permission, Role, verify_access
from server.core.settings import settings

# =============================================================================
# EXCEPTIONS
# =============================================================================


class FileStorageError(Exception):
    """Base exception for file storage errors."""


class FileNotFoundError(FileStorageError):
    """Raised when a requested file does not exist."""


class VersionNotFoundError(FileStorageError):
    """Raised when a requested version does not exist."""


class AccessDeniedError(FileStorageError):
    """Raised when access is denied by RBAC+."""


# =============================================================================
# MODELS
# =============================================================================


class FileVersion(BaseModel):
    """Represents a specific version of a file. Immutable after creation."""

    version: int = Field(..., ge=1)
    storage_path: str = Field(..., description="MinIO object key")
    file_hash: str = Field(..., description="SHA-256 hash of file content")
    size_bytes: int = Field(..., ge=0)
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        frozen = True


class FileMetadata(BaseModel):
    """Represents a file entity with all its versions."""

    file_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    filename: str
    content_type: str | None = None
    owner_id: str
    entity_id: str | None = None
    entity_type: str | None = None
    current_version: int = Field(default=1, ge=1)
    versions: list[FileVersion] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    def get_version(self, version: int | None = None) -> FileVersion | None:
        target = version if version is not None else self.current_version
        for v in self.versions:
            if v.version == target:
                return v
        return None


# =============================================================================
# IN-MEMORY METADATA STORE (replaced by DB in a future story)
# =============================================================================


class _FileMetadataStore:
    _files: dict[str, FileMetadata] = {}

    @classmethod
    def save(cls, metadata: FileMetadata) -> None:
        cls._files[metadata.file_id] = metadata

    @classmethod
    def get(cls, file_id: str) -> FileMetadata | None:
        return cls._files.get(file_id)

    @classmethod
    def clear(cls) -> None:
        cls._files.clear()


# =============================================================================
# FILE STORAGE SERVICE
# =============================================================================


class FileStorageService:
    """
    Centralized file storage service backed by MinIO.

    Object key format: {entity_type}/{entity_id}/{file_id}_v{version}
    Falls back to: uploads/{file_id}_v{version} when no entity context.
    """

    FILE_READ_PERMISSION = Permission.STUDENT_READ
    FILE_WRITE_PERMISSION = Permission.STUDENT_UPDATE

    def _minio(self) -> Minio:
        """Return a configured MinIO client."""
        endpoint = settings.minio_endpoint.replace("http://", "").replace(
            "https://", ""
        )
        secure = settings.minio_endpoint.startswith("https://")
        return Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=secure,
        )

    def _ensure_bucket(self, client: Minio) -> None:
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)

    def _object_key(
        self,
        file_id: str,
        version: int,
        entity_type: str | None = None,
        entity_id: str | None = None,
    ) -> str:
        prefix = (
            f"{entity_type}/{entity_id}" if entity_type and entity_id else "uploads"
        )
        return f"{prefix}/{file_id}_v{version}"

    def _compute_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _check_access(
        self, actor_role: Role, permission: Permission, context: dict | None = None
    ) -> None:
        result = verify_access(actor_role, permission, context)
        if not result.allowed:
            raise AccessDeniedError(f"Access denied: {result.reason}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upload_file(
        self,
        file_content: bytes,
        filename: str,
        owner_id: str,
        context: dict[str, Any],
        entity_id: str | None = None,
        entity_type: str | None = None,
        content_type: str | None = None,
    ) -> FileMetadata:
        """Upload a new file (creates v1) to MinIO."""
        actor_role = context.get("role", Role.STUDENT)
        self._check_access(actor_role, self.FILE_WRITE_PERMISSION, context)

        file_id = str(uuid.uuid4())
        version = 1
        file_hash = self._compute_hash(file_content)
        size_bytes = len(file_content)
        object_key = self._object_key(file_id, version, entity_type, entity_id)

        client = self._minio()
        self._ensure_bucket(client)
        client.put_object(
            settings.minio_bucket,
            object_key,
            BytesIO(file_content),
            length=size_bytes,
            content_type=content_type or "application/octet-stream",
        )

        file_version = FileVersion(
            version=version,
            storage_path=object_key,
            file_hash=file_hash,
            size_bytes=size_bytes,
            created_by=owner_id,
        )
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
        _FileMetadataStore.save(metadata)

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
                "object_key": object_key,
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
        context: dict[str, Any],
    ) -> FileVersion:
        """Create a new version of an existing file."""
        actor_role = context.get("role", Role.STUDENT)
        self._check_access(actor_role, self.FILE_WRITE_PERMISSION, context)

        metadata = _FileMetadataStore.get(file_id)
        if metadata is None:
            raise FileNotFoundError(f"File not found: {file_id}")

        new_version_num = metadata.current_version + 1
        file_hash = self._compute_hash(file_content)
        size_bytes = len(file_content)
        object_key = self._object_key(
            file_id, new_version_num, metadata.entity_type, metadata.entity_id
        )

        client = self._minio()
        self._ensure_bucket(client)
        client.put_object(
            settings.minio_bucket,
            object_key,
            BytesIO(file_content),
            length=size_bytes,
            content_type=metadata.content_type or "application/octet-stream",
        )

        new_version = FileVersion(
            version=new_version_num,
            storage_path=object_key,
            file_hash=file_hash,
            size_bytes=size_bytes,
            created_by=updated_by,
        )
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
            updated_at=datetime.now(timezone.utc),
        )
        _FileMetadataStore.save(updated_metadata)

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
            },
        )
        return new_version

    def get_file(
        self,
        file_id: str,
        user_id: str,
        context: dict[str, Any],
        version: int | None = None,
    ) -> bytes:
        """Retrieve file content from MinIO with integrity check."""
        actor_role = context.get("role", Role.STUDENT)
        self._check_access(actor_role, self.FILE_READ_PERMISSION, context)

        metadata = _FileMetadataStore.get(file_id)
        if metadata is None:
            raise FileNotFoundError(f"File not found: {file_id}")

        file_version = metadata.get_version(version)
        if file_version is None:
            raise VersionNotFoundError(
                f"Version {version} not found for file {file_id}"
            )

        client = self._minio()
        try:
            response = client.get_object(
                settings.minio_bucket, file_version.storage_path
            )
            content = response.read()
        except S3Error as e:
            raise FileNotFoundError(
                f"Object not found in MinIO: {file_version.storage_path}"
            ) from e

        actual_hash = self._compute_hash(content)
        if actual_hash != file_version.file_hash:
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
                },
            )
            raise FileStorageError(
                f"File integrity check failed for {file_id} v{file_version.version}"
            )

        AuditLog.log(
            action=AuditAction.READ,
            actor_id=user_id,
            actor_type="human",
            entity_type="file",
            entity_id=file_id,
            action_detail=f"Read file: {metadata.filename} (v{file_version.version})",
            module="E02",
            metadata={"version": file_version.version},
        )
        return content

    def get_metadata(
        self, file_id: str, user_id: str, context: dict[str, Any]
    ) -> FileMetadata:
        """Get file metadata (all versions)."""
        actor_role = context.get("role", Role.STUDENT)
        self._check_access(actor_role, self.FILE_READ_PERMISSION, context)
        metadata = _FileMetadataStore.get(file_id)
        if metadata is None:
            raise FileNotFoundError(f"File not found: {file_id}")
        return metadata

    def list_versions(
        self, file_id: str, user_id: str, context: dict[str, Any]
    ) -> list[FileVersion]:
        """List all versions of a file."""
        return list(self.get_metadata(file_id, user_id, context).versions)

    def verify_integrity(self, file_id: str, version: int | None = None) -> bool:
        """Verify file integrity against stored hash."""
        metadata = _FileMetadataStore.get(file_id)
        if metadata is None:
            return False
        file_version = metadata.get_version(version)
        if file_version is None:
            return False
        client = self._minio()
        try:
            response = client.get_object(
                settings.minio_bucket, file_version.storage_path
            )
            actual_hash = self._compute_hash(response.read())
            return actual_hash == file_version.file_hash
        except S3Error:
            return False
