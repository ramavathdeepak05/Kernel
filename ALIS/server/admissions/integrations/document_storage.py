"""
P14 — Document Storage Integration

Cloud object storage adapter for applicant document uploads (Stage 3)
and any generated files (offer letters, admit cards, receipts).

Supports:
  - AWS S3 (primary)
  - Azure Blob Storage (alternative)
  - Local filesystem (development fallback)

The rest of ALIS uses this adapter via the FileStorageService interface.
All methods are sync-wrapped — Celery tasks call these directly.

When not configured, falls back to local filesystem storage under
ALIS_DATA_DIR/uploads/ so development never breaks.
"""

from __future__ import annotations

import io
import logging
import mimetypes
import os
import shutil
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# =============================================================================
# PROVIDER ENUM
# =============================================================================

class StorageProvider(str, Enum):
    S3 = "S3"
    AZURE_BLOB = "AZURE_BLOB"
    LOCAL = "LOCAL"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class UploadResult:
    """Result of a file upload."""
    success: bool
    storage_key: str             # Full path/key in storage (e.g. org/applicant/doc.pdf)
    storage_url: Optional[str]   # Public or pre-signed URL (None for local)
    provider: str
    size_bytes: int = 0
    content_type: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DownloadResult:
    """Result of a file download."""
    success: bool
    content: Optional[bytes] = None
    content_type: str = ""
    size_bytes: int = 0
    error: Optional[str] = None


@dataclass
class PresignedURL:
    """A pre-signed URL for upload or download."""
    url: str
    expires_in_seconds: int
    method: str  # GET or PUT
    storage_key: str


@dataclass
class FileInfo:
    """Metadata about a file in storage."""
    storage_key: str
    size_bytes: int
    content_type: str
    last_modified: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# DOCUMENT STORAGE CLIENT
# =============================================================================

