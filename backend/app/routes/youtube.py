"""YouTube metadata endpoint — powers the auto-filled project name and the
green "valid link" indicator in the UI."""
from __future__ import annotations

from fastapi import APIRouter

from ..schemas import YouTubeInfoRequest, YouTubeInfoResponse
from ..services import youtube

router = APIRouter(prefix="/api/youtube", tags=["youtube"])


@router.post("/info", response_model=YouTubeInfoResponse)
async def info(req: YouTubeInfoRequest) -> YouTubeInfoResponse:
    if not youtube.is_valid_youtube_url(req.url):
        return YouTubeInfoResponse(valid=False, error="Invalid YouTube URL")

    try:
        meta = youtube.fetch_metadata(req.url)
    except Exception as exc:  # noqa: BLE001
        return YouTubeInfoResponse(valid=False, error=str(exc))

    return YouTubeInfoResponse(**meta)
