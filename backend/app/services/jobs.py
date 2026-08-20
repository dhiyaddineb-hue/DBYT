"""In-process job manager.

Keeps dubbing jobs tracked in memory and persisted as JSON on disk so status
survives a restart. Jobs run in a background thread (the pipeline itself is
async; we bridge it with `asyncio.run` inside a thread).
"""
from __future__ import annotations

import asyncio
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from ..config import settings
from .pipeline import DubbingPipeline


class Job:
    def __init__(self, job_id: str, params: dict):
        self.id = job_id
        self.params = params
        self.status = "queued"
        self.progress = 0
        self.message = "Queued"
        self.project_name = params.get("project_name")
        self.output_path: Optional[str] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "job_id": self.id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "project_name": self.project_name,
            "output_url": f"/api/results/{self.id}/download" if self.output_path else None,
            "error": self.error,
        }


class JobManager:
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, params: dict) -> Job:
        job = Job(uuid.uuid4().hex[:12], params)
        with self._lock:
            self._jobs[job.id] = job
        self._save(job)
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def _update(self, job: Job, **fields) -> None:
        with self._lock:
            for k, v in fields.items():
                setattr(job, k, v)
            self._save(job)

    def _progress(self, job: Job):
        def cb(progress: int, message: str) -> None:
            self._update(job, progress=progress, message=message)

        return cb

    def _run(self, job: Job) -> None:
        try:
            params = job.params
            work_dir = settings.jobs_dir / job.id
            work_dir.mkdir(parents=True, exist_ok=True)

            if params["source"] == "youtube":
                from . import youtube

                self._update(job, status="downloading", progress=5, message="Downloading video...")
                media = youtube.download_media(
                    params["youtube_url"], work_dir / "source", prefer_audio=False
                )
                source_lang = params.get("source_language")
            else:  # upload
                media = Path(params["upload_path"])
                source_lang = params.get("source_language")

            pipeline = DubbingPipeline(
                target_language=params["target_language"],
                engine=params.get("engine", "edge"),
                voice=params.get("voice"),
                keep_background=params.get("keep_background", True),
                preserve_emotions=params.get("preserve_emotions", True),
                granularity=params.get("granularity", "word"),
                lip_sync=params.get("lip_sync", False),
                progress=self._progress(job),
            )
            final = asyncio.run(pipeline.run(media, work_dir, source_language=source_lang))
            self._update(
                job, status="done", progress=100, message="Dubbing complete",
                output_path=str(final),
            )
            _maybe_commit_to_repo(f"dub({job.id}): {job.project_name}")
        except Exception as exc:  # noqa: BLE001
            self._update(job, status="error", message="Failed", error=str(exc))

    def _save(self, job: Job) -> None:
        try:
            path = settings.jobs_dir / job.id / "job.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(job.to_dict(), ensure_ascii=False, indent=2))
        except Exception:  # noqa: BLE001
            pass


def _maybe_commit_to_repo(message: str) -> None:
    """Persist produced files to the GitHub repository (the workspace).

    Only runs when `DBYT_AUTO_COMMIT=true`. Requires git identity configured in
    the environment (local or GitHub Actions). Failures are non-fatal — the
    job is already done; the user can run `./scripts/sync_workspace.sh` manually.
    """
    import subprocess

    if not settings.auto_commit:
        return
    try:
        subprocess.run(["git", "add", "workspace"], check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"chore(workspace): {message}"],
            check=True, capture_output=True,
        )
        subprocess.run(["git", "push"], check=True, capture_output=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[auto-commit] skipped: {exc}")


jobs = JobManager()
