"""Generation job persistence helpers."""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.trip import GenerationJob


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