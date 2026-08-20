"""YouTube helpers: URL validation, metadata fetching and media download.

Uses `yt-dlp` under the hood. These functions are shared by the API
(auto-fill project name, green-link validation) and the dubbing pipeline.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_YT_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/|/v/)([A-Za-z0-9_-]{11})"
)


def extract_video_id(url: str) -> Optional[str]:
    """Extract the 11-char YouTube video id from any common URL shape."""
    if not url:
        return None
    m = _YT_ID_RE.search(url.strip())
    return m.group(1) if m else None


def is_valid_youtube_url(url: str) -> bool:
    return extract_video_id(url) is not None


def _slugify(title: str, max_len: int = 60) -> str:
    """Turn a video title into a filesystem/URL-safe project name."""
    slug = re.sub(r"[^\w\s-]", "", title or "", flags=re.UNICODE)
    slug = re.sub(r"\s+", " ", slug).strip()
    slug = slug.replace(" ", "-")
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:max_len].strip("-") or "project"


def fetch_metadata(url: str) -> dict:
    """Return video metadata without downloading the media.

    Returns a dict with keys: valid, video_id, title, channel, duration,
    thumbnail, suggested_project_name. Raises on network/availability errors.
    """
    import yt_dlp

    video_id = extract_video_id(url)
    if not video_id:
        return {"valid": False, "error": "Invalid YouTube URL"}

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001 — surface a clean message
        return {"valid": False, "video_id": video_id, "error": f"Could not fetch video: {exc}"}

    title = info.get("title") or ""
    return {
        "valid": True,
        "video_id": video_id,
        "title": title,
        "channel": info.get("channel") or info.get("uploader") or "",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail") or "",
        "suggested_project_name": _slugify(title),
    }


def download_media(url: str, out_dir: Path, prefer_audio: bool = True) -> Path:
    """Download the best available audio (or video) for a YouTube URL.

    Returns the path to the downloaded file (audio as .m4a by default).
    """
    import yt_dlp

    out_dir.mkdir(parents=True, exist_ok=True)
    if prefer_audio:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "192",
                }
            ],
        }
    else:
        opts = {
            "format": "best[height<=1080]/best",
            "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "merge_output_format": "mp4",
        }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    # After FFmpegExtractAudio the extension changes to m4a
    if prefer_audio and not Path(filename).exists():
        filename = str(Path(filename).with_suffix(".m4a"))
    return Path(filename)
