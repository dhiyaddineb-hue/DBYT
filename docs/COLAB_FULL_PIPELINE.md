# DBYT: التشغيل الكامل داخل Google Colab

هذا هو المسار الرئيسي لتشغيل DBYT عندما تكون شبكة GitHub Actions غير مناسبة لتنزيل YouTube أو تنفيذ Whisper وTTS بسرعة كافية. ينفذ Colab كل المراحل، بينما يستخدم GitHub لحفظ الكود والملفات والنتائج فقط.

```text
YouTube → yt-dlp داخل Colab → Whisper → ترجمة → Fasih-TTS-V1 → ffmpeg
                                                              ↓
                           GitHub Release: source.mp4 + dubbed.mp4 + run.json
```

## المتطلبات

يحتاج التشغيل إلى جلسة Google Colab، ويفضل اختيار **GPU** من `Runtime → Change runtime type`. يستطيع المسار استخدام CPU، لكن نموذج Fasih وWhisper سيكونان أبطأ بكثير. النموذج الموصى به للعربية هو `NightPrince/Fasih-TTS-V1`، وهو صوت ذكوري احترافي للفصحى مبني على XTTS-v2. يختار الدفتر تلقائيًا مقطعًا صوتيًا قصيرًا من المصدر لاستعماله كمرجع للصوت.

الخلية الأولى تفحص Internet وDNS إلى PyPI خلال 12 ثانية قبل أي تثبيت؛ إذا كانت شبكة Colab معطلة تتوقف برسالة واضحة بدل انتظار apt/pip عدة دقائق. بعد نجاح الفحص تثبت `yt-dlp[default]` بإصدار مثبت و`yt-dlp-ejs` و`pydantic-settings`، وتثبت **Deno** تلقائيًا داخل `/content/dbty/.deno` بطريقة غير تفاعلية، ثم تتحقق من وجود `ffmpeg` و`yt-dlp` وتطبع الإصدارات، بما فيها إصدار `pydantic-settings`. يحتاج yt-dlp الحديث إلى JavaScript runtime وEJS لحل تحديات YouTube؛ لذلك لا تتجاوز الخلية الأولى حتى تظهر رسالتا الإصدار بنجاح.

> **تنبيه الترخيص:** بطاقة Fasih-TTS-V1 تذكر أن النموذج موزع وفق Coqui Public Model License، مع استخدام غير تجاري وإسناد. لا تستخدمه تجاريًا قبل مراجعة الرخصة والشروط الحالية.

## إعداد GitHub Secret في Colab

أنشئ Fine-grained Personal Access Token مخصصًا لمستودع `DBYT` فقط. فعّل صلاحية `Contents: Read and write`، ولا تحتاج إلى `Actions` لأن هذا الدفتر لا يشغل GitHub Actions. في Colab افتح أيقونة المفتاح، اختر **Add new secret**، واكتب الاسم بالضبط:

```text
DBYT_COLAB_TOKEN
```

الصق القيمة في خانة Value، وفعّل **Notebook access**. لا تكتب القيمة في خلية Notebook ولا تطبعها.

إذا ظهر من YouTube الخطأ `Sign in to confirm you're not a bot`، أضف Secret اختياريًا باسم `YOUTUBE_COOKIES` وضع فيه محتوى ملف cookies بصيغة Netscape. تقرأ الخلية 2 السر إلى ملف مؤقت داخل جلسة Colab فقط، وتمرره إلى yt-dlp، ولا ترفعه إلى GitHub أو تعرض محتواه. إذا لم تضف هذا السر، سيستمر الدفتر بمحاولة الوصول المجهول.

## التشغيل

