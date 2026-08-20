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

# Make the repo root importable regardless of how this file is invoked
# (python -m backend.cli  OR  python backend/cli.py  OR  GitHub Actions).
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
    """Download through Cobalt in Chrome first, then fall back to yt-dlp."""
    use_cobalt = os.environ.get("DBYT_COBALT_BROWSER", "1").strip().lower() not in {
        "0", "false", "no", "off"
    }
    if use_cobalt:
        try:
            from backend.app.services.cobalt_browser import download_via_browser

            print("🌐 Downloader: Chrome → cobalt.tools → local workspace")
            return download_via_browser(url, out_dir)
        except Exception as exc:  # noqa: BLE001 - deliberate downloader fallback
            print(f"⚠️ Cobalt browser download failed: {str(exc)[:300]}")
            print("↩️ Falling back to yt-dlp…")

    return youtube.download_media(url, out_dir, prefer_audio=False)


def main() -> None:
    args = parse_args()
    target = args.input.strip()
    is_url = youtube.is_valid_youtube_url(target)

    project_name = args.project_name or None
    work_dir = Path(args.output_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    progress = lambda p, m: print(f"[{p:3d}%] {m}")  # noqa: E731

    if is_url:
        meta = youtube.fetch_metadata(target)
        if not meta.get("valid"):
            raise SystemExit(f"Invalid/unavailable URL: {meta.get('error')}")
        project_name = project_name or meta.get("suggested_project_name") or "project"
        print(f"🎬 Dubbing: {meta.get('title')}")
        print(f"🌍 Target language: {args.target_language} | Engine: {args.engine}")

        media = _download_source(target, work_dir / "source")
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

    # Move to the output dir with the project name
    dest = work_dir / f"{project_name}{final.suffix}"
    shutil.move(str(final), str(dest))
    print(f"\n✅ Done! Output: {dest}")


if __name__ == "__main__":
    main()
