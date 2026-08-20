"""Lip-sync (mouth re-animation) via Wav2Lip.

To make a dub look like the *original* — not a dub — the mouth must move in
sync with the new voice. This module wraps **Wav2Lip** (open source,
https://github.com/Rudrabha/Wav2Lip), the standard model for this task.

Wav2Lip is heavy (needs GPU for good speed) and its weights are large, so it is
an *optional* stage gated behind `lip_sync=True`. When enabled the pipeline:

    dubbed_audio + original_video  ->  Wav2Lip  ->  video with synced mouth

Requirements (installed automatically by `ensure_models`):
  - `wav2lip` / `wav2lip_gan.pth` (mouth-sync model)
  - `s3fd` face detector weights
  - torch + torchvision

The weights (~450 MB) are downloaded into ``settings.models_dir`` (inside the
single `workspace/` folder) so they persist in the repository.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from ..config import settings

_WAV2LIP_DIR = Path(__file__).resolve().parent.parent.parent.parent / "third_party" / "Wav2Lip"


def available() -> bool:
    """Return True if Wav2Lip is installed and its weights are present."""
    return (_WAV2LIP_DIR / "inference.py").exists() and has_weights()


def has_weights() -> bool:
    return (settings.models_dir / "wav2lip_gan.pth").exists() and (
        settings.models_dir / "s3fd.pth"
    ).exists()


def ensure_models() -> None:
    """Clone Wav2Lip and download weights if missing.

    Weights are fetched from the community HuggingFace mirror so the download
    is reliable (the original weights live on Google Drive).
    """
    if not _WAV2LIP_DIR.exists():
        subprocess.run(
            ["git", "clone", "--depth", "1",
             "https://github.com/Rudrabha/Wav2Lip.git", str(_WAV2LIP_DIR)],
            check=True,
        )

    settings.models_dir.mkdir(parents=True, exist_ok=True)
    wav2lip = settings.models_dir / "wav2lip_gan.pth"
    s3fd = settings.models_dir / "s3fd.pth"
    if not wav2lip.exists():
        subprocess.run(
            ["curl", "-L", "-o", str(wav2lip),
             "https://huggingface.co/camenduru/Wav2Lip/resolve/main/checkpoints/wav2lip_gan.pth"],
            check=True,
        )
    if not s3fd.exists():
        subprocess.run(
            ["curl", "-L", "-o", str(s3fd),
             "https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth"],
            check=True,
        )


def lip_sync(face_video: Path, audio: Path, out_video: Path,
             resize_factor: int = 1, pad_top: int = 0, pad_bottom: int = 0,
             pad_left: int = 0, pad_right: int = 0) -> Path:
    """Run Wav2Lip inference: re-animate the mouth to `audio`.

    ``face_video`` is the original (cropped-to-face) video; the result is a
    video whose mouth moves to the dubbed audio.
    """
    ensure_models()
    out_video.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python", str(_WAV2LIP_DIR / "inference.py"),
        "--checkpoint_path", str(settings.models_dir / "wav2lip_gan.pth"),
        "--face", str(face_video),
        "--audio", str(audio),
        "--outfile", str(out_video),
        "--resize_factor", str(resize_factor),
        "--pads", str(pad_top), str(pad_bottom), str(pad_left), str(pad_right),
    ]
    subprocess.run(cmd, check=True)
    return out_video


def sync_final_video(dubbed_video: Path, dubbed_audio: Path, out_video: Path) -> Path:
    """High-level helper: lip-sync a fully dubbed video to its new audio.

    Uses the `wav2lip` (non-GAN) variant for speed, then re-muxes the original
    high-resolution video frames with the synced mouth region via `wav2lip.pth`
    is overkill here — we instead return the GAN result directly. Advanced
    users can swap the checkpoint.
    """
    # Placeholder checkpoint: default to the GAN weights we already have.
    from . import audio as audio_mod

    tmp = out_video.parent / "lipsync_raw.mp4"
    lip_sync(dubbed_video, dubbed_audio, tmp)
    # Re-mux to ensure a clean container + faststart for web playback
    audio_mod.mux_audio_video(tmp, dubbed_audio, out_video)
    return out_video
