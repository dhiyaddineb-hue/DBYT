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

> **إصدار Notebook: `2026.08.21-03`** — افتح هذه النسخة ولا تستخدم نسخة أقدم محفوظة في Colab.

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

code("""#@title 1) تثبيت الأدوات الأساسية — DBYT Notebook v2026.08.21-03
NOTEBOOK_VERSION = '2026.08.21-03'
print(f'🧩 DBYT Colab Notebook version: {NOTEBOOK_VERSION}', flush=True)

import sys, shutil, subprocess
from urllib.request import urlopen

# Fail fast if Colab has no Internet instead of waiting through apt/pip DNS retries.
try:
    with urlopen('https://pypi.org/simple/yt-dlp/', timeout=12) as response:
        if response.status != 200:
            raise RuntimeError(f'PyPI connectivity check returned HTTP {response.status}')
except Exception as exc:
    raise RuntimeError('Colab Internet is disabled or DNS is unavailable. Open Runtime settings, enable Internet access, restart the runtime, and run this cell again.') from exc

if shutil.which('ffmpeg') is None:
    subprocess.run(['apt-get', '-o', 'Acquire::Retries=1', '-o', 'Acquire::http::Timeout=15', '-o', 'Acquire::https::Timeout=15', 'update', '-qq'], check=True)
    subprocess.run(['apt-get', '-o', 'Acquire::Retries=1', '-o', 'Acquire::http::Timeout=15', '-o', 'Acquire::https::Timeout=15', 'install', '-y', '-qq', 'ffmpeg'], check=True)
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-U', 'yt-dlp[default]==2026.8.19', 'yt-dlp-ejs', 'pydantic==2.7.4', 'pydantic-settings==2.3.4', 'requests', 'faster-whisper', 'deep-translator', 'soundfile', 'huggingface_hub', 'nest_asyncio'], check=True)

from pathlib import Path
import importlib.metadata
import json, os, re, shutil, subprocess, sys, uuid
from urllib.parse import quote
import requests

WORK_DIR = Path('/content/dbty')
WORK_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault('HF_HOME', str(WORK_DIR / 'models' / 'huggingface'))
os.environ.setdefault('TTS_HOME', str(WORK_DIR / 'models' / 'tts'))

# yt-dlp now needs a real JavaScript runtime for YouTube. Install Deno in
# the project directory instead of assuming that Colab runs as root.
deno_root = WORK_DIR / '.deno'
deno_path = deno_root / 'bin' / 'deno'
os.environ['DENO_INSTALL'] = str(deno_root)
os.environ['DENO_DIR'] = str(WORK_DIR / 'models' / 'deno')
if not (deno_path.is_file() and os.access(deno_path, os.X_OK)):
    install_env = os.environ.copy()
    # The current Deno installer asks interactive shell/completion questions
    # when stdout is a terminal. Colab must never block on those prompts.
    install_env['CI'] = '1'
    subprocess.run(
        ['bash', '-lc', 'curl -fsSL https://deno.land/install.sh | sh'],
        env=install_env,
        check=True,
    )
if not (deno_path.is_file() and os.access(deno_path, os.X_OK)):
    raise RuntimeError(f'Deno installation failed; expected executable: {deno_path}')
os.environ['PATH'] = f'{deno_path.parent}:{os.environ.get("PATH", "")}'
subprocess.run([str(deno_path), '--version'], check=True)
if shutil.which('ffmpeg') is None or shutil.which('yt-dlp') is None:
    raise RuntimeError('ffmpeg or yt-dlp is not available on PATH after installation.')
print('✅ Base Colab environment ready:', WORK_DIR)
print('✅ yt-dlp:', importlib.metadata.version('yt-dlp'), '| Deno:', deno_path)
print('✅ pydantic-settings:', importlib.metadata.version('pydantic-settings'))
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
except Exception:
    userdata = None

if userdata is not None:
    try:
        GITHUB_TOKEN = userdata.get('DBYT_COLAB_TOKEN')
    except Exception:
        GITHUB_TOKEN = os.environ.get('DBYT_COLAB_TOKEN', '')
    try:
        youtube_cookies_blob = userdata.get('YOUTUBE_COOKIES')
    except Exception:
        youtube_cookies_blob = os.environ.get('YOUTUBE_COOKIES', '')
else:
    GITHUB_TOKEN = os.environ.get('DBYT_COLAB_TOKEN', '')
    youtube_cookies_blob = os.environ.get('YOUTUBE_COOKIES', '')

YOUTUBE_COOKIES_PATH = None
if youtube_cookies_blob:
    YOUTUBE_COOKIES_PATH = WORK_DIR / 'youtube_cookies.txt'
    YOUTUBE_COOKIES_PATH.write_text(youtube_cookies_blob, encoding='utf-8')
    cookie_lines = [line for line in youtube_cookies_blob.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    cookie_is_netscape = any(len(line.split('\t')) >= 7 for line in cookie_lines)
    if YOUTUBE_COOKIES_PATH.stat().st_size < 100 or not cookie_is_netscape:
        raise RuntimeError('YOUTUBE_COOKIES موجود لكنه ليس ملف Netscape صالحًا. ضع محتوى ملف cookies.txt الكامل في Secret، وليس اسم الملف أو مساره.')
    print(f'✅ Optional YouTube cookies loaded for yt-dlp ({YOUTUBE_COOKIES_PATH.stat().st_size} bytes; value hidden).')
else:
    print('⚠️ No optional YOUTUBE_COOKIES Secret; yt-dlp will use anonymous access and YouTube may reject the request.')

if not GITHUB_TOKEN:
    raise RuntimeError('أضف DBYT_COLAB_TOKEN إلى Colab Secrets قبل المتابعة.')
if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', GITHUB_REPO):
    raise ValueError('GITHUB_REPO يجب أن يكون owner/repository')
if not re.match(r'https://(www\\.)?youtube\\.com/|https://youtu\\.be/', VIDEO_URL):
    raise ValueError('VIDEO_URL يجب أن يكون رابط YouTube')
if TTS_ENGINE == 'fasih' and TARGET_LANGUAGE != 'ar':
    raise ValueError('Fasih-TTS-V1 مخصص للعربية الفصحى؛ اختر ar أو استخدم Sherpa.')

# Install only the selected TTS backend. Fasih 0.27.5 currently needs
# transformers 5.0.0: transformers 5.1+ removed isin_mps_friendly.
tts_packages = ['coqui-tts==0.27.5', 'transformers==5.0.0'] if TTS_ENGINE == 'fasih' else ['sherpa-onnx==1.13.6']
subprocess.run([
    sys.executable, '-m', 'pip', 'install', '-q', '--upgrade', '--upgrade-strategy', 'eager', *tts_packages,
], check=True)
if TTS_ENGINE == 'fasih':
    try:
        import torch
        import transformers
        import transformers.pytorch_utils as _pt_utils
        if not hasattr(_pt_utils, 'isin_mps_friendly'):
            def isin_mps_friendly(elements, test_elements, *args, **kwargs):
                return torch.isin(elements, test_elements, *args, **kwargs)
            _pt_utils.isin_mps_friendly = isin_mps_friendly
            print('ℹ️ Applied compatibility shim: transformers.pytorch_utils.isin_mps_friendly → torch.isin', flush=True)
        for module_name in list(sys.modules):
            if module_name == 'TTS' or module_name.startswith('TTS.'):
                del sys.modules[module_name]
        from transformers.pytorch_utils import isin_mps_friendly
        from TTS.api import TTS as _FasihTTS
        print(f'✅ Fasih compatibility check: coqui-tts 0.27.5 + transformers {transformers.__version__}', flush=True)
    except Exception as exc:
        raise RuntimeError(f'Fasih import failed after compatibility setup. transformers={globals().get("transformers", "unknown")}') from exc
try:
    import torch
    has_gpu = bool(torch.cuda.is_available())
except Exception:
    has_gpu = False
if TTS_ENGINE == 'fasih' and not has_gpu:
    print('⚠️ No GPU detected. Fasih will run on CPU and may be slow; switch TTS_ENGINE to sherpa for a lighter run.')
print(f'✅ Settings loaded: {GITHUB_REPO} | engine={TTS_ENGINE} | target={TARGET_LANGUAGE} | granularity={GRANULARITY}')
""")

