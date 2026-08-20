#!/usr/bin/env python3
"""Generate the full Google Colab DBYT dubbing notebook."""
from __future__ import annotations

import json
from pathlib import Path

CELLS: list[dict] = []


def md(source: str) -> None:
    CELLS.append({"cell_type": "markdown", "metadata": {}, "source": source.splitlines(True)})


def code(source: str) -> None:
    CELLS.append(
        {
            "cell_type": "code",
            "metadata": {},
            "execution_count": None,
            "outputs": [],
            "source": source.splitlines(True),
        }
    )


md("""# DBYT — الدبلجة الكاملة داخل Google Colab

هذا هو المسار الرئيسي الجديد لـ DBYT:

```text
Colab: تنزيل YouTube → Whisper → ترجمة → TTS → مزج وMux
                                                ↓
GitHub: حفظ الكود والملفات والنتائج فقط
```

لن يستخدم هذا الدفتر GitHub Actions لتنفيذ الدبلجة. يستخدم **Fasih-TTS-V1** كصوت عربي فصيح احترافي على GPU Colab، مع استخراج مقطع مرجعي تلقائيًا من الفيديو. إذا لم يتوفر GPU أو أردت نموذجًا أخف، يمكنك اختيار **Sherpa-ONNX** كبديل محلي.

> **ترخيص الصوت:** Fasih-TTS-V1 مبني على XTTS-v2 ومرخّص وفق Coqui Public Model License، وهي رخصة غير تجارية مع إسناد. راجع الرخصة قبل استخدام الناتج تجاريًا.

شغّل الخلايا بالترتيب. خزّن مفتاح GitHub في Colab Secret باسم `DBYT_COLAB_TOKEN` ولا تكتبه داخل أي خلية.
""")

code("""#@title 1) تثبيت أدوات Colab
!sudo apt-get update -qq
!sudo apt-get install -y -qq ffmpeg
!pip -q install -U "yt-dlp[default]" requests faster-whisper deep-translator soundfile huggingface_hub "coqui-tts==0.27.5"

from pathlib import Path
import asyncio, json, os, re, shutil, subprocess, sys, uuid
from urllib.parse import quote
import requests

WORK_DIR = Path('/content/dbty')
WORK_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('HF_HOME', str(WORK_DIR / 'models' / 'huggingface'))
os.environ.setdefault('TTS_HOME', str(WORK_DIR / 'models' / 'tts'))
print('✅ Colab environment ready:', WORK_DIR)
""")

code("""#@title 2) الإعدادات والأسرار
VIDEO_URL = "https://www.youtube.com/watch?v=CAwRm-VO-kU"  #@param {type:"string"}
TARGET_LANGUAGE = "ar"  #@param ["ar", "en", "fr", "es", "de", "tr"]
TTS_ENGINE = "fasih"  #@param ["fasih", "sherpa"]
GRANULARITY = "segment"  #@param ["segment", "word"]
KEEP_BACKGROUND = True  #@param {type:"boolean"}
PROJECT_NAME = ""  #@param {type:"string"}
GITHUB_REPO = "dhiyaddineb-hue/DBYT"  #@param {type:"string"}

try:
    from google.colab import userdata
    GITHUB_TOKEN = userdata.get('DBYT_COLAB_TOKEN')
except Exception:
    GITHUB_TOKEN = os.environ.get('DBYT_COLAB_TOKEN', '')

if not GITHUB_TOKEN:
    raise RuntimeError('أضف DBYT_COLAB_TOKEN إلى Colab Secrets قبل المتابعة.')
if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', GITHUB_REPO):
    raise ValueError('GITHUB_REPO يجب أن يكون owner/repository')
if not re.match(r'https://(www\\.)?youtube\\.com/|https://youtu\\.be/', VIDEO_URL):
    raise ValueError('VIDEO_URL يجب أن يكون رابط YouTube')
if TTS_ENGINE == 'fasih' and TARGET_LANGUAGE != 'ar':
    raise ValueError('Fasih-TTS-V1 مخصص للعربية الفصحى؛ اختر ar أو استخدم Sherpa.')

print(f'✅ Settings loaded: {GITHUB_REPO} | engine={TTS_ENGINE} | target={TARGET_LANGUAGE} | granularity={GRANULARITY}')
""")

