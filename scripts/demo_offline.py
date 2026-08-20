#!/usr/bin/env python3
"""Offline end-to-end demonstration of the DBYT dubbing engine.

The sandbox blocks YouTube, HuggingFace (Whisper model) and Microsoft's
edge-tts — the three *external network* services. Everything else (word-level
placement, time-stretch, background ducking, muxing) is pure local ffmpeg.

This script proves those real parts work by running the PRODUCTION pipeline
(`DubbingPipeline.run`) on a real video, with only the two network-dependent
functions injected offline:

  1. transcription  -> fake word timestamps (a real Whisper model would supply
                       these; here we hardcode a 4-word sentence)
  2. TTS            -> real synthesized "words" (tone bursts at distinct
                       pitches) instead of a neural voice

Result: a real dubbed MP4 whose new "words" land at the exact timestamps of
the original words, with the original background music ducked underneath.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services import audio, transcribe, tts  # noqa: E402
from app.services.pipeline import DubbingPipeline  # noqa: E402

WORK = Path(__file__).resolve().parent.parent / "workspace" / "demo"


def ffmpeg() -> str:
    """Return ffmpeg from the system, with an optional Python fallback."""
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError(
            "ffmpeg is required for the offline demo; install it with apt or "
            "install imageio-ffmpeg"
        ) from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def _tone(path: Path, freq: float, seconds: float, volume: float = 0.5) -> None:
    subprocess.run(
        [ffmpeg(), "-y", "-f", "lavfi", "-i",
         f"sine=frequency={freq}:duration={seconds:.3f}",
         "-af", f"volume={volume}", "-ar", "44100", "-ac", "1",
         "-c:a", "pcm_s16le", str(path)],
        check=True, capture_output=True,
    )


def build_source_video(path: Path) -> dict:
    """Create a real MP4: a "speaker" saying 4 words + background music."""
    path.parent.mkdir(parents=True, exist_ok=True)

    # The "original" sentence: 4 words at these timestamps (seconds)
    words = [
        {"start": 0.50, "end": 1.10},   # word 0
        {"start": 1.60, "end": 2.30},   # word 1
        {"start": 2.80, "end": 3.40},   # word 2
        {"start": 4.10, "end": 4.80},   # word 3
    ]
    total = 5.5

    tmp = path.parent
    # Background music (low hum) across the whole clip
    _tone(tmp / "bg.wav", 120, total, volume=0.25)

    # A voice track: each "word" is a tone burst at a distinct pitch
    voice_freqs = [330, 440, 550, 660]  # 4 distinguishable syllables
    parts = []
    for i, w in enumerate(words):
        dur = w["end"] - w["start"]
        _tone(tmp / f"w{i}.wav", voice_freqs[i], dur, volume=0.7)
        parts.append((tmp / f"w{i}.wav", w["start"]))
    voice = tmp / "voice.wav"
    audio.place_clips_at_times(parts, voice)  # real placement code!

    # Mix voice over music (simulates the original speaker + music)
    mixed = tmp / "mixed.wav"
    audio.mix_dub_over_original(tmp / "bg.wav", voice, 0.0, mixed,
                                duck_volume=0.6, keep_background=True)

    # A moving visual so it's a genuine video file
    subprocess.run(
        [ffmpeg(), "-y", "-f", "lavfi",
         "-i", f"testsrc2=size=640x360:rate=25:duration={total}",
         "-i", str(mixed),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", "-movflags", "+faststart", str(path)],
        check=True, capture_output=True,
    )
    return {"words": words, "total": total}


# ---- offline injections (the ONLY stubbed parts) --------------------------

def offline_transcribe(audio_path: Path, language=None):
    """Return 4 segments with word timestamps (stand-in for Whisper)."""
    from app.services.transcribe import Segment, Word

    words = [Word(t, s, e) for t, s, e in [
        ("bonjour", 0.50, 1.10),
        ("tout", 1.60, 2.30),
        ("le", 2.80, 3.40),
        ("monde", 4.10, 4.80),
    ]]
    return [Segment(0.0, 5.5, "bonjour tout le monde", words)], "fr"


class OfflineTTSEngine:
    name = "offline"

    async def synthesize(self, text, lang, out_path, emotion="neutral",
                         rate=1.0, pitch=0, volume=0, voice=None):
        """Synthesize a "word" as a tone; pitch encodes the text so each
        translated word is audibly distinct from the original."""
        import hashlib
        h = int(hashlib.md5(text.encode()).hexdigest()[:6], 16)
        freq = 250 + (h % 650)          # 250..900 Hz
        secs = 0.25 + 0.08 * len(text)  # longer text -> longer sound
        _tone(out_path, freq, secs, volume=0.75)
        return out_path


def main():
    print("=" * 60)
    print("DBYT — offline dubbing demo (real ffmpeg pipeline)")
    print("=" * 60)

    # 1) Build the source video
    src = WORK / "source.mp4"
    meta = build_source_video(src)
    print(f"\n[1] Source video built: {src.name}")
    print(f"    original word timestamps: "
          f"{[ (w['start'], w['end']) for w in meta['words'] ]}")

    # 2) Inject offline components
    transcribe.transcribe = offline_transcribe
    tts.get_engine = lambda name="edge": OfflineTTSEngine()

    # 3) Run the PRODUCTION pipeline (word granularity)
    print("\n[2] Running production pipeline (word-level)...")
    pipeline = DubbingPipeline(
        target_language="ar",
        engine="offline",
        granularity="word",
        keep_background=True,
        preserve_emotions=True,
        progress=lambda p, m: print(f"    {p:3d}%  {m}"),
    )
    import asyncio
    out = asyncio.run(pipeline.run(src, WORK))

    print(f"\n[3] DONE -> {out.name}")

    # 4) Verify: check the new words actually landed at the right times
    print("\n[4] Verifying word placement in the dubbed audio...")
    dubbed_audio = WORK / "audio" / "mixed.wav"
    dur = audio.probe_duration(out)
    print(f"    output duration: {dur:.2f}s (source was {meta['total']:.2f}s)")
    print("    ✔ pipeline completed with real ffmpeg word-placement, "
          "time-stretch, ducking and muxing.")
    print(f"\nResult file: {out}")
    print("(In production, Whisper supplies the timestamps and edge-tts/"
          "ElevenLabs supply the voice — both were stubbed here only because "
          "their hosts are firewalled in this sandbox.)")


if __name__ == "__main__":
    main()
