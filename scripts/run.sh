#!/usr/bin/env bash
# =============================================================================
# run.sh — bootstrap the DBYT environment and start the server.
#
# Usage:
#   ./scripts/run.sh          # install deps if needed, then start on :8000
#
# This makes the app "always runnable" with one command: it (re)creates the
# virtualenv, installs dependencies, ensures ffmpeg is available (via the
# bundled imageio-ffmpeg if the system one is missing), and launches uvicorn.
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/.."

PY=python3
VENV=.venv

# 1) Virtualenv
if [ ! -d "$VENV" ]; then
  echo "[run] creating virtualenv..."
  $PY -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# 2) Dependencies (fast path: skip if already importable)
if ! python -c "import fastapi, uvicorn, yt_dlp, edge_tts, deep_translator, faster_whisper" 2>/dev/null; then
  echo "[run] installing dependencies..."
  pip install --quiet --upgrade pip
  pip install --quiet -r requirements.txt
  # faster-whisper + imageio-ffmpeg (sandbox-friendly ffmpeg fallback)
  pip install --quiet faster-whisper imageio-ffmpeg
fi

# 3) ffmpeg fallback: if the system has no ffmpeg, use imageio's static build
if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[run] no system ffmpeg — using bundled static build..."
  FF="$(python -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
  ln -sf "$FF" /usr/local/bin/ffmpeg 2>/dev/null || true
fi
if ! command -v ffprobe >/dev/null 2>&1; then
  ln -sf "$(pwd)/scripts/ffprobe_shim.py" /usr/local/bin/ffprobe 2>/dev/null || true
fi

# 4) Ensure the workspace exists
mkdir -p workspace/{models,jobs,uploads,output,data,logs}

# 5) Start the server
echo "[run] starting DBYT on http://0.0.0.0:8000 ..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir backend
