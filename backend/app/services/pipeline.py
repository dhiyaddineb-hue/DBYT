"""The dubbing pipeline orchestrator.

End-to-end flow for turning any video into a dubbed video that looks *original*:

    media -> transcribe (Whisper, word timestamps)
          -> translate (to target language)
          -> detect emotion per segment
          -> synthesize speech (pluggable TTS engine + prosody)
          -> time-stretch each unit to the original timing
          -> place every unit at its EXACT timestamp (word-level precision)
          -> concatenate + mix over the (ducked) original audio
          -> [optional] lip-sync the mouth to the new voice (Wav2Lip)

Two granularities are supported:

  * ``word``   — each word is synthesized & stretched to the original word's
                 duration and dropped at the exact moment it was spoken. This is
                 the "every word in its place" mode.
  * ``segment`` — each sentence is synthesized and stretched to the sentence
                 duration (faster, but coarser).

The pipeline reports progress through an optional `progress` callback so the
web UI (and the GitHub Actions runner) can show live status.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ..config import settings
from . import audio, emotion, lipsync, transcribe, translate, tts, youtube

ProgressFn = Callable[[int, str], None]

_WORD_RE = re.compile(r"\S+")


def split_words(text: str) -> List[str]:
    return _WORD_RE.findall(text or "")


def _map_target_words(target_words: List[str], n_source: int) -> List[str]:
    """Map translated words onto source word slots (1:1 in order).

    When the counts differ we stretch/shrink evenly so every source slot gets
    a chunk of speech and no words are dropped.
    """
    if n_source <= 0:
        return target_words or [""]
    if not target_words:
        return [""] * n_source
    if len(target_words) == n_source:
        return target_words
    if len(target_words) < n_source:
        # Repeat words to fill (cheap; keeps timing). Better than silence.
        out: List[str] = []
        while len(out) < n_source:
            out.extend(target_words)
        return out[:n_source]
    # More target words than source slots: merge the tail words into slots.
    per = len(target_words) // n_source
    remainder = len(target_words) % n_source
    out = []
    i = 0
    for s in range(n_source):
        take = per + (1 if s < remainder else 0)
        chunk = " ".join(target_words[i:i + take])
        out.append(chunk)
        i += take
    return out


class DubbingPipeline:
    def __init__(
        self,
        target_language: str = "ar",
        engine: str = "edge",
        voice: Optional[str] = None,
        keep_background: bool = True,
        preserve_emotions: bool = True,
        granularity: str = "word",
        lip_sync: bool = False,
        progress: Optional[ProgressFn] = None,
    ):
        self.target_language = target_language
        self.engine_name = engine
        self.voice = voice
        self.keep_background = keep_background
        self.preserve_emotions = preserve_emotions
        self.granularity = granularity
        self.lip_sync_enabled = lip_sync
        self.progress = progress or (lambda p, m: None)

    def _report(self, progress: int, message: str) -> None:
        self.progress(progress, message)

    async def run(
        self,
        media_path: Path,
        work_dir: Path,
        source_language: Optional[str] = None,
    ) -> Path:
        """Run the full pipeline. Returns the path to the dubbed video."""
        work_dir.mkdir(parents=True, exist_ok=True)
        audio_dir = work_dir / "audio"
        tts_dir = work_dir / "tts"
        audio_dir.mkdir(parents=True, exist_ok=True)
        tts_dir.mkdir(parents=True, exist_ok=True)

        # 1) Transcribe
        self._report(12, "Transcribing speech (Whisper)...")
        segments, detected_lang = transcribe.transcribe(media_path, language=source_language)
        if not segments:
            raise RuntimeError("No speech detected in the video.")
        src_lang = (detected_lang or "").split("-")[0] if detected_lang else "auto"

        # 2) Translate (sentence level — words need context)
        self._report(28, f"Translating to {self.target_language}...")
        texts = [s.text for s in segments]
        translated = translate.translate_texts(texts, self.target_language, source_lang="auto")

        # 3) Synthesize + time-stretch + place at exact timestamps
        engine = tts.get_engine(self.engine_name)
        placements: List[Tuple[Path, float]] = []
        total_units = self._count_units(segments)

        unit_idx = 0
        for seg, seg_translated in zip(segments, translated):
            emo = emotion.analyze(seg.text, src_lang, preserve=self.preserve_emotions)
            units = self._make_units(seg, seg_translated)
            for text_chunk, start, duration in units:
                unit_idx += 1
                if unit_idx % 5 == 0 or unit_idx == 1:
                    self._report(
                        30 + int(40 * unit_idx / max(1, total_units)),
                        f"Voicing unit {unit_idx}/{total_units}...",
                    )
                out = tts_dir / f"{unit_idx:06d}.wav"
                if not text_chunk.strip():
                    # a real pause — keep silence
                    await asyncio.to_thread(_make_silence, out, duration)
                else:
                    await engine.synthesize(
                        text=text_chunk,
                        lang=self.target_language,
                        out_path=out,
                        emotion=emo.emotion,
                        rate=emo.rate,
                        pitch=emo.pitch,
                        volume=emo.volume,
                        voice=self.voice,
                    )
                # Stretch the clip to match the original timing
                target_dur = max(0.2, duration)
                stretched = tts_dir / f"{unit_idx:06d}_s.wav"
                audio.time_stretch(out, stretched, target_dur)
                placements.append((stretched, start))

        # 4) Assemble the dubbed track with word-level placement
        self._report(78, "Placing every word at its exact moment...")
        dub_track = audio_dir / "dub.wav"
        audio.place_clips_at_times(placements, dub_track)

        # 5) Mix over original audio (duck music/ambience under the voice)
        self._report(88, "Mixing dubbed voice with background...")
        original_audio = audio_dir / "original.wav"
        await asyncio.to_thread(_extract_audio, media_path, original_audio)
        mixed = audio_dir / "mixed.wav"
        audio.mix_dub_over_original(
            original_audio, dub_track, 0.0, mixed,
            duck_volume=settings.background_duck_volume,
            keep_background=self.keep_background,
        )

        # 6) Mux into video (or produce audio-only if input was audio)
        self._report(94, "Muxing final video...")
        has_video = _has_video_stream(media_path)
        if has_video:
            final = work_dir / "dubbed.mp4"
            audio.mux_audio_video(media_path, mixed, final)
        else:
            final = work_dir / "dubbed.mp3"
            await asyncio.to_thread(_to_mp3, mixed, final)

        # 7) Optional lip-sync so the mouth moves with the new voice
        if self.lip_sync_enabled and has_video:
            self._report(97, "Lip-syncing the mouth (Wav2Lip)...")
            synced = work_dir / "dubbed_lipsync.mp4"
            try:
                final = await asyncio.to_thread(
                    lipsync.sync_final_video, final, mixed, synced
                )
            except Exception as exc:  # noqa: BLE001 — fall back gracefully
                print(f"[lipsync] skipped: {exc}")

        self._report(100, "Done")
        return final

    def _count_units(self, segments) -> int:
        if self.granularity == "word":
            return sum(len(s.words) or 1 for s in segments)
        return len(segments)

    def _make_units(self, seg, seg_translated: str) -> List[Tuple[str, float, float]]:
        """Return a list of ``(text, start, duration)`` units to synthesize.

        Word mode splits the translated sentence onto the original word slots;
        segment mode uses the whole sentence for the whole segment.
        """
        if self.granularity != "word" or not seg.words:
            return [(seg_translated or "", seg.start, seg.end - seg.start)]

        src_words = seg.words
        tgt_words = split_words(seg_translated)
        mapped = _map_target_words(tgt_words, len(src_words))
        units: List[Tuple[str, float, float]] = []
        for i, w in enumerate(src_words):
            chunk = mapped[i] if i < len(mapped) else ""
            start = w.start
            end = w.end if w.end > w.start else w.start + 0.3
            units.append((chunk, start, end - start))
        return units


# ---- small blocking helpers -------------------------------------------------

def _make_silence(path: Path, seconds: float) -> None:
    import subprocess

    seconds = max(0.1, seconds)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
         "-t", f"{seconds:.2f}", str(path)],
        check=True, capture_output=True,
    )


def _extract_audio(media: Path, out: Path) -> None:
    import subprocess

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(media), "-vn", "-ac", "2", "-ar", "44100", str(out)],
        check=True, capture_output=True,
    )


def _has_video_stream(media: Path) -> bool:
    import subprocess

    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=codec_type", "-of", "csv=p=0", str(media)],
            text=True,
        )
        return "video" in out
    except Exception:  # noqa: BLE001
        return False


def _to_mp3(wav: Path, out: Path) -> None:
    import subprocess

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "192k", str(out)],
        check=True, capture_output=True,
    )


async def run_youtube_dub(
    url: str,
    work_dir: Path,
    **kwargs,
) -> Path:
    """Convenience wrapper: download a YouTube video then dub it."""
    media = youtube.download_media(url, work_dir / "source", prefer_audio=False)
    pipeline = DubbingPipeline(**kwargs)
    return await pipeline.run(media, work_dir)
