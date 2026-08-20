"""YouTube helpers: URL validation, metadata fetching and media download.

Uses `yt-dlp` under the hood. These functions are shared by the API
(auto-fill project name, green-link validation) and the dubbing pipeline.
"""
from __future__ import annotations

import os
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


_PLAYER_CLIENTS = ["android", "tv", "mweb", "ios", "web"]

# When browser cookies are present, the WEB client is the correct one
# (browser cookies are meant for web requests). Try web FIRST.
_PLAYER_CLIENTS_WITH_COOKIES = ["web", "android", "tv", "mweb", "ios"]

# Real browser User-Agent — some player clients reject the default python UA.
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

# Optional cookies file path (set via env DBYT_YOUTUBE_COOKIES or the standard
# ~/.cache/yt-dlp/youtube/cookies.txt).
_COOKIES_PATH = os.environ.get("DBYT_YOUTUBE_COOKIES") or os.path.expanduser(
    "~/.cache/yt-dlp/youtube/cookies.txt"
)


def _try_extract(url: str, download: bool, out_dir: Optional[Path] = None, prefer_audio: bool = True):
    """Try yt-dlp across several player clients; return (info, filename)."""
    import yt_dlp

    has_cookies = os.path.exists(_COOKIES_PATH)
    clients = _PLAYER_CLIENTS_WITH_COOKIES if has_cookies else _PLAYER_CLIENTS

    last_err = None
    for client in clients:
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestaudio/best" if prefer_audio else "best",
            "extractor_args": {"youtube": {"player_client": [client]}},
            "http_headers": {"User-Agent": _BROWSER_UA},
        }
        if has_cookies:
            opts["cookiefile"] = _COOKIES_PATH
        if download:
            opts["outtmpl"] = str(out_dir / "%(id)s.%(ext)s")
            if prefer_audio:
                opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "192",
                }]
            else:
                opts["merge_output_format"] = "mp4"
        else:
            opts["skip_download"] = True

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=download)
            filename = ydl.prepare_filename(info) if download else None
            return info, filename
        except Exception as exc:
            last_err = exc
            print(f"[youtube] client={client} failed: {str(exc)[:120]}")
    raise last_err


def fetch_metadata(url: str) -> dict:
    """Return video metadata without downloading the media."""
    video_id = extract_video_id(url)
    if not video_id:
        return {"valid": False, "error": "Invalid YouTube URL"}

    try:
        info, _ = _try_extract(url, download=False)
    except Exception as exc:
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
    """Download the best available audio (or video) for a YouTube URL."""
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        filename = _download_via_frontend(url, out_dir, prefer_audio)
        print("[youtube] downloaded via Invidious/Piped front-end ✓")
        return Path(filename)
    except Exception as exc:
        print(f"[youtube] front-ends failed ({str(exc)[:120]}); trying yt-dlp…")

    info, filename = _try_extract(url, download=True, out_dir=out_dir, prefer_audio=prefer_audio)

    if prefer_audio and not Path(filename).exists():
        filename = str(Path(filename).with_suffix(".m4a"))
    return Path(filename)


_INSTANCES = [
    "https://inv.nadeko.net",
    "https://invidious.f5.si",
    "https://yewtu.be",
    "https://invidious.nerdvpn.de",
    "https://pipedapi.kavin.rocks",
    "https://api.piped.private.coffee",
]


def _download_via_frontend(url: str, out_dir: Path, prefer_audio: bool) -> str:
    """Download via an Invidious/Piped API instance (proxies YouTube)."""
    import json
    import urllib.request

    video_id = extract_video_id(url)
    if not video_id:
        raise RuntimeError(f"Invalid YouTube URL: {url}")

    last_err = None
    for base in _INSTANCES:
        try:
            api = f"{base}/streams/{video_id}"
            req = urllib.request.Request(api, headers={"User-Agent": "DBYT/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                streams = json.loads(resp.read())

            if prefer_audio:
                audios = [s for s in streams.get("audioStreams", [])]
                best = max(audios, key=lambda s: s.get("bitrate", 0))
            else:
                videos = [s for s in streams.get("videoStreams", [])]
                best = max(videos, key=lambda s: s.get("quality", ""))
            file_url = best["url"]

            ext = "m4a" if prefer_audio else "mp4"
            dest = out_dir / f"{video_id}.{ext}"
            req2 = urllib.request.Request(file_url, headers={"User-Agent": "DBYT/1.0"})
            with urllib.request.urlopen(req2, timeout=600) as r, open(dest, "wb") as f:
                while True:
                    chunk = r.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
            return str(dest)
        except Exception as exc:
            last_err = exc
    raise RuntimeError(f"All Invidious/Piped instances failed: {last_err}")
