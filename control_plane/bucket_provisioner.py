"""
Per-Tenant S3 Bucket Provisioner — S5

Each tenant gets an isolated MinIO/S3 bucket:
    Bucket name: alis-tenant-{tenant_id}

Bucket lifecycle:
  - Created during tenant provisioning
  - Versioning enabled (document history)
  - Server-side encryption enabled (AES256 by default, SSE-KMS if configured)
  - Retention/lifecycle policy: move to GLACIER tier after 90 days (optional)
  - Destroyed (or archived to a cold bucket) on tenant deletion

The provisioner uses the boto3-compatible MinIO SDK. In production
(AWS S3), the same API works with real S3 ARNs.

Bucket naming convention:
  alis-tenant-{tenant_id}    e.g. alis-tenant-3fa85f64-5717-...

The bucket name is stored in cp_tenants.bucket_name after provisioning.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _bucket_name(tenant_id: str) -> str:
    """Canonical bucket name for a tenant."""
    return f"alis-tenant-{tenant_id}"


class BucketProvisioner:
    """
    Manages per-tenant MinIO/S3 buckets.

    Uses boto3-compatible API (botocore). Works with:
    - MinIO (self-hosted, docker-compose)
    - AWS S3 (production)
    - Any S3-compatible store (GCS, DigitalOcean Spaces, etc.)
    """

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: str = "us-east-1",
        force_path_style: bool = True,   # required for MinIO
        enable_versioning: bool = True,
        enable_encryption: bool = True,
    ) -> None:
        from control_plane.settings import settings as cp_settings

        self._endpoint = endpoint_url or cp_settings.s3_endpoint_url
        self._access_key = access_key or cp_settings.s3_access_key
        self._secret_key = secret_key or cp_settings.s3_secret_key
        self._region = region or cp_settings.s3_region
        self._force_path_style = force_path_style
        self._versioning = enable_versioning
        self._encryption = enable_encryption

    def _client(self):
        import boto3
        return boto3.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            config=_boto_config(self._force_path_style),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def provision(self, tenant_id: str) -> str:
        """
        Create and configure the tenant bucket.

        Returns the bucket name.
        Idempotent — safe to call if the bucket already exists.
        """
        name = _bucket_name(tenant_id)
        client = self._client()

        # 1. Create bucket (idempotent)
        try:
            if self._region == "us-east-1":
                # boto3 quirk: us-east-1 must NOT pass CreateBucketConfiguration
                client.create_bucket(Bucket=name)
            else:
                client.create_bucket(
                    Bucket=name,
                    CreateBucketConfiguration={"LocationConstraint": self._region},
                )
            logger.info("BucketProvisioner: created bucket %s", name)
        except client.exceptions.BucketAlreadyOwnedByYou:
            logger.debug("BucketProvisioner: bucket %s already exists (owned)", name)
        except client.exceptions.BucketAlreadyExists:
            logger.debug("BucketProvisioner: bucket %s already exists", name)

        # 2. Block all public access
        client.put_public_access_block(
            Bucket=name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )

        # 3. Enable versioning
        if self._versioning:
            client.put_bucket_versioning(
                Bucket=name,
                VersioningConfiguration={"Status": "Enabled"},
            )

        # 4. Enable server-side encryption (AES256)
        if self._encryption:
            client.put_bucket_encryption(
                Bucket=name,
                ServerSideEncryptionConfiguration={
                    "Rules": [{
                        "ApplyServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256",
                        },
                        "BucketKeyEnabled": True,
                    }]
                },
            )

        # 5. Lifecycle policy — transition to GLACIER after 90 days (optional)
        try:
            client.put_bucket_lifecycle_configuration(
                Bucket=name,
                LifecycleConfiguration={
                    "Rules": [{
                        "ID": "alis-archive-policy",
                        "Status": "Enabled",
                        "Filter": {"Prefix": "documents/"},
                        "Transitions": [{
                            "Days": 90,
                            "StorageClass": "GLACIER",
                        }],
                        "NoncurrentVersionTransitions": [{
                            "NoncurrentDays": 30,
                            "StorageClass": "GLACIER",
                        }],
                    }]
                },
            )
        except Exception as exc:
            # MinIO may not support lifecycle in all configs — non-fatal
            logger.debug("BucketProvisioner: lifecycle config skipped (%s)", exc)

        logger.info("BucketProvisioner: bucket %s provisioned (versioning=%s, enc=%s)",
                    name, self._versioning, self._encryption)
        return name

    def destroy(self, tenant_id: str, *, archive_first: bool = True) -> bool:
        """
        Destroy the tenant bucket.

        If `archive_first=True`, copy all objects to the archive bucket
        `alis-archive-{tenant_id}` before deletion (preserves audit trail).
        If `archive_first=False`, the bucket is emptied and deleted immediately.

        Returns True if destroyed, False if bucket did not exist.
        """
        name = _bucket_name(tenant_id)
        client = self._client()

        # Check existence
        try:
            client.head_bucket(Bucket=name)
        except Exception:
            logger.debug("BucketProvisioner: bucket %s does not exist, skipping destroy", name)
            return False

        if archive_first:
            self._archive_to_cold_bucket(client, name, tenant_id)

        # Delete all versions + objects
        _empty_bucket(client, name)
        client.delete_bucket(Bucket=name)
        logger.info("BucketProvisioner: bucket %s destroyed", name)
        return True

    def bucket_name(self, tenant_id: str) -> str:
        return _bucket_name(tenant_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _archive_to_cold_bucket(self, client, source_bucket: str, tenant_id: str) -> None:
        """Copy all objects from source to alis-archive-{tenant_id}."""
        archive_bucket = f"alis-archive-{tenant_id}"
        try:
            client.create_bucket(Bucket=archive_bucket)
        except Exception:
            pass  # already exists

        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=source_bucket):
            for obj in page.get("Contents", []):
                client.copy_object(
                    Bucket=archive_bucket,
                    CopySource={"Bucket": source_bucket, "Key": obj["Key"]},
                    Key=obj["Key"],
                )
        logger.info("BucketProvisioner: archived %s → alis-archive-%s", source_bucket, tenant_id)


def _empty_bucket(client, bucket_name: str) -> None:
    """Delete all objects (all versions) from a bucket."""
    try:
        paginator = client.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=bucket_name):
            objects_to_delete = [
                {"Key": v["Key"], "VersionId": v["VersionId"]}
                for v in page.get("Versions", [])
            ] + [
                {"Key": m["Key"], "VersionId": m["VersionId"]}
                for m in page.get("DeleteMarkers", [])
            ]
            if objects_to_delete:
                client.delete_objects(Bucket=bucket_name, Delete={"Objects": objects_to_delete})
    except Exception:
        # Versioning may not be enabled — fall back to plain object list
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket_name):
            objects = [{"Key": o["Key"]} for o in page.get("Contents", [])]
            if objects:
                client.delete_objects(Bucket=bucket_name, Delete={"Objects": objects})


def _boto_config(force_path_style: bool):
    try:
        from botocore.config import Config
        return Config(s3={"addressing_style": "path" if force_path_style else "auto"})
    except ImportError:
        return None
