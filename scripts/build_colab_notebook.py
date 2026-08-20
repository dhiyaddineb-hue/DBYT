#!/usr/bin/env python3
"""Generate the DBYT Colab notebook (real, GPU dubbing with lip-sync)."""
import json
from pathlib import Path

CELLS = []


def md(src):
    CELLS.append({"cell_type": "markdown", "metadata": {}, "source": src.splitlines(True)})


def code(src):
    CELLS.append({"cell_type": "code", "metadata": {}, "execution_count": None,
                  "outputs": [], "source": src.splitlines(True)})


md("""# 🎙️ DBYT — دبلجة فيديو حقيقية بالعربية (بتوقيت كل كلمة + مزامنة الشفاه)

هذا الدفتر ينفّذ **الدبلجة الكاملة** لأي فيديو يوتيوب:

1. تحميل الفيديو
2. نسخ الكلام بتوقيت **كل كلمة** (Whisper)
3. الترجمة للعربية
4. توليد صوت عربي طبيعي (edge-tts مجاني / ElevenLabs بمشاعر)
5. وضع **كل كلمة في لحظتها الزمنية الدقيقة** (تمديد زمني + محاذاة)
6. دمج الصوت فوق الخلفية الأصلية
7. (اختياري) **مزامنة الشفاه** Wav2Lip على GPU

> **شغّل الخلايا بالترتيب.** لتسريع المهمة: `Runtime → Change runtime type → T4 GPU`.
""")

code("""#@title 1) الإعداد — تثبيت الأدوات
#@markdown شغّل هذه الخلية مرة واحدة.

!sudo apt-get -y install ffmpeg > /dev/null 2>&1
!pip -q install yt-dlp faster-whisper deep-translator edge-tts
!pip -q install pydub

import os, re, subprocess, asyncio
from pathlib import Path

os.makedirs("work", exist_ok=True)
print("✅ جاهز")
""")

code("""#@title 2) الإعدادات
VIDEO_URL = "https://youtu.be/5MgBikgcWnY"  #@param {type:"string"}
TARGET_LANG = "ar"        #@param ["ar","fr","en","es","de"]
VOICE = "ar-SA-HamedNeural"  #@param {type:"string"}  (أو ar-EG-SalmaNeural لصوت أنثوي)
USE_ELEVENLABS = False    #@param {type:"boolean"}  (لصوت بشري بمشاعر حقيقية — ضع المفتاح بالأسفل)
ELEVENLABS_KEY = ""       #@param {type:"string"}
WHISPER_MODEL = "small"   #@param ["tiny","base","small","medium","large-v3"]
GRANULARITY = "word"      #@param ["word","segment"]
KEEP_BACKGROUND = True    #@param {type:"boolean"}

if USE_ELEVENLABS and ELEVENLABS_KEY:
    import os as _os; _os.environ["ELEVENLABS_API_KEY"] = ELEVENLABS_KEY
print("✅ الإعدادات جاهزة")
""")

code("""#@title 3) تحميل الفيديو
import yt_dlp

opts = {
    "format": "best[height<=720]/best",
    "outtmpl": "work/source.%(ext)s",
    "merge_output_format": "mp4",
    "quiet": True,
    "noplaylist": True,
}
with yt_dlp.YoutubeDL(opts) as y:
    info = y.extract_info(VIDEO_URL, download=True)
    src = y.prepare_filename(info)
    if not os.path.exists(src) and src.endswith(".webm"):
        src = src[:-5] + ".mp4"

print("العنوان:", info.get("title"))
print("المدة (ث):", info.get("duration"))
print("الملف:", src)
""")

code("""#@title 4) نسخ الكلام بتوقيت كل كلمة (Whisper)
from faster_whisper import WhisperModel

model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="auto")
segments, info = model.transcribe(
    src, word_timestamps=True, vad_filter=True, beam_size=5
)

segs = []
for s in segments:
    words = [w for w in (s.words or []) if w.word.strip()]
    segs.append({"start": s.start, "end": s.end,
                 "text": s.text.strip(), "words": words})

print("اللغة المكتشفة:", info.language)
print("عدد المقاطع:", len(segs))
print("مثال:", segs[0]["text"])
""")

