#!/usr/bin/env python3
"""Generate the Colab-to-GitHub downloader notebook."""
from __future__ import annotations

import json
from pathlib import Path

CELLS: list[dict] = []


def md(source: str) -> None:
    CELLS.append({"cell_type": "markdown", "metadata": {}, "source": source.splitlines(True)})


def code(source: str) -> None:
    CELLS.append({
        "cell_type": "code",
        "metadata": {},
        "execution_count": None,
        "outputs": [],
        "source": source.splitlines(True),
    })


md("""# DBYT — تنزيل YouTube من Colab ثم تشغيل GitHub Actions

هذا الدفتر يفصل **مرحلة تنزيل YouTube** عن GitHub: ينزّل `yt-dlp` الفيديو داخل Google Colab، ثم يرفعه مؤقتًا كـ **Release asset خاص بالمستودع**، ويرسل `repository_dispatch` إلى GitHub. بعدها يعالج GitHub Actions الملف المحلي بالدبلجة ويحفظ الناتج في `workspace/output`.

شغّل الخلايا بالترتيب. لا تضع GitHub token داخل الكود؛ خزّنه في Colab Secrets بالاسم `DBYT_COLAB_TOKEN`. يحتاج token إلى صلاحية المستودع الخاص: **Contents: Read and write** و **Actions: Read and write**.

> هذا المسار لا يرسل cookies إلى GitHub. إذا استخدمت cookies في Colab، تبقى داخل جلسة Colab ولا تُرفع إلى المستودع.
""")

code("""#@title 1) تثبيت الأدوات وإعداد Colab
!sudo apt-get update -qq
!sudo apt-get install -y -qq ffmpeg
!pip -q install yt-dlp requests

from pathlib import Path
import json, os, re, shutil, subprocess, uuid
from urllib.parse import quote
import requests

WORK_DIR = Path('/content/dbty')
WORK_DIR.mkdir(parents=True, exist_ok=True)
print('✅ Colab downloader ready:', WORK_DIR)
""")

code("""#@title 2) الإعدادات
VIDEO_URL = "https://www.youtube.com/watch?v=CAwRm-VO-kU"  #@param {type:"string"}
TARGET_LANGUAGE = "ar"  #@param ["ar","en","fr","es","de","tr"]
PROJECT_NAME = ""  #@param {type:"string"}
GITHUB_REPO = "dhiyaddineb-hue/DBYT"  #@param {type:"string"}
GITHUB_BRANCH = "main"  #@param {type:"string"}

# Store DBYT_COLAB_TOKEN in the Colab Secrets panel (key icon), never in this cell.
try:
    from google.colab import userdata
    GITHUB_TOKEN = userdata.get('DBYT_COLAB_TOKEN')
except Exception:
    GITHUB_TOKEN = os.environ.get('DBYT_COLAB_TOKEN', '')

if not GITHUB_TOKEN:
    raise RuntimeError('Add DBYT_COLAB_TOKEN to Colab Secrets before continuing.')
if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', GITHUB_REPO):
    raise ValueError('GITHUB_REPO must look like owner/repository')
if not re.match(r'https://(www\\.)?youtube\\.com/|https://youtu\\.be/', VIDEO_URL):
    raise ValueError('VIDEO_URL must be a YouTube URL')

print('✅ Settings loaded for', GITHUB_REPO, 'target=', TARGET_LANGUAGE)
""")

