"""Generate a Kaggle-compatible DBYT full dubbing notebook from the Colab source."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'notebooks' / 'DBYT_colab_full_dubbing.ipynb'
TARGET = ROOT / 'notebooks' / 'DBYT_kaggle_full_dubbing.ipynb'

notebook = json.loads(SOURCE.read_text(encoding='utf-8'))

KAGGLE_BOOTSTRAP = """from pathlib import Path
import importlib.metadata
import json, os, re, shutil, subprocess, sys, uuid
from urllib.parse import quote
import requests

# Kaggle must have Internet enabled before apt/pip can run. Fail fast instead
# of waiting several minutes on DNS retries when the setting is disabled.
try:
    from urllib.request import urlopen
    with urlopen('https://pypi.org/simple/yt-dlp/', timeout=12) as response:
        if response.status != 200:
            raise RuntimeError(f'PyPI connectivity check returned HTTP {response.status}')
except Exception as exc:
    raise RuntimeError('Kaggle Internet is disabled or DNS is unavailable. Open Notebook Settings → Internet, enable it, restart the session, and run this cell again.') from exc

if shutil.which('ffmpeg') is None:
    subprocess.run(['apt-get', '-o', 'Acquire::Retries=1', '-o', 'Acquire::http::Timeout=15', '-o', 'Acquire::https::Timeout=15', 'update', '-qq'], check=True)
    subprocess.run(['apt-get', '-o', 'Acquire::Retries=1', '-o', 'Acquire::http::Timeout=15', '-o', 'Acquire::https::Timeout=15', 'install', '-y', '-qq', 'ffmpeg'], check=True)
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', '-U', 'yt-dlp[default]==2026.8.19', 'yt-dlp-ejs', 'pydantic==2.7.4', 'pydantic-settings==2.3.4', 'requests', 'faster-whisper', 'deep-translator', 'soundfile', 'huggingface_hub', 'nest_asyncio'], check=True)
"""

for cell in notebook.get('cells', []):
    source = ''.join(cell.get('source', []))
    if cell.get('cell_type') == 'markdown':
        source = source.replace('Google Colab', 'Kaggle Notebook')
        source = source.replace('Colab', 'Kaggle')
        source = source.replace('DBYT_COLAB_TOKEN', 'DBYT_GITHUB_TOKEN')
        source = source.replace('Google Kaggle', 'Kaggle')
        cell['source'] = source.splitlines(True)
        continue

    if '#@title 1)' in source:
        title, remainder = source.split('\n', 1)
        import_start = remainder.find('from pathlib import Path')
        if import_start < 0:
            raise RuntimeError('Kaggle bootstrap could not locate Python imports in cell 1')
        source = title + '\n' + KAGGLE_BOOTSTRAP + remainder[import_start:]
    source = source.replace("WORK_DIR = Path('/content/dbty')", "WORK_DIR = Path('/kaggle/working/dbty')")
    source = source.replace('DBYT_COLAB_TOKEN', 'DBYT_GITHUB_TOKEN')
    source = source.replace("print('✅ Base Colab environment ready:', WORK_DIR)", "print('✅ Base Kaggle environment ready:', WORK_DIR)")

    if '#@title 2)' in source:
        old_secret_block = """try:
    from google.colab import userdata
    GITHUB_TOKEN = userdata.get('DBYT_GITHUB_TOKEN')
except Exception:
    GITHUB_TOKEN = os.environ.get('DBYT_GITHUB_TOKEN', '')
"""
        new_secret_block = """try:
    from kaggle_secrets import UserSecretsClient
    GITHUB_TOKEN = UserSecretsClient().get_secret('DBYT_GITHUB_TOKEN')
except Exception:
    GITHUB_TOKEN = os.environ.get('DBYT_GITHUB_TOKEN', '')
"""
        if old_secret_block not in source:
            raise RuntimeError('Kaggle secret block was not found in settings cell')
        source = source.replace(old_secret_block, new_secret_block)
        source = source.replace(
            "if TTS_ENGINE == 'fasih' and not has_gpu:\n    print('⚠️ No GPU detected. Fasih will run on CPU and may be slow; switch TTS_ENGINE to sherpa for a lighter run.')",
            "if TTS_ENGINE == 'fasih' and not has_gpu:\n    raise RuntimeError('GPU غير مفعّل في Kaggle. افتح Settings → Accelerator واختر GPU ثم أعد تشغيل الجلسة.')",
        )
    cell['source'] = source.splitlines(True)

setup_note = {
    'cell_type': 'markdown',
    'metadata': {},
    'source': ("## إعداد Kaggle قبل التشغيل\n\n"
               "فعّل **Internet** و**GPU** من لوحة Settings في Notebook. أنشئ Kaggle Secret باسم `DBYT_GITHUB_TOKEN` وضع فيه GitHub token بصلاحية Contents: Read and write. لا تضع السر داخل الخلية أو المستودع. شغّل الخلايا بالترتيب من 1 إلى 8.\n").splitlines(True),
}
notebook['cells'].insert(1 if notebook.get('cells') else 0, setup_note)
for index, cell in enumerate(notebook['cells'], start=1):
    cell['id'] = f'dbyt-kaggle-{index:03d}'

TARGET.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Wrote {TARGET}')