code("""#@title 3) تنزيل الفيديو من YouTube داخل Colab
source_path = WORK_DIR / 'source.mp4'
formats = [
    'bv*[height<=720]+ba/b[height<=720]/best',
    'best[ext=mp4][height<=720]/best[height<=720]/best',
    'best',
]
last_error = ''
for attempt, selected_format in enumerate(formats, start=1):
    for old in WORK_DIR.glob('source.*'):
        old.unlink(missing_ok=True)
    command = [
        'yt-dlp', '--ignore-config', '--no-playlist',
        '--retries', '10', '--fragment-retries', '10',
        '--socket-timeout', '30', '--format', selected_format,
        '--merge-output-format', 'mp4',
        '--output', str(WORK_DIR / 'source.%(ext)s'), VIDEO_URL,
    ]
    print(f'⬇️ Download attempt {attempt}/{len(formats)} with format: {selected_format}', flush=True)
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode == 0:
        print(completed.stdout[-2000:], flush=True)
        break
    last_error = (completed.stderr or completed.stdout or 'unknown yt-dlp error')
    print(f'⚠️ Attempt {attempt} failed; yt-dlp said:\\n{last_error[-4000:]}', flush=True)
else:
    raise RuntimeError(f'yt-dlp failed for every format. Last error:\\n{last_error[-6000:]}')

candidates = sorted(WORK_DIR.glob('source.*'))
if not candidates:
    raise FileNotFoundError('yt-dlp انتهى دون ملف مصدر')
source_path = WORK_DIR / 'source.mp4' if (WORK_DIR / 'source.mp4').exists() else candidates[0]
if source_path.suffix.lower() != '.mp4':
    converted = WORK_DIR / 'source.mp4'
    subprocess.run(['ffmpeg', '-y', '-i', str(source_path), '-c', 'copy', str(converted)], check=True)
    source_path = converted

probe = subprocess.check_output([
    'ffprobe', '-v', 'error', '-show_entries', 'format=duration,size',
    '-of', 'default=noprint_wrappers=1', str(source_path)
], text=True)
print('✅ Source ready:', source_path, '\\n', probe)
""")

code("""#@title 4) استخراج مقطع صوت مرجعي للصوت العربي
reference_path = WORK_DIR / 'reference.wav'
duration = float(subprocess.check_output([
    'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
    '-of', 'default=noprint_wrappers=1:nokey=1', str(source_path)
], text=True).strip())
start = 5.0 if duration > 15 else 0.0
length = min(8.0, max(2.0, duration - start))
subprocess.run([
    'ffmpeg', '-y', '-ss', str(start), '-t', str(length), '-i', str(source_path),
    '-vn', '-ac', '1', '-ar', '24000', '-c:a', 'pcm_s16le', str(reference_path)
], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
if not reference_path.exists() or reference_path.stat().st_size < 1000:
    raise RuntimeError('تعذر إنشاء المقطع المرجعي للصوت')
print(f'✅ Reference audio: {reference_path} ({length:.1f}s)')
""")

code("""#@title 5) جلب كود DBYT الخاص عبر GitHub API
import io, tarfile

API_ROOT = f'https://api.github.com/repos/{GITHUB_REPO}'
API_HEADERS = {
    'Authorization': f'Bearer {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
}
archive_response = requests.get(f'{API_ROOT}/tarball/main', headers=API_HEADERS, timeout=180)
if not archive_response.ok:
    raise RuntimeError(f'GitHub source download failed ({archive_response.status_code})')
archive_root = Path('/content/dbty_repo_archive')
if archive_root.exists():
    shutil.rmtree(archive_root)
archive_root.mkdir(parents=True)
with tarfile.open(fileobj=io.BytesIO(archive_response.content), mode='r:gz') as bundle:
    base = archive_root.resolve()
    for member in bundle.getmembers():
        target = (archive_root / member.name).resolve()
        if target != base and base not in target.parents:
            raise RuntimeError('Unsafe path in GitHub source archive')
    bundle.extractall(archive_root)
roots = [p for p in archive_root.iterdir() if p.is_dir()]
if len(roots) != 1:
    raise RuntimeError('Unexpected GitHub source archive layout')
REPO_DIR = roots[0]
os.chdir(REPO_DIR)
sys.path.insert(0, str(REPO_DIR))
print('✅ DBYT source loaded:', REPO_DIR)
""")

