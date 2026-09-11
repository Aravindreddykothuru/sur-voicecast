from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.storage.base import StorageBackend


class LocalStorage(StorageBackend):
    """Local filesystem storage backend for development without MinIO/S3."""

    def __init__(self, root_dir: str = "./data/storage") -> None:
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        safe_key = key.replace("/", os.sep).lstrip(os.sep)
        path = self.root / safe_key
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def presigned_put_url(self, key: str, content_type: str, expires_in: int = 3600) -> str:
        # For local dev, return a mock upload endpoint or direct key
        return f"/api/storage/upload/{key}"

    def presigned_get_url(self, key: str, expires_in: int = 3600) -> str:
        return f"/api/storage/files/{key}"

    def upload_file(self, key: str, local_path: str, content_type: str | None = None) -> None:
        target = self._resolve_path(key)
        shutil.copyfile(local_path, target)

    def download_file(self, key: str, local_path: str) -> None:
        target = self._resolve_path(key)
        if target.exists():
            shutil.copyfile(target, local_path)

    def exists(self, key: str) -> bool:
        return self._resolve_path(key).exists()

    def delete(self, key: str) -> None:
        target = self._resolve_path(key)
        if target.exists():
            target.unlink()

    def get_size(self, key: str) -> int:
        target = self._resolve_path(key)
        if not target.exists():
            raise FileNotFoundError(f"no object at key {key!r}")
        return target.stat().st_size
