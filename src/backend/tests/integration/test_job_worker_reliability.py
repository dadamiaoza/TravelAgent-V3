"""Integration coverage for reliable generation-job execution."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.trip import GenerationJob, Trip
from app.services import generation_jobs
from app.services.job_worker import process_pending_jobs


@pytest.fixture
def job_factory():
    trip_ids: list[UUID] = []

    def create(
        *,
        status: str = "pending",
        attempts: int = 0,
        max_attempts: int = 3,
        next_run_at: datetime | None = None,
        heartbeat_at: datetime | None = None,
        run_token: UUID | None = None,
    ) -> UUID:
        with SessionLocal() as db:
            trip = Trip(
                destination=f"test-{uuid4()}",
                start_date=date(2030, 1, 1),
                end_date=date(2030, 1, 2),
            )
            db.add(trip)
            db.flush()
            job = GenerationJob(
                trip_id=trip.id,
                status=status,
                attempts=attempts,
                max_attempts=max_attempts,
                next_run_at=next_run_at,
                heartbeat_at=heartbeat_at,
                run_token=run_token,
                progress=0,
                message="test",
            )
            db.add(job)
            db.commit()
            trip_ids.append(trip.id)
            return job.id

    yield create

    with SessionLocal() as db:
        db.query(Trip).filter(Trip.id.in_(trip_ids)).delete(
            synchronize_session=False
        )
        db.commit()


def load_job(job_id: UUID) -> GenerationJob:
    with SessionLocal() as db:
        return db.get(GenerationJob, job_id)


def test_claim_selects_pending_not_future_retry_and_sets_lease(job_factory) -> None:
    now = datetime.now(timezone.utc)
    future_retry_id = job_factory(
        status="retry_wait",
        next_run_at=now + timedelta(minutes=1),
    )
    pending_id = job_factory()

    claim = generation_jobs.claim_next_job(now=now)

    assert claim is not None
    assert claim.id == pending_id
    claimed = load_job(pending_id)
    future_retry = load_job(future_retry_id)
    assert claimed.status == "running"
    assert claimed.attempts == 1
    assert claimed.run_token == claim.run_token
    assert claimed.heartbeat_at == now
    assert claimed.next_run_at is None
    assert claimed.progress == 10
    assert claimed.status_version == 1
    assert future_retry.status == "retry_wait"


def test_claim_skips_a_locked_eligible_row(job_factory) -> None:
    job_id = job_factory()

    with SessionLocal() as locking_db:
        locking_db.execute(
            select(GenerationJob)
            .where(GenerationJob.id == job_id)
            .with_for_update()
        ).scalar_one()

        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(generation_jobs.claim_next_job).result(timeout=2)

    assert result is None
    assert load_job(job_id).status == "pending"


def test_retryable_failure_waits_then_exhausts_total_claims(job_factory) -> None:
    job_id = job_factory(max_attempts=2)
    before = datetime.now(timezone.utc)

    def malformed_output(_db, _trip) -> None:
        raise ValueError("raw malformed model response")

    assert process_pending_jobs(regenerate=malformed_output) == 1

    first_failure = load_job(job_id)
    assert first_failure.status == "retry_wait"
    assert first_failure.attempts == 1
    assert before + timedelta(seconds=5) <= first_failure.next_run_at
    assert first_failure.next_run_at <= datetime.now(timezone.utc) + timedelta(seconds=5)
    assert first_failure.error_code == "MALFORMED_MODEL_OUTPUT"
    assert "raw malformed model response" in first_failure.error

    with SessionLocal() as db:
        job = db.get(GenerationJob, job_id)
        job.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()

    assert process_pending_jobs(regenerate=malformed_output) == 1

    exhausted = load_job(job_id)
    assert exhausted.status == "failed"
    assert exhausted.attempts == 2
    assert exhausted.progress == 100
    assert exhausted.finished_at is not None
    assert exhausted.error_code == "MALFORMED_MODEL_OUTPUT"
    assert exhausted.message == "行程生成失败，请稍后重试"


def test_stale_recovery_retries_remaining_and_fails_exhausted(job_factory) -> None:
    now = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
    stale = now - timedelta(minutes=11)
    retry_id = job_factory(
        status="running",
        attempts=1,
        max_attempts=3,
        heartbeat_at=stale,
        run_token=uuid4(),
    )
    failed_id = job_factory(
        status="running",
        attempts=3,
        max_attempts=3,
        heartbeat_at=stale,
        run_token=uuid4(),
    )

    assert generation_jobs.recover_stale_jobs(now=now) == 2

    retried = load_job(retry_id)
    assert retried.status == "retry_wait"
    assert retried.next_run_at == now + timedelta(seconds=5)
    assert retried.error_code == "WORKER_LOST"
    assert retried.run_token is None
    assert retried.status_version == 1

    failed = load_job(failed_id)
    assert failed.status == "failed"
    assert failed.progress == 100
    assert failed.finished_at == now
    assert failed.error_code == "WORKER_LOST"
    assert failed.run_token is None
    assert failed.status_version == 1


def test_lifecycle_updates_reject_stale_run_token(job_factory) -> None:
    active_token = uuid4()
    job_id = job_factory(
        status="running",
        attempts=1,
        heartbeat_at=datetime.now(timezone.utc),
        run_token=active_token,
    )

    assert generation_jobs.mark_job_succeeded(job_id, uuid4()) is False
    still_running = load_job(job_id)
    assert still_running.status == "running"
    assert still_running.progress == 0

    assert generation_jobs.mark_job_succeeded(job_id, active_token) is True
    succeeded = load_job(job_id)
    assert succeeded.status == "succeeded"
    assert succeeded.progress == 100
    assert succeeded.status_version == 1


def test_heartbeat_updates_only_for_active_token(job_factory) -> None:
    active_token = uuid4()
    original = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
    renewed = original + timedelta(seconds=30)
    job_id = job_factory(
        status="running",
        attempts=1,
        heartbeat_at=original,
        run_token=active_token,
    )

    assert generation_jobs.renew_heartbeat(job_id, uuid4(), now=renewed) is False
    assert load_job(job_id).heartbeat_at == original

    assert generation_jobs.renew_heartbeat(job_id, active_token, now=renewed) is True
    heartbeat = load_job(job_id)
    assert heartbeat.heartbeat_at == renewed
    assert heartbeat.status == "running"
    assert heartbeat.status_version == 0


def test_programming_error_is_permanent(job_factory) -> None:
    job_id = job_factory(max_attempts=3)

    def programming_error(_db, _trip) -> None:
        raise RuntimeError("private implementation detail")

    assert process_pending_jobs(regenerate=programming_error) == 1

    failed = load_job(job_id)
    assert failed.status == "failed"
    assert failed.attempts == 1
    assert failed.error_code == "INTERNAL_ERROR"
    assert failed.message == "行程生成失败，请检查输入后重试"
    assert "private implementation detail" in failed.error


def test_invalid_input_is_permanent(job_factory) -> None:
    job_id = job_factory(max_attempts=3)

    class GeneratorInput(BaseModel):
        people_count: int

    def invalid_input(_db, _trip) -> None:
        GeneratorInput(people_count="not-an-integer")

    assert process_pending_jobs(regenerate=invalid_input) == 1

    failed = load_job(job_id)
    assert failed.status == "failed"
    assert failed.attempts == 1
    assert failed.error_code == "INVALID_INPUT"
