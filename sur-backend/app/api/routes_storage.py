"""Serves LocalStorage's presigned URLs when STORAGE_BACKEND=local.

`app/storage/local.py` hands out URLs shaped like `/api/storage/upload/{key}`
and `/api/storage/files/{key}` (standing in for what a real presigned S3/MinIO
URL would do) but nothing served them -- this router is that implementation,
so local dev (the default: `STORAGE_BACKEND=local`, no MinIO required) can
actually round-trip an upload without a real object store. It's a no-op
(404) when a real backend (S3/MinIO) is configured, since those URLs point
straight at the object store instead.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response

from app.config import get_settings

router = APIRouter(prefix="/api/storage", tags=["storage"])

_ROOT = Path("./data/storage")


def _resolve(key: str) -> Path:
    # Mirrors LocalStorage._resolve_path -- keeps both sides of the same
    # on-disk layout in agreement without importing the storage singleton.
    safe_key = key.strip("/")
    path = (_ROOT / safe_key).resolve()
    if _ROOT.resolve() not in path.parents and path != _ROOT.resolve():
        raise HTTPException(400, detail="Invalid storage key")
    return path


def _require_local_backend() -> None:
    if get_settings().storage_backend != "local":
        raise HTTPException(404, detail="Local storage endpoints are disabled")


@router.put("/upload/{key:path}")
async def upload_local_file(key: str, request: Request) -> Response:
    _require_local_backend()
    target = _resolve(key)
    target.parent.mkdir(parents=True, exist_ok=True)
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    written = 0
    with target.open("wb") as f:
        async for chunk in request.stream():
            written += len(chunk)
            if written > max_bytes:
                f.close()
                target.unlink(missing_ok=True)
                raise HTTPException(
                    413, detail=f"Upload exceeds max_upload_mb ({get_settings().max_upload_mb}MB)"
                )
            f.write(chunk)
    return Response(status_code=200)


@router.get("/files/{key:path}")
async def get_local_file(key: str) -> FileResponse:
    _require_local_backend()
    target = _resolve(key)
    if not target.exists() or not target.is_file():
        raise HTTPException(404, detail="File not found")
    return FileResponse(target)
