"""Translation layer — with OFFLINE (self-hosted) backends.

Backends (selected via `DBYT_TRANSLATOR_BACKEND`):

  * ``google``  (default) — deep-translator, free Google translate (needs internet)
  * ``openai``  — OpenAI (needs `DBYT_OPENAI_API_KEY`)
  * ``argos``   — Argos Translate, fully OFFLINE neural MT (en↔ar among others)
                 → solves "translation host blocked" by running locally.
  * ``nllb``    — Meta NLLB-200, best Arabic quality (chrF 63.8), OFFLINE via
                 CTranslate2 / transformers. Larger model (~2.5 GB).

The interface always returns `list[str]`, so the pipeline never cares which
backend is active. Offline backends fail back to `google` if not installed.
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
    backend = settings.translator_backend

    if backend == "openai" and settings.openai_api_key:
        return _translate_openai(texts, target_lang)
    if backend == "argos":
        try:
            return _translate_argos(texts, target_lang, source_lang)
        except Exception as exc:  # noqa: BLE001 — fall back to Google
            print(f"[translate] argos unavailable ({exc}); falling back to google")
    if backend == "nllb":
        try:
            return _translate_nllb(texts, target_lang, source_lang)
        except Exception as exc:  # noqa: BLE001
            print(f"[translate] nllb unavailable ({exc}); falling back to google")
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


# ---- OFFLINE backends ------------------------------------------------------

def _argos_lang(code: str) -> str:
    """Argos uses 2-letter codes with a few exceptions."""
    return {"zh": "zh", "pt": "pt", "en": "en", "ar": "ar"}.get(code, code)


def _translate_argos(texts: List[str], target_lang: str, source_lang: str) -> List[str]:
    """Argos Translate — offline, model installed from `argospm` package index.

    Install once:
        pip install argostranslate
        python -m argostranslate.cli install-package translate-en_ar  # or -ar_en
    """
    import argostranslate.package
    import argostranslate.translate

    # Resolve source: Argos needs explicit from-code (auto-detect not built-in).
    from_codes = _argos_lang(source_lang if source_lang and source_lang != "auto" else "en")
    to_codes = _argos_lang(target_lang)

    # Ensure the language pair is installed
    try:
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()
        pair = next(
            (p for p in available
             if p.from_code == from_codes and p.to_code == to_codes),
            None,
        )
        if pair is None:
            raise RuntimeError(f"Argos pair {from_codes}->{to_codes} not installed")
        argostranslate.package.install_from_path(pair.download())
    except Exception as exc:  # noqa: BLE001
        # Already installed models still work; only re-raise if nothing installed
        installed = argostranslate.package.get_installed_packages()
        if not any(p.from_code == from_codes and p.to_code == to_codes for p in installed):
            raise exc

    out: List[str] = []
    for t in texts:
        if not t.strip():
            out.append("")
            continue
        out.append(argostranslate.translate.translate(t, from_codes, to_codes))
    return out


def _translate_nllb(texts: List[str], target_lang: str, source_lang: str) -> List[str]:
    """Meta NLLB-200 — best offline Arabic quality (chrF 63.8).

    Install:  pip install ctranslate2 transformers sentencepiece
    Model:    facebook/nllb-200-distilled-600M (~2.5 GB, cached in workspace/models)
    """
    import ctranslate2
    import sentencepiece as spm
    import transformers
    from huggingface_hub import snapshot_download

    # NLLB language codes
    NLLB = {
        "ar": "arb_Arab", "fr": "fra_Latn", "en": "eng_Latn", "es": "spa_Latn",
        "de": "deu_Latn", "it": "ita_Latn", "pt": "por_Latn", "tr": "tur_Latn",
        "ru": "rus_Cyrl", "zh": "zho_Hans", "ja": "jpn_Jpan", "ko": "kor_Hang",
        "hi": "hin_Deva", "nl": "nld_Latn",
    }
    tgt = NLLB.get(target_lang, target_lang)
    src = NLLB.get(source_lang, "eng_Latn") if source_lang != "auto" else "eng_Latn"

    model_dir = snapshot_download("facebook/nllb-200-distilled-600M")
    ct_model = ctranslate2.Translator(str(model_dir), device="cpu")
    tok = transformers.AutoTokenizer.from_pretrained(model_dir)
    sp = spm.SentencePieceProcessor(model_file=str(model_dir) + "/sentencepiece.bpe.model")

    def _detect_src(t: str) -> str:
        # NLLB needs a source language per sentence; default to English.
        return src

    out: List[str] = []
    for t in texts:
        if not t.strip():
            out.append("")
            continue
        source = _detect_src(t)
        target_prefix = [f"__{tgt}__"]
        src_tokens = sp.encode("__" + source + "__ " + t, out_type=str)
        results = ct_model.translate_batch(
            [src_tokens],
            target_prefix=[target_prefix],
            beam_size=4,
            max_batch_size=8,
        )
        out.append(" ".join(results[0].hypotheses[0]).strip())
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
