"""Pydantic request/response models for the DBYT API."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class YouTubeInfoRequest(BaseModel):
    url: str = Field(..., description="A YouTube URL (watch, youtu.be, or shorts)")


class YouTubeInfoResponse(BaseModel):
    valid: bool
    video_id: Optional[str] = None
    title: Optional[str] = None
    channel: Optional[str] = None
    duration: Optional[float] = None
    thumbnail: Optional[str] = None
    suggested_project_name: Optional[str] = None
    error: Optional[str] = None


class DubbingRequest(BaseModel):
    """Request to start a dubbing job from a YouTube URL or an uploaded file."""

    source: Literal["youtube", "upload"] = "youtube"
    youtube_url: Optional[str] = None
    upload_id: Optional[str] = None  # reference to a previously uploaded file

    project_name: Optional[str] = None  # auto-filled from the video title when empty
    target_language: str = "ar"  # e.g. ar, fr, en, es, de ...
    engine: Literal["edge", "elevenlabs", "bark", "xtts"] = "edge"
    voice: Optional[str] = None  # optional voice override
    keep_background: bool = True  # keep original audio ducked under the new voice
    preserve_emotions: bool = True  # map detected emotion -> prosody


class JobStatusResponse(BaseModel):
    job_id: str
    status: Literal["queued", "downloading", "transcribing", "translating",
                    "synthesizing", "mixing", "done", "error"]
    progress: int = 0
    message: str = ""
    project_name: Optional[str] = None
    output_url: Optional[str] = None
    error: Optional[str] = None
