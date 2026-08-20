# 🧭 خريطة الحلول — مشاريع مفتوحة المصدر لحل كل مشاكل الدبلجة والحجب

هذا المستند يوثّق البحث الكامل عن المشاريع المفتوحة المصدر التي تحل:

1. **مشاكل الحجب** (يوتيوب، نماذج HuggingFace، خدمة الصوت، جوجل للترجمة)
2. **مشاكل الدبلجة** (جودة الصوت، مزامنة الشفاه، محاذاة الكلمات، عزل الصوت)

---

## 1) حل مشكلة حجب يوتيوب (التحميل)

المشكلة: `yt-dlp` يحتاج وصولاً مباشراً لخوادم يوتيوب/جوجل، وقد يكون محجوباً.

| المشروع | ما يفعله | الرابط |
|---|---|---|
| **Invidious** | بديل مفتوح المصدر لواجهة يوتيوب، يوفر API عام + استضافة ذاتية | [invidious.io](https://invidious.io) / [github](https://github.com/iv-org/invidious) |
| **Piped** | بديل يوتيوب، API عام، **NewPipeExtractor** لاستخراج روابط البث بدون API رسمي | [github](https://github.com/TeamPiped/Piped) |
| **NewPipe Extractor** | المكتبة الأساسية التي تستخرج روابط الفيديو من يوتيوب بدون API جوجل | [github](https://github.com/TeamNewPipe/NewPipeExtractor) |
| **MeTube** | واجهة ويب ذاتية لـ yt-dlp (Docker) — تحميل بدون متصفح | [github](https://github.com/alexta69/metube) |
| **Tube Archivist** | أرشيف يوتيوب ذاتي — يحمّل القنوات تلقائياً ويحفظها محلياً | [github](https://github.com/tubearchivist/tubearchivist) |

✅ **الحل المدمج في DBYT**: دالة `youtube._download_via_frontend()` تحاول التحميل
المباشر أولاً ثم تنتقل تلقائياً لقائمة من نسخ Invidious/Piped العامة.

---

## 2) حل مشكلة حجب نماذج Whisper (HuggingFace)

المشكلة: `faster-whisper` يحمّل النموذج من HuggingFace عند أول تشغيل.

| الحل | الوصف |
|---|---|
| **تخزين النموذج مسبقاً** | نزّل `small.bin`/`medium.bin` مرة واحدة وضعه في `workspace/models/` (يُحفظ في المستودع عبر Git LFS) |
| **مشاريع بديلة** | **WhisperX** (محاذاة كلمات أدق + تجزئة المتحدثين)، **SenseVoice** (STT أسرع، من Alibaba) |

✅ **الحل في DBYT**: `faster-whisper` يدعم `download_root=workspace/models`، فيتحقق
من النموذج المحلي قبل أي طلب شبكة.

---

## 3) حل مشكلة حجب خدمة الصوت (Microsoft Bing TTS)

المشكلة: `edge-tts` يتصل بـ `speech.platform.bing.com` (محجوب في بيئات كثيرة).

| المحرك | النوع | يدعم العربية؟ | ملاحظات |
|---|---|---|---|
| **Piper** (Rhasspy) | OFFLINE، ONNX، سريع جداً على CPU | ✅ (ar_JO-kareem) | الحل الأمثل للعمل دون إنترنت |
| **Coqui XTTS v2** | OFFLINE، استنساخ صوت من 6 ثوانٍ، 17 لغة | ✅ | يبقي صوت المتحدث الأصلي في الدبلجة |
| **Kokoro** | OFFLINE، جودة عالية | جزئي | Apache-2.0 |
| **Bark** (Suno) | OFFLINE، مشاعر حقيقية | ✅ (بجودة متوسطة) | ثقيل |
| **espeak-ng** | OFFLINE، خفيف جداً | ✅ | جودة روبوتية (حل طوارئ فقط) |

✅ **الحل المدمج في DBYT**: أضيف محرك `piper` (أوفلاين عربي) ومحرك `xtts`
(استنساخ صوت المتحدث) في `tts.py`، مع `edge` و`elevenlabs` كخيارات.

---

## 4) حل مشكلة حجب جوجل للترجمة

المشكلة: `deep-translator` (Google) و`translate.google.com` محجوبان.

| المحرك | النوع | جودة العربية (chrF) | الحجم |
|---|---|---|---|
| **Argos Translate** | OFFLINE، OpenNMT، سريع (14×) | 57.2 | ~170 MB |
| **NLLB-200** (Meta) | OFFLINE، أفضل جودة | **63.8** | ~2.5 GB |
| **LibreTranslate** | واجهة API ذاتية فوق Argos | — | Docker |

✅ **الحل المدمج في DBYT**: أضيف `argos` (خفيف وسريع) و`nllb` (الأفضل للعربية)
كخلفيات ترجمة في `translate.py`.

---

## 5) مشاريع دبلجة جاهزة (مرجعية معمارية)

هذه مشاريع تنفّذ نفس الهدف — استفدنا من معماريّتها:

| المشروع | المزايا البارزة | الرابط |
|---|---|---|
| **VideoLingo** (~16k ⭐) | دبلجة بمستوى Netflix، ترجمة 3 مراحل | [github](https://github.com/Huanshere/VideoLingo) |
| **pyVideoTrans** (~16k ⭐) | أدوات ترجمة فيديو معيارية، CLI/GUI | [github](https://github.com/jianchang512/pyvideotrans) |
| **KrillinAI** (~10k ⭐) | دبلجة بسيطة للفيديوهات القصيرة | [github](https://github.com/krillinai/KrillinAI) |
| **Linly-Dubbing** (~3k ⭐) | دبلجة بمزامنة شفاه + Demucs + UVR5 | [github](https://github.com/Kedreamix/Linly-Dubbing) |
| **youtube-auto-dub** | دبلجة يوتيوب محلية، استنساخ صوت + NLLB + Wav2Lip | [github](https://github.com/mazzasaverio/youtube-auto-dub) |
| **AutoDub** | دبلجة فيديو **دون إنترنت** (Whisper+Ollama+XTTS) | [github](https://github.com/shyhirt/AutoDub) |
| **open-dubbing** (Softcatala) | دبلجة محلية بـ Coqui TTS + NLLB | [github](https://github.com/Softcatala/open-dubbing) |
| **InfiniteTalk** (~5k ⭐) | إعادة توليد الفيديو (رأس وجسم وشفاه) بالانتشار | [github](https://github.com/MeiGen-AI/InfiniteTalk) |

---

## 6) حل مشاكل جودة الدبلجة (غير الحجب)

| المشكلة | الحل المفتوح المصدر |
|---|---|
| **عزل صوت المتحدث عن الموسيقى** | **Demucs** / **UVR5** — قبل الدبلجة لعزل الكلام |
| **محاذاة كلمات أدق** | **WhisperX** (محاذاة فونيمية) بدل Whisper العادي |
| **مزامنة الشفاه** | **Wav2Lip** (الأساسي)، **Wav2Lip-HQ**، **Video-Retalking**، **SadTalker** |
| **مزامنة شفاه عالية الجودة** | **InfiniteTalk**، **EchoMimic** — توليد كامل للوجه |
| **استنساخ صوت المتحدث** | **Coqui XTTS v2**، **Chatterbox**، **OpenVoice** |

---

## 7) الخلاصة — الحل النهائي للعمل "دائماً"

دمج DBYT الآن يدعم **3 مستويات تشغيل** حسب توفر الشبكة:

```
المستوى 1: إنترنت كامل (GitHub Actions / خادم) → edge-tts + Google + yt-dlp
المستوى 2: إنترنت جزئي → Invidious/Piped للتحميل + Piper/XTTS للصوت + Argos للترجمة
المستوى 3: دون إنترنت (بعد تحميل النماذج مرة) → Piper + Argos + نماذج Whisper محلية
```

بهذا، مشاكل الحجب تُحل **بالتصميم** عبر البدائل المفتوحة المصدر أعلاه.
