"""Build a private Kaggle download-only kernel payload for GitHub Actions."""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "tools" / "kaggle_youtube_download_runner.py"
OUTPUT = Path(os.environ.get("KAGGLE_KERNEL_DIR", ROOT / ".kaggle-download-kernel"))


def encode(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def main() -> None:
    source_url = os.environ.get("SOURCE_URL", "").strip()
    kernel_id = os.environ.get("KAGGLE_KERNEL_ID", "").strip()
    if not source_url:
        raise SystemExit("SOURCE_URL is required")
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", kernel_id):
        raise SystemExit("KAGGLE_KERNEL_ID must be kaggle_username/kernel-slug")

    source = TEMPLATE.read_text(encoding="utf-8")
    source, count = re.subn(
        r'^JOB_SOURCE_URL_B64\s*=\s*""\s*$',
        f'JOB_SOURCE_URL_B64 = "{encode(source_url)}"',
        source,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise SystemExit("Download runner placeholder was not found exactly once")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "dbyt_youtube_download.py").write_text(source, encoding="utf-8")
    metadata = {
        "id": kernel_id,
        "title": "DBYT Download",
        "code_file": "dbyt_youtube_download.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": "true",
        "enable_gpu": "false",
        "enable_internet": "true",
        "machine_shape": "",
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (OUTPUT / "kernel-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Prepared private Kaggle download kernel in {OUTPUT}")


if __name__ == "__main__":
    main()