code("""#@title 3) تنزيل الفيديو مباشرة في Colab
source_path = WORK_DIR / 'source.mp4'
if source_path.exists():
    source_path.unlink()

command = [
    'yt-dlp',
    '--no-playlist',
    '--format', 'bv*[height<=720]+ba/b[height<=720]/best',
    '--merge-output-format', 'mp4',
    '--output', str(WORK_DIR / 'source.%(ext)s'),
    VIDEO_URL,
]
print('⬇️ Downloading in Colab…')
subprocess.run(command, check=True)

candidates = sorted(WORK_DIR.glob('source.*'))
if not candidates:
    raise FileNotFoundError('yt-dlp completed but no source file was found')
source_path = candidates[0]
if source_path.suffix.lower() != '.mp4':
    converted = WORK_DIR / 'source.mp4'
    subprocess.run(['ffmpeg', '-y', '-i', str(source_path), '-c', 'copy', str(converted)], check=True)
    source_path = converted

size_mb = source_path.stat().st_size / (1024 * 1024)
print(f'✅ Downloaded: {source_path} ({size_mb:.1f} MB)')
""")

code("""#@title 4) رفع الملف إلى Release asset خاص بالمستودع
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

request_id = uuid.uuid4().hex[:12]
release_tag = f'dbyt-colab-{request_id}'
release_name = f'DBYT Colab upload {request_id}'
release = check(requests.post(
    f'{API_ROOT}/releases',
    headers=HEADERS,
    json={
        'tag_name': release_tag,
        'target_commitish': GITHUB_BRANCH,
        'name': release_name,
        'body': 'Temporary DBYT source upload created by Colab.',
        'draft': False,
        'prerelease': True,
        'generate_release_notes': False,
    },
    timeout=60,
), 'release creation')

asset_name = f'{request_id}.mp4'
asset_upload_url = release['upload_url'].split('{', 1)[0] + '?name=' + quote(asset_name)
with source_path.open('rb') as stream:
    asset = check(requests.post(
        asset_upload_url,
        headers={**HEADERS, 'Content-Type': 'video/mp4'},
        data=stream,
        timeout=1800,
    ), 'asset upload')

print('✅ Uploaded private release asset:', asset_name)
print('   asset id:', asset['id'])
""")

code("""#@title 5) إرسال إشارة إلى GitHub Actions
project = PROJECT_NAME.strip() or f'dbyt-{request_id}'
payload = {
    'release_id': release['id'],
    'release_tag': release_tag,
    'asset_id': asset['id'],
    'asset_api_url': asset['url'],
    'filename': asset_name,
    'target_language': TARGET_LANGUAGE,
    'project_name': project,
}
response = requests.post(
    f'{API_ROOT}/dispatches',
    headers=HEADERS,
    json={'event_type': 'dbyt_video_uploaded', 'client_payload': payload},
    timeout=60,
)
if response.status_code not in (204, 200):
    raise RuntimeError(f'repository_dispatch failed ({response.status_code}): {response.text[:500]}')

print('✅ GitHub Actions triggered')
print(f'🔗 Watch: https://github.com/{GITHUB_REPO}/actions')
print('The workflow downloads the private release asset, runs the dubbing pipeline, commits workspace/output, and removes the temporary release after success.')
""")

md("""## ملاحظات التشغيل

إذا فشل Workflow، يبقى Release المؤقت موجودًا حتى يمكن فحصه أو إعادة تشغيل المعالجة. احذفه يدويًا بعد الانتهاء من صفحة Releases إذا لم يُحذف تلقائيًا. لا تشارك `DBYT_COLAB_TOKEN` ولا تطبع قيمته في الخلايا.

إذا كان الفيديو كبيرًا، استخدام Release asset أفضل من Contents API لأنه لا يضع الفيديو داخل Git history. الناتج المدبلج يُحفظ في `workspace/output` ويظهر أيضًا كـ Artifact في GitHub Actions.
""")

notebook = {
    "cells": CELLS,
    "metadata": {
        "colab": {"provenance": []},
        "kernelspec": {"display_name": "Python 3", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

output = Path(__file__).resolve().parent.parent / 'notebooks' / 'DBYT_colab_downloader.ipynb'
output.write_text(json.dumps(notebook, ensure_ascii=False, indent=1), encoding='utf-8')
print(f'wrote {output} ({len(CELLS)} cells)')
