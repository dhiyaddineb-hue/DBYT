"""Generate a Kaggle-compatible DBYT full dubbing notebook from the Colab source."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'notebooks' / 'DBYT_colab_full_dubbing.ipynb'
TARGET = ROOT / 'notebooks' / 'DBYT_kaggle_full_dubbing.ipynb'

notebook = json.loads(SOURCE.read_text(encoding='utf-8'))
for cell in notebook.get('cells', []):
    source = ''.join(cell.get('source', []))
    if cell.get('cell_type') == 'markdown':
        source = source.replace('Google Colab', 'Kaggle Notebook')
        source = source.replace('Colab', 'Kaggle')
        source = source.replace('Colab Secret باسم `DBYT_COLAB_TOKEN`', 'Kaggle Secret باسم `DBYT_GITHUB_TOKEN`')
        source = source.replace('DBYT_COLAB_TOKEN', 'DBYT_GITHUB_TOKEN')
        source = source.replace('Google Kaggle', 'Kaggle')
        cell['source'] = source.splitlines(True)
        continue

    source = source.replace("WORK_DIR = Path('/content/dbty')", "WORK_DIR = Path('/kaggle/working/dbty')")
    source = source.replace("!sudo apt-get update -qq", "!apt-get update -qq")
    source = source.replace("!sudo apt-get install -y -qq ffmpeg", "!apt-get install -y -qq ffmpeg")
    source = source.replace('!pip -q install -U', '%pip -q install -U')
    source = source.replace('DBYT_COLAB_TOKEN', 'DBYT_GITHUB_TOKEN')
    source = source.replace("print('✅ Base Colab environment ready:', WORK_DIR)", "print('✅ Base Kaggle environment ready:', WORK_DIR)")

    if '#@title 2)' in source:
        old_secret_block = """try:\n    from google.colab import userdata\n    GITHUB_TOKEN = userdata.get('DBYT_GITHUB_TOKEN')\nexcept Exception:\n    GITHUB_TOKEN = os.environ.get('DBYT_GITHUB_TOKEN', '')\n"""
        new_secret_block = """try:\n    from kaggle_secrets import UserSecretsClient\n    GITHUB_TOKEN = UserSecretsClient().get_secret('DBYT_GITHUB_TOKEN')\nexcept Exception:\n    GITHUB_TOKEN = os.environ.get('DBYT_GITHUB_TOKEN', '')\n"""
        if old_secret_block not in source:
            raise RuntimeError('Kaggle secret block was not found in settings cell')
        source = source.replace(old_secret_block, new_secret_block)
        source = source.replace(
            "if TTS_ENGINE == 'fasih' and not has_gpu:\n    print('⚠️ No GPU detected. Fasih will run on CPU and may be slow; switch TTS_ENGINE to sherpa for a lighter run.')",
            "if TTS_ENGINE == 'fasih' and not has_gpu:\n    raise RuntimeError('GPU غير مفعّل في Kaggle. افتح Settings → Accelerator واختر GPU ثم أعد تشغيل الجلسة.')",
        )
        source = source.replace("أضف DBYT_GITHUB_TOKEN إلى Kaggle Secrets قبل المتابعة.", "أضف DBYT_GITHUB_TOKEN إلى Kaggle Secrets قبل المتابعة.")

    cell['source'] = source.splitlines(True)

# Add a Kaggle-specific setup note before the first code cell.
setup_note = {
    'cell_type': 'markdown',
    'metadata': {},
    'source': ("## إعداد Kaggle قبل التشغيل\n\n"
               "فعّل **Internet** و**GPU** من لوحة Settings في Notebook. أنشئ Kaggle Secret باسم `DBYT_GITHUB_TOKEN` وضع فيه GitHub token بصلاحية Contents: Read and write. لا تضع السر داخل الخلية أو المستودع. شغّل الخلايا بالترتيب من 1 إلى 8.\n").splitlines(True),
}
insert_at = 1 if notebook.get('cells') else 0
notebook['cells'].insert(insert_at, setup_note)

TARGET.write_text(json.dumps(notebook, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Wrote {TARGET}')
