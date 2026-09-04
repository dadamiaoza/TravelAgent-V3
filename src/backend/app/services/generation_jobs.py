"""Generation job persistence helpers."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.trip import GenerationJob, Trip
from app.services.itinerary_persistence import persist_itinerary


SessionFactory = Callable[[], Session]
STALE_HEARTBEAT_AFTER = timedelta(minutes=10)
STALE_RETRY_DELAY = timedelta(seconds=5)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class GenerationJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class InvalidGenerationJobTransitionError(ValueError):
    """Raised when a generation job lifecycle transition is not allowed."""


RETRY_EXHAUSTED = "RETRY_EXHAUSTED"
DEADLINE_EXPIRED = "DEADLINE_EXPIRED"
PERMANENT_ERROR = "PERMANENT_ERROR"
WORKER_LOST = "WORKER_LOST"

_ALLOWED_TRANSITIONS = {
    (GenerationJobStatus.PENDING, GenerationJobStatus.RUNNING),
    (GenerationJobStatus.RETRY_WAIT, GenerationJobStatus.RUNNING),
    (GenerationJobStatus.RUNNING, GenerationJobStatus.RETRY_WAIT),
    (GenerationJobStatus.RUNNING, GenerationJobStatus.SUCCEEDED),
    (GenerationJobStatus.RUNNING, GenerationJobStatus.FAILED),
}
_TERMINAL_FAIL_TRANSITIONS = {
    (GenerationJobStatus.PENDING, GenerationJobStatus.FAILED),
    (GenerationJobStatus.RETRY_WAIT, GenerationJobStatus.FAILED),
}
_TERMINAL_FAIL_REASONS = {
    RETRY_EXHAUSTED,
    DEADLINE_EXPIRED,
    PERMANENT_ERROR,
    WORKER_LOST,
}


def _coerce_status(value: GenerationJobStatus | str) -> GenerationJobStatus:
    try:
        return value if isinstance(value, GenerationJobStatus) else GenerationJobStatus(value)
    except ValueError as exc:
        raise InvalidGenerationJobTransitionError(
            f"Invalid generation job transition: {value}"
        ) from exc


def validate_job_transition(
    current: GenerationJobStatus | str,
    target: GenerationJobStatus | str,
    *,
    reason: str | None = None,
) -> None:
    """Raise if a lifecycle transition is not allowed."""
    try:
        current_status = _coerce_status(current)
        target_status = _coerce_status(target)
    except InvalidGenerationJobTransitionError as exc:
        raise InvalidGenerationJobTransitionError(
            f"Invalid generation job transition: {current} -> {target}"
        ) from exc

    pair = (current_status, target_status)
    if pair in _ALLOWED_TRANSITIONS:
        return
    if pair in _TERMINAL_FAIL_TRANSITIONS and reason in _TERMINAL_FAIL_REASONS:
        return
    raise InvalidGenerationJobTransitionError(
        f"Invalid generation job transition: {current_status.value} -> {target_status.value}"
    )


def apply_job_transition(
    job: GenerationJob,
    new_status: GenerationJobStatus | str,
    *,
    reason: str | None = None,
) -> None:
    """Validate and mutate status/version without committing."""
    target = _coerce_status(new_status)
    validate_job_transition(job.status, target, reason=reason)
    job.status = target.value
    job.status_version = (job.status_version or 0) + 1


@dataclass(frozen=True)
class ClaimedGenerationJob:
    """Immutable ownership data for one claimed generation attempt."""

    id: UUID
    trip_id: UUID
    run_token: UUID
    attempts: int
    max_attempts: int


def _mark_trip_generation_failed(db: Session, trip_id: UUID) -> None:
    trip = db.get(Trip, trip_id)
    if trip is not None:
        trip.status = "generation_failed"


def _terminalize_eligible_exhausted_jobs(
    db: Session,
    terminalized_at: datetime,
) -> int:
    jobs = db.execute(
        select(GenerationJob)
        .where(
            GenerationJob.attempts >= GenerationJob.max_attempts,
            GenerationJob.status.in_(
                (
                    GenerationJobStatus.PENDING.value,
                    GenerationJobStatus.RETRY_WAIT.value,
                )
            ),
        )
        .order_by(GenerationJob.created_at.asc())
        .with_for_update(skip_locked=True)
    ).scalars()

    terminalized = 0
    for job in jobs:
        apply_job_transition(
            job,
            GenerationJobStatus.FAILED,
            reason=RETRY_EXHAUSTED,
        )
        job.progress = 100
        job.message = "行程生成失败，请稍后重试"
        job.error = "Generation job exhausted all retry attempts"
        job.error_code = RETRY_EXHAUSTED
        job.next_run_at = None
        job.heartbeat_at = None
        job.run_token = None
        job.finished_at = terminalized_at
        _mark_trip_generation_failed(db, job.trip_id)
        terminalized += 1
    return terminalized


def terminalize_exhausted_jobs(
    *,
    session_factory: SessionFactory = SessionLocal,
    now: datetime | None = None,
) -> int:
    """Fail eligible exhausted active jobs through an explicit recovery path."""
    terminalized_at = now or _now()
    with session_factory() as db:
        with db.begin():
            return _terminalize_eligible_exhausted_jobs(db, terminalized_at)


def claim_next_job(
    *,
    session_factory: SessionFactory = SessionLocal,
    now: datetime | None = None,
) -> ClaimedGenerationJob | None:
    """Atomically claim the oldest eligible job without waiting on other workers."""
    claimed_at = now or _now()
    with session_factory() as db:
        with db.begin():
            _terminalize_eligible_exhausted_jobs(db, claimed_at)
            job = db.execute(
                select(GenerationJob)
                .where(
                    GenerationJob.attempts < GenerationJob.max_attempts,
                    or_(
                        GenerationJob.status == GenerationJobStatus.PENDING.value,
                        (
                            (
                                GenerationJob.status
                                == GenerationJobStatus.RETRY_WAIT.value
                            )
                            & (GenerationJob.next_run_at <= claimed_at)
                        ),
                    )
                )
                .order_by(GenerationJob.created_at.asc())
                .limit(1)
                .with_for_update(skip_locked=True)
            ).scalar_one_or_none()
            if job is None:
                return None

            run_token = uuid4()
            apply_job_transition(job, GenerationJobStatus.RUNNING)
            job.attempts = (job.attempts or 0) + 1
            job.run_token = run_token
            job.heartbeat_at = claimed_at
            job.next_run_at = None
            job.progress = 10
            job.message = "正在准备生成行程..."
            job.started_at = claimed_at
            job.finished_at = None
            return ClaimedGenerationJob(
                id=job.id,
                trip_id=job.trip_id,
                run_token=run_token,
                attempts=job.attempts,
                max_attempts=job.max_attempts,
            )


def _update_running_job(
    job_id: UUID,
    run_token: UUID,
    fields: dict,
    *,
    increment_version: bool,
    session_factory: SessionFactory,
) -> bool:
    values = dict(fields)
    if "status" in values:
        validate_job_transition(GenerationJobStatus.RUNNING, values["status"])
    if increment_version:
        values["status_version"] = GenerationJob.status_version + 1

    with session_factory() as db:
        result = db.execute(
            update(GenerationJob)
            .where(
                GenerationJob.id == job_id,
                GenerationJob.status == GenerationJobStatus.RUNNING.value,
                GenerationJob.run_token == run_token,
            )
            .values(**values)
        )
        db.commit()
        return result.rowcount == 1


def update_job_progress(
    job_id: UUID,
    run_token: UUID,
    *,
    progress: int,
    message: str,
    session_factory: SessionFactory = SessionLocal,
) -> bool:
    """Update progress only while the caller still owns the running attempt."""
    return _update_running_job(
        job_id,
        run_token,
        {"progress": progress, "message": message},
        increment_version=False,
        session_factory=session_factory,
    )


def renew_heartbeat(
    job_id: UUID,
    run_token: UUID,
    *,
    session_factory: SessionFactory = SessionLocal,
    now: datetime | None = None,
) -> bool:
    """Renew only the active attempt's heartbeat in a short transaction."""
    return _update_running_job(
        job_id,
        run_token,
        {"heartbeat_at": now or _now()},
        increment_version=False,
        session_factory=session_factory,
    )


