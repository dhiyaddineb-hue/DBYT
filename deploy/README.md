# DBYT production deployment

هذا المجلد يحوّل DBYT من مشروع يعمل داخل GitHub Actions فقط إلى خدمة مستمرة على خادم Linux. يبقى GitHub هو مصدر الكود والاختبارات والنشر، بينما يشغّل الخادم FastAPI وffmpeg وyt-dlp ويحفظ `workspace/` على قرص دائم.

## المعمارية

| المكوّن | الدور |
|---|---|
| GitHub repository | مصدر الكود، pull requests، الاختبارات، وسجل النشر |
| `deploy/docker-compose.prod.yml` | تشغيل DBYT وCaddy مع إعادة تشغيل تلقائية وvolumes دائمة |
| DBYT container | FastAPI + frontend + ffmpeg + Whisper/TTS pipeline |
| Caddy | reverse proxy وHTTPS تلقائي عند ربط domain صحيح |
| GitHub Actions `deploy.yml` | مزامنة الكود عبر SSH وتشغيل `deploy/update.sh` |
| `/opt/dbyt/.env` | إعدادات التشغيل والأسرار، ولا يُنسخ من GitHub |

## المتطلبات

يحتاج الخادم إلى Ubuntu 24.04 أو ما يعادله، Docker Engine مع Compose v2، اسم نطاق يشير إليه عبر سجل A، وقرص دائم مناسب للنماذج والملفات الناتجة. لا توجد GPU في الإعداد الافتراضي؛ استخدم Whisper على CPU أو خادمًا يدعم GPU إذا أردت نماذج أكبر أو lip-sync.

## إعداد الخادم مرة واحدة

نفّذ على الخادم بصلاحية المستخدم `ubuntu` أو مستخدم نشر مخصص:

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends git ca-certificates curl docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
sudo mkdir -p /opt/dbyt/workspace
sudo chown -R "$USER:$USER" /opt/dbyt
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

سجّل الخروج ثم ادخل مجددًا لتفعيل مجموعة Docker. انسخ المستودع إلى `/opt/dbyt` أو اترك Workflow النشر ينشئه، ثم ثبّت ملف البيئة:

```bash
cd /opt/dbyt
cp .env.example .env
chmod 600 .env
```

عدّل `.env` وأضف على الأقل `DBYT_DOMAIN` و`DBYT_API_KEY` و`DBYT_CORS_ORIGINS`. لا تضع cookies أو API keys في GitHub repository. إذا كان الخادم يحتاج YouTube proxy، أضف `DBYT_YOUTUBE_PROXIES` إلى `.env` المحلي على الخادم فقط.

شغّل أول نسخة يدويًا:

```bash
cd /opt/dbyt
docker compose -f deploy/docker-compose.prod.yml up -d --build
docker compose -f deploy/docker-compose.prod.yml ps
curl -fsS https://YOUR_DOMAIN/api/health
```

إذا أُريد تشغيل Compose عبر systemd، انسخ `deploy/dbyt-compose.service` إلى `/etc/systemd/system/`، ثم نفّذ:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dbyt-compose.service
```

## إعداد GitHub Actions للنشر

أنشئ GitHub Environment باسم `production`، ثم أضف الأسرار التالية إليه:

| Secret | القيمة |
|---|---|
| `DEPLOY_HOST` | عنوان IP أو hostname للخادم |
| `DEPLOY_USER` | غالبًا `ubuntu` |
| `DEPLOY_SSH_KEY` | المفتاح الخاص Ed25519 المخصص للنشر فقط |
| `DEPLOY_KNOWN_HOSTS` | سطر host key موثوق للخادم، يُجمع مسبقًا ويتحقق منه خارج Actions |
| `DEPLOY_PATH` | `/opt/dbyt`، ويمكن تركه فارغًا لاستخدام القيمة الافتراضية |

أضف المفتاح العام المقابل إلى `~/.ssh/authorized_keys` على الخادم، وقيّد المفتاح إن أمكن باستخدام `restrict` و`command` مناسبين. لا تستخدم `ssh-keyscan` داخل Workflow لتجاوز التحقق؛ ذلك يفتح باب هجوم الوسيط.

بعد ذلك، كل push إلى `main` يشغّل الاختبارات الموجودة في Workflow الحالي ثم `deploy.yml` يزامن الكود ويعيد بناء الحاوية. لا ينسخ Workflow ملف `.env` أو `workspace/`؛ تبقى الأسرار والبيانات على الخادم.

## التشغيل المحلي وGitHub Actions

للتطوير المحلي استخدم `docker-compose.yml` أو `scripts/run.sh`. وللتشغيل المؤقت من GitHub Actions استخدم `Dubbing Pipeline`. في الإنتاج، `DBYT_COBALT_BROWSER=false` هو الإعداد الافتراضي لتجنب pool مواقع عامة غير موثوقة وبطيئة؛ استخدم Cobalt أو Proxy مصرحًا به عبر `.env` إذا كان تنزيل YouTube يتطلب مسارًا مختلفًا.

## المراقبة واستكشاف الأعطال

```bash
docker compose -f deploy/docker-compose.prod.yml logs -f --tail=200 dbyt
docker compose -f deploy/docker-compose.prod.yml logs -f --tail=200 caddy
docker compose -f deploy/docker-compose.prod.yml ps
curl -i https://YOUR_DOMAIN/api/health
```

الـ API يتطلب `X-API-Key` أو `Authorization: Bearer <DBYT_API_KEY>` عندما يكون `DBYT_API_KEY` معرفًا. مسار `/api/health` عام حتى يستطيع Caddy إجراء health checks. لا تستخدم `DBYT_AUTO_COMMIT=true` على خادم متعدد العمال أو مع أكثر من job متزامن؛ قد تحدث تعارضات Git. احفظ backups يومية لمجلد `workspace/` أو volume الخادم.
