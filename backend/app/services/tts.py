"""Text-to-speech engines.

A pluggable set of engines. Every engine exposes:

    synthesize(text, lang, out_path, emotion, rate, pitch, volume) -> Path

`emotion` is the detected emotion name; `rate/pitch/volume` are prosody hints
produced by `emotion.analyze`. Engines translate those hints into their own
controls:

- `edge`: free, fast, natural Microsoft neural voices, multilingual (default).
- `elevenlabs`: premium, human-like with true emotion (needs API key).
- `bark`: open-source, emotion-aware (needs heavier deps; optional).
- `xtts`: open-source voice cloning (Coqui XTTS v2, 17 languages incl. Arabic).
- `piper`: OFFLINE, ultra-fast neural TTS (Rhasspy) with an Arabic voice.
  → solves "TTS host blocked" by running 100% locally (ONNX, CPU).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..config import settings

# Map language code -> edge-tts voice (extend as needed).
_EDGE_VOICES = {
    "ar": "ar-SA-HamedNeural",        # Arabic (Saudi) — male
    "ar-f": "ar-EG-SalmaNeural",      # Arabic (Egypt) — female
    "fr": "fr-FR-HenriNeural",        # French — male
    "fr-f": "fr-FR-DeniseNeural",     # French — female
    "en": "en-US-ChristopherNeural",  # English — male
    "en-f": "en-US-JennyNeural",      # English — female
    "es": "es-ES-AlvaroNeural",
    "de": "de-DE-ConradNeural",
    "it": "it-IT-DiegoNeural",
    "pt": "pt-PT-DuarteNeural",
    "tr": "tr-TR-AhmetNeural",
    "ru": "ru-RU-DmitryNeural",
    "zh": "zh-CN-YunxiNeural",
    "ja": "ja-JP-KeitaNeural",
    "ko": "ko-KR-InJoonNeural",
    "hi": "hi-IN-MadhurNeural",
}


def get_engine(name: Optional[str] = None):
    name = name or settings.default_engine
    if name == "edge":
        return EdgeEngine()
    if name == "elevenlabs":
        return ElevenLabsEngine()
    if name == "bark":
        return BarkEngine()
    if name == "xtts":
        return XTTSEngine()
    if name == "piper":
        return PiperEngine()
    raise ValueError(f"Unknown TTS engine: {name}")


def _voice_for(lang: str, female: bool = False) -> str:
    key = f"{lang}-f" if female else lang
    return _EDGE_VOICES.get(key, _EDGE_VOICES.get(lang, "en-US-ChristopherNeural"))


class EdgeEngine:
    """Free Microsoft neural voices via edge-tts."""

    name = "edge"

    async def synthesize(
        self,
        text: str,
        lang: str,
        out_path: Path,
        emotion: str = "neutral",
        rate: float = 1.0,
        pitch: float = 0,
        volume: float = 0,
        voice: Optional[str] = None,
    ) -> Path:
        import edge_tts

        v = voice or _voice_for(lang)
        # Map prosody hints onto edge-tts controls
        rate_pct = int(round((rate - 1.0) * 100))
        pitch_hz = int(round(pitch * 25))  # semitones -> ~Hz for edge
        volume_pct = int(round(volume * 10))
        rate_str = f"{rate_pct:+d}%" if rate_pct else "+0%"
        pitch_str = f"{pitch_hz:+d}Hz" if pitch_hz else "+0Hz"
        volume_str = f"{volume_pct:+d}%" if volume_pct else "+0%"

        communicate = edge_tts.Communicate(
            text, v, rate=rate_str, pitch=pitch_str, volume=volume_str
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        await communicate.save(str(out_path))
        return out_path


class ElevenLabsEngine:
    """Premium emotional TTS (requires DBYT_ELEVENLABS_API_KEY)."""

    name = "elevenlabs"

    async def synthesize(
        self,
        text: str,
        lang: str,
        out_path: Path,
        emotion: str = "neutral",
        rate: float = 1.0,
        pitch: float = 0,
        volume: float = 0,
        voice: Optional[str] = None,
    ) -> Path:
        import asyncio

        def _run():
            from elevenlabs import VoiceSettings, generate, save

            # Emotion -> stability / similarity / style (ElevenLabs Multilingual v2)
            emotion_settings = {
                "neutral": (0.50, 0.75, 0.0),
                "happy": (0.30, 0.80, 0.6),
                "sad": (0.75, 0.70, -0.4),
                "angry": (0.25, 0.85, 0.7),
                "surprised": (0.28, 0.78, 0.8),
                "fearful": (0.45, 0.72, 0.3),
            }
            stability, similarity, style = emotion_settings.get(emotion, (0.5, 0.75, 0.0))

            audio = generate(
                text=text,
                voice=voice or settings.elevenlabs_voice_id,
                model="eleven_multilingual_v2",
                voice_settings=VoiceSettings(
                    stability=stability,
                    similarity_boost=similarity,
                    style=style,
                    use_speaker_boost=True,
                ),
            )
            save(audio, str(out_path))

        await asyncio.to_thread(_run)
        return out_path


class BarkEngine:
    """Open-source emotion-aware TTS (Suno Bark). Heavy; optional dependency."""

    name = "bark"

    async def synthesize(
        self,
        text: str,
        lang: str,
        out_path: Path,
        emotion: str = "neutral",
        rate: float = 1.0,
        pitch: float = 0,
        volume: float = 0,
        voice: Optional[str] = None,
    ) -> Path:
        import asyncio

        from .emotion import bark_emotion_prefix

        def _run():
            import numpy as np
            import scipy.io.wavfile as wavfile
            from bark import SAMPLE_RATE, generate_audio, preload_models

            preload_models()
            prefix = bark_emotion_prefix(emotion)
            audio = generate_audio(prefix + text, history_prompt="v2/en_speaker_6")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            wavfile.write(str(out_path), SAMPLE_RATE, np.asarray(audio))

        await asyncio.to_thread(_run)
        return out_path


class PiperEngine:
    """Piper TTS (Rhasspy) — 100% OFFLINE neural voices on CPU.

    Fast ONNX models. The Arabic voice is fetched into ``settings.models_dir``
    on first use, so no runtime network is needed afterwards (solves the
    "TTS host blocked" problem by design).

    Install:  pip install piper-tts
    """

    name = "piper"

    # language -> (huggingface repo file, quality)
    _VOICES = {
        "ar": ("ar_JO/kareem/medium", "ar_JO-kareem-medium"),
        "en": ("en_US/amy/medium", "en_US-amy-medium"),
        "fr": ("fr_FR/siwis/medium", "fr_FR-siwis-medium"),
        "de": ("de_DE/thorsten/medium", "de_DE-thorsten-medium"),
        "es": ("es_ES/davefx/medium", "es_ES-davefx-medium"),
    }

    def _ensure_voice(self, lang: str) -> str:
        from piper.download import ensure_voice_exists, find_voice, get_voices

        voice_key = self._VOICES.get(lang, self._VOICES["en"])[1]
        try:
            voices = get_voices()
            return next(v for v in voices if voice_key in v)[0]
        except Exception:  # noqa: BLE001
            return ensure_voice_exists(voice_key, [str(settings.models_dir)], str(settings.models_dir))

    async def synthesize(
        self,
        text: str,
        lang: str,
        out_path: Path,
        emotion: str = "neutral",
        rate: float = 1.0,
        pitch: float = 0,
        volume: float = 0,
        voice: Optional[str] = None,
    ) -> Path:
        import asyncio
        import wave

        def _run():
            from piper import PiperVoice

            model_path = voice or self._ensure_voice(lang)
            v = PiperVoice.load(model_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(out_path), "wb") as wf:
                v.synthesize(text, wf)

        await asyncio.to_thread(_run)
        return out_path


class XTTSEngine:
    """Open-source voice cloning (Coqui XTTS v2). Needs GPU for real-time.

    Clones the ORIGINAL speaker's voice from a 6s sample, so the dub keeps the
    speaker's identity in the target language — the closest free equivalent to
    ElevenLabs. Supports 17 languages including Arabic.

    Install:  pip install coqui-tts
    """

    name = "xtts"

    async def synthesize(
        self,
        text: str,
        lang: str,
        out_path: Path,
        emotion: str = "neutral",
        rate: float = 1.0,
        pitch: float = 0,
        volume: float = 0,
        voice: Optional[str] = None,
    ) -> Path:
        import asyncio

        def _run():
            from TTS.api import TTS

            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
            tts.tts_to_file(
                text=text,
                speaker_wav=voice,  # path to a 6s+ reference clip of the speaker
                language=lang,
                file_path=str(out_path),
            )

        await asyncio.to_thread(_run)
        return out_path

    name = "xtts"

    async def synthesize(
        self,
        text: str,
        lang: str,
        out_path: Path,
        emotion: str = "neutral",
        rate: float = 1.0,
        pitch: float = 0,
        volume: float = 0,
        voice: Optional[str] = None,
    ) -> Path:
        import asyncio

        def _run():
            from TTS.api import TTS

            tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
            tts.tts_to_file(text=text, speaker_wav=None, language=lang, file_path=str(out_path))

        await asyncio.to_thread(_run)
        return out_path
