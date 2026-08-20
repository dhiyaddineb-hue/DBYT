# Colab downloader → GitHub dubbing pipeline

هذا المسار يحل مشكلة حجب YouTube من GitHub Actions بفصل التنزيل عن المعالجة. Google Colab ينفّذ `yt-dlp` خارج شبكة GitHub، ثم يرفع الملف إلى GitHub Release مؤقت خاص بالمستودع ويرسل `repository_dispatch`. Workflow `Process Colab upload` ينزّل asset من GitHub، وليس من YouTube، ثم يشغّل DBYT على ملف محلي.

## الملفات

| الملف | الوظيفة |
|---|---|
| `notebooks/DBYT_colab_downloader.ipynb` | Notebook جاهز لـ Google Colab |
| `scripts/build_colab_uploader_notebook.py` | مولّد Notebook قابل لإعادة البناء |
| `.github/workflows/process-uploaded.yml` | يستقبل event وينفذ الدبلجة |
| `workspace/incoming/` | مصدر مؤقت داخل runner، يُحذف بعد النجاح |
| `workspace/output/` | الفيديو المدبلج وملفات النتائج |

## إعداد GitHub token في Colab

أنشئ Fine-grained Personal Access Token من إعدادات GitHub، وقيّده بمستودع `DBYT` فقط. يحتاج token إلى صلاحيات المستودع التالية:

| الصلاحية | المستوى | السبب |
|---|---|---|
| Contents | Read and write | إنشاء Release مؤقت ورفع asset |
| Actions | Read and write | إرسال `repository_dispatch` |

في Google Colab افتح لوحة **Secrets** عبر أيقونة المفتاح، وأنشئ سرًا باسم `DBYT_COLAB_TOKEN`. لا تضع token في خلية Notebook أو في GitHub repository.

## التشغيل

افتح Notebook، شغّل الخلايا بالترتيب، وأدخل رابط YouTube واللغة واسم المستودع. الخلية الأولى تثبت ffmpeg وyt-dlp، والخلية الثالثة تنزّل الفيديو داخل Colab. الخلية الرابعة تنشئ Release مؤقتًا وترفع الفيديو، ثم الخلية الخامسة ترسل الحدث إلى GitHub.

بعد ذلك افتح تبويب Actions وتابع **Process Colab upload**. Workflow يثبت ffmpeg وPython، ينزّل الـ asset الخاص عبر `GITHUB_TOKEN`، ويشغّل:

```bash
python -m backend.cli workspace/incoming/source.mp4 \
  --target-language ar \
  --project-name my-project \
  --output-dir workspace/output
```

عند النجاح، يحذف المصدر المؤقت ويعمل commit إلى `workspace/output` ويرفع Artifact. كما يحذف Release المؤقت وtag المرتبط به. عند الفشل، يبقى الـ Release مؤقتًا حتى يمكن فحصه أو إعادة المحاولة يدويًا.

## حدود هذا المسار

هذا الحل لا يجعل GitHub يتصل بـ YouTube؛ GitHub يتعامل فقط مع ملف رفعه Colab. لذلك لا يحتاج Workflow إلى `YOUTUBE_COOKIES` أو Proxy لتنزيل المصدر. ما زالت خطوات Whisper والترجمة وTTS تحتاج شبكاتها الخاصة، وقد تحتاج `DBYT_OPENAI_API_KEY` أو إعدادات TTS إذا اخترت محركًا مدفوعًا.

استخدم Release asset بدل commit مباشر للفيديو؛ ذلك يتجنب وضع الفيديو الثنائي في Git history. لا ترفع cookies إلى Release أو إلى المستودع. احذف token فورًا إذا ظهر في سجل أو Notebook مشارك.
