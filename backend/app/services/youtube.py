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


# Clients are ordered from browser-based clients that can obtain PO tokens
# through WPC, to clients that may work without account cookies.
_PLAYER_CLIENTS = [
    "web_safari",
    "mweb",
    "web",
    "android_vr",
    "web_embedded",
    "tv_embedded",
    "ios",
]
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
_COOKIES_PATH = os.environ.get("DBYT_YOUTUBE_COOKIES") or os.path.expanduser(
    "~/.cache/yt-dlp/youtube/cookies.txt"
)
_WPC_BROWSER = os.environ.get("DBYT_WPC_BROWSER") or "/usr/bin/google-chrome"


def _configured_cobalt() -> tuple[str, str]:
    """Return an explicitly authorized Cobalt endpoint and API key.

    Hosted Cobalt instances are not treated as anonymous public infrastructure.
    Both values must be supplied by the operator through environment variables;
    cookies are never forwarded to Cobalt.
    """
    endpoint = os.environ.get("DBYT_COBALT_URL", "").strip().rstrip("/")
    api_key = os.environ.get("DBYT_COBALT_API_KEY", "").strip()
    return endpoint, api_key


def _configured_frontends() -> tuple[str, ...]:
    """Return explicitly trusted Invidious-compatible endpoints.

    There is deliberately no baked-in public-instance list. Public instances
    are unstable and may be operated by unknown parties; an operator must
    opt in by setting DBYT_INVIDIOUS_INSTANCES.
    """
    raw = os.environ.get("DBYT_INVIDIOUS_INSTANCES", "")
    return tuple(value.strip().rstrip("/") for value in re.split(r"[,\n]", raw) if value.strip())


def _configured_proxies() -> tuple[str, ...]:
    """Read optional proxies without requiring one for normal operation.

    The value may be a single URL or a comma/newline-separated list. Proxy
    values stay in memory and are never written to logs or generated files.
    """
    raw = os.environ.get("DBYT_YOUTUBE_PROXIES", "")
    return tuple(value.strip() for value in re.split(r"[,\n]", raw) if value.strip())


def _has_usable_cookies(path: str | os.PathLike[str]) -> bool:
    """Return true only when a Netscape cookie file contains cookie rows."""
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


def _cobalt_headers(api_url: str, api_key: str, target_url: str) -> dict[str, str]:
    """Build headers without leaking a Cobalt key to a redirected origin."""
    headers = {"User-Agent": _BROWSER_UA}
    api_host = urllib.parse.urlparse(api_url).netloc
    target_host = urllib.parse.urlparse(target_url).netloc
    if api_key and api_host and target_host == api_host:
        headers["Authorization"] = f"Api-Key {api_key}"
    return headers


def _download_url(url: str, destination: Path, headers: Optional[dict[str, str]] = None) -> None:
    """Stream a remote media URL to disk without buffering the whole file."""
    request = urllib.request.Request(url, headers=headers or {"User-Agent": _BROWSER_UA})
    with urllib.request.urlopen(request, timeout=900) as response, destination.open("wb") as handle:
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"Media endpoint returned an empty file for {destination.name}")


def _safe_suffix(filename: str, fallback: str) -> str:
    suffix = Path(urllib.parse.urlparse(filename).path).suffix.lower()
    return suffix if suffix in {".mp3", ".m4a", ".wav", ".ogg", ".opus", ".mp4", ".webm", ".mkv"} else fallback


