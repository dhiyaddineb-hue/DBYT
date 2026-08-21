# DBYT — التشغيل السريع عبر جهازك

هذا المسار مناسب عندما لا يسمح Kaggle بتفعيل Internet. GitHub يبقى مكان الضغط والكود والنتيجة، بينما ينفذ جهازك التنزيل والدبلجة محليًا. لا يُرفع `source.mp4` إلى GitHub قبل الدبلجة؛ يُرفع الفيديو النهائي فقط.

## الإعداد مرة واحدة

افتح صفحة إضافة Runner في مستودع DBYT:

`Settings → Actions → Runners → New self-hosted runner`

اختر نظام جهازك، ثم نفّذ أوامر GitHub التي تظهر في الصفحة داخل Terminal على جهازك. لا تكتب registration token في المستودع أو في هذه الوثيقة. يجب أن يكون Runner في حالة **Idle** أو **Online** قبل تشغيل Workflow.

شغّل Runner في كل مرة تريد فيها الدبلجة. في Linux يكون الأمر عادةً:

```bash
./run.sh
```

اترك هذه النافذة مفتوحة حتى ينتهي التشغيل. لا تحتاج إلى خادم دائم؛ يكفي أن يكون جهازك متصلًا أثناء العملية.

## التشغيل

افتح [Self-hosted one-click YouTube dubbing](https://github.com/dhiyaddineb-hue/DBYT/actions/workflows/self-hosted-one-click.yml)، واضغط **Run workflow**. أدخل رابط YouTube، واللغة، واسم المشروع، ثم اختر `sherpa` و`tiny` و`segment` للسرعة.

ينزّل Runner الفيديو إلى `workspace/incoming`، يدبلجه مباشرة من القرص نفسه، ثم يرفع النتيجة فقط إلى GitHub Release. لذلك لا توجد دورة رفع ثم تنزيل للمصدر.

يمكن استخدام `YOUTUBE_COOKIES` كـ GitHub Actions Secret اختياري. إذا اخترت `fasih`، يجب أيضًا إدخال رابط مباشر لملف reference audio في `reference_url`.

## الأمان

استخدم self-hosted runner فقط في مستودع تملكه وتثق بكل Workflow فيه. لا تقبل Pull Requests غير موثوقة لتعمل على هذا Runner، لأن Workflow يستطيع تنفيذ أوامر على جهازك. لا تضع registration token أو cookies داخل الملفات أو السجل.
