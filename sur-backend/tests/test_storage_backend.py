"""get_storage() must honor STORAGE_BACKEND rather than silently substituting
LocalStorage when the configured S3/MinIO/AWS backend fails to construct.
CONTRACTS.md #5: a bad AWS key, wrong bucket, or wrong region must surface
as a startup error -- not as uploads quietly landing on local disk while a
presigned URL handed to the browser points at a bucket that never receives
anything.
"""
from __future__ import annotations

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_caches():
    from app.storage.s3 import get_storage

    get_storage.cache_clear()
    get_settings.cache_clear()
    yield
    get_storage.cache_clear()
    get_settings.cache_clear()


def test_local_backend_returns_local_storage(monkeypatch):
    from app.storage.local import LocalStorage
    from app.storage.s3 import get_storage

    monkeypatch.setenv("STORAGE_BACKEND", "local")
    assert isinstance(get_storage(), LocalStorage)


def test_s3_backend_construction_failure_raises_not_falls_back(monkeypatch):
    """The original bug: any exception constructing S3Storage (bad
    credentials, wrong region, nonexistent bucket) was swallowed and
    LocalStorage returned instead, with only a log line as evidence."""
    import app.storage.s3 as s3_module

    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("STORAGE_ACCESS_KEY", "wrong")
    monkeypatch.setenv("STORAGE_SECRET_KEY", "wrong")

    def _boom():
        raise RuntimeError("InvalidAccessKeyId: the AWS access key does not exist")

    monkeypatch.setattr(s3_module, "S3Storage", _boom)

    with pytest.raises(RuntimeError, match="InvalidAccessKeyId"):
        s3_module.get_storage()


def test_ensure_bucket_passes_location_constraint_outside_us_east_1(monkeypatch):
    """AWS S3 (unlike MinIO/R2) rejects create_bucket for any region other
    than us-east-1 unless CreateBucketConfiguration.LocationConstraint is
    set -- a bucket in ap-southeast-2 would fail to auto-create without it."""
    from botocore.exceptions import ClientError

    from app.storage.s3 import S3Storage

    storage = S3Storage.__new__(S3Storage)
    storage._bucket = "my-bucket"

    calls: list[dict] = []

    class _FakeMeta:
        region_name = "ap-southeast-2"

    class _FakeClient:
        meta = _FakeMeta()

        def head_bucket(self, Bucket):
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket")

        def create_bucket(self, **kwargs):
            calls.append(kwargs)

    storage._client = _FakeClient()
    storage._ensure_bucket()

    assert calls == [
        {"Bucket": "my-bucket", "CreateBucketConfiguration": {"LocationConstraint": "ap-southeast-2"}}
    ]


def test_ensure_bucket_omits_location_constraint_in_us_east_1(monkeypatch):
    from botocore.exceptions import ClientError

    from app.storage.s3 import S3Storage

    storage = S3Storage.__new__(S3Storage)
    storage._bucket = "my-bucket"

    calls: list[dict] = []

    class _FakeMeta:
        region_name = "us-east-1"

    class _FakeClient:
        meta = _FakeMeta()

        def head_bucket(self, Bucket):
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadBucket")

        def create_bucket(self, **kwargs):
            calls.append(kwargs)

    storage._client = _FakeClient()
    storage._ensure_bucket()

    assert calls == [{"Bucket": "my-bucket"}]


def test_real_aws_endpoint_uses_regional_host_not_global():
    """boto3 defaults to the legacy global s3.amazonaws.com for virtual-hosted
    addressing, which returns a plain 400 against "opt-in" regions
    (ap-south-2/Hyderabad, ap-southeast-3/4, eu-south-2, eu-central-2,
    me-central-1, ...) -- confirmed live against a real ap-south-2 bucket.
    The regional endpoint works for every region, so it's always built
    explicitly rather than left to boto3's default resolution."""
    from app.storage.s3 import _real_aws_endpoint

    assert _real_aws_endpoint("ap-south-2") == "https://s3.ap-south-2.amazonaws.com"
    assert _real_aws_endpoint("us-east-1") == "https://s3.us-east-1.amazonaws.com"


def test_s3storage_uses_regional_endpoint_when_none_configured(monkeypatch):
    """STORAGE_ENDPOINT_URL unset (real AWS) must resolve to the region's own
    endpoint, not None/boto3's default global host."""
    import boto3

    from app.storage.s3 import S3Storage

    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("STORAGE_REGION", "ap-south-2")
    monkeypatch.delenv("STORAGE_ENDPOINT_URL", raising=False)
    monkeypatch.delenv("STORAGE_PUBLIC_ENDPOINT_URL", raising=False)
    get_settings.cache_clear()

    seen_endpoints: list[str | None] = []
    real_client = boto3.client

    def _spy_client(service_name, **kwargs):
        seen_endpoints.append(kwargs.get("endpoint_url"))
        return real_client(service_name, **kwargs)

    monkeypatch.setattr(boto3, "client", _spy_client)
    storage = S3Storage.__new__(S3Storage)
    storage._ensure_bucket = lambda: None  # no network in this test
    S3Storage.__init__(storage)

    assert seen_endpoints == [
        "https://s3.ap-south-2.amazonaws.com",
        "https://s3.ap-south-2.amazonaws.com",
    ]


def test_s3storage_uses_configured_endpoint_for_minio(monkeypatch):
    """An explicit STORAGE_ENDPOINT_URL (MinIO/R2) must NOT be overridden by
    the real-AWS regional-endpoint logic."""
    import boto3

    from app.storage.s3 import S3Storage

    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    monkeypatch.setenv("STORAGE_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("STORAGE_PUBLIC_ENDPOINT_URL", "http://localhost:9000")
    get_settings.cache_clear()

    seen_endpoints: list[str | None] = []
    real_client = boto3.client

    def _spy_client(service_name, **kwargs):
        seen_endpoints.append(kwargs.get("endpoint_url"))
        return real_client(service_name, **kwargs)

    monkeypatch.setattr(boto3, "client", _spy_client)
    storage = S3Storage.__new__(S3Storage)
    storage._ensure_bucket = lambda: None
    S3Storage.__init__(storage)

    assert seen_endpoints == ["http://minio:9000", "http://localhost:9000"]