def _download_via_cobalt(
    url: str,
    out_dir: Path,
    prefer_audio: bool,
    endpoint: str,
    api_key: str,
) -> Path:
    """Download through an operator-authorized Cobalt processing instance."""
    if urllib.parse.urlparse(endpoint).scheme not in {"http", "https"}:
        raise RuntimeError("DBYT_COBALT_URL must be an http(s) URL")

    video_id = extract_video_id(url)
    if not video_id:
        raise RuntimeError(f"Invalid YouTube URL: {url}")

    payload = {
        "url": url,
        "downloadMode": "audio" if prefer_audio else "auto",
        "audioFormat": "mp3" if prefer_audio else "best",
        "videoQuality": "max",
        "youtubeVideoCodec": "h264",
        "youtubeVideoContainer": "mp4",
        "filenameStyle": "basic",
        "alwaysProxy": True,
    }
    request = urllib.request.Request(
        f"{endpoint}/",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            **_cobalt_headers(endpoint, api_key, endpoint),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read())
    except Exception as exc:  # noqa: BLE001 - caller will try the next route
        raise RuntimeError(f"Cobalt request failed: {type(exc).__name__}") from exc

    status = data.get("status")
    if status == "error":
        error = data.get("error") or {}
        raise RuntimeError(f"Cobalt returned {error.get('code') or 'an unknown error'}")

    if status in {"redirect", "tunnel"} and data.get("url"):
        filename = str(data.get("filename") or "")
        suffix = _safe_suffix(filename, ".mp3" if prefer_audio else ".mp4")
        destination = out_dir / f"{video_id}{suffix}"
        _download_url(data["url"], destination, _cobalt_headers(endpoint, api_key, data["url"]))
        return destination

    if status == "local-processing":
        tunnels = [value for value in data.get("tunnel", []) if isinstance(value, str) and value]
        if not tunnels:
            raise RuntimeError("Cobalt returned local-processing without tunnels")
        if prefer_audio or data.get("type") == "audio":
            destination = out_dir / f"{video_id}.mp3"
            _download_url(tunnels[-1], destination, _cobalt_headers(endpoint, api_key, tunnels[-1]))
            return destination
        if len(tunnels) < 2:
            raise RuntimeError("Cobalt returned incomplete local-processing tunnels")
        import subprocess

        video_path = out_dir / f"{video_id}.video"
        audio_path = out_dir / f"{video_id}.audio"
        output_path = out_dir / f"{video_id}.mp4"
        try:
            _download_url(tunnels[0], video_path, _cobalt_headers(endpoint, api_key, tunnels[0]))
            _download_url(tunnels[1], audio_path, _cobalt_headers(endpoint, api_key, tunnels[1]))
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", str(video_path), "-i", str(audio_path),
                    "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
                    str(output_path),
                ],
                check=True,
            )
        finally:
            video_path.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
        return output_path

    raise RuntimeError(f"Cobalt returned unsupported status {status or 'missing'}")


def _try_extract(
    url: str,
    download: bool,
    out_dir: Optional[Path] = None,
    prefer_audio: bool = True,
):
    """Try WPC-enabled yt-dlp across configured proxies and player clients."""
    import yt_dlp

    if download and out_dir is None:
        raise ValueError("out_dir is required when download=True")
    if download:
        out_dir.mkdir(parents=True, exist_ok=True)

    has_cookies = _has_usable_cookies(_COOKIES_PATH)
    proxies = _configured_proxies()
    attempts = (*proxies, None) if proxies else (None,)
    last_error: Optional[Exception] = None

    for proxy in attempts:
        for client in _PLAYER_CLIENTS:
            extractor_args = {
                "youtube": {"player_client": [client]},
                "youtubepot-wpc": {"browser_path": _WPC_BROWSER},
            }
            options = {
                "quiet": True,
                "no_warnings": False,
                "noplaylist": True,
                "extractor_args": extractor_args,
                "http_headers": {"User-Agent": _BROWSER_UA},
                "js_runtimes": {"node": {}},
                "retries": 3,
                "fragment_retries": 3,
                "file_access_retries": 3,
                "extractor_retries": 3,
            }
            if proxy:
                options["proxy"] = proxy
            # Do not pass an expired secret to embedded clients. Browser clients
            # may still use it, but disable it for later attempts after auth errors.
            if has_cookies and client not in {"android_vr", "web_embedded", "tv_embedded"}:
                options["cookiefile"] = _COOKIES_PATH
            if download:
                options["format"] = "bv*+ba/b"
                options["outtmpl"] = str(out_dir / "%(id)s.%(ext)s")
                options["merge_output_format"] = "mp4"
                if prefer_audio:
                    options["format"] = "ba/b"
                    options["postprocessors"] = [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "m4a",
                        "preferredquality": "192",
                    }]
            else:
                options["skip_download"] = True
                options["extract_flat"] = True

            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=download)
                    prepared_filename = ydl.prepare_filename(info) if download else None
                return info, prepared_filename
            except Exception as exc:  # noqa: BLE001 - try the next route
                last_error = exc
                message = str(exc)
                route = "configured proxy" if proxy else "direct"
                print(f"[youtube] client={client} via={route} failed: {message[:240]}")
                if has_cookies and any(
                    marker in message.lower()
                    for marker in (
                        "cookies are no longer valid",
                        "sign in to confirm",
                        "cookies are invalid",
                    )
                ):
                    has_cookies = False
                    print("[youtube] disabling stale cookie secret for remaining attempts")

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
    failures: list[str] = []

    try:
        info, prepared_filename = _try_extract(
            url, download=True, out_dir=out_dir, prefer_audio=prefer_audio
        )
        return _downloaded_file(info, prepared_filename, out_dir, prefer_audio)
    except Exception as exc:
        failures.append(f"yt-dlp: {str(exc)[:180]}")
        print(f"[youtube] yt-dlp failed ({str(exc)[:200]})")

    cobalt_url, cobalt_key = _configured_cobalt()
    if cobalt_url:
        try:
            return _download_via_cobalt(
                url, out_dir, prefer_audio, cobalt_url, cobalt_key
            )
        except Exception as exc:
            failures.append(f"Cobalt: {str(exc)[:180]}")
            print(f"[youtube] configured Cobalt fallback failed ({str(exc)[:200]})")

    frontends = _configured_frontends()
    if frontends:
        try:
            return Path(_download_via_frontend(url, out_dir, frontends))
        except Exception as exc:
            failures.append(f"Invidious: {str(exc)[:180]}")
            print(f"[youtube] configured Invidious fallback failed ({str(exc)[:200]})")

    raise RuntimeError(
        "No usable YouTube download route. "
        "yt-dlp was blocked by YouTube; configure DBYT_YOUTUBE_PROXIES or "
        "DBYT_COBALT_URL/DBYT_COBALT_API_KEY, and optionally "
        "DBYT_INVIDIOUS_INSTANCES. Details: " + " | ".join(failures)
    )


