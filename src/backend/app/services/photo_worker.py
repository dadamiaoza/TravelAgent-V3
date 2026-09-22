"""In-process photo job worker. Not Redis/Celery."""
from __future__ import annotations

import logging
import threading
import time
from uuid import UUID

from app.db.session import SessionLocal
from app.models.photo import PhotoJob
from app.services.photo_pipeline import process_photo_job

logger = logging.getLogger(__name__)

_started = False
_lock = threading.Lock()


def run_job(job_id: UUID) -> None:
    with SessionLocal() as db:
        try:
            process_photo_job(db, job_id)
        except Exception:
            logger.exception("photo job %s failed", job_id)
            job = db.get(PhotoJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error = "处理失败"
                job.progress = 100
                db.commit()


def enqueue_photo_job(job_id: UUID) -> None:
    thread = threading.Thread(target=run_job, args=(job_id,), daemon=True, name=f"photo-job-{job_id}")
    thread.start()


def _poll_loop() -> None:
    while True:
        job_id: UUID | None = None
        with SessionLocal() as db:
            job = (
                db.query(PhotoJob)
                .filter(PhotoJob.status == "pending")
                .order_by(PhotoJob.created_at)
                .first()
            )
            if job is not None:
                job.status = "running"
                db.commit()
                job_id = job.id
        if job_id is not None:
            run_job(job_id)
        else:
            time.sleep(0.8)


def start_photo_worker_thread() -> None:
    global _started
    with _lock:
        if _started:
            return
        _started = True
        threading.Thread(target=_poll_loop, daemon=True, name="photo-worker").start()
