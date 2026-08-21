"""Build a private Kaggle kernel payload for one-click DBYT runs."""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "tools" / "kaggle_dbyt_runner.py"
OUTPUT = Path(os.environ.get("KAGGLE_KERNEL_DIR", ROOT / ".kaggle-kernel"))


def encode(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def main() -> None:
    required = {
        "KAGGLE_KERNEL_ID": os.environ.get("KAGGLE_KERNEL_ID", "").strip(),
        "SOURCE_URL": os.environ.get("SOURCE_URL", "").strip(),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise SystemExit("Missing required configuration: " + ", ".join(missing))
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", required["KAGGLE_KERNEL_ID"]):
        raise SystemExit("KAGGLE_KERNEL_ID must use the form kaggle_username/kernel-slug")

    values = {
        "JOB_SOURCE_URL_B64": required["SOURCE_URL"],
        "JOB_REPOSITORY_B64": os.environ.get("DBYT_REPOSITORY", "dhiyaddineb-hue/DBYT"),
        "JOB_REF_B64": os.environ.get("DBYT_REF", "main"),
        "JOB_TARGET_LANGUAGE_B64": os.environ.get("TARGET_LANGUAGE", "ar"),
        "JOB_PROJECT_NAME_B64": os.environ.get("PROJECT_NAME", "dbyt-project"),
        "JOB_ENGINE_B64": os.environ.get("TTS_ENGINE", "fasih"),
        "JOB_GRANULARITY_B64": os.environ.get("GRANULARITY", "segment"),
        "JOB_WHISPER_MODEL_B64": os.environ.get("WHISPER_MODEL", "small"),
    }

    source = TEMPLATE.read_text(encoding="utf-8")
    for variable, value in values.items():
        replacement = f'{variable} = "{encode(value)}"'
        source, count = re.subn(
            rf'^{re.escape(variable)}\s*=\s*""\s*$', replacement, source, flags=re.MULTILINE
        )
        if count != 1:
            raise SystemExit(f"Template placeholder not found exactly once: {variable}")

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "dbyt_one_click.py").write_text(source, encoding="utf-8")
    metadata = {
        "id": required["KAGGLE_KERNEL_ID"],
        "title": "DBYT One Click",
        "code_file": "dbyt_one_click.py",
        "language": "python",
        "kernel_type": "script",
        "is_private": "true",
        "enable_gpu": "true",
        "enable_internet": "true",
        "machine_shape": "NvidiaTeslaT4",
        "dataset_sources": [],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }
    (OUTPUT / "kernel-metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Prepared private Kaggle kernel payload in {OUTPUT}")


if __name__ == "__main__":
    main()
