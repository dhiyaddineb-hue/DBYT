"""DBYT configuration.

All settings are read from environment variables (12-factor style) so the same
code runs locally, inside Docker, or on GitHub Actions. Provide secrets via a
`.env` file (see `.env.example`) or the repository/runner secret store.
"""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.getenv("DBYT_DATA_DIR", BASE_DIR / "data"))
JOBS_DIR = Path(os.getenv("DBYT_JOBS_DIR", BASE_DIR / "jobs"))
UPLOADS_DIR = Path(os.getenv("DBYT_UPLOADS_DIR", BASE_DIR / "uploads"))
OUTPUT_DIR = Path(os.getenv("DBYT_OUTPUT_DIR", BASE_DIR / "output"))


class Settings(BaseSettings):
    """Runtime settings, overridable via environment or `.env`."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="DBYT_", extra="ignore")

    app_name: str = "DBYT — Professional Video Dubbing"
    host: str = "0.0.0.0"
    port: int = 8000

    # Directories
    data_dir: Path = DATA_DIR
    jobs_dir: Path = JOBS_DIR
    uploads_dir: Path = UPLOADS_DIR
    output_dir: Path = OUTPUT_DIR

    # Whisper transcription
    whisper_model: str = "small"  # tiny | base | small | medium | large-v3
    whisper_device: str = "auto"  # auto | cpu | cuda
    whisper_compute_type: str = "auto"  # auto | int8 | float16

    # Translation
    default_target_lang: str = "ar"
    translator_backend: str = "google"  # google | openai | deepl | none

    # TTS
    default_engine: str = "edge"  # edge | elevenlabs | bark | xtts
    openai_api_key: str | None = None
    elevenlabs_api_key: str | None = None
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"  # default "Rachel" (can be changed)

    # Mixing
    background_duck_volume: float = 0.18  # original audio kept at 18% under new voice
    keep_background: bool = True

    max_upload_mb: int = 2048
    cors_origins: str = "*"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.jobs_dir, self.uploads_dir, self.output_dir):
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
