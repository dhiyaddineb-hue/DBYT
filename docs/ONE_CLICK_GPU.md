# DBYT — YouTube إلى GitHub بضغطة واحدة

يعمل Workflow `One-click YouTube to GitHub dubbing` بالسلسلة التالية:

```text
GitHub Actions
    ↓ يرسل رابط YouTube إلى Kaggle
Kaggle
    ↓ ينزّل source.mp4 فقط
GitHub Release مؤقت
    ↓ يسحب source.mp4
GitHub Actions CPU
    ↓ Whisper + الترجمة + Sherpa
GitHub Release نهائي
```

بعد الإعداد الأول، لا تحتاج إلى فتح Kaggle أو رفع الفيديو يدويًا. تضغط **Run workflow** في GitHub وتضع رابط YouTube فقط.

## الإعداد الأول مرة واحدة

أنشئ API token من [Kaggle API Settings](https://www.kaggle.com/settings/api)، ثم أضف Secret في مستودع GitHub من:

`Settings → Secrets and variables → Actions → New repository secret`

| الاسم | القيمة |
|---|---|
| `KAGGLE_API_TOKEN` | قيمة Kaggle API token |
| `KAGGLE_KERNEL_ID` | اختياري؛ الصيغة `kaggle_username/dbyt-youtube-download` إذا لم يستطع Workflow اكتشاف حساب Kaggle من Kernels السابقة |

ينشئ Workflow Notebook باسم `dbyt-youtube-download` بدل Script. افتح هذا Notebook في Kaggle مرة واحدة، وفعّل Internet من إعدادات Notebook، ثم أضف Secret باسم `YOUTUBE_COOKIES` من **Add-ons → Secrets**. لا تضع cookies داخل المستودع أو داخل الكود.

## التشغيل

افتح [Workflow التشغيل](https://github.com/dhiyaddineb-hue/DBYT/actions/workflows/one-click-gpu-dubbing.yml)، ثم اضغط **Run workflow** وأدخل:

| الحقل | القيمة المقترحة |
|---|---|
| `source_url` | رابط YouTube الكامل |
| `target_language` | `ar` للعربية |
| `project_name` | اسم النتيجة، مثل `dbyt-project` |
| `whisper_model` | `tiny` للسرعة على GitHub CPU، أو `base` لجودة أعلى |

بعد التشغيل، ينشئ GitHub Release مؤقتًا للمصدر، ثم Release نهائيًا للفيديو المدبلج. إذا فشل Kaggle في التنزيل، ستجد `download.log` في Artifact الخاص بالتشغيل.

## القيود الواقعية

Kaggle هو الذي يحاول تنزيل YouTube، لذلك لا نستخدم GitHub لتنزيل YouTube مباشرة. إذا حجب YouTube شبكة Kaggle أيضًا، فستظهر رسالة في `download.log`، ولا يستطيع الكود تجاوزها دون cookies حديثة أو مسار تنزيل مصرح به. في هذه الحالة حدّث Secret `YOUTUBE_COOKIES` من جلسة YouTube صالحة ثم أعد تشغيل Workflow.

الدبلجة في هذه النسخة تنفذ داخل GitHub CPU باستخدام `Sherpa`، لأن المطلوب هو أن يكون Kaggle مسؤولًا عن التنزيل فقط. يستخدم Workflow `DBYT_WHISPER_DEVICE=cpu` و`DBYT_WHISPER_COMPUTE_TYPE=int8` و`segment` لتقليل الزمن. أما تشغيل Fasih فيحتاج نقل مرحلة الدبلجة نفسها إلى Kaggle GPU، وهو مسار مختلف عن هذا التصميم.

### المراجع

[1]: https://www.kaggle.com/settings/api — Kaggle API token settings
[2]: https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md — Kaggle Kernel push, status, and output
[3]: https://www.kaggle.com/code/dhiyaddineberkane/dbyt-youtube-download — Download Notebook created by the workflow
[4]: https://github.com/dhiyaddineb-hue/DBYT/actions/workflows/one-click-gpu-dubbing.yml — Workflow in DBYT
