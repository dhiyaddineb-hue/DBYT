"""Translation layer.

Default backend is `deep-translator` (free Google translate). An OpenAI-backed
translator is available when `DBYT_OPENAI_API_KEY` is set, and DeepL is a
straightforward drop-in. The interface returns the same `list[str]` shape so
the pipeline never cares which backend is active.
"""
from __future__ import annotations

from typing import List

from ..config import settings

_LANG_MAP = {
    "ar": "arabic",
    "fr": "french",
    "en": "english",
    "es": "spanish",
    "de": "german",
    "it": "italian",
    "pt": "portuguese",
    "tr": "turkish",
    "ru": "russian",
    "zh": "chinese (simplified)",
    "ja": "japanese",
    "ko": "korean",
    "hi": "hindi",
    "nl": "dutch",
}


def translate_texts(texts: List[str], target_lang: str, source_lang: str = "auto") -> List[str]:
    """Translate a batch of texts into the target language."""
    if settings.translator_backend == "openai" and settings.openai_api_key:
        return _translate_openai(texts, target_lang)
    return _translate_google(texts, target_lang)


def _translate_google(texts: List[str], target_lang: str) -> List[str]:
    from deep_translator import GoogleTranslator

    tl = _LANG_MAP.get(target_lang, target_lang)
    translator = GoogleTranslator(source="auto", target=tl)
    out: List[str] = []
    for t in texts:
        if not t.strip():
            out.append("")
            continue
        try:
            out.append(translator.translate(t))
        except Exception:  # noqa: BLE001 — keep original text on failure
            out.append(t)
    return out


def _translate_openai(texts: List[str], target_lang: str) -> List[str]:
    import json
    import urllib.request

    out: List[str] = []
    for t in texts:
        if not t.strip():
            out.append("")
            continue
        payload = json.dumps(
            {
                "model": "gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"You are a professional dubbing translator. Translate the user "
                            f"text into {target_lang}, keeping it natural, idiomatic and "
                            "close in length to the original so it fits the same timing."
                        ),
                    },
                    {"role": "user", "content": t},
                ],
                "temperature": 0.3,
            }
        )
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload.encode(),
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        out.append(data["choices"][0]["message"]["content"].strip())
    return out