code("""#@title 5) الترجمة إلى العربية
from deep_translator import GoogleTranslator

tr = GoogleTranslator(source="auto", target=TARGET_LANG)
for s in segs:
    try:
        s["translated"] = tr.translate(s["text"])
    except Exception:
        s["translated"] = s["text"]

print("مثال ترجمة:", segs[0]["translated"])
""")

code("""#@title 6) توليد الصوت + وضع كل كلمة في مكانها الزمني الدقيق

def split_words(t):
    return re.findall(r"\\S+", t or "")

def map_target_words(target_words, n_source):
    if n_source <= 0: return target_words or [""]
    if not target_words: return [""] * n_source
    if len(target_words) == n_source: return target_words
    if len(target_words) < n_source:
        out = []
        while len(out) < n_source: out.extend(target_words)
        return out[:n_source]
    per, rem = divmod(len(target_words), n_source)
    out, i = [], 0
    for s in range(n_source):
        take = per + (1 if s < rem else 0)
        out.append(" ".join(target_words[i:i+take])); i += take
    return out

def atempo_chain(factor):
    factor = max(0.5, min(2.0, factor))
    parts = []
    while factor > 2.0: parts.append("atempo=2.0"); factor /= 2
    while factor < 0.5: parts.append("atempo=0.5"); factor /= 0.5
    parts.append(f"atempo={factor:.4f}")
    return ",".join(parts)

def synth_edge(text, path):
    async def _s():
        await edge_tts.Communicate(text, VOICE).save(path)
    asyncio.run(_s())

def synth(text, path):
    if USE_ELEVENLABS and ELEVENLABS_KEY:
        from elevenlabs import generate, save
        audio = generate(text=text, voice=None, model="eleven_multilingual_v2")
        save(audio, path)
    else:
        synth_edge(text, path)

os.makedirs("work/tts", exist_ok=True)
placements = []   # (path, start_seconds)
unit = 0

for s in segs:
    if GRANULARITY == "word" and s["words"]:
        tgt = split_words(s["translated"])
        mapped = map_target_words(tgt, len(s["words"]))
        for i, w in enumerate(s["words"]):
            chunk = mapped[i] if i < len(mapped) else ""
            unit += 1
            out = f"work/tts/{unit:05d}.wav"
            if chunk.strip():
                synth(chunk, out)
                dur = max(0.2, w.end - w.start)
                stretched = f"work/tts/{unit:05d}_s.wav"
                src_dur = float(subprocess.check_output(
                    ["ffprobe","-v","error","-show_entries","format=duration",
                     "-of","csv=p=0", out], text=True))
                if src_dur > 0 and not (0.97 <= src_dur/dur <= 1.03):
                    subprocess.run(["ffmpeg","-y","-i",out,"-filter:a",
                        atempo_chain(src_dur/dur),"-ar","44100",stretched],
                        capture_output=True)
                else:
                    stretched = out
            else:
                subprocess.run(["ffmpeg","-y","-f","lavfi",
                    "-i",f"anullsrc=r=44100:cl=mono","-t",f"{max(0.1,w.end-w.start):.2f}",
                    out], capture_output=True)
                stretched = out
            placements.append((stretched, w.start))
    else:
        unit += 1
        out = f"work/tts/{unit:05d}.wav"
        synth(s["translated"], out)
        dur = max(0.2, s["end"] - s["start"])
        src_dur = float(subprocess.check_output(
            ["ffprobe","-v","error","-show_entries","format=duration",
             "-of","csv=p=0", out], text=True))
        stretched = f"work/tts/{unit:05d}_s.wav"
        if src_dur > 0 and not (0.97 <= src_dur/dur <= 1.03):
            subprocess.run(["ffmpeg","-y","-i",out,"-filter:a",
                atempo_chain(src_dur/dur),"-ar","44100",stretched], capture_output=True)
        else:
            stretched = out
        placements.append((stretched, s["start"]))

print(f"✅ وُلّد {len(placements)} وحدة صوتية ووُضعت في مواضعها الزمنية")
""")

