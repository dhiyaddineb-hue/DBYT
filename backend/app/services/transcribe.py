"""Speech-to-text via faster-whisper (CPU-friendly Whisper).

Produces word-level timestamps so we can later align the dubbed audio with the
original speaker's timing — the key to a "tight" dub.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..config import settings


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: List[Word] = field(default_factory=list)


def transcribe(audio_path: Path, language: Optional[str] = None):
    """Transcribe an audio/video file into timestamped segments.

    Returns a tuple ``(segments, detected_language)`` where ``detected_language``
    is the language Whisper detected (e.g. "en", "fr"), or ``None``.
    """
    from faster_whisper import WhisperModel

    model = WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )
    segments_iter, info = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
    )

    segments: List[Segment] = []
    for s in segments_iter:
        words = [Word(w.word.strip(), w.start, w.end) for w in (s.words or []) if w.word.strip()]
        segments.append(Segment(start=s.start, end=s.end, text=s.text.strip(), words=words))

    # If no word timestamps survived, synthesize them from segment bounds
    for seg in segments:
        if not seg.words and seg.text:
            seg.words = [Word(seg.text, seg.start, seg.end)]

    detected = info.language if info else None
    return segments, detected


def duration_of(audio_path: Path) -> float:
    """Return media duration in seconds using ffprobe."""
    import subprocess

    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
        ],
        text=True,
    )
    return float(out.strip())
