# تنزيل YouTube مع DBYT

يستخدم DBYT `yt-dlp` مباشرةً، ويحاول عملاء YouTube المتاحين بالتتابع. إذا كان عنوان IP الذي ينفذ المهمة محجوبًا من YouTube، يمكن تمرير Proxy اختياري من خلال GitHub Secret باسم `YOUTUBE_PROXIES`.

## إعداد GitHub Secret

افتح:

`Settings → Secrets and variables → Actions → New repository secret`

ثم أنشئ السر:

- **Name:** `YOUTUBE_PROXIES`
- **Secret:** عنوان Proxy واحد أو عدة عناوين، كل عنوان في سطر مستقل.

أمثلة للقيمة:

```text
socks5h://USER:PASSWORD@HOST:PORT
http://USER:PASSWORD@HOST:PORT
```

يمكن أيضًا استخدام Proxy بلا مصادقة:

```text
socks5h://HOST:PORT
```

لا تستخدم Proxy مجهولًا مع cookies أو أي بيانات شخصية. يمرر DBYT قيمة السر إلى `yt-dlp` في الذاكرة فقط، ولا يكتبها في السجل أو ملفات workspace.

## سلوك التنزيل

يحاول DBYT كل Proxy بالترتيب، ثم يحاول الاتصال المباشر. داخل كل مسار يجرب عملاء YouTube المتاحين. عند نجاح أحد المسارات يتوقف ويعيد الملف إلى خط الدبلجة. إذا لم تُعرّف `YOUTUBE_PROXIES`، يبقى السلوك السابق كما هو: اتصال مباشر فقط.

## ملاحظة تشغيلية

لا يضمن Proxy تجاوز حجب YouTube؛ يجب أن يكون صالحًا، سريعًا بما يكفي لتنزيل ملف الوسائط، ويسمح باتصالات HTTPS طويلة إلى خوادم YouTube و`googlevideo.com`. يفضل استخدام Proxy خاص أو موثوق بدل القوائم العامة المجانية، لأن القوائم العامة متغيرة وقد تسرّب حركة المرور أو تتوقف دون إنذار.