def _download_via_frontend(url: str, out_dir: Path, instances: tuple[str, ...]) -> str:
    """Download separate video/audio streams through an Invidious instance."""
    import subprocess

    video_id = extract_video_id(url)
    if not video_id:
        raise RuntimeError(f"Invalid YouTube URL: {url}")

    last_error: Optional[Exception] = None
    for base in instances:
        try:
            api = f"{base}/api/v1/videos/{video_id}"
            request = urllib.request.Request(api, headers={"User-Agent": "DBYT/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.loads(response.read())

            video_streams = data.get("formatStreams", []) or data.get("videoStreams", [])
            audio_streams = data.get("adaptiveFormats", []) or data.get("audioStreams", [])
            if not video_streams or not audio_streams:
                raise RuntimeError("front-end returned incomplete streams")

            def bitrate(stream: dict) -> int:
                try:
                    return int(stream.get("bitrate") or stream.get("qualityLabel", "0p").rstrip("p") or 0)
                except (TypeError, ValueError):
                    return 0

            video = max(
                (s for s in video_streams if s.get("url") and (s.get("type", "").startswith("video/") or s.get("qualityLabel"))),
                key=bitrate,
            )
            audio = max(
                (s for s in audio_streams if s.get("url") and (s.get("type", "").startswith("audio/") or s.get("itag"))),
                key=bitrate,
            )

            video_path = out_dir / f"{video_id}.video"
            audio_path = out_dir / f"{video_id}.audio"
            output_path = out_dir / f"{video_id}.mp4"

            for stream, destination in ((video, video_path), (audio, audio_path)):
                stream_request = urllib.request.Request(
                    stream["url"], headers={"User-Agent": "DBYT/1.0"}
                )
                with urllib.request.urlopen(stream_request, timeout=900) as response, destination.open("wb") as handle:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)

            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-i", str(video_path), "-i", str(audio_path),
                    "-map", "0:v:0", "-map", "1:a:0", "-c", "copy",
                    str(output_path),
                ],
                check=True,
            )
            video_path.unlink(missing_ok=True)
            audio_path.unlink(missing_ok=True)
            return str(output_path)
        except Exception as exc:  # noqa: BLE001 - try the next instance
            last_error = exc

    raise RuntimeError(f"All Invidious instances failed: {last_error}")


__all__ = [
    "download_media",
    "extract_video_id",
    "fetch_metadata",
    "is_valid_youtube_url",
]