def retry_delay(attempts: int) -> timedelta:
    """Return bounded exponential retry delay for a completed attempt."""
    seconds = min(5 * (2 ** max(attempts - 1, 0)), 60)
    return timedelta(seconds=seconds)


def schedule_job_retry(
    claim: ClaimedGenerationJob,
    *,
    error_code: str,
    error: str,
    message: str,
    session_factory: SessionFactory = SessionLocal,
    now: datetime | None = None,
) -> bool:
    """Move an owned running attempt to retry_wait."""
    failed_at = now or _now()
    return _update_running_job(
        claim.id,
        claim.run_token,
        {
            "status": GenerationJobStatus.RETRY_WAIT.value,
            "progress": 0,
            "message": message,
            "error": error,
            "error_code": error_code,
            "next_run_at": failed_at + retry_delay(claim.attempts),
            "heartbeat_at": None,
            "run_token": None,
        },
        increment_version=True,
        session_factory=session_factory,
    )


def mark_job_failed(
    claim: ClaimedGenerationJob,
    *,
    error_code: str,
    error: str,
    message: str,
    session_factory: SessionFactory = SessionLocal,
    now: datetime | None = None,
) -> bool:
    """Fail an owned running attempt and persist Trip generation_failed together."""
    failed_at = now or _now()
    with session_factory() as db:
        with db.begin():
            job = db.execute(
                select(GenerationJob)
                .where(
                    GenerationJob.id == claim.id,
                    GenerationJob.status == GenerationJobStatus.RUNNING.value,
                    GenerationJob.run_token == claim.run_token,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if job is None:
                return False
            apply_job_transition(job, GenerationJobStatus.FAILED)
            job.progress = 100
            job.message = message
            job.error = error
            job.error_code = error_code
            job.next_run_at = None
            job.heartbeat_at = None
            job.run_token = None
            job.finished_at = failed_at
            _mark_trip_generation_failed(db, claim.trip_id)
            return True


def mark_job_succeeded(
    job_id: UUID,
    run_token: UUID,
    *,
    session_factory: SessionFactory = SessionLocal,
    now: datetime | None = None,
) -> bool:
    """Complete a job only if the caller still owns its running attempt."""
    return _update_running_job(
        job_id,
        run_token,
        {
            "status": GenerationJobStatus.SUCCEEDED.value,
            "progress": 100,
            "message": "行程生成完成",
            "error": None,
            "error_code": None,
            "next_run_at": None,
            "heartbeat_at": None,
            "run_token": None,
            "finished_at": now or _now(),
        },
        increment_version=True,
        session_factory=session_factory,
    )


def finalize_job_success(
    claim: ClaimedGenerationJob,
    draft: dict,
    *,
    session_factory: SessionFactory = SessionLocal,
    now: datetime | None = None,
) -> bool:
    """Persist itinerary, trip status, and job success in one short transaction."""
    finished_at = now or _now()
    with session_factory() as db:
        with db.begin():
            job = db.execute(
                select(GenerationJob)
                .where(GenerationJob.id == claim.id)
                .with_for_update()
            ).scalar_one_or_none()
            if (
                job is None
                or job.status != GenerationJobStatus.RUNNING.value
                or job.run_token != claim.run_token
            ):
                return False

            trip = db.get(Trip, claim.trip_id)
            if trip is None:
                apply_job_transition(job, GenerationJobStatus.FAILED)
                job.progress = 100
                job.message = "关联的行程不存在"
                job.error = "Trip missing at finalization"
                job.error_code = "TRIP_NOT_FOUND"
                job.next_run_at = None
                job.heartbeat_at = None
                job.run_token = None
                job.finished_at = finished_at
                return False

            persist_itinerary(db, trip, draft, trip.start_date, commit=False)
            apply_job_transition(job, GenerationJobStatus.SUCCEEDED)
            job.progress = 100
            job.message = "行程生成完成"
            job.error = None
            job.error_code = None
            job.next_run_at = None
            job.heartbeat_at = None
            job.run_token = None
            job.finished_at = finished_at
            return True


def recover_stale_jobs(
    *,
    session_factory: SessionFactory = SessionLocal,
    now: datetime | None = None,
) -> int:
    """Recover running attempts whose worker heartbeat has expired."""
    recovered_at = now or _now()
    cutoff = recovered_at - STALE_HEARTBEAT_AFTER
    recovered = 0

    with session_factory() as db:
        with db.begin():
            jobs = db.execute(
                select(GenerationJob)
                .where(
                    GenerationJob.status == GenerationJobStatus.RUNNING.value,
                    or_(
                        GenerationJob.heartbeat_at < cutoff,
                        and_(
                            GenerationJob.heartbeat_at.is_(None),
                            or_(
                                GenerationJob.started_at.is_(None),
                                GenerationJob.started_at < cutoff,
                            ),
                        ),
                    ),
                )
                .order_by(GenerationJob.created_at.asc())
                .with_for_update(skip_locked=True)
            ).scalars()

            for job in jobs:
                job.error_code = WORKER_LOST
                job.error = "Worker heartbeat expired"
                job.heartbeat_at = None
                job.run_token = None
                if (job.attempts or 0) < job.max_attempts:
                    apply_job_transition(job, GenerationJobStatus.RETRY_WAIT)
                    job.progress = 0
                    job.message = "生成任务中断，正在准备重试"
                    job.next_run_at = recovered_at + STALE_RETRY_DELAY
                else:
                    apply_job_transition(
                        job,
                        GenerationJobStatus.FAILED,
                        reason=WORKER_LOST,
                    )
                    job.progress = 100
                    job.message = "行程生成失败，请稍后重试"
                    job.next_run_at = None
                    job.finished_at = recovered_at
                    _mark_trip_generation_failed(db, job.trip_id)
                recovered += 1

    return recovered


def transition_job(
    db: Session,
    job: GenerationJob,
    new_status: GenerationJobStatus | str,
    *,
    reason: str | None = None,
) -> GenerationJob:
    """Apply and persist one valid generation job status transition."""
    apply_job_transition(job, new_status, reason=reason)
    db.commit()
    db.refresh(job)
    return job


def create_job(
    db: Session,
    trip_id: UUID,
    *,
    commit: bool = True,
    idempotency_key: str | None = None,
) -> GenerationJob:
    job = GenerationJob(
        trip_id=trip_id,
        status="pending",
        progress=0,
        message="等待生成",
        idempotency_key=idempotency_key,
    )
    db.add(job)
    if commit:
        db.commit()
        db.refresh(job)
    return job


def get_job(db: Session, job_id: UUID) -> GenerationJob | None:
    return db.get(GenerationJob, job_id)


def get_job_by_idempotency_key(db: Session, key: str) -> GenerationJob | None:
    return (
        db.query(GenerationJob)
        .filter(GenerationJob.idempotency_key == key)
        .one_or_none()
    )


def update_job(db: Session, job_id: UUID, **fields) -> GenerationJob:
    job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
    if not job:
        raise ValueError("job not found")
    status = fields.pop("status", None)
    if status is not None:
        apply_job_transition(job, status)
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