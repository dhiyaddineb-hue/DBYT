# DBYT — تشغيل الدبلجة بضغطة واحدة من GitHub

يضيف Workflow `One-click GPU dubbing` زرًا واحدًا داخل GitHub Actions. بعد إعداد الأسرار مرة واحدة، يكتب المستخدم رابط الفيديو ويضغط **Run workflow** فقط. يرسل GitHub نسخة التشغيل إلى Kaggle GPU، وينتظر انتهاء الدبلجة، ثم ينشر `mp4` و`run.json` و`pipeline.log` في GitHub Release.

## الإعداد الأول فقط

أنشئ Kaggle API token من [Kaggle Account API](https://www.kaggle.com/settings/api)، ثم أضف Secret المصادقة في مستودع GitHub من:

`Settings → Secrets and variables → Actions → New repository secret`

| الاسم | القيمة |
|---|---|
| `KAGGLE_API_TOKEN` | قيمة Kaggle API token فقط |
| `KAGGLE_KERNEL_ID` | اختياري. أضفه فقط إذا لم يكن لديك Kernel شخصي سابق، بصيغة `your-kaggle-name/dbyt-one-click`. |

لا تضع هذه القيم في ملفات المستودع. يستخدم Kaggle CLI متغير `KAGGLE_API_TOKEN` رسميًا. يحاول Workflow اكتشاف اسم مستخدم Kaggle تلقائيًا من Kernels الخاصة بالحساب، ثم يستخدم `username/dbyt-one-click`. إذا لم يكن للحساب أي Kernel سابق ولم يستطع Workflow اكتشاف اسم المستخدم، أضف `KAGGLE_KERNEL_ID` اختياريًا. [1] [2]

إذا كان المصدر رابط YouTube ويحتاج إلى cookies، أضف Secret باسم `YOUTUBE_COOKIES` داخل Notebook/حساب Kaggle، وليس داخل GitHub أو الكود. يمكن تشغيل الروتين دون cookies، لكن YouTube قد يحجب الشبكة.

## التشغيل المتكرر

افتح:

`Actions → One-click GPU dubbing → Run workflow`

ثم أدخل `source_url`. يمكن أن يكون الرابط رابط YouTube، أو رابطًا مباشرًا لملف فيديو عام، أو رابط GitHub Release asset عام. اختر `fasih` للعربية الفصحى، ثم اختر `small` للجودة الأعلى أو `base`/`tiny` للسرعة. بعد الضغط على **Run workflow**، لا تحتاج إلى فتح Kaggle أو تشغيل Notebook يدويًا.

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