code("""#@title 3) تنزيل الفيديو من YouTube داخل Colab
import time
source_path = WORK_DIR / 'source.mp4'
if YOUTUBE_COOKIES_PATH and YOUTUBE_COOKIES_PATH.exists():
    print(f'🔐 yt-dlp will use YOUTUBE_COOKIES ({YOUTUBE_COOKIES_PATH.stat().st_size} bytes; value hidden).', flush=True)
else:
    print('⚠️ yt-dlp is running without YOUTUBE_COOKIES; expect bot-check if YouTube blocks anonymous access.', flush=True)
attempts = [
    ('android_vr', 'bv*[height<=720]+ba/b[height<=720]/best'),
    ('android_vr', None),
    (None, None),
]
last_error = ''
for attempt, (selected_client, selected_format) in enumerate(attempts, start=1):
    for old in WORK_DIR.glob('source.*'):
        old.unlink(missing_ok=True)
    command = [
        'yt-dlp', '--ignore-config', '--no-playlist',
        '--retries', '10', '--fragment-retries', '10',
        '--socket-timeout', '30', '--newline',
        '--js-runtimes', f'deno:{deno_path}',
        '--remote-components', 'ejs:github',
        '--merge-output-format', 'mp4',
    ]
    if selected_client:
        command += ['--extractor-args', f'youtube:player_client={selected_client}']
    if YOUTUBE_COOKIES_PATH and YOUTUBE_COOKIES_PATH.exists():
        command += ['--cookies', str(YOUTUBE_COOKIES_PATH)]
    if selected_format:
        command += ['--format', selected_format]
    command += [
        '--output', str(WORK_DIR / 'source.%(ext)s'), VIDEO_URL,
    ]
    print(f'⬇️ Download attempt {attempt}/{len(attempts)} with client={selected_client or "default"}, format={selected_format or "auto"}', flush=True)
    output_lines = []
    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as process:
        assert process.stdout is not None
        for line in process.stdout:
            print(line.rstrip(), flush=True)
            output_lines.append(line)
        return_code = process.wait()
    if return_code == 0:
        print('✅ yt-dlp completed this attempt.', flush=True)
        break
    last_error = ''.join(output_lines) or 'unknown yt-dlp error'
    print(f'⚠️ Attempt {attempt} failed; yt-dlp said:\\n{last_error[-4000:]}', flush=True)
    lowered_error = last_error.lower()
    if 'sign in to confirm' in lowered_error or 'not a bot' in lowered_error or 'http error 429' in lowered_error:
        if YOUTUBE_COOKIES_PATH:
            print('ℹ️ YouTube rejected the supplied cookies or still blocks this network; export a fresh cookie file if needed.', flush=True)
        else:
            print('ℹ️ YouTube is rate-limiting or blocking this Colab network; a new Colab runtime may be required. A YOUTUBE_COOKIES Secret may help.', flush=True)
    if attempt < len(attempts):
        time.sleep(min(30, 5 * attempt))
else:
    print('❌ YouTube download failed. This Colab network is blocked by YouTube.', flush=True)
    print('⬆️ Upload fallback: choose the original video file from your computer to continue dubbing.', flush=True)
    try:
        from google.colab import files
        uploaded = files.upload()
    except Exception as exc:
        raise RuntimeError(f'YouTube download failed and Colab upload fallback is unavailable. Last error:\\n{last_error[-6000:]}') from exc
    video_extensions = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v'}
    uploaded_name = next((name for name in uploaded if Path(name).suffix.lower() in video_extensions), None)
    if not uploaded_name:
        raise RuntimeError('لم يتم رفع ملف فيديو/صوت صالح. ارفع MP4 أو MKV أو MOV أو WebM ثم أعد الخلية 3.')
    uploaded_path = WORK_DIR / Path(uploaded_name).name
    uploaded_path.write_bytes(uploaded[uploaded_name])
    if uploaded_path.suffix.lower() == '.mp4':
        source_path = uploaded_path
    else:
        source_path = WORK_DIR / 'source.mp4'
        subprocess.run(['ffmpeg', '-y', '-i', str(uploaded_path), '-c:v', 'libx264', '-c:a', 'aac', str(source_path)], check=True)
    print(f'✅ Uploaded source selected: {source_path}', flush=True)

candidates = [source_path] if source_path.exists() else sorted(WORK_DIR.glob('source.*'))
if not candidates:
    raise FileNotFoundError('لم يتم العثور على ملف مصدر بعد التنزيل أو الرفع')
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
if 'source_path' not in globals() or not Path(source_path).exists():
    raise RuntimeError('شغّل الخلية 3 بنجاح أولًا؛ source_path غير موجود.')
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
if not GITHUB_TOKEN:
    raise RuntimeError('GITHUB_TOKEN غير موجود؛ تحقق من Colab Secret DBYT_COLAB_TOKEN.')
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
archive_root = WORK_DIR / 'repo_archive'
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
if 'source_path' not in globals() or not Path(source_path).exists():
    raise RuntimeError('ملف المصدر غير موجود؛ شغّل الخلية 3 أولًا.')
if TTS_ENGINE == 'fasih' and ('reference_path' not in globals() or not Path(reference_path).exists()):
    raise RuntimeError('المقطع المرجعي غير موجود؛ شغّل الخلية 4 أولًا.')
def _ensure_repo_code():
    global REPO_DIR
    raw_repo_dir = globals().get('REPO_DIR')
    candidate = Path(raw_repo_dir).expanduser().resolve() if raw_repo_dir else None
    if candidate is None or not (candidate / 'backend' / 'app' / 'services' / 'pipeline.py').is_file():
        if not GITHUB_TOKEN:
            raise RuntimeError('GITHUB_TOKEN غير موجود؛ لا يمكن جلب كود DBYT تلقائيًا.')
        import io, tarfile
        api_root = f'https://api.github.com/repos/{GITHUB_REPO}'
        api_headers = {
            'Authorization': f'Bearer {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        }
        response = requests.get(f'{api_root}/tarball/main', headers=api_headers, timeout=180)
        if not response.ok:
            raise RuntimeError(f'GitHub source download failed ({response.status_code})')
        archive_root = WORK_DIR / 'repo_archive'
        if archive_root.exists():
            shutil.rmtree(archive_root)
        archive_root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(response.content), mode='r:gz') as bundle:
            base = archive_root.resolve()
            for member in bundle.getmembers():
                target = (archive_root / member.name).resolve()
                if target != base and base not in target.parents:
                    raise RuntimeError('Unsafe path in GitHub source archive')
            bundle.extractall(archive_root)
        roots = [path for path in archive_root.iterdir() if path.is_dir()]
        if len(roots) != 1:
            raise RuntimeError('Unexpected GitHub source archive layout')
        candidate = roots[0]
    REPO_DIR = Path(candidate).resolve()
    backend_dir = REPO_DIR / 'backend'
    if not (backend_dir / 'app' / 'services' / 'pipeline.py').is_file():
        raise RuntimeError(f'كود DBYT غير مكتمل داخل REPO_DIR: {REPO_DIR}')
    os.chdir(REPO_DIR)
    sys.path.insert(0, str(backend_dir))
    import importlib
    importlib.invalidate_caches()
    for module_name in list(sys.modules):
        if module_name == 'app' or module_name.startswith('app.'):
            del sys.modules[module_name]
    return backend_dir

BACKEND_DIR = _ensure_repo_code()
from app.services.pipeline import DubbingPipeline

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

final_path = await pipeline.run(source_path, work_dir)
project = PROJECT_NAME.strip() or f'dbyt-{uuid.uuid4().hex[:10]}'
output_path = WORK_DIR / f'{project}{final_path.suffix}'
shutil.copy2(final_path, output_path)
print('✅ Dubbed output:', output_path)
""")

code("""#@title 7) فحص النتيجة وتشغيل المعاينة
if 'output_path' not in globals() or not Path(output_path).exists():
    raise RuntimeError('الناتج غير موجود؛ شغّل الخلية 6 بنجاح أولًا.')
probe = subprocess.check_output([
    'ffprobe', '-v', 'error', '-show_entries', 'format=duration,size',
    '-of', 'default=noprint_wrappers=1', str(output_path)
], text=True)
print('✅ Output metadata:\\n', probe)
from IPython.display import Video, display
display(Video(str(output_path), embed=True))
""")

code("""#@title 8) رفع المصدر والنتيجة والسجل إلى GitHub Releases
if 'output_path' not in globals() or not Path(output_path).exists():
    raise RuntimeError('الناتج غير موجود؛ شغّل الخلية 6 بنجاح أولًا.')
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

for index, cell in enumerate(CELLS, start=1):
    cell['id'] = f'dbyt-{index:03d}'

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
