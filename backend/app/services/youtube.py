"""YouTube metadata and media download helpers.

The implementation intentionally keeps metadata extraction separate from format
selection. YouTube frequently changes which streams are exposed to each player
client; asking for a media format while only requesting metadata can therefore
fail before the actual download even starts.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

_YT_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/|/v/)([A-Za-z0-9_-]{11})"
)


def extract_video_id(url: str) -> Optional[str]:
    """Extract the 11-character YouTube video id from common URL shapes."""
    if not url:
        return None
    match = _YT_ID_RE.search(url.strip())
    return match.group(1) if match else None


def is_valid_youtube_url(url: str) -> bool:
    return extract_video_id(url) is not None


def _slugify(title: str, max_len: int = 60) -> str:
    """Turn a video title into a filesystem/URL-safe project name."""
    slug = re.sub(r"[^\w\s-]", "", title or "", flags=re.UNICODE)
    slug = re.sub(r"\s+", " ", slug).strip()
    slug = slug.replace(" ", "-")
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug[:max_len].strip("-") or "project"


# Embedded clients often remain available when the browser client is challenged.
# Keep them first so an expired cookie cannot block an otherwise public video.
_PLAYER_CLIENTS = [
    "android_vr",
    "tv_embedded",
    "android",
    "web",
    "web_embedded",
    "mweb",
    "ios",
]
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_COOKIES_PATH = os.environ.get("DBYT_YOUTUBE_COOKIES") or os.path.expanduser(
    "~/.cache/yt-dlp/youtube/cookies.txt"
)


def _has_usable_cookies(path: str | os.PathLike[str]) -> bool:
    """Return true only when a Netscape cookie file contains cookie rows.

    GitHub Actions creates the file from a secret. If the secret is missing or
    empty, treating the header-only file as authenticated makes yt-dlp choose a
    less reliable client order and produces confusing diagnostics.
    """
    try:
        cookie_path = Path(path)
        if not cookie_path.is_file() or cookie_path.stat().st_size == 0:
            return False
        with cookie_path.open("r", encoding="utf-8", errors="replace") as handle:
            return any(
                line.strip() and not line.lstrip().startswith("#")
                for line in handle
            )
    except OSError:
        return False


def _downloaded_file(
    info: dict,
    prepared_filename: Optional[str],
    out_dir: Path,
    prefer_audio: bool,
) -> Path:
    """Resolve the file created after yt-dlp post-processing/merging."""
    candidates: list[Path] = []
    if prepared_filename:
        prepared = Path(prepared_filename)
        candidates.extend(
            [prepared, prepared.with_suffix(".mp4"), prepared.with_suffix(".m4a")]
        )

    video_id = info.get("id") or ""
    if video_id:
        suffixes = (".m4a", ".mp3", ".webm", ".opus", ".wav") if prefer_audio else (
            ".mp4", ".mkv", ".webm", ".mov", ".avi"
        )
        candidates.extend(out_dir / f"{video_id}{suffix}" for suffix in suffixes)

    for candidate in candidates:
        if candidate.is_file() and candidate.stat().st_size > 0:
            return candidate

    # This also handles an unusual container extension selected by a future
    # yt-dlp release while avoiding .part and temporary files.
    if video_id:
        discovered = sorted(
            (
                path
                for path in out_dir.glob(f"{video_id}.*")
                if path.is_file() and path.stat().st_size > 0 and path.suffix != ".part"
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if discovered:
            return discovered[0]

    expected = prepared_filename or str(out_dir / f"{video_id or 'download'}.media")
    raise FileNotFoundError(f"yt-dlp completed but output file was not found: {expected}")


def _try_extract(
    url: str,
    download: bool,
    out_dir: Optional[Path] = None,
    prefer_audio: bool = True,
):
    """Try yt-dlp across player clients; return ``(info, filename)``.

    For metadata requests no format selector is supplied. This is important:
    selecting ``bestaudio`` during metadata-only extraction can fail when a
    player client exposes metadata but not that particular stream.
    """
    import yt_dlp

    if download and out_dir is None:
        raise ValueError("out_dir is required when download=True")
    if download:
        out_dir.mkdir(parents=True, exist_ok=True)

    has_cookies = _has_usable_cookies(_COOKIES_PATH)
    clients = _PLAYER_CLIENTS
    last_error: Optional[Exception] = None

    for client in clients:
        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extractor_args": {"youtube": {"player_client": [client]}},
            "http_headers": {"User-Agent": _BROWSER_UA},
        }
        # Embedded clients are intentionally tried without browser cookies.
        # This keeps an expired secret from turning a public video into a
        # sign-in failure; browser clients still receive the cookie when useful.
        if has_cookies and client not in {"tv_embedded", "web_embedded"}:
            options["cookiefile"] = _COOKIES_PATH
        if download:
            options["format"] = (
                "ba/b" if prefer_audio else "bv*[height<=1080]+ba/b[height<=1080]/b"
            )
            options["outtmpl"] = str(out_dir / "%(id)s.%(ext)s")
            if prefer_audio:
                options["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "192",
                }]
            else:
                options["merge_output_format"] = "mp4"
        else:
            options["skip_download"] = True
            # Metadata does not need a media format. Flat extraction prevents
            # a missing player stream from becoming a false "invalid URL".
            options["extract_flat"] = True

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=download)
                prepared_filename = ydl.prepare_filename(info) if download else None
            return info, prepared_filename
        except Exception as exc:  # noqa: BLE001 - try the next client
            last_error = exc
            print(f"[youtube] client={client} failed: {str(exc)[:160]}")

    if last_error is not None:
        raise last_error
    raise RuntimeError("yt-dlp could not select a YouTube player client")


def _fetch_oembed_metadata(url: str, video_id: str) -> Optional[dict]:
    """Fetch public title/author metadata without requesting player streams."""
    endpoint = "https://www.youtube.com/oembed?" + urllib.parse.urlencode({
        "url": url,
        "format": "json",
    })
    request = urllib.request.Request(endpoint, headers={"User-Agent": _BROWSER_UA})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read())
    except Exception:
        return None

    title = data.get("title") or ""
    return {
        "valid": True,
        "video_id": video_id,
        "title": title,
        "channel": data.get("author_name") or "",
        "duration": None,
        "thumbnail": data.get("thumbnail_url") or "",
        "suggested_project_name": _slugify(title),
    }


def fetch_metadata(url: str) -> dict:
    """Return video metadata without selecting or downloading a media format."""
    video_id = extract_video_id(url)
    if not video_id:
        return {"valid": False, "error": "Invalid YouTube URL"}

    try:
        info, _ = _try_extract(url, download=False, prefer_audio=False)
    except Exception as exc:
        fallback = _fetch_oembed_metadata(url, video_id)
        if fallback:
            print(f"[youtube] player metadata unavailable ({str(exc)[:120]}); using oEmbed")
            return fallback
        return {
            "valid": False,
            "video_id": video_id,
            "error": f"Could not fetch video: {exc}",
        }

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
    """Download media with yt-dlp and return the actual postprocessed file."""
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        info, prepared_filename = _try_extract(
            url, download=True, out_dir=out_dir, prefer_audio=prefer_audio
        )
        return _downloaded_file(info, prepared_filename, out_dir, prefer_audio)
    except Exception as exc:
        print(f"[youtube] yt-dlp failed ({str(exc)[:160]}); trying front-end fallback…")

    # Front-end fallback is retained for audio-only jobs, where a single audio
    # stream is sufficient. A video-only front-end stream would silently remove
    # the original soundtrack, so fail clearly instead of producing a broken dub.
    if not prefer_audio:
        raise RuntimeError(
            "yt-dlp could not download the video; refusing a video-only front-end "
            "fallback because dubbing requires the original audio"
        )
    return Path(_download_via_frontend(url, out_dir, prefer_audio=True))


_INSTANCES = [
    "https://inv.nadeko.net",
    "https://invidious.f5.si",
    "https://yewtu.be",
    "https://invidious.nerdvpn.de",
    "https://pipedapi.kavin.rocks",
    "https://api.piped.private.coffee",
]


def _download_via_frontend(url: str, out_dir: Path, prefer_audio: bool) -> str:
    """Download a single audio stream through an Invidious/Piped instance."""
    import json
    import urllib.request

    video_id = extract_video_id(url)
    if not video_id:
        raise RuntimeError(f"Invalid YouTube URL: {url}")

    last_error: Optional[Exception] = None
    for base in _INSTANCES:
        try:
            api = f"{base}/streams/{video_id}"
            request = urllib.request.Request(api, headers={"User-Agent": "DBYT/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                streams = json.loads(response.read())

            audio_streams = streams.get("audioStreams", [])
            if not audio_streams:
                raise RuntimeError("front-end returned no audio streams")
            best = max(audio_streams, key=lambda stream: stream.get("bitrate", 0))
            file_url = best["url"]
            ext = "m4a" if prefer_audio else "mp4"
            destination = out_dir / f"{video_id}.{ext}"
            request = urllib.request.Request(file_url, headers={"User-Agent": "DBYT/1.0"})
            with urllib.request.urlopen(request, timeout=600) as response, destination.open("wb") as handle:
                while chunk := response.read(1024 * 256):
                    handle.write(chunk)
            return str(destination)
        except Exception as exc:  # noqa: BLE001 - try the next instance
            last_error = exc

    raise RuntimeError(f"All Invidious/Piped instances failed: {last_error}")


__all__ = [
    "download_media",
    "extract_video_id",
    "fetch_metadata",
    "is_valid_youtube_url",
]