class DocumentStorageClient:
    """
    Unified cloud storage client for applicant documents.

    Usage:
        client = DocumentStorageClient()

        # Upload a file
        result = client.upload(
            org_id="uuid...",
            applicant_id="uuid...",
            file_name="marksheet_10.pdf",
            content=pdf_bytes,
            content_type="application/pdf",
            doc_type="MARKSHEET_10",
        )

        # Generate pre-signed download URL
        url = client.get_download_url(result.storage_key, expires_in=3600)

        # Download file content
        dl = client.download(result.storage_key)

        # Delete file
        client.delete(result.storage_key)

        # List files for an applicant
        files = client.list_files(org_id="uuid...", applicant_id="uuid...")
    """

    def __init__(self) -> None:
        from server.core.settings import settings
        self._settings = settings
        self._provider = getattr(settings, "storage_provider", "LOCAL").upper()
        self._bucket = getattr(settings, "storage_bucket", "alis-documents")
        self._region = getattr(settings, "storage_region", "ap-south-1")

        # Local storage fallback directory
        data_dir = getattr(settings, "alis_data_dir", "data")
        self._local_root = Path(data_dir) / "uploads"
        self._local_root.mkdir(parents=True, exist_ok=True)

    @property
    def provider(self) -> str:
        return self._provider

    # -------------------------------------------------------------------------
    # UPLOAD
    # -------------------------------------------------------------------------

    def upload(
        self,
        org_id: str,
        applicant_id: str,
        file_name: str,
        content: bytes,
        content_type: str = "",
        doc_type: str = "OTHER",
        metadata: Optional[Dict[str, str]] = None,
    ) -> UploadResult:
        """
        Upload a file to cloud storage.

        Storage key format: {org_id}/{applicant_id}/{doc_type}/{uuid}_{file_name}
        This ensures uniqueness and tenant isolation.
        """
        if not content_type:
            content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"

        # Build storage key
        unique_prefix = uuid4().hex[:8]
        safe_name = file_name.replace(" ", "_").replace("/", "_")
        storage_key = f"{org_id}/{applicant_id}/{doc_type}/{unique_prefix}_{safe_name}"

        file_metadata = {
            "org_id": org_id,
            "applicant_id": applicant_id,
            "doc_type": doc_type,
            "original_filename": file_name,
            **(metadata or {}),
        }

        if self._provider == StorageProvider.S3:
            return self._s3_upload(storage_key, content, content_type, file_metadata)
        elif self._provider == StorageProvider.AZURE_BLOB:
            return self._azure_upload(storage_key, content, content_type, file_metadata)
        else:
            return self._local_upload(storage_key, content, content_type, file_metadata)

    def _s3_upload(
        self, key: str, content: bytes, content_type: str, metadata: Dict[str, str]
    ) -> UploadResult:
        try:
            import boto3
            s3 = boto3.client(
                "s3",
                region_name=self._region,
                aws_access_key_id=getattr(self._settings, "aws_access_key_id", None),
                aws_secret_access_key=getattr(self._settings, "aws_secret_access_key", None),
            )
            s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
                Metadata=metadata,
            )
            url = f"https://{self._bucket}.s3.{self._region}.amazonaws.com/{key}"
            logger.info("S3: uploaded [%s] (%d bytes)", key, len(content))
            return UploadResult(
                success=True,
                storage_key=key,
                storage_url=url,
                provider=StorageProvider.S3,
                size_bytes=len(content),
                content_type=content_type,
                metadata=metadata,
            )
        except Exception as exc:
            logger.error("S3: upload failed — %s", exc)
            return UploadResult(
                success=False,
                storage_key=key,
                storage_url=None,
                provider=StorageProvider.S3,
                error=str(exc),
            )

    def _azure_upload(
        self, key: str, content: bytes, content_type: str, metadata: Dict[str, str]
    ) -> UploadResult:
        try:
            from azure.storage.blob import BlobServiceClient, ContentSettings
            conn_str = self._settings.azure_storage_connection_string
            blob_service = BlobServiceClient.from_connection_string(conn_str)
            container = blob_service.get_container_client(self._bucket)
            blob = container.get_blob_client(key)
            blob.upload_blob(
                content,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type),
                metadata=metadata,
            )
            url = blob.url
            logger.info("Azure: uploaded [%s] (%d bytes)", key, len(content))
            return UploadResult(
                success=True,
                storage_key=key,
                storage_url=url,
                provider=StorageProvider.AZURE_BLOB,
                size_bytes=len(content),
                content_type=content_type,
                metadata=metadata,
            )
        except Exception as exc:
            logger.error("Azure: upload failed — %s", exc)
            return UploadResult(
                success=False,
                storage_key=key,
                storage_url=None,
                provider=StorageProvider.AZURE_BLOB,
                error=str(exc),
            )

    def _local_upload(
        self, key: str, content: bytes, content_type: str, metadata: Dict[str, str]
    ) -> UploadResult:
        try:
            file_path = self._local_root / key
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(content)
            logger.info("Local: stored [%s] (%d bytes)", key, len(content))
            return UploadResult(
                success=True,
                storage_key=key,
                storage_url=f"file://{file_path.resolve()}",
                provider=StorageProvider.LOCAL,
                size_bytes=len(content),
                content_type=content_type,
                metadata=metadata,
            )
        except Exception as exc:
            logger.error("Local: upload failed — %s", exc)
            return UploadResult(
                success=False,
                storage_key=key,
                storage_url=None,
                provider=StorageProvider.LOCAL,
                error=str(exc),
            )

    # -------------------------------------------------------------------------
    # DOWNLOAD
    # -------------------------------------------------------------------------

    def download(self, storage_key: str) -> DownloadResult:
        """Download a file from storage."""
        if self._provider == StorageProvider.S3:
            return self._s3_download(storage_key)
        elif self._provider == StorageProvider.AZURE_BLOB:
            return self._azure_download(storage_key)
        else:
            return self._local_download(storage_key)

    def _s3_download(self, key: str) -> DownloadResult:
        try:
            import boto3
            s3 = boto3.client(
                "s3",
                region_name=self._region,
                aws_access_key_id=getattr(self._settings, "aws_access_key_id", None),
                aws_secret_access_key=getattr(self._settings, "aws_secret_access_key", None),
            )
            response = s3.get_object(Bucket=self._bucket, Key=key)
            content = response["Body"].read()
            return DownloadResult(
                success=True,
                content=content,
                content_type=response.get("ContentType", ""),
                size_bytes=len(content),
            )
        except Exception as exc:
            logger.error("S3: download failed [%s] — %s", key, exc)
            return DownloadResult(success=False, error=str(exc))

    def _azure_download(self, key: str) -> DownloadResult:
        try:
            from azure.storage.blob import BlobServiceClient
            conn_str = self._settings.azure_storage_connection_string
            blob_service = BlobServiceClient.from_connection_string(conn_str)
            blob = blob_service.get_container_client(self._bucket).get_blob_client(key)
            download_stream = blob.download_blob()
            content = download_stream.readall()
            props = blob.get_blob_properties()
            return DownloadResult(
                success=True,
                content=content,
                content_type=props.content_settings.content_type or "",
                size_bytes=len(content),
            )
        except Exception as exc:
            logger.error("Azure: download failed [%s] — %s", key, exc)
            return DownloadResult(success=False, error=str(exc))

    def _local_download(self, key: str) -> DownloadResult:
        try:
            file_path = self._local_root / key
            if not file_path.exists():
                return DownloadResult(success=False, error=f"File not found: {key}")
            content = file_path.read_bytes()
            content_type = mimetypes.guess_type(str(file_path))[0] or ""
            return DownloadResult(
                success=True,
                content=content,
                content_type=content_type,
                size_bytes=len(content),
            )
        except Exception as exc:
            logger.error("Local: download failed [%s] — %s", key, exc)
            return DownloadResult(success=False, error=str(exc))

    # -------------------------------------------------------------------------
    # PRE-SIGNED URLs
    # -------------------------------------------------------------------------

    def get_download_url(
        self, storage_key: str, expires_in: int = 3600
    ) -> Optional[PresignedURL]:
        """
        Generate a pre-signed download URL.
        Only supported for S3 and Azure Blob. Returns None for local storage.
        """
        if self._provider == StorageProvider.S3:
            return self._s3_presigned_url(storage_key, expires_in, "get_object")
        elif self._provider == StorageProvider.AZURE_BLOB:
            return self._azure_presigned_url(storage_key, expires_in, "r")
        else:
            logger.warning("Pre-signed URLs not supported for LOCAL storage")
            return None

    def get_upload_url(
        self, storage_key: str, expires_in: int = 3600
    ) -> Optional[PresignedURL]:
        """
        Generate a pre-signed upload URL for direct browser uploads.
        Reduces server load — the file goes directly from browser to S3/Azure.
        """
        if self._provider == StorageProvider.S3:
            return self._s3_presigned_url(storage_key, expires_in, "put_object")
        else:
            logger.warning("Pre-signed upload URLs only supported for S3")
            return None

    def _s3_presigned_url(
        self, key: str, expires_in: int, method: str
    ) -> Optional[PresignedURL]:
        try:
            import boto3
            s3 = boto3.client(
                "s3",
                region_name=self._region,
                aws_access_key_id=getattr(self._settings, "aws_access_key_id", None),
                aws_secret_access_key=getattr(self._settings, "aws_secret_access_key", None),
            )
            url = s3.generate_presigned_url(
                method,
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            return PresignedURL(
                url=url,
                expires_in_seconds=expires_in,
                method="GET" if method == "get_object" else "PUT",
                storage_key=key,
            )
        except Exception as exc:
            logger.error("S3: pre-signed URL generation failed — %s", exc)
            return None

    def _azure_presigned_url(
        self, key: str, expires_in: int, permission: str
    ) -> Optional[PresignedURL]:
        try:
            from datetime import datetime, timedelta, timezone
            from azure.storage.blob import (
                BlobServiceClient, BlobSasPermissions, generate_blob_sas
            )

            conn_str = self._settings.azure_storage_connection_string
            account_name = self._settings.azure_storage_account_name
            account_key = self._settings.azure_storage_account_key

            sas_token = generate_blob_sas(
                account_name=account_name,
                account_key=account_key,
                container_name=self._bucket,
                blob_name=key,
                permission=BlobSasPermissions(read=(permission == "r")),
                expiry=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            )
            url = f"https://{account_name}.blob.core.windows.net/{self._bucket}/{key}?{sas_token}"
            return PresignedURL(
                url=url,
                expires_in_seconds=expires_in,
                method="GET",
                storage_key=key,
            )
        except Exception as exc:
            logger.error("Azure: SAS token generation failed — %s", exc)
            return None

    # -------------------------------------------------------------------------
    # DELETE
    # -------------------------------------------------------------------------

    def delete(self, storage_key: str) -> bool:
        """
        Delete a file from storage.
        Returns True on success, False on failure. Always logs errors.
        """
        if self._provider == StorageProvider.S3:
            return self._s3_delete(storage_key)
        elif self._provider == StorageProvider.AZURE_BLOB:
            return self._azure_delete(storage_key)
        else:
            return self._local_delete(storage_key)

    def _s3_delete(self, key: str) -> bool:
        try:
            import boto3
            s3 = boto3.client(
                "s3",
                region_name=self._region,
                aws_access_key_id=getattr(self._settings, "aws_access_key_id", None),
                aws_secret_access_key=getattr(self._settings, "aws_secret_access_key", None),
            )
            s3.delete_object(Bucket=self._bucket, Key=key)
            logger.info("S3: deleted [%s]", key)
            return True
        except Exception as exc:
            logger.error("S3: delete failed [%s] — %s", key, exc)
            return False

    def _azure_delete(self, key: str) -> bool:
        try:
            from azure.storage.blob import BlobServiceClient
            conn_str = self._settings.azure_storage_connection_string
            blob_service = BlobServiceClient.from_connection_string(conn_str)
            blob = blob_service.get_container_client(self._bucket).get_blob_client(key)
            blob.delete_blob()
            logger.info("Azure: deleted [%s]", key)
            return True
        except Exception as exc:
            logger.error("Azure: delete failed [%s] — %s", key, exc)
            return False

    def _local_delete(self, key: str) -> bool:
        try:
            file_path = self._local_root / key
            if file_path.exists():
                file_path.unlink()
                logger.info("Local: deleted [%s]", key)
                return True
            else:
                logger.warning("Local: file not found for deletion [%s]", key)
                return False
        except Exception as exc:
            logger.error("Local: delete failed [%s] — %s", key, exc)
            return False

    # -------------------------------------------------------------------------
    # LIST FILES
    # -------------------------------------------------------------------------

    def list_files(
        self, org_id: str, applicant_id: Optional[str] = None
    ) -> List[FileInfo]:
        """
        List all files stored for an org (optionally filtered by applicant).
        """
        prefix = f"{org_id}/"
        if applicant_id:
            prefix = f"{org_id}/{applicant_id}/"

        if self._provider == StorageProvider.S3:
            return self._s3_list(prefix)
        elif self._provider == StorageProvider.AZURE_BLOB:
            return self._azure_list(prefix)
        else:
            return self._local_list(prefix)

    def _s3_list(self, prefix: str) -> List[FileInfo]:
        try:
            import boto3
            s3 = boto3.client(
                "s3",
                region_name=self._region,
                aws_access_key_id=getattr(self._settings, "aws_access_key_id", None),
                aws_secret_access_key=getattr(self._settings, "aws_secret_access_key", None),
            )
            response = s3.list_objects_v2(Bucket=self._bucket, Prefix=prefix, MaxKeys=1000)
            files = []
            for obj in response.get("Contents", []):
                files.append(FileInfo(
                    storage_key=obj["Key"],
                    size_bytes=obj["Size"],
                    content_type="",  # Would need head_object for this
                    last_modified=str(obj.get("LastModified", "")),
                ))
            return files
        except Exception as exc:
            logger.error("S3: list failed [%s] — %s", prefix, exc)
            return []

    def _azure_list(self, prefix: str) -> List[FileInfo]:
        try:
            from azure.storage.blob import BlobServiceClient
            conn_str = self._settings.azure_storage_connection_string
            blob_service = BlobServiceClient.from_connection_string(conn_str)
            container = blob_service.get_container_client(self._bucket)
            files = []
            for blob in container.list_blobs(name_starts_with=prefix):
                files.append(FileInfo(
                    storage_key=blob.name,
                    size_bytes=blob.size or 0,
                    content_type=blob.content_settings.content_type or "",
                    last_modified=str(blob.last_modified) if blob.last_modified else None,
                ))
            return files
        except Exception as exc:
            logger.error("Azure: list failed [%s] — %s", prefix, exc)
            return []

    def _local_list(self, prefix: str) -> List[FileInfo]:
        try:
            search_dir = self._local_root / prefix
            if not search_dir.exists():
                return []
            files = []
            for file_path in search_dir.rglob("*"):
                if file_path.is_file():
                    rel = file_path.relative_to(self._local_root)
                    content_type = mimetypes.guess_type(str(file_path))[0] or ""
                    files.append(FileInfo(
                        storage_key=str(rel).replace("\\", "/"),
                        size_bytes=file_path.stat().st_size,
                        content_type=content_type,
                    ))
            return files
        except Exception as exc:
            logger.error("Local: list failed [%s] — %s", prefix, exc)
            return []
