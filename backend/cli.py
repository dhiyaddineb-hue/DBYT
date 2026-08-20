"""Command-line entrypoint for the dubbing pipeline.

Usage:
    python -m backend.cli "<youtube-url>" \
        --target-language ar --engine edge --project-name "my-project"

Also accepts a local file path instead of a URL (dubs a local video).
Used by the GitHub Actions workflow and for local/CI runs.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app.config import settings
from backend.app.services import youtube
from backend.app.services.pipeline import DubbingPipeline


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="DBYT — professional video dubbing")
    p.add_argument("input", help="YouTube URL or local media file path")
    p.add_argument("--target-language", default="ar", help="Target language code")
    p.add_argument("--engine", default="edge", choices=["edge", "elevenlabs", "bark", "xtts", "piper", "sherpa"])
    p.add_argument("--voice", default=None, help="Optional TTS voice override")
    p.add_argument("--project-name", default="", help="Project name (auto from title if empty)")
    p.add_argument("--keep-background", default="true", choices=["true", "false"])
    p.add_argument("--preserve-emotions", default="true", choices=["true", "false"])
    p.add_argument("--granularity", default="word", choices=["word", "segment"])
    p.add_argument("--lip-sync", default="false", choices=["true", "false"])
    p.add_argument("--output-dir", default=str(settings.output_dir))
    return p.parse_args()


def _download_source(url: str, out_dir: Path) -> Path:
    """Use the browser/site downloader first; yt-dlp is the last fallback."""
    use_browser = os.environ.get("DBYT_COBALT_BROWSER", "0").strip().lower() not in {
        "0", "false", "no", "off"
    }
    if use_browser:
        try:
            from backend.app.services.cobalt_browser import download_via_browser
            print("🌐 Downloader: Chrome → browser download sites → local workspace")
            return download_via_browser(url, out_dir)
        except Exception as exc:  # noqa: BLE001 - deliberate fallback
            print(f"⚠️ Browser downloader failed: {str(exc)[:500]}")
            print("↩️ Falling back to yt-dlp…")

    return youtube.download_media(url, out_dir, prefer_audio=False)


def _project_name_from_media(media: Path) -> str:
    """Produce a stable project name without contacting YouTube for metadata."""
    stem = media.stem.strip() or "project"
    safe = " ".join(stem.replace("_", " ").replace("-", " ").split())
    return safe[:80] or "project"


def main() -> None:
    args = parse_args()
    target = args.input.strip()
    is_url = youtube.is_valid_youtube_url(target)

    project_name = args.project_name or None
    work_dir = Path(args.output_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    progress = lambda p, m: print(f"[{p:3d}%] {m}")  # noqa: E731

    if is_url:
        # Critical ordering: do NOT call YouTube metadata extraction first.
        # GitHub-hosted runners can be bot-challenged by YouTube even when a
        # normal browser-based downloader site can retrieve the media.
        media = _download_source(target, work_dir / "source")
        project_name = project_name or _project_name_from_media(media)
        print(f"🎬 Source downloaded: {media.name}")
        print(f"🌍 Target language: {args.target_language} | Engine: {args.engine}")
    else:
        media = Path(target)
        if not media.exists():
            raise SystemExit(f"File not found: {target}")
        project_name = project_name or media.stem

    pipeline = DubbingPipeline(
        target_language=args.target_language,
        engine=args.engine,
        voice=args.voice,
        keep_background=args.keep_background == "true",
        preserve_emotions=args.preserve_emotions == "true",
        granularity=args.granularity,
        lip_sync=args.lip_sync == "true",
        progress=progress,
    )
    final = asyncio.run(pipeline.run(media, work_dir / "work"))

    dest = work_dir / f"{project_name}{final.suffix}"
    shutil.move(str(final), str(dest))
    print(f"\n✅ Done! Output: {dest}")


if __name__ == "__main__":
    main()
