"""Durable generation job query and notification SSE."""
import json
import time
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models.trip import GenerationJob
from app.schemas.job import GenerationJobOut
from app.services.generation_jobs import GenerationJobStatus, get_job


router = APIRouter(prefix="/jobs", tags=["jobs"])
SSE_POLL_INTERVAL_SECONDS = 1.0
_TERMINAL_STATUSES = {
    GenerationJobStatus.SUCCEEDED.value,
    GenerationJobStatus.FAILED.value,
}


def _to_job_out(job: GenerationJob) -> GenerationJobOut:
    return GenerationJobOut.model_validate(job)


@router.get("/{job_id}", response_model=GenerationJobOut)
def get_generation_job(job_id: UUID, db: Session = Depends(get_db)):
    """Return the durable generation job snapshot from PostgreSQL."""
    job = get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_job_out(job)


@router.get("/{job_id}/events")
def stream_generation_job_events(job_id: UUID, db: Session = Depends(get_db)):
    """Notify job changes. The first event is a snapshot; GET remains the source of truth."""
    if get_job(db, job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    def event_generator():
        last_version: int | None = None
        while True:
            with SessionLocal() as session:
                job = get_job(session, job_id)
                if job is None:
                    payload = json.dumps({"detail": "Job not found"})
                    yield f"event: error\ndata: {payload}\n\n"
                    return
                snapshot = _to_job_out(job).model_dump(mode="json")
                encoded = json.dumps(snapshot, ensure_ascii=False)
                if last_version is None:
                    yield f"event: snapshot\ndata: {encoded}\n\n"
                    last_version = job.status_version
                elif job.status_version != last_version:
                    yield f"event: update\ndata: {encoded}\n\n"
                    last_version = job.status_version
                if job.status in _TERMINAL_STATUSES:
                    return
            time.sleep(SSE_POLL_INTERVAL_SECONDS)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
