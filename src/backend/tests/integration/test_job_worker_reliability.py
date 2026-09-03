"""Integration coverage for reliable generation-job execution."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import threading
import time
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.trip import GenerationJob, Trip
from app.services import generation_jobs, job_worker
from app.services.job_worker import process_pending_jobs


@pytest.fixture(scope="module", autouse=True)
def suspend_application_worker():
    """Keep daemon workers from consuming this module's committed DB fixtures."""
    original = job_worker.process_pending_jobs
    job_worker.process_pending_jobs = lambda max_jobs=1, **_kwargs: 0
    try:
        yield
    finally:
        job_worker.process_pending_jobs = original


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
        started_at: datetime | None = None,
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
                started_at=started_at,
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


def test_claim_skips_locked_row_and_claims_second_eligible_row(job_factory) -> None:
    locked_id = job_factory()
    available_id = job_factory()

    with SessionLocal() as locking_db:
        locking_db.execute(
            select(GenerationJob)
            .where(GenerationJob.id == locked_id)
            .with_for_update()
        ).scalar_one()

        with ThreadPoolExecutor(max_workers=1) as pool:
            claim = pool.submit(generation_jobs.claim_next_job).result(timeout=2)

    assert claim is not None
    assert claim.id == available_id
    assert load_job(locked_id).status == "pending"
    assert load_job(available_id).status == "running"


def test_claim_terminalizes_eligible_exhausted_jobs_before_selecting_work(
    job_factory,
) -> None:
    now = datetime.now(timezone.utc)
    pending_id = job_factory(
        status="pending",
        attempts=3,
        max_attempts=3,
        next_run_at=now,
        heartbeat_at=now,
        run_token=uuid4(),
    )
    retry_id = job_factory(
        status="retry_wait",
        attempts=2,
        max_attempts=2,
        next_run_at=now - timedelta(seconds=1),
        heartbeat_at=now,
        run_token=uuid4(),
    )
    future_retry_id = job_factory(
        status="retry_wait",
        attempts=2,
        max_attempts=2,
        next_run_at=now + timedelta(minutes=1),
    )
    pending_trip_id = load_job(pending_id).trip_id

    assert generation_jobs.claim_next_job(now=now) is None

    for job_id in (pending_id, retry_id):
        exhausted = load_job(job_id)
        assert exhausted.status == "failed"
        assert exhausted.progress == 100
        assert exhausted.attempts == exhausted.max_attempts
        assert exhausted.finished_at == now
        assert exhausted.error_code == "RETRY_EXHAUSTED"
        assert exhausted.message == "行程生成失败，请稍后重试"
        assert exhausted.run_token is None
        assert exhausted.heartbeat_at is None
        assert exhausted.next_run_at is None
        assert exhausted.status_version == 1

    assert load_job(future_retry_id).status == "retry_wait"

    with SessionLocal() as db:
        replacement = GenerationJob(
            trip_id=pending_trip_id,
            status="pending",
            progress=0,
            message="replacement",
        )
        db.add(replacement)
        db.commit()
        assert replacement.status == "pending"


@pytest.mark.parametrize(
    ("attempts", "expected_seconds"),
    [(1, 5), (2, 10), (3, 20), (4, 40), (5, 60), (20, 60)],
)
def test_retry_delay_uses_literal_bounded_backoff(
    attempts: int,
    expected_seconds: int,
) -> None:
    assert generation_jobs.retry_delay(attempts) == timedelta(
        seconds=expected_seconds
    )


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


def test_stale_recovery_handles_null_heartbeat_orphans(job_factory) -> None:
    now = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
    stale_started = now - timedelta(minutes=11)
    fresh_started = now - timedelta(minutes=9)
    never_started_id = job_factory(
        status="running",
        attempts=1,
        heartbeat_at=None,
        started_at=None,
        run_token=uuid4(),
    )
    stale_started_id = job_factory(
        status="running",
        attempts=1,
        heartbeat_at=None,
        started_at=stale_started,
        run_token=uuid4(),
    )
    fresh_started_id = job_factory(
        status="running",
        attempts=1,
        heartbeat_at=None,
        started_at=fresh_started,
        run_token=uuid4(),
    )

    assert generation_jobs.recover_stale_jobs(now=now) == 2
    assert load_job(never_started_id).status == "retry_wait"
    assert load_job(stale_started_id).status == "retry_wait"
    assert load_job(fresh_started_id).status == "running"


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


def test_heartbeat_lifecycle_renews_and_cleans_up_thread(job_factory) -> None:
    now = datetime.now(timezone.utc)
    job_id = job_factory()
    claim = generation_jobs.claim_next_job(now=now)
    assert claim is not None
    assert claim.id == job_id

    thread_name = f"generation-heartbeat-{job_id}"
    with job_worker._heartbeat_during(claim, interval=0.01):
        deadline = time.monotonic() + 1
        while load_job(job_id).heartbeat_at == now and time.monotonic() < deadline:
            time.sleep(0.01)
        assert load_job(job_id).heartbeat_at > now

    assert all(thread.name != thread_name for thread in threading.enumerate())


def test_heartbeat_cleanup_does_not_wait_forever_for_hung_renewal(
    monkeypatch,
) -> None:
    renewal_started = threading.Event()
    release_renewal = threading.Event()
    claim = generation_jobs.ClaimedGenerationJob(
        id=uuid4(),
        trip_id=uuid4(),
        run_token=uuid4(),
        attempts=1,
        max_attempts=3,
    )

    def hanging_renewal(_job_id, _run_token) -> bool:
        renewal_started.set()
        release_renewal.wait(timeout=5)
        return True

    monkeypatch.setattr(job_worker, "renew_heartbeat", hanging_renewal)

    started = time.monotonic()
    with job_worker._heartbeat_during(
        claim,
        interval=0.001,
        join_timeout=0.05,
    ):
        assert renewal_started.wait(timeout=1)
    elapsed = time.monotonic() - started
    release_renewal.set()

    assert elapsed < 0.5
    deadline = time.monotonic() + 1
    thread_name = f"generation-heartbeat-{claim.id}"
    while (
        any(thread.name == thread_name for thread in threading.enumerate())
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert all(thread.name != thread_name for thread in threading.enumerate())


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
