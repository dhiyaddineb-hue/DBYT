"""Lightweight emotion detection from transcribed speech.

Detects the dominant emotion of each segment from lexical cues and punctuation,
then maps it to prosody hints (rate / pitch / volume) that each TTS engine
translates into its own controls. This is what lets the dubbed voice "carry the
same feelings" as the original speaker without needing a heavy speech-emotion
model. ElevenLabs additionally captures emotion natively from its voice model.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

# Lexicons per language — extend freely. Keys are lowercase stems.
_EMOTION_LEXICON: Dict[str, Dict[str, str]] = {
    "happy": {
        "ar": ["فرح", "سعيد", "مبسوط", "رائع", "جميل", "ممتاز", "أحب", "حلو", "ضحك", "مبروك", "نجاح"],
        "en": ["happy", "great", "wonderful", "amazing", "love", "awesome", "excited", "fun", "beautiful", "congratulations"],
        "fr": ["heureux", "génial", "super", "merveilleux", "aime", "adorer", "magnifique", "génial", "bravo", "excellent"],
    },
    "sad": {
        "ar": ["حزين", "حزن", "بكاء", "ألم", "مؤلم", "فقد", "وداع", "سيء", "مأساة", "متعب", "خسارة"],
        "en": ["sad", "sorry", "cry", "pain", "lost", "miss", "tragic", "unfortunate", "regret", "heartbreak"],
        "fr": ["triste", "tristesse", "pleurer", "douleur", "perdu", "regret", "tragique", "désolé", "manque", "peine"],
    },
    "angry": {
        "ar": ["غاضب", "غضب", "أكره", "ظلم", "كفى", "غبي", "مستحيل", "احذر", "خطير"],
        "en": ["angry", "hate", "stupid", "outrageous", "unfair", "never", "stop", "damn", "furious"],
        "fr": ["colère", "fâché", "déteste", "injuste", "stupide", "assez", "jamais", "rage"],
    },
    "surprised": {
        "ar": ["مدهش", "مفاجأة", "لا أصدق", "مذهل", "غريب", "حقاً", "يا إلهي"],
        "en": ["wow", "amazing", "surprised", "unbelievable", "incredible", "what", "really", "oh"],
        "fr": ["wow", "surprenant", "incroyable", "vraiment", "quoi", "étonnant"],
    },
    "fearful": {
        "ar": ["خائف", "خوف", "مرعب", "خطر", "انقذ", "مخيف", "احترس"],
        "en": ["afraid", "scared", "fear", "terrified", "danger", "help", "horror"],
        "fr": ["peur", "effrayé", "terrifié", "danger", "aide", "horreur"],
    },
}

# prosody hints: (rate_multiplier, pitch_shift_semitones, volume_delta_db)
_EMOTION_PROSODY: Dict[str, Tuple[float, float, float]] = {
    "neutral": (1.0, 0, 0),
    "happy": (1.10, +2, +1.5),
    "sad": (0.88, -3, -2.0),
    "angry": (1.14, +3, +3.0),
    "surprised": (1.12, +4, +2.0),
    "fearful": (1.04, -1, +1.0),
}


@dataclass
class EmotionResult:
    emotion: str
    rate: float
    pitch: float
    volume: float


def _detect(text: str, lang: str) -> str:
    t = text.lower()
    # Punctuation signals
    exclaims = t.count("!")
    questions = t.count("?")
    if exclaims >= 2 or (exclaims >= 1 and questions >= 1):
        return "surprised"

    scores: Dict[str, int] = {}
    for emotion, langs in _EMOTION_LEXICON.items():
        lexicon = langs.get(lang) or langs.get("en", [])
        scores[emotion] = sum(1 for w in lexicon if w.lower() in t)
    best = max(scores, key=scores.get) if any(scores.values()) else None
    return best or "neutral"


def analyze(text: str, lang: str = "auto", preserve: bool = True) -> EmotionResult:
    """Return the prosody profile for a segment of speech."""
    if not preserve:
        return EmotionResult("neutral", 1.0, 0, 0)
    emotion = _detect(text, lang)
    rate, pitch, volume = _EMOTION_PROSODY[emotion]
    return EmotionResult(emotion, rate, pitch, volume)


def bark_emotion_prefix(emotion: str) -> str:
    """Bark-style emotion tokens."""
    mapping = {
        "happy": "[laughter] ",
        "sad": "[sad] ",
        "surprised": "[excited] ",
        "angry": "[angry] ",
        "fearful": "[fearful] ",
        "neutral": "",
    }
    return mapping.get(emotion, "")