افتح [Notebook الدبلجة الكاملة](https://colab.research.google.com/github/dhiyaddineb-hue/DBYT/blob/main/notebooks/DBYT_colab_full_dubbing.ipynb)، ثم شغّل الخلايا بالترتيب. في خلية الإعدادات غيّر `VIDEO_URL` فقط، واختر `TTS_ENGINE = "fasih"` للعربية الفصحى. إذا كان YouTube يحجب الوصول المجهول، فعّل Secret الاختياري `YOUTUBE_COOKIES` كما هو موضح أعلاه قبل تشغيل الخلية 2. اختر `sherpa` إذا لم يتوفر GPU أو أردت مسارًا أخف يعمل محليًا. إذا فشلت الخلية 3، اطبع آخر جزء من `yt-dlp said:`؛ فالخلية تعرض سجل yt-dlp ونسب التقدم مباشرة، ثم تعرض سبب الخطأ الحقيقي وتجرب أولًا عميل `android_vr` بصيغتين، ثم المحاولة الافتراضية. في الخلية 6 يُضاف مسار `REPO_DIR/backend` مباشرة إلى `sys.path` ويُستورد Pipeline عبر `app.services.pipeline` لتجنب مشاكل استيراد الحزمة من جذر Colab. وإذا كانت `REPO_DIR` مفقودة أو غير صالحة، تعيد الخلية جلب tarball تلقائيًا إلى `WORK_DIR/repo_archive` بدل الاعتماد على الخلية 5 أو على مسار root. إذا ظهرت رسائل `HTTP 429` أو `Sign in to confirm you're not a bot` في جميع المحاولات، فالمشكلة حجب/تحديد معدل من YouTube لشبكة Colab الحالية وليست خطأً في الدفتر. بعد انتهاء المحاولات الثلاث تفتح الخلية تلقائيًا نافذة رفع؛ اختر ملف الفيديو الأصلي بصيغة MP4 أو MKV أو MOV أو WebM، وستتابع الخلية استخراج المرجع والدبلجة من الملف المرفوع بدل التوقف. إذا أردت إعادة تجربة YouTube، استخدم جلسة Colab جديدة لاحقًا أو شبكة مختلفة، ولا تكرر المحاولات بسرعة. أما رسائل `Deno installation failed` أو `ffmpeg or yt-dlp is not available` فهي مشكلة تهيئة، وقد أصبحت الخلية تعرض المسار المتوقع والإصدارات لتحديدها مباشرة.

يُفضّل استخدام `GRANULARITY = "segment"` للفيديوهات الطويلة؛ فهو أسرع من توليد صوت لكل كلمة، مع بقاء المحاذاة على مستوى الجملة. يمكن اختيار `word` عندما تكون دقة التوقيت أهم من سرعة التنفيذ.

## الملفات الناتجة

الخلية الأخيرة تنشئ Release دائمًا في GitHub وترفع إليه الملفات التالية:

| الملف | الوصف |
|---|---|
| `source.mp4` | الفيديو الذي نزّله Colab من YouTube |
| `<project>.mp4` | الفيديو المدبلج النهائي |
| `run.json` | اللغة والمحرك وأحجام الملفات ووسم Release |

لا يوضع الفيديو في Git history ولا يحتاج إلى Git LFS. توجد الملفات في GitHub Release تحت وسم يبدأ بـ `dbyt-result-`.

## إعادة المحاولة والتنظيف

إذا انقطعت جلسة Colab قبل الرفع، يمكن إعادة تشغيل الخلية المتوقفة بعد التأكد من وجود الملفات في `/content/dbty`. إذا نجحت الخلية الأخيرة، لا تعِد تشغيلها دون تغيير `run_id` لأن Release جديدًا سيُنشأ لكل تشغيل. احذف Releases القديمة يدويًا من GitHub عندما لا تعود بحاجة إلى نسخ المصدر أو النتائج.

## لماذا لا نستخدم GitHub Actions هنا؟

GitHub Actions يبقى مناسبًا للاختبارات وبناء الكود، لكنه ليس مكان التنفيذ الرئيسي لهذا المسار. Colab ينفذ `yt-dlp` خارج شبكة GitHub، ويستطيع استخدام GPU لـ Whisper وFasih، ثم يرسل الملفات النهائية إلى GitHub فقط. لذلك لا يحتاج المسار إلى Proxy أو Cobalt أو cookies داخل GitHub.
