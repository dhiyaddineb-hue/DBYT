"""Build a private Kaggle notebook payload for GitHub-triggered downloads."""
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
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": source.splitlines(keepends=True),
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    (OUTPUT / "dbyt_youtube_download.ipynb").write_text(
        json.dumps(notebook, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    metadata = {
        "id": kernel_id,
        "title": "DBYT Download",
        "code_file": "dbyt_youtube_download.ipynb",
        "language": "python",
        "kernel_type": "notebook",
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
    print(f"Prepared private Kaggle notebook payload in {OUTPUT}")


if __name__ == "__main__":
    main()
