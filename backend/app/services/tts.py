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
    if name == "sherpa":
        return SherpaEngine()
    if name == "fasih":
        return FasihEngine()
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


class SherpaEngine:
    """sherpa-onnx VITS — high-quality multilingual neural TTS (incl. Arabic).

    The BEST free Arabic quality path. Models are hosted on GitHub Releases
    (not HuggingFace), so they download fine on GitHub Actions / any machine
    with internet. The Arabic voice `vits-piper-ar_JO-kareem-medium` is a
    neural Piper VITS model (~67 MB).

    Install:  pip install sherpa-onnx
    """

    name = "sherpa"

    def __init__(self):
        # Reusing the loaded ONNX session is essential for long videos: the
        # pipeline synthesizes one unit at a time, often hundreds of units.
        self._tts_cache = {}

    # language -> model asset name on the `tts-models` GitHub release
    _MODELS = {
        "ar": "vits-piper-ar_JO-kareem-medium",
        "en": "vits-piper-en_US-lessac-medium",
        "fr": "vits-piper-fr_FR-siwis-medium",
        "es": "vits-piper-es_ES-davefx-medium",
        "de": "vits-piper-de_DE-thorsten-medium",
    }

    def _model_dir(self, lang: str) -> Path:
        """Download and locate the official Sherpa/Piper model directory."""
        import tarfile
        import urllib.request

        model = self._MODELS.get(lang, self._MODELS["en"])
        root = settings.models_dir / "sherpa" / model
        onnx_files = list(root.rglob("*.onnx")) if root.exists() else []
        if onnx_files:
            return onnx_files[0].parent

        root.mkdir(parents=True, exist_ok=True)
        archive = root / f"{model}.tar.bz2"
        url = (
            "https://github.com/k2-fsa/sherpa-onnx/releases/download/"
            f"tts-models/{model}.tar.bz2"
        )
        try:
            urllib.request.urlretrieve(url, archive)
            with tarfile.open(archive, "r:bz2") as bundle:
                base = root.resolve()
                for member in bundle.getmembers():
                    target = (root / member.name).resolve()
                    if target != base and base not in target.parents:
                        raise RuntimeError("Sherpa model archive contains an unsafe path")
                bundle.extractall(root)
            archive.unlink(missing_ok=True)
            onnx_files = list(root.rglob("*.onnx"))
            if not onnx_files:
                raise RuntimeError("Sherpa model archive contains no ONNX model")
            return onnx_files[0].parent
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to download sherpa model {model}: {exc}") from exc

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
            import wave
            import sherpa_onnx

            model_dir = Path(voice) if voice else self._model_dir(lang)
            model_files = list(model_dir.glob("*.onnx"))
            if not model_files:
                raise RuntimeError(f"Sherpa model file not found in {model_dir}")
            cache_key = str(model_files[0].resolve())
            tts = self._tts_cache.get(cache_key)
            if tts is None:
                tokens = model_dir / "tokens.txt"
                data_dir = model_dir / "espeak-ng-data"
                tts_config = sherpa_onnx.OfflineTtsConfig(
                    model=sherpa_onnx.OfflineTtsModelConfig(
                        vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                            model=cache_key,
                            tokens=str(tokens),
                            data_dir=str(data_dir) if data_dir.is_dir() else "",
                        ),
                        provider="cpu",
                        num_threads=2,
                    ),
                    max_num_sentences=1,
                )
                if not tts_config.validate():
                    raise RuntimeError(f"Invalid Sherpa TTS configuration for {model_dir}")
                tts = sherpa_onnx.OfflineTts(tts_config)
                self._tts_cache[cache_key] = tts
            generation = sherpa_onnx.GenerationConfig()
            generation.sid = 0
            generation.speed = max(0.5, min(2.0, rate))
            audio = tts.generate(text, generation)
            if len(audio.samples) == 0:
                raise RuntimeError("Sherpa TTS returned empty audio")
            import numpy as np
            samples = np.asarray(audio.samples, dtype=np.float32)
            pcm = np.clip(samples, -1.0, 1.0)
            pcm16 = (pcm * 32767.0).astype(np.int16)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(out_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(audio.sample_rate)
                wf.writeframes(pcm16.tobytes())

        await asyncio.to_thread(_run)
        return out_path


class FasihEngine:
    """Fasih-TTS-V1: high-quality Arabic MSA voice on GPU Colab.

    The model is a fine-tuned XTTS-v2 checkpoint. It requires a short reference
    clip for speaker conditioning; the full Colab notebook extracts that clip
    from the downloaded source video automatically.
    """

    name = "fasih"
    model_id = "NightPrince/Fasih-TTS-V1"

    def __init__(self):
        self._model = None
        self._conditioning = None
        self._reference = None

    def _load(self, reference: Path):
        import torch
        from huggingface_hub import snapshot_download
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts

        model_dir = Path(snapshot_download(self.model_id))
        config = XttsConfig()
        config.load_json(str(model_dir / "config.json"))
        model = Xtts.init_from_config(config)
        model.load_checkpoint(
            config,
            checkpoint_path=str(model_dir / "model.pth"),
            vocab_path=str(model_dir / "vocab.json"),
            use_deepspeed=False,
        )
        if torch.cuda.is_available():
            model.cuda()
        model.eval()
        self._model = model
        self._conditioning = model.get_conditioning_latents(audio_path=[str(reference)])
        self._reference = str(reference)

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
        import numpy as np
        import soundfile as sf

        def _run():
            reference = Path(voice) if voice else None
            if reference is None or not reference.is_file():
                raise RuntimeError("Fasih requires a reference WAV passed with --voice")
            if self._model is None or self._reference != str(reference):
                self._load(reference)
            gpt_cond, speaker = self._conditioning
            result = self._model.inference(
                text,
                lang,
                gpt_cond,
                speaker,
                temperature=0.65,
                repetition_penalty=2.0,
            )
            samples = result["wav"]
            if hasattr(samples, "detach"):
                samples = samples.detach().cpu().numpy()
            samples = np.asarray(samples, dtype=np.float32).reshape(-1)
            if not samples.size:
                raise RuntimeError("Fasih returned empty audio")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(out_path), samples, 24000, subtype="PCM_16")

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