code("""#@title 6) تشغيل خط الدبلجة كاملًا داخل Colab
from backend.app.services.pipeline import DubbingPipeline

work_dir = WORK_DIR / 'pipeline'
work_dir.mkdir(parents=True, exist_ok=True)

def progress(percent, message):
    print(f'[{percent:3d}%] {message}', flush=True)

pipeline = DubbingPipeline(
    target_language=TARGET_LANGUAGE,
    engine=TTS_ENGINE,
    voice=str(reference_path) if TTS_ENGINE == 'fasih' else None,
    keep_background=KEEP_BACKGROUND,
    preserve_emotions=True,
    granularity=GRANULARITY,
    lip_sync=False,
    progress=progress,
)

final_path = asyncio.run(pipeline.run(source_path, work_dir))
project = PROJECT_NAME.strip() or f'dbyt-{uuid.uuid4().hex[:10]}'
output_path = WORK_DIR / f'{project}{final_path.suffix}'
shutil.copy2(final_path, output_path)
print('✅ Dubbed output:', output_path)
""")

code("""#@title 7) فحص النتيجة وتشغيل المعاينة
probe = subprocess.check_output([
    'ffprobe', '-v', 'error', '-show_entries', 'format=duration,size',
    '-of', 'default=noprint_wrappers=1', str(output_path)
], text=True)
print('✅ Output metadata:\\n', probe)
from IPython.display import Video, display
display(Video(str(output_path), embed=True))
""")

code("""#@title 8) رفع المصدر والنتيجة والسجل إلى GitHub Releases
API_ROOT = f'https://api.github.com/repos/{GITHUB_REPO}'
HEADERS = {
    'Authorization': f'Bearer {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
}

def check(response, label):
    if not response.ok:
        raise RuntimeError(f'{label} failed ({response.status_code}): {response.text[:500]}')
    return response.json() if response.content else {}

run_id = uuid.uuid4().hex[:12]
tag = f'dbyt-result-{run_id}'
release = check(requests.post(
    f'{API_ROOT}/releases', headers=HEADERS,
    json={
        'tag_name': tag,
        'target_commitish': 'main',
        'name': f'DBYT result {run_id}',
        'body': f'Full Colab dubbing run; engine={TTS_ENGINE}; target={TARGET_LANGUAGE}.',
        'draft': False, 'prerelease': False, 'generate_release_notes': False,
    }, timeout=60,
), 'result release creation')

run_report = {
    'source_url': VIDEO_URL,
    'target_language': TARGET_LANGUAGE,
    'tts_engine': TTS_ENGINE,
    'granularity': GRANULARITY,
    'source_bytes': source_path.stat().st_size,
    'output_bytes': output_path.stat().st_size,
    'release_tag': tag,
}
report_path = WORK_DIR / 'run.json'
report_path.write_text(json.dumps(run_report, ensure_ascii=False, indent=2), encoding='utf-8')

for path, asset_name, content_type in [
    (source_path, 'source.mp4', 'video/mp4'),
    (output_path, output_path.name, 'video/mp4'),
    (report_path, 'run.json', 'application/json'),
]:
    upload_url = release['upload_url'].split('{', 1)[0] + '?name=' + quote(asset_name)
    print(f'⬆️ Uploading {asset_name} ({path.stat().st_size / 1024 / 1024:.1f} MB)…')
    with path.open('rb') as stream:
        check(requests.post(
            upload_url,
            headers={**HEADERS, 'Content-Type': content_type},
            data=stream,
            timeout=3600,
        ), f'upload {asset_name}')

print(f'✅ Saved source, dubbed video, and run.json in GitHub Release: {tag}')
print(f'🔗 https://github.com/{GITHUB_REPO}/releases/tag/{tag}')
""")

md("""## النتيجة

بعد نجاح الخلية الأخيرة، ستجد في GitHub Release واحدًا:

| الملف | الاستخدام |
|---|---|
| `source.mp4` | نسخة المصدر التي نزلها Colab |
| ملف الفيديو باسم المشروع | الفيديو المدبلج النهائي |
| `run.json` | إعدادات التشغيل وأحجام الملفات |

لا يحتاج هذا المسار إلى تشغيل GitHub Actions. إذا انقطعت جلسة Colab قبل الخلية الأخيرة، أعد تشغيل الدفتر من الخلية المناسبة؛ أما إذا انتهت الدبلجة ونجح الرفع، تبقى الملفات في GitHub حتى بعد انتهاء جلسة Colab.
""")

notebook = {
    'cells': CELLS,
    'metadata': {
        'colab': {'provenance': []},
        'kernelspec': {'display_name': 'Python 3', 'name': 'python3'},
        'language_info': {'name': 'python'},
    },
    'nbformat': 4,
    'nbformat_minor': 5,
}

output = Path(__file__).resolve().parent.parent / 'notebooks' / 'DBYT_colab_full_dubbing.ipynb'
output.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding='utf-8')
print(f'wrote {output} ({len(CELLS)} cells)')
