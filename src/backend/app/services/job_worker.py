"""Simple DB-backed generation job worker.

Polls pending generation_jobs and executes them via trip_editor.
Designed for single-instance demo; can be replaced by Redis/RQ later.
"""
import logging
import threading
import time
from datetime import datetime, timezone
from uuid import UUID

from app.db.session import SessionLocal
from app.models.trip import GenerationJob, Trip
from app.services.trip_editor import regenerate_trip

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def process_pending_jobs(max_jobs: int = 1) -> int:
    db = SessionLocal()
    processed = 0
    try:
        jobs = (
            db.query(GenerationJob)
            .filter(GenerationJob.status == "pending")
            .order_by(GenerationJob.created_at.asc())
            .limit(max_jobs)
            .all()
        )

        for job in jobs:
            job.status = "running"
            job.progress = 10
            job.message = "正在准备生成行程..."
            job.attempts = (job.attempts or 0) + 1
            job.started_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(job)

            trip = db.query(Trip).filter(Trip.id == job.trip_id).first()
            if not trip:
                job.status = "failed"
                job.progress = 100
                job.error = "行程不存在"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                processed += 1
                continue

            try:
                job.progress = 30
                job.message = "AI 正在生成行程..."
                db.commit()
                regenerate_trip(db, trip)
                job.status = "succeeded"
                job.progress = 100
                job.message = "行程生成完成"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                processed += 1
            except Exception as exc:
                db.rollback()
                if (job.attempts or 0) < MAX_RETRIES:
                    job.status = "pending"
                    job.progress = 0
                    job.message = f"生成失败，准备重试：{exc}"
                    job.error = str(exc)
                else:
                    job.status = "failed"
                    job.progress = 100
                    job.message = f"生成失败：{exc}"
                    job.error = str(exc)
                    job.finished_at = datetime.now(timezone.utc)
                db.commit()
                processed += 1
    finally:
        db.close()
    return processed


def job_worker_loop(interval: float = 2.0):
    while True:
        try:
            count = process_pending_jobs()
            if count:
                logger.info("processed %d generation jobs", count)
        except Exception:
            logger.exception("job worker iteration failed")
        time.sleep(interval)


def start_worker_thread():
    thread = threading.Thread(target=job_worker_loop, daemon=True)
    thread.start()
    return thread