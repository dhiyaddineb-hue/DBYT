# DBYT — Kaggle GPU pipeline

هذا هو مسار تنفيذ DBYT على **Kaggle Notebooks**. يحتفظ GitHub بالكود والنتائج فقط، بينما ينفذ Kaggle تنزيل الفيديو، Whisper، الترجمة، TTS، المزج، وMux على جلسة GPU.

## قبل التشغيل

أنشئ Notebook جديدًا في Kaggle أو ارفع `notebooks/DBYT_kaggle_full_dubbing.ipynb`. من لوحة Settings فعّل **Internet** و**GPU**. قد يكون GPU في طابور عند ازدحام الخدمة؛ لا تبدأ التنفيذ قبل أن يظهر GPU في الجلسة.

أنشئ Kaggle Secret باسم `DBYT_GITHUB_TOKEN` وضع فيه GitHub token بصلاحية **Contents: Read and write** للمستودع الخاص. لا تكتب السر داخل Notebook أو GitHub، ولا تطبع قيمته.

## التشغيل

شغّل الخلايا الثماني بالترتيب. الخلية الأولى تفحص اتصال Internet وDNS إلى PyPI أولًا؛ إذا كان Internet معطلًا تتوقف خلال نحو 12 ثانية برسالة واضحة بدل انتظار apt/pip عدة دقائق. بعد ذلك تثبت ffmpeg وyt-dlp وDeno و`pydantic-settings` وتستخدم المسار `/kaggle/working/dbty`. الخلية الثانية تقرأ السر من `kaggle_secrets` وتتحقق من GPU؛ إذا اخترت `fasih` دون GPU ستتوقف برسالة واضحة بدل بدء دبلجة بطيئة.

في الخلية الثانية استخدم الإعدادات التالية للعربية الفصحى:

```python
TARGET_LANGUAGE = "ar"
TTS_ENGINE = "fasih"
GRANULARITY = "segment"
KEEP_BACKGROUND = True
```

الخلية الثالثة تنزل الفيديو باستخدام yt-dlp وDeno وتعرض السجل مباشرة. الخلية الرابعة تنشئ `reference.wav`. الخلية الخامسة تجلب كود DBYT من GitHub. الخلية السادسة تضيف `REPO_DIR/backend` إلى `sys.path` وتستورد `app.services.pipeline`; وإذا كان `REPO_DIR` غير موجود تعيد جلب tarball تلقائيًا إلى `/kaggle/working/dbty/repo_archive`. الخلية السابعة تفحص الناتج، والثامنة ترفع المصدر والفيديو المدبلج و`run.json` إلى GitHub Release.

## ملاحظات مهمة

إذا ظهرت `HTTP 429` أو `Sign in to confirm you're not a bot`، فهذا يعني أن YouTube يحجب شبكة Kaggle الحالية؛ GPU لا يحل حجب YouTube. في هذه الحالة ارفع `source.mp4` إلى Kaggle وشغّل الخلايا من استخراج المرجع فصاعدًا، أو جرّب جلسة لاحقة.

إذا نفدت سعة GPU أو وُضعت في طابور، انتظر أو استخدم Paperspace/Lightning. لا تعتمد على GitHub Actions للدبلجة؛ GitHub يحفظ الملفات فقط.

## رابط الملف

`notebooks/DBYT_kaggle_full_dubbing.ipynb`
