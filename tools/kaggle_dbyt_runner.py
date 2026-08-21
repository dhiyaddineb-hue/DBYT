"""Non-interactive Kaggle runner for DBYT one-click GitHub Actions jobs.

The GitHub workflow prepends base64-encoded job variables before uploading this
file as a Kaggle kernel. No GitHub or Kaggle secret is embedded in this file.
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Any

# These assignments are prepended by the GitHub workflow.
JOB_SOURCE_URL_B64 = ""
JOB_REPOSITORY_B64 = ""
JOB_REF_B64 = ""
JOB_TARGET_LANGUAGE_B64 = ""
JOB_PROJECT_NAME_B64 = ""
JOB_ENGINE_B64 = ""
JOB_GRANULARITY_B64 = ""
JOB_WHISPER_MODEL_B64 = ""


def _decode(value: str, default: str = "") -> str:
    if not value:
        return default
    return base64.b64decode(value.encode("ascii")).decode("utf-8")


SOURCE_URL = _decode(JOB_SOURCE_URL_B64)
REPOSITORY = _decode(JOB_REPOSITORY_B64, "dhiyaddineb-hue/DBYT")
REPOSITORY_REF = _decode(JOB_REF_B64, "main")
TARGET_LANGUAGE = _decode(JOB_TARGET_LANGUAGE_B64, "ar")
PROJECT_NAME = _decode(JOB_PROJECT_NAME_B64, "dbyt-project")
REQUESTED_ENGINE = _decode(JOB_ENGINE_B64, "fasih").lower()
GRANULARITY = _decode(JOB_GRANULARITY_B64, "segment")
WHISPER_MODEL = _decode(JOB_WHISPER_MODEL_B64, "small")

ROOT = Path("/kaggle/working/dbty-one-click")
SOURCE_DIR = ROOT / "source"
REPO_DIR = ROOT / "repo"
RUN_DIR = ROOT / "run"
OUTPUT_DIR = Path("/kaggle/working/dbyt_output")
LOG_PATH = OUTPUT_DIR / "pipeline.log"


def _run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None,
         log: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(command), flush=True)
    target = open(log, "a", encoding="utf-8") if log else subprocess.PIPE
    try:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            env=env,
            text=True,
            stdout=target,
            stderr=subprocess.STDOUT if log else subprocess.PIPE,
            check=check,
        )
    finally:
        if log:
            target.close()


def _install_runtime() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("[1/6] Installing DBYT runtime dependencies", flush=True)
    if shutil.which("ffmpeg") is None:
        _run(["bash", "-lc", "apt-get update -qq && apt-get install -y -qq ffmpeg"])
    packages = [
        "yt-dlp[default]==2026.8.19",
        "yt-dlp-ejs",
        "pydantic==2.7.4",
        "pydantic-settings==2.3.4",
        "requests",
        "faster-whisper==1.0.3",
        "deep-translator==1.11.4",
        "soundfile",
        "huggingface_hub",
        "numpy<2",
        "coqui-tts==0.27.5",
        "transformers==5.0.0",
    ]
    _run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "--upgrade-strategy", "eager", *packages])
    _run([sys.executable, "-m", "pip", "install", "-q", "--upgrade", "sherpa-onnx==1.13.6"])


def _download_url(url: str, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"[2/6] Downloading source asset: {url}", flush=True)
    request = urllib.request.Request(url, headers={"User-Agent": "DBYT-one-click/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response, destination.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    if destination.stat().st_size < 1024:
        raise RuntimeError("The source URL returned an empty or invalid media file.")
    return destination


def _install_deno() -> Path:
    deno_root = ROOT / ".deno"
    deno_path = deno_root / "bin" / "deno"
    deno_root.mkdir(parents=True, exist_ok=True)
    os.environ["DENO_INSTALL"] = str(deno_root)
    os.environ["DENO_DIR"] = str(ROOT / "deno-cache")
    if not deno_path.is_file():
        installer_env = os.environ.copy()
        installer_env["CI"] = "1"
        _run(["bash", "-lc", "curl -fsSL https://deno.land/install.sh | sh"], env=installer_env)
    if not deno_path.is_file():
        raise RuntimeError(f"Deno installation failed: {deno_path}")
    return deno_path


def _download_youtube(url: str, destination: Path) -> Path:
    deno = _install_deno()
    cookies_path = ROOT / "youtube-cookies.txt"
    try:
        from kaggle_secrets import UserSecretsClient
        cookies = UserSecretsClient().get_secret("YOUTUBE_COOKIES")
    except Exception:
        cookies = os.environ.get("YOUTUBE_COOKIES", "")
    if cookies:
        cookies_path.write_text(cookies, encoding="utf-8")

    attempts = [
        ["--format", "bv*[height<=720]+ba/b[height<=720]/best"],
        [],
    ]
    last_error = ""
    for index, format_args in enumerate(attempts, start=1):
        for old in SOURCE_DIR.glob("source.*"):
            old.unlink(missing_ok=True)
        command = [
            "yt-dlp", "--ignore-config", "--no-playlist", "--retries", "5",
            "--fragment-retries", "5", "--socket-timeout", "30",
            "--js-runtimes", f"deno:{deno}", "--remote-components", "ejs:github",
            "--merge-output-format", "mp4",
        ]
        if cookies_path.is_file():
            command += ["--cookies", str(cookies_path)]
        command += format_args + ["--output", str(SOURCE_DIR / "source.%(ext)s"), url]
        print(f"[2/6] YouTube download attempt {index}/{len(attempts)}", flush=True)
        completed = _run(command, log=LOG_PATH, check=False)
        if completed.returncode == 0:
            candidates = sorted(SOURCE_DIR.glob("source.*"))
            if candidates:
                return candidates[0]
        last_error = f"yt-dlp attempt {index} failed with exit code {completed.returncode}"
    raise RuntimeError(last_error or "yt-dlp could not download the YouTube source.")


def _download_source() -> Path:
    if not SOURCE_URL:
        raise RuntimeError("SOURCE_URL is empty. Provide a public GitHub Release URL or YouTube URL.")
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    if re.match(r"https://(www\.)?(youtube\.com|youtu\.be)/", SOURCE_URL):
        return _download_youtube(SOURCE_URL, SOURCE_DIR / "source.mp4")
    return _download_url(SOURCE_URL, SOURCE_DIR / "source.mp4")


def _fetch_repository() -> Path:
    print(f"[3/6] Fetching DBYT source {REPOSITORY}@{REPOSITORY_REF}", flush=True)
    if REPO_DIR.exists():
        shutil.rmtree(REPO_DIR)
    REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
    archive = ROOT / "repo.tar.gz"
    archive_url = f"https://github.com/{REPOSITORY}/archive/{REPOSITORY_REF}.tar.gz"
    request = urllib.request.Request(archive_url, headers={"User-Agent": "DBYT-one-click/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        archive.write_bytes(response.read())
    extract_root = ROOT / "repo-extract"
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as bundle:
        base = extract_root.resolve()
        for member in bundle.getmembers():
            target = (extract_root / member.name).resolve()
            if target != base and base not in target.parents:
                raise RuntimeError("Unsafe path in DBYT source archive")
        bundle.extractall(extract_root)
    roots = [item for item in extract_root.iterdir() if item.is_dir()]
    if len(roots) != 1:
        raise RuntimeError("Unexpected DBYT archive layout")
    roots[0].rename(REPO_DIR)
    return REPO_DIR


def _extract_reference(source: Path) -> Path:
    reference = RUN_DIR / "reference.wav"
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    duration = float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(source),
    ], text=True).strip())
    start = 5.0 if duration > 15 else 0.0
    length = min(8.0, max(2.0, duration - start))
    _run([
        "ffmpeg", "-y", "-ss", str(start), "-t", str(length), "-i", str(source),
        "-vn", "-ac", "1", "-ar", "24000", "-c:a", "pcm_s16le", str(reference),
    ])
    return reference


def _write_compatibility_shim() -> Path:
    shim_dir = ROOT / "python-shims"
    shim_dir.mkdir(parents=True, exist_ok=True)
    (shim_dir / "sitecustomize.py").write_text(
        "import torch\n"
        "try:\n"
        "    import transformers.pytorch_utils as _pt_utils\n"
        "    if not hasattr(_pt_utils, 'isin_mps_friendly'):\n"
        "        def isin_mps_friendly(elements, test_elements, *args, **kwargs):\n"
        "            return torch.isin(elements, test_elements, *args, **kwargs)\n"
        "        _pt_utils.isin_mps_friendly = isin_mps_friendly\n"
        "except Exception:\n"
        "    pass\n",
        encoding="utf-8",
    )
    return shim_dir


def _run_pipeline(repo: Path, source: Path, engine: str, reference: Path | None) -> tuple[int, Path]:
    output_dir = RUN_DIR / ("output-" + engine)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    environment = os.environ.copy()
    environment.update({
        "DBYT_WORKSPACE_DIR": str(RUN_DIR / f"workspace-{engine}"),
        "DBYT_WHISPER_MODEL": WHISPER_MODEL,
        "DBYT_WHISPER_DEVICE": "auto",
        "DBYT_WHISPER_COMPUTE_TYPE": "auto",
        "DBYT_DEFAULT_ENGINE": engine,
        "PYTHONPATH": str(_write_compatibility_shim()) + os.pathsep + str(repo) + os.pathsep + environment.get("PYTHONPATH", ""),
    })
    command = [
        sys.executable, "-u", "-m", "backend.cli", str(source),
        "--target-language", TARGET_LANGUAGE,
        "--engine", engine,
        "--project-name", PROJECT_NAME,
        "--keep-background", "true",
        "--preserve-emotions", "true",
        "--granularity", GRANULARITY,
        "--lip-sync", "false",
        "--output-dir", str(output_dir),
    ]
    if reference is not None:
        command += ["--voice", str(reference)]
    with LOG_PATH.open("a", encoding="utf-8") as log:
        log.write(f"\n=== pipeline engine={engine} started {time.time()} ===\n")
        completed = subprocess.run(command, cwd=str(repo), env=environment, text=True,
                                   stdout=log, stderr=subprocess.STDOUT, check=False)
        log.write(f"=== pipeline engine={engine} exit={completed.returncode} ===\n")
    outputs = sorted(output_dir.glob("*.mp4")) + sorted(output_dir.glob("*.mp3"))
    return completed.returncode, (outputs[-1] if outputs else Path())


def main() -> None:
    started = time.time()
    _install_runtime()
    source = _download_source()
    repo = _fetch_repository()
    reference = _extract_reference(source) if REQUESTED_ENGINE == "fasih" else None
    print("[4/6] Starting DBYT dubbing", flush=True)
    engines = [REQUESTED_ENGINE]
    if REQUESTED_ENGINE == "fasih":
        engines.append("sherpa")
    selected_engine = None
    final_path = Path()
    for engine in engines:
        if engine not in {"fasih", "sherpa"}:
            raise RuntimeError(f"Unsupported automatic engine: {engine}")
        code, candidate = _run_pipeline(repo, source, engine, reference if engine == "fasih" else None)
        if code == 0 and candidate.is_file():
            selected_engine, final_path = engine, candidate
            break
        print(f"Engine {engine} failed; trying fallback if available.", flush=True)
    if not selected_engine:
        raise RuntimeError("Both requested TTS and fallback engine failed. See pipeline.log.")

    print("[5/6] Collecting output", flush=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_video = OUTPUT_DIR / f"{PROJECT_NAME}.mp4"
    shutil.copy2(final_path, output_video)
    report: dict[str, Any] = {
        "source_url": SOURCE_URL,
        "repository": REPOSITORY,
        "repository_ref": REPOSITORY_REF,
        "target_language": TARGET_LANGUAGE,
        "requested_engine": REQUESTED_ENGINE,
        "selected_engine": selected_engine,
        "whisper_model": WHISPER_MODEL,
        "granularity": GRANULARITY,
        "output_file": output_video.name,
        "duration_seconds": round(time.time() - started, 2),
        "gpu_available": bool(__import__("torch").cuda.is_available()),
    }
    (OUTPUT_DIR / "run.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(LOG_PATH, OUTPUT_DIR / "pipeline.log")
    print("[6/6] Done", json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
