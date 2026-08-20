"""The dubbing pipeline orchestrator.

End-to-end flow for turning any video into a dubbed video:

    media -> transcribe (Whisper, word timestamps)
          -> translate (to target language)
          -> detect emotion per segment
          -> synthesize speech (pluggable TTS engine + prosody)
          -> time-stretch each clip to the speaker's original timing
          -> concatenate + mix over the (ducked) original audio
          -> mux back into the video

The pipeline reports progress through an optional `progress` callback so the
web UI (and the GitHub Actions runner) can show live status.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, List, Optional

from ..config import settings
from . import audio, emotion, transcribe, translate, tts, youtube

ProgressFn = Callable[[int, str], None]


class DubbingPipeline:
    def __init__(
        self,
        target_language: str = "ar",
        engine: str = "edge",
        voice: Optional[str] = None,
        keep_background: bool = True,
        preserve_emotions: bool = True,
        progress: Optional[ProgressFn] = None,
    ):
        self.target_language = target_language
        self.engine_name = engine
        self.voice = voice
        self.keep_background = keep_background
        self.preserve_emotions = preserve_emotions
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
        self._report(15, "Transcribing speech (Whisper)...")
        segments, detected_lang = transcribe.transcribe(media_path, language=source_language)
        if not segments:
            raise RuntimeError("No speech detected in the video.")
        src_lang = (detected_lang or "").split("-")[0] if detected_lang else "auto"

        # 2) Translate
        self._report(35, f"Translating to {self.target_language}...")
        texts = [s.text for s in segments]
        translated = translate.translate_texts(texts, self.target_language, source_lang="auto")

        # 3) Synthesize (with emotion-aware prosody), per segment
        engine = tts.get_engine(self.engine_name)
        clips: List[Path] = []
        total = len(segments)
        for i, (seg, text) in enumerate(zip(segments, translated)):
            self._report(
                40 + int(45 * i / total),
                f"Synthesizing voice {i + 1}/{total}...",
            )
            if not text.strip():
                # silence for a gap
                gap = seg.end - seg.start
                silence = tts_dir / f"{i:04d}_silence.wav"
                await asyncio.to_thread(_make_silence, silence, gap)
                clips.append(silence)
                continue

            emo = emotion.analyze(seg.text, src_lang, preserve=self.preserve_emotions)
            out = tts_dir / f"{i:04d}.wav"
            await engine.synthesize(
                text=text,
                lang=self.target_language,
                out_path=out,
                emotion=emo.emotion,
                rate=emo.rate,
                pitch=emo.pitch,
                volume=emo.volume,
                voice=self.voice,
            )
            # 4) time-stretch to the original speaker's duration
            target_dur = max(0.25, seg.end - seg.start)
            stretched = tts_dir / f"{i:04d}_stretched.wav"
            audio.time_stretch(out, stretched, target_dur)
            clips.append(stretched)

        # 5) Concatenate the dubbed track
        self._report(88, "Assembling dubbed audio...")
        dub_track = audio_dir / "dub.wav"
        audio.concat_wavs(clips, dub_track)

        # 6) Mix over original audio
        self._report(93, "Mixing dubbed voice with background...")
        original_audio = audio_dir / "original.wav"
        await asyncio.to_thread(
            _extract_audio, media_path, original_audio
        )
        mixed = audio_dir / "mixed.wav"
        audio.mix_dub_over_original(
            original_audio, dub_track, 0.0, mixed,
            duck_volume=settings.background_duck_volume,
            keep_background=self.keep_background,
        )

        # 7) Mux into video (or produce audio-only if input was audio)
        self._report(98, "Muxing final video...")
        final = work_dir / "dubbed.mp4"
        if _has_video_stream(media_path):
            audio.mux_audio_video(media_path, mixed, final)
        else:
            final = work_dir / "dubbed.mp3"
            await asyncio.to_thread(_to_mp3, mixed, final)

        self._report(100, "Done")
        return final


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
