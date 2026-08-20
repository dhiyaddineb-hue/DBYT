"""File upload endpoint — the user can dub a local video, not just YouTube."""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..config import settings

router = APIRouter(prefix="/api/upload", tags=["upload"])

ALLOWED = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4a", ".mp3", ".wav", ".flac", ".ogg"}


@router.post("")
async def upload(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(400, f"Unsupported file type: {suffix or 'unknown'}")

    upload_id = uuid.uuid4().hex[:12]
    dest_dir = settings.uploads_dir / upload_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"source{suffix}"

    size = 0
    max_bytes = settings.max_upload_mb * 1024 * 1024
    with dest.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB limit")
            f.write(chunk)

    return {"upload_id": upload_id, "filename": file.filename, "size": size,
            "path": str(dest)}
