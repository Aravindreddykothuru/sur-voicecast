from abc import ABC, abstractmethod


class StorageBackend(ABC):
    """Everything the pipeline needs from object storage, behind one small
    interface -- swap S3 for R2/MinIO/GCS by implementing this, nothing else
    changes."""

    @abstractmethod
    def presigned_put_url(self, key: str, content_type: str, expires_in: int = 3600) -> str: ...

    @abstractmethod
    def presigned_get_url(self, key: str, expires_in: int = 3600) -> str: ...

    @abstractmethod
    def upload_file(self, key: str, local_path: str, content_type: str | None = None) -> None: ...

    @abstractmethod
    def download_file(self, key: str, local_path: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def get_size(self, key: str) -> int:
        """Size in bytes of the object at `key`. Used to enforce
        Settings.max_upload_mb server-side at /upload/confirm -- the client
        reported a size once when it uploaded, but only the storage backend's
        own answer is trusted for enforcement. Raises if the key doesn't
        exist (never returns 0 as a stand-in)."""
        ...
