"""Download-only Kaggle job for the DBYT GitHub handoff."""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

JOB_SOURCE_URL_B64 = ""


def _decode(value: str) -> str:
    return base64.b64decode(value.encode("ascii")).decode("utf-8") if value else ""


SOURCE_URL = _decode(JOB_SOURCE_URL_B64)
ROOT = Path("/kaggle/working/dbty-download")
WORK_DIR = ROOT / "work"
OUTPUT_DIR = Path("/kaggle/working/dbyt_download_output")
LOG_PATH = OUTPUT_DIR / "download.log"


def _run(command: list[str], *, log: Path | None = None, check: bool = True,
         env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(command), flush=True)
    if log is None:
        return subprocess.run(command, text=True, check=check, env=env)
    with log.open("a", encoding="utf-8") as handle:
        return subprocess.run(command, text=True, stdout=handle, stderr=subprocess.STDOUT, check=check, env=env)


def _install_tools() -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        _run(["bash", "-lc", "apt-get update -qq && apt-get install -y -qq --no-install-recommends ffmpeg"], check=False)
    _run([
        sys.executable, "-m", "pip", "install", "-q", "--upgrade", "--break-system-packages",
        "yt-dlp",
    ], check=False)
    deno_root = ROOT / ".deno"
    deno_path = deno_root / "bin" / "deno"
    deno_root.mkdir(parents=True, exist_ok=True)
    if not deno_path.is_file():
        env = os.environ.copy()
        env.update({"DENO_INSTALL": str(deno_root), "DENO_DIR": str(ROOT / "deno-cache"), "CI": "1"})
        _run(["bash", "-lc", "curl -fsSL https://deno.land/install.sh | sh"], check=False, env=env)
    return deno_path


def _get_cookies() -> str:
    try:
        from kaggle_secrets import UserSecretsClient
        return UserSecretsClient().get_secret("YOUTUBE_COOKIES") or ""
    except Exception:
        return os.environ.get("YOUTUBE_COOKIES", "")


def _download_youtube(deno: Path) -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    cookie_path = ROOT / "youtube-cookies.txt"
    cookies = _get_cookies()
    if cookies:
        cookie_path.write_text(cookies, encoding="utf-8")
    cookie_options = [cookie_path, None] if cookie_path.is_file() else [None]
    format_options = [
        ["--format", "bv*[height<=720]+ba/b[height<=720]/best"],
        [],
    ]
    attempt = 0
    for cookie_option in cookie_options:
        for format_args in format_options:
            attempt += 1
            for old in WORK_DIR.glob("source.*"):
                old.unlink(missing_ok=True)
            command = [
                "yt-dlp", "--ignore-config", "--no-playlist", "--retries", "5",
                "--fragment-retries", "5", "--socket-timeout", "30",
                "--js-runtimes", f"deno:{deno}", "--remote-components", "ejs:github",
                "--merge-output-format", "mp4",
            ]
            if cookie_option is not None:
                command += ["--cookies", str(cookie_option)]
            command += format_args + ["--output", str(WORK_DIR / "source.%(ext)s"), SOURCE_URL]
            print(f"Download attempt {attempt}/4; cookies={'yes' if cookie_option else 'no'}", flush=True)
            completed = _run(command, log=LOG_PATH, check=False)
            if completed.returncode == 0:
                candidates = sorted(
                    path for path in WORK_DIR.glob("source.*")
                    if path.is_file() and not path.name.endswith(".part") and path.stat().st_size > 1024
                )
                if candidates:
                    return candidates[-1]
    raise RuntimeError("Kaggle could not download YouTube after cookie and anonymous attempts. See download.log.")


def _download_direct() -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    destination = WORK_DIR / "source.mp4"
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "DBYT-kaggle-download/1.0"})
    with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    if destination.stat().st_size <= 1024:
        raise RuntimeError("The direct source URL returned an empty file.")
    return destination


def main() -> None:
    if not SOURCE_URL.startswith(("http://", "https://")):
        raise RuntimeError("SOURCE_URL must be an HTTP(S) URL.")
    started = time.time()
    deno = _install_tools()
    if "youtube.com/" in SOURCE_URL or "youtu.be/" in SOURCE_URL:
        source = _download_youtube(deno)
    else:
        source = _download_direct()
    duration = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(source),
    ], text=True).strip())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output = OUTPUT_DIR / "source.mp4"
    if source.suffix.lower() == ".mp4":
        shutil.copy2(source, output)
    else:
        _run(["ffmpeg", "-y", "-i", str(source), "-c", "copy", str(output)])
    report = {
        "source_url": SOURCE_URL,
        "output_file": "source.mp4",
        "size_bytes": output.stat().st_size,
        "duration_seconds": duration,
        "elapsed_seconds": round(time.time() - started, 2),
    }
    (OUTPUT_DIR / "run.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not LOG_PATH.exists():
        LOG_PATH.write_text("Download completed without subprocess diagnostics.\n", encoding="utf-8")
    print("Download complete:", json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
