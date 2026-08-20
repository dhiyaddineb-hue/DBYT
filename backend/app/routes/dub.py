"""Dubbing endpoints: start a job, poll status, download the result."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..schemas import DubbingRequest, JobStatusResponse
from ..services.jobs import jobs
from ..services.youtube import fetch_metadata

router = APIRouter(prefix="/api", tags=["dubbing"])


@router.post("/dub", response_model=JobStatusResponse)
async def start_dub(req: DubbingRequest) -> JobStatusResponse:
    params = {
        "source": req.source,
        "youtube_url": req.youtube_url,
        "target_language": req.target_language,
        "engine": req.engine,
        "voice": req.voice,
        "keep_background": req.keep_background,
        "preserve_emotions": req.preserve_emotions,
        "granularity": req.granularity,
        "lip_sync": req.lip_sync,
        "project_name": req.project_name,
    }

    if req.source == "youtube":
        if not req.youtube_url:
            raise HTTPException(400, "YouTube URL is required")
        # Auto-fill project name from the video title when not provided
        if not req.project_name:
            meta = fetch_metadata(req.youtube_url)
            params["project_name"] = meta.get("suggested_project_name") or "project"
            params["source_language"] = None
    else:  # upload
        if not req.upload_id:
            raise HTTPException(400, "upload_id is required")
        from ..config import settings

        upload_dir = settings.uploads_dir / req.upload_id
        matches = list(upload_dir.glob("source.*"))
        if not matches:
            raise HTTPException(404, "Uploaded file not found")
        params["upload_path"] = str(matches[0])
        if not params["project_name"]:
            params["project_name"] = req.upload_id

    job = jobs.create(params)
    return JobStatusResponse(**job.to_dict())


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def status(job_id: str) -> JobStatusResponse:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JobStatusResponse(**job.to_dict())


@router.get("/results/{job_id}/download")
async def download(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if not job or not job.output_path:
        raise HTTPException(404, "Result not ready")
    path = Path(job.output_path)
    if not path.exists():
        raise HTTPException(404, "Result file missing")
    return FileResponse(path, media_type="application/octet-stream",
                        filename=f"{job.project_name or job_id}{path.suffix}")
