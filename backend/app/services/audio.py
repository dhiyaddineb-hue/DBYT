"""Audio helpers built on ffmpeg: time-stretch, concatenation, mixing.

Time-stretching each dubbed segment to match the original speaker's duration is
what keeps the dub "tight" against the video (the mouth keeps moving for about
as long as the words last).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List


def probe_duration(path: Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        text=True,
    )
    return float(out.strip())


def _atempo_chain(factor: float) -> str:
    """Build an ffmpeg atempo filter chain. atempo supports 0.5..2.0."""
    factor = max(0.5, min(2.0, factor))
    parts: List[str] = []
    # clamp into 0.5..2.0 by chaining
    while factor > 2.0:
        parts.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        parts.append("atempo=0.5")
        factor /= 0.5
    parts.append(f"atempo={factor:.4f}")
    return ",".join(parts)


def time_stretch(src: Path, dst: Path, target_duration: float) -> Path:
    """Stretch/compress audio to `target_duration` seconds."""
    src_dur = probe_duration(src)
    if src_dur <= 0:
        return src
    factor = src_dur / target_duration
    if 0.97 <= factor <= 1.03:
        return src  # already close; skip to preserve quality
    af = _atempo_chain(factor)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-filter:a", af, "-ar", "44100", str(dst)],
        check=True, capture_output=True,
    )
    return dst


def place_clips_at_times(
    clips: List[Tuple[Path, float]],
    dst: Path,
    sample_rate: int = 44100,
) -> Path:
    """Place audio clips at exact start times and mix them into one track.

    This is the heart of *word-level* dubbing: each word's audio is dropped at
    precisely the moment the original speaker uttered it, so the dub lines up
    with the video "as if it were the original".

    ``clips`` is a list of ``(path, start_seconds)``. Clips may overlap; we
    mix with ffmpeg `amix` (each input delayed by its start time).
    """
    clips = sorted(clips, key=lambda c: c[1])
    if not clips:
        raise ValueError("No clips to place")

    # Normalize every clip to the same codec/rate/channels so amix is safe.
    tmp_dir = dst.parent / "placed"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    normalized: List[Tuple[Path, float]] = []
    for i, (p, start) in enumerate(clips):
        np_ = tmp_dir / f"{i:05d}.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(p), "-ar", str(sample_rate), "-ac", "1",
             "-c:a", "pcm_s16le", str(np_)],
            check=True, capture_output=True,
        )
        normalized.append((np_, start))

    # Build a filter graph: [i:a]adelay=ms|ms[...] then amix all
    inputs: List[str] = []
    filters: List[str] = []
    for i, (p, start) in enumerate(normalized):
        inputs += ["-i", str(p)]
        ms = int(round(start * 1000))
        filters.append(f"[{i}:a]adelay={ms}|{ms}[d{i}]")
    mix_inputs = "".join(f"[d{i}]" for i in range(len(normalized)))
    filters.append(
        f"{mix_inputs}amix=inputs={len(normalized)}:duration=longest:"
        f"dropout_transition=3:normalize=0[a]"
    )

    graph = ";".join(filters)
    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", graph,
         "-map", "[a]", "-ar", str(sample_rate), "-ac", "2", str(dst)],
        check=True, capture_output=True,
    )
    return dst


def concat_wavs(paths: List[Path], dst: Path, silence_gap: float = 0.12) -> Path:
    """Concatenate WAV files with a tiny silence gap between segments."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        list_file = f.name
        for p in paths:
            f.write(f"file '{p.resolve()}'\n")

    # Use concat demuxer (requires same codec/rate). We normalize to 44100 WAV.
    normalized = []
    tmp_dir = dst.parent / "norm"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(paths):
        np_ = tmp_dir / f"{i:04d}.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(p), "-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(np_)],
            check=True, capture_output=True,
        )
        normalized.append(np_)

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        list_file2 = f.name
        for p in normalized:
            f.write(f"file '{p.resolve()}'\n")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file2, "-c:a", "pcm_s16le", str(dst)],
        check=True, capture_output=True,
    )
    return dst


def mix_dub_over_original(
    original_audio: Path,
    dub_audio: Path,
    dub_start: float,
    output: Path,
    duck_volume: float = 0.18,
    keep_background: bool = True,
) -> Path:
    """Overlay the dubbed track on top of the original audio.

    When `keep_background` is True the original audio is kept (ducked) so music
    and ambience survive; otherwise the dub fully replaces the soundtrack.
    """
    if not keep_background:
        # Full replacement: just place dub at the right offset
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(dub_audio), "-af", f"adelay={int(dub_start*1000)}|{int(dub_start*1000)}",
             "-ar", "44100", "-ac", "2", str(output)],
            check=True, capture_output=True,
        )
        return output

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(original_audio),
            "-i", str(dub_audio),
            "-filter_complex",
            (
                f"[0:a]volume={duck_volume}[bg];"
                f"[1:a]adelay={int(dub_start*1000)}|{int(dub_start*1000)}[dub];"
                f"[bg][dub]amix=inputs=2:duration=longest:dropout_transition=3[a]"
            ),
            "-map", "[a]", "-ar", "44100", "-ac", "2", str(output),
        ],
        check=True, capture_output=True,
    )
    return output


def mux_audio_video(video_path: Path, audio_path: Path, output: Path) -> Path:
    """Replace the audio track of a video file."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart", str(output),
        ],
        check=True, capture_output=True,
    )
    return output
