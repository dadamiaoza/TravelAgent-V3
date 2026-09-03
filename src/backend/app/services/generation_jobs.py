"""Generation job persistence helpers."""
from enum import Enum
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.trip import GenerationJob


class GenerationJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class InvalidGenerationJobTransitionError(ValueError):
    """Raised when a generation job lifecycle transition is not allowed."""


_ALLOWED_TRANSITIONS = {
    (GenerationJobStatus.PENDING, GenerationJobStatus.RUNNING),
    (GenerationJobStatus.RETRY_WAIT, GenerationJobStatus.RUNNING),
    (GenerationJobStatus.RUNNING, GenerationJobStatus.RETRY_WAIT),
    (GenerationJobStatus.RUNNING, GenerationJobStatus.SUCCEEDED),
    (GenerationJobStatus.RUNNING, GenerationJobStatus.FAILED),
}


def transition_job(
    db: Session,
    job: GenerationJob,
    new_status: GenerationJobStatus | str,
) -> GenerationJob:
    """Apply and persist one valid generation job status transition."""
    try:
        current = GenerationJobStatus(job.status)
        target = GenerationJobStatus(new_status)
    except ValueError as exc:
        raise InvalidGenerationJobTransitionError(
            f"Invalid generation job transition: {job.status} -> {new_status}"
        ) from exc

    if (current, target) not in _ALLOWED_TRANSITIONS:
        raise InvalidGenerationJobTransitionError(
            f"Invalid generation job transition: {current.value} -> {target.value}"
        )

    job.status = target.value
    job.status_version = (job.status_version or 0) + 1
    db.commit()
    db.refresh(job)
    return job


def create_job(db: Session, trip_id: UUID) -> GenerationJob:
    job = GenerationJob(trip_id=trip_id, status="pending", progress=0, message="等待生成")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_job(db: Session, job_id: UUID, **fields) -> GenerationJob:
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job:
        raise ValueError("job not found")
    for key, value in fields.items():
        setattr(job, key, value)
    db.commit()
    db.refresh(job)
    return job


def get_latest_job_for_trip(db: Session, trip_id: UUID) -> GenerationJob | None:
    return (
        db.query(GenerationJob)
        .filter(GenerationJob.trip_id == trip_id)
        .order_by(GenerationJob.created_at.desc())
        .first()
    )