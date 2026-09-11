from __future__ import annotations

from functools import lru_cache

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import get_settings
from app.storage.base import StorageBackend


def _real_aws_endpoint(region: str) -> str:
    """The region-qualified endpoint, not the legacy global `s3.amazonaws.com`.

    boto3 defaults to the global host for virtual-hosted addressing, which
    silently 400s against "opt-in" regions (ap-south-2/Hyderabad,
    ap-southeast-3/4, eu-south-2, eu-central-2, me-central-1, ...) -- those
    only accept requests signed against and sent to their own regional
    endpoint. Always building the regional endpoint explicitly works for
    every AWS region, not just the legacy ones, so there's no reason to rely
    on boto3's ambiguous default here.
    """
    return f"https://s3.{region}.amazonaws.com"


class S3Storage(StorageBackend):
    """Works against AWS S3, Cloudflare R2, or the bundled MinIO container
    unchanged -- they all speak the S3 API. `storage_public_endpoint_url`
    exists because in docker-compose the API/worker reach MinIO at
    `http://minio:9000` but a presigned URL handed to a browser must instead
    point at `http://localhost:9000`.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.storage_bucket
        # None (real AWS) -> the region's own endpoint, not boto3's default.
        # An explicit value (MinIO/R2/etc.) is used untouched.
        endpoint = settings.storage_endpoint_url or _real_aws_endpoint(settings.storage_region)
        self._public_endpoint = settings.storage_public_endpoint_url or endpoint

        client_kwargs = dict(
            endpoint_url=endpoint,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            region_name=settings.storage_region,
            use_ssl=settings.storage_use_ssl,
            config=BotoConfig(signature_version="s3v4"),
        )
        self._client = boto3.client("s3", **client_kwargs)

        # Public-facing client only used to *generate* presigned URLs whose
        # host the browser can actually reach; requests still land on the
        # same bucket/credentials.
        public_kwargs = dict(client_kwargs, endpoint_url=self._public_endpoint)
        self._public_client = boto3.client("s3", **public_kwargs)

        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            # Real AWS S3 rejects create_bucket with an explicit
            # LocationConstraint for us-east-1 (it's the implicit default)
            # but REQUIRES one for every other region -- omitting it there
            # raises IllegalLocationConstraintException. MinIO/R2 ignore the
            # kwarg either way, so this is safe for all three targets.
            region = self._client.meta.region_name
            if region and region != "us-east-1":
                self._client.create_bucket(
                    Bucket=self._bucket,
                    CreateBucketConfiguration={"LocationConstraint": region},
                )
            else:
                self._client.create_bucket(Bucket=self._bucket)

    def presigned_put_url(self, key: str, content_type: str, expires_in: int = 3600) -> str:
        return self._public_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=expires_in,
        )

    def presigned_get_url(self, key: str, expires_in: int = 3600) -> str:
        return self._public_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def upload_file(self, key: str, local_path: str, content_type: str | None = None) -> None:
        extra = {"ContentType": content_type} if content_type else {}
        self._client.upload_file(local_path, self._bucket, key, ExtraArgs=extra)

    def download_file(self, key: str, local_path: str) -> None:
        self._client.download_file(self._bucket, key, local_path)

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def get_size(self, key: str) -> int:
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as e:
            raise FileNotFoundError(f"no object at key {key!r}") from e
        return int(head["ContentLength"])


@lru_cache
def get_storage() -> StorageBackend:
    """STORAGE_BACKEND is an explicit operator choice -- honor it or fail
    loud, never silently substitute. A bad AWS key, wrong bucket, or wrong
    region under STORAGE_BACKEND=s3 must surface as a startup error, not as
    uploads silently landing on local disk while presigned URLs point at a
    bucket that never receives anything. See CONTRACTS.md #5."""
    settings = get_settings()
    if getattr(settings, "storage_backend", "local") == "local":
        from app.storage.local import LocalStorage
        return LocalStorage()
    return S3Storage()

