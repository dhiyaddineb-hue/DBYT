# DBYT — تشغيل الدبلجة بضغطة واحدة من GitHub

يضيف Workflow `One-click GPU dubbing` زرًا واحدًا داخل GitHub Actions. يكتب المستخدم رابط الفيديو ويضغط **Run workflow** فقط. إذا كان `KAGGLE_API_TOKEN` موجودًا، يرسل GitHub نسخة التشغيل إلى Kaggle GPU؛ وإذا لم يكن موجودًا، يستخدم GitHub CPU تلقائيًا مع Whisper `tiny` وSherpa بدل التوقف بخطأ. في كلا المسارين ينشر `mp4` و`run.json` و`pipeline.log` في GitHub Release.

## الإعداد الأول فقط

أنشئ Kaggle API token من [Kaggle Account API](https://www.kaggle.com/settings/api)، ثم أضف Secret المصادقة في مستودع GitHub من:

`Settings → Secrets and variables → Actions → New repository secret`

| الاسم | القيمة |
|---|---|
| `KAGGLE_API_TOKEN` | اختياري. رمز Kaggle API من أجل تشغيل GPU وFasih. إذا غاب، يعمل المسار الاحتياطي على GitHub CPU مع Sherpa. |
| `KAGGLE_KERNEL_ID` | اختياري، ويُستخدم فقط مع Kaggle GPU إذا لم يستطع Workflow اكتشاف Kernel الشخصي. |

لا تضع هذه القيم في ملفات المستودع. يستخدم Kaggle CLI متغير `KAGGLE_API_TOKEN` رسميًا. يحاول Workflow اكتشاف اسم مستخدم Kaggle تلقائيًا من Kernels الخاصة بالحساب، ثم يستخدم `username/dbyt-one-click`. إذا لم يكن للحساب أي Kernel سابق ولم يستطع Workflow اكتشاف اسم المستخدم، أضف `KAGGLE_KERNEL_ID` اختياريًا. عدم وجود هذه الأسرار لا يمنع التشغيل؛ يختار Workflow مسار GitHub CPU تلقائيًا. [1] [2]

إذا كان المصدر رابط YouTube ويحتاج إلى cookies، أضف Secret باسم `YOUTUBE_COOKIES` في GitHub Actions أو داخل حساب Kaggle، وليس داخل الكود. يجب أن يكون ملف cookies حديثًا؛ إذا ظهر في السجل `cookies are no longer valid` فلا تعاد المحاولة بالملف نفسه. يجرب Workflow أولًا cookies ثم بدونها، وبعد ذلك يستخدم فقط مسارات fallback التي يصرّح بها المشغل عبر `COBALT_API_URL`/`COBALT_API_KEY` أو `INVIDIOUS_INSTANCES` أو `YOUTUBE_PROXIES`. إذا لم تتوفر هذه المسارات وحجبت YouTube شبكة GitHub، استخدم رابط GitHub Release مباشر للفيديو؛ هذا هو المسار الأكثر ثباتًا.

## التشغيل المتكرر

افتح:

`Actions → One-click GPU dubbing → Run workflow`

ثم أدخل `source_url`. يمكن أن يكون الرابط رابط YouTube، أو رابطًا مباشرًا لملف فيديو عام، أو رابط GitHub Release asset عام. اختر `fasih` للعربية الفصحى عند إعداد Kaggle GPU، ثم اختر `small` للجودة الأعلى أو `base`/`tiny` للسرعة. إذا لم يُضف `KAGGLE_API_TOKEN`، سيستبدل Workflow المحرك تلقائيًا بـ Sherpa ويستخدم Whisper `tiny` عند اختيار `small` حتى لا يتوقف التشغيل. بعد الضغط على **Run workflow**، لا تحتاج إلى فتح Kaggle أو تشغيل Notebook يدويًا.

عند النجاح، يطبع سجل GitHub رابط Release النهائي بصيغة:

```text
https://github.com/<owner>/<repo>/releases/tag/dbyt-result-<run-id>
```

## ملاحظة عن رفع ملف محلي

واجهة `workflow_dispatch` في GitHub تقبل نصًا أو رابطًا، ولا توفر خانة رفع ملف ثنائي مباشرة داخل زر **Run workflow**. لذلك لملف موجود على جهازك، يجب رفعه مرة واحدة إلى GitHub Release أو إلى استضافة عامة ثم وضع الرابط في `source_url`. بعد توفير الرابط، تصبح كل عملية لاحقة ضغطة واحدة.

## ما يحدث داخليًا

يولّد GitHub Kernel Kaggle خاصًا بالتشغيل الحالي، ويثبت قيم التشغيل داخله دون وضع الأسرار في الكود، ثم يطلب Kaggle GPU من نوع T4 مع Internet. يشغّل Kernel Whisper والترجمة وFasih، ويعود تلقائيًا إلى Sherpa إذا فشل تحميل Fasih. بعد انتهاء Kernel، ينزّل GitHub المخرجات وينشئ Release جديدًا.

يتطلب هذا التصميم توفر GPU في طابور Kaggle؛ فقد ينتظر التشغيل عند ازدحام الخدمة. كما أن YouTube قد يحجب أي شبكة سحابية، ولذلك لا يمكن ضمان التنزيل من YouTube في كل تشغيل. عند الحجب استخدم رابط ملف مباشر في GitHub Release بدل إعادة محاولة YouTube.

### المراجع

[1]: https://www.kaggle.com/docs/api — Kaggle Public API and authentication  
[2]: https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels_metadata.md — Kaggle Kernel metadata  
[3]: https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md — Kaggle Kernel push and accelerator options