code("""#@title 7) تجميع المسار المدبلج + دمج الخلفية + تركيب الفيديو
import glob

# ضع كل مقطع في لحظته (adelay + amix)
inputs, filters = [], []
for i, (p, start) in enumerate(sorted(placements, key=lambda c: c[1])):
    np_ = f"work/tts/n{i:05d}.wav"
    subprocess.run(["ffmpeg","-y","-i",p,"-ar","44100","-ac","1",
                    "-c:a","pcm_s16le",np_], capture_output=True)
    inputs += ["-i", np_]
    ms = int(round(start*1000))
    filters.append(f"[{i}:a]adelay={ms}|{ms}[d{i}]")
mix_in = "".join(f"[d{i}]" for i in range(len(placements)))
filters.append(f"{mix_in}amix=inputs={len(placements)}:duration=longest:"
               f"dropout_transition=3:normalize=0[a]")
subprocess.run(["ffmpeg","-y",*inputs,"-filter_complex",";".join(filters),
                "-map","[a]","work/dub.wav"], capture_output=True)

# استخرج صوت الخلفية الأصلي
subprocess.run(["ffmpeg","-y","-i",src,"-vn","-ac","2","-ar","44100",
                "work/orig.wav"], capture_output=True)

# ادمج الدبلجة فوق الخلفية (خفض الموسيقى)
duck = "0.18" if KEEP_BACKGROUND else "0.0"
subprocess.run(["ffmpeg","-y","-i","work/orig.wav","-i","work/dub.wav",
    "-filter_complex",
    f"[0:a]volume={duck}[bg];[1:a]adelay=0|0[dub];"
    f"[bg][dub]amix=inputs=2:duration=longest:dropout_transition=3[a]",
    "-map","[a]","work/mixed.wav"], capture_output=True)

# ركّب الصوت الجديد في الفيديو
subprocess.run(["ffmpeg","-y","-i",src,"-i","work/mixed.wav",
    "-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-b:a","192k",
    "-shortest","-movflags","+faststart","work/dubbed.mp4"], capture_output=True)

print("✅ الفيديو المدبلج: work/dubbed.mp4")
""")

code("""#@title 8) تحميل النتيجة إلى جهازك
from google.colab import files
files.download("work/dubbed.mp4")
""")

md("""---
## 👄 (اختياري) مزامنة الشفاه — Wav2Lip على GPU

هذه الخطوة تعيد تحريك فم المتحدث ليطابق الصوت الجديد، فيبدو الفيديو **أصلياً لا دوبلاج**.

**المتطلبات:** خلية `Runtime → T4 GPU` مفعّلة. لفيديو طويل قد تستغرق وقتاً.
""")

code("""#@title 9) تثبيت Wav2Lip + الأوزان
!git clone --depth 1 https://github.com/Rudrabha/Wav2Lip.git > /dev/null 2>&1
!pip -q install torch torchvision --index-url https://download.pytorch.org/whl/cu118
!pip -q install opencv-python numpy librosa
!mkdir -p Wav2Lip/checkpoints
!wget -q -O Wav2Lip/checkpoints/wav2lip_gan.pth \\
  "https://huggingface.co/camenduru/Wav2Lip/resolve/main/checkpoints/wav2lip_gan.pth"
!wget -q -O Wav2Lip/s3fd.pth \\
  "https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth"
print("✅ Wav2Lip جاهز")
""")

code("""#@title 10) تشغيل مزامنة الشفاه
!cd Wav2Lip && python inference.py \\
  --checkpoint_path checkpoints/wav2lip_gan.pth \\
  --face ../work/source.mp4 \\
  --audio ../work/mixed.wav \\
  --outfile ../work/dubbed_lipsync.mp4 \\
  --pads 0 10 0 0

# إعادة دمج الصوت النهائي
!ffmpeg -y -i work/dubbed_lipsync.mp4 -i work/mixed.wav \\
  -map 0:v:0 -map 1:a:0 -c:v copy -c:a aac -b:a 192k -shortest \\
  -movflags +faststart work/final.mp4

from google.colab import files
files.download("work/final.mp4")
print("✅ الفيديو النهائي بمزامنة الشفاه: work/final.mp4")
""")

nb = {
    "cells": CELLS,
    "metadata": {
        "colab": {"provenance": [], "gpuType": "T4"},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 0,
}

out = Path(__file__).resolve().parent.parent / "notebooks" / "DBYT_dubbing.ipynb"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(nb, ensure_ascii=False, indent=1))
print(f"wrote {out} ({len(CELLS)} cells)")
