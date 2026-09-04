"""Integration coverage for atomic generation creation and finalization."""

from contextlib import contextmanager
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.api.v1 import trips as trips_api
from app.db.session import SessionLocal
from app.models.trip import GenerationJob, ItineraryDay, ItineraryItem, Trip
from app.schemas.trip import TripCreate
from app.services import generation_jobs, itinerary_persistence, job_worker
from app.services.job_worker import process_pending_jobs


@pytest.fixture(scope="module", autouse=True)
def suspend_application_worker():
    original = job_worker.process_pending_jobs
    job_worker.process_pending_jobs = lambda max_jobs=1, **_kwargs: 0
    try:
        yield
    finally:
        job_worker.process_pending_jobs = original


GENERATED_DRAFT = {
    "days": [
        {
            "day_index": 1,
            "route_type": "city",
            "items": [
                {
                    "seq": 1,
                    "poi_name": "新景点",
                    "duration_h": 2,
                    "travel_minutes_from_prev": 0,
                }
            ],
        }
    ]
}


@pytest.fixture
def generation_record_factory():
    trip_ids: list[UUID] = []

    def create(
        *,
        job_status: str = "running",
        attempts: int = 1,
        max_attempts: int = 3,
        run_token: UUID | None = None,
    ) -> tuple[UUID, UUID, UUID | None]:
        with SessionLocal() as db:
            trip = Trip(
                destination=f"atomic-{uuid4()}",
                city="杭州",
                start_date=date(2030, 1, 1),
                end_date=date(2030, 1, 2),
                people_count=2,
                must_visit=["西湖"],
                status="generating",
            )
            db.add(trip)
            db.flush()
            day = ItineraryDay(
                trip_id=trip.id,
                day_index=1,
                date=trip.start_date,
                route_type="city",
            )
            db.add(day)
            db.flush()
            db.add(
                ItineraryItem(
                    day_id=day.id,
                    seq=1,
                    poi_name="旧景点",
                )
            )
            token = run_token
            if job_status == "running" and token is None:
                token = uuid4()
            job = GenerationJob(
                trip_id=trip.id,
                status=job_status,
                attempts=attempts,
                max_attempts=max_attempts,
                run_token=token,
                heartbeat_at=datetime.now(timezone.utc),
                progress=30,
                message="AI 正在生成行程...",
                error_code="OLD_ERROR",
                error="old detail",
            )
            db.add(job)
            db.commit()
            trip_ids.append(trip.id)
            return trip.id, job.id, token

    yield create

    with SessionLocal() as db:
        db.query(Trip).filter(Trip.id.in_(trip_ids)).delete(
            synchronize_session=False
        )
        db.commit()


def _claim_for(job_id: UUID, trip_id: UUID, run_token: UUID):
    return generation_jobs.ClaimedGenerationJob(
        id=job_id,
        trip_id=trip_id,
        run_token=run_token,
        attempts=1,
        max_attempts=3,
    )


def _load_result(trip_id: UUID, job_id: UUID):
    with SessionLocal() as db:
        trip = db.get(Trip, trip_id)
        job = db.get(GenerationJob, job_id)
        poi_names = [
            item.poi_name
            for day in trip.days
            for item in day.items
        ]
        return trip.status, poi_names, {
            "status": job.status,
            "progress": job.progress,
            "message": job.message,
            "error": job.error,
            "error_code": job.error_code,
            "next_run_at": job.next_run_at,
            "heartbeat_at": job.heartbeat_at,
            "run_token": job.run_token,
            "finished_at": job.finished_at,
            "status_version": job.status_version,
        }


def test_create_trip_rolls_back_when_job_creation_fails(monkeypatch) -> None:
    destination = f"rollback-{uuid4()}"
    body = TripCreate(
        destination=destination,
        city="杭州",
        start_date=date(2030, 1, 1),
        end_date=date(2030, 1, 2),
    )

    def fail_job_insert(_db, _trip_id, **_kwargs):
        raise RuntimeError("injected job insert failure")

    monkeypatch.setattr(trips_api, "create_job", fail_job_insert)

    with SessionLocal() as db:
        with pytest.raises(RuntimeError, match="injected job insert failure"):
            trips_api.create_trip(body, db)

    with SessionLocal() as db:
        assert db.query(Trip).filter(Trip.destination == destination).first() is None


def test_success_finalization_commits_itinerary_trip_and_job_together(
    generation_record_factory,
) -> None:
    trip_id, job_id, token = generation_record_factory()
    finished_at = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)

    assert generation_jobs.finalize_job_success(
        _claim_for(job_id, trip_id, token),
        GENERATED_DRAFT,
        now=finished_at,
    )

    trip_status, poi_names, job = _load_result(trip_id, job_id)
    assert trip_status == "generated"
    assert poi_names == ["新景点"]
    assert job == {
        "status": "succeeded",
        "progress": 100,
        "message": "行程生成完成",
        "error": None,
        "error_code": None,
        "next_run_at": None,
        "heartbeat_at": None,
        "run_token": None,
        "finished_at": finished_at,
        "status_version": 1,
    }


def test_stale_token_cannot_mutate_itinerary_or_trip(
    generation_record_factory,
) -> None:
    trip_id, job_id, _token = generation_record_factory()
    stale_claim = _claim_for(job_id, trip_id, uuid4())

    assert generation_jobs.finalize_job_success(
        stale_claim,
        GENERATED_DRAFT,
    ) is False

    trip_status, poi_names, job = _load_result(trip_id, job_id)
    assert trip_status == "generating"
    assert poi_names == ["旧景点"]
    assert job["status"] == "running"
    assert job["progress"] == 30


@contextmanager
def _hide_trips():
    original_get = Session.get

    def get(self, entity, ident, **kwargs):
        if entity is Trip:
            return None
        return original_get(self, entity, ident, **kwargs)

    Session.get = get
    try:
        yield
    finally:
        Session.get = original_get


def test_missing_trip_fails_fenced_job_without_persisting_itinerary(
    generation_record_factory,
) -> None:
    trip_id, job_id, token = generation_record_factory()
    finished_at = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)

    with _hide_trips():
        result = generation_jobs.finalize_job_success(
            _claim_for(job_id, trip_id, token),
            GENERATED_DRAFT,
            now=finished_at,
        )

    assert result is False

    trip_status, poi_names, job = _load_result(trip_id, job_id)
    assert trip_status == "generating"
    assert poi_names == ["旧景点"]
    assert job["status"] == "failed"
    assert job["error_code"] == "TRIP_NOT_FOUND"
    assert job["message"] == "关联的行程不存在"
    assert job["error"] == "Trip missing at finalization"
    assert "Traceback" not in (job["error"] or "")
    assert job["progress"] == 100
    assert job["run_token"] is None
    assert job["heartbeat_at"] is None
    assert job["next_run_at"] is None
    assert job["finished_at"] == finished_at
    assert job["status_version"] == 1


def test_stale_token_cannot_fail_taken_over_job_when_trip_is_missing(
    generation_record_factory,
) -> None:
    active_token = uuid4()
    trip_id, job_id, _token = generation_record_factory(run_token=active_token)

    with _hide_trips():
        result = generation_jobs.finalize_job_success(
            _claim_for(job_id, trip_id, uuid4()),
            GENERATED_DRAFT,
        )

    assert result is False

    trip_status, poi_names, job = _load_result(trip_id, job_id)
    assert trip_status == "generating"
    assert poi_names == ["旧景点"]
    assert job["status"] == "running"
    assert job["run_token"] == active_token
    assert job["progress"] == 30
    assert job["error_code"] == "OLD_ERROR"


def test_finalization_failure_rolls_back_itinerary_and_terminal_status(
    monkeypatch,
    generation_record_factory,
) -> None:
    trip_id, job_id, token = generation_record_factory()
    real_persist = itinerary_persistence.persist_itinerary

    def fail_after_persistence(*args, **kwargs):
        real_persist(*args, **kwargs)
        raise RuntimeError("injected finalization failure")

    monkeypatch.setattr(
        generation_jobs,
        "persist_itinerary",
        fail_after_persistence,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="injected finalization failure"):
        generation_jobs.finalize_job_success(
            _claim_for(job_id, trip_id, token),
            GENERATED_DRAFT,
        )

    trip_status, poi_names, job = _load_result(trip_id, job_id)
    assert trip_status == "generating"
    assert poi_names == ["旧景点"]
    assert job["status"] == "running"
    assert job["progress"] == 30
    assert job["run_token"] == token


def test_generation_runs_after_input_session_closes(
    monkeypatch,
    generation_record_factory,
) -> None:
    trip_id, job_id, _token = generation_record_factory(
        job_status="pending",
        attempts=0,
        run_token=None,
    )
    real_session_factory = SessionLocal
    read_session_closed = False
    observed_inputs = []

    class TrackingReadSession:
        def __enter__(self):
            self.session = real_session_factory()
            return self.session

        def __exit__(self, exc_type, exc, traceback):
            nonlocal read_session_closed
            self.session.close()
            read_session_closed = True

    monkeypatch.setattr(job_worker, "SessionLocal", TrackingReadSession)

    def generate(generation_input):
        assert read_session_closed is True
        assert generation_input.trip_id == trip_id
        assert generation_input.destination.startswith("atomic-")
        assert generation_input.must_visit == ("西湖",)
        with pytest.raises(FrozenInstanceError):
            generation_input.destination = "mutated"
        observed_inputs.append(generation_input)
        return GENERATED_DRAFT

    assert process_pending_jobs(regenerate=generate) == 1
    assert len(observed_inputs) == 1

    trip_status, poi_names, job = _load_result(trip_id, job_id)
    assert trip_status == "generated"
    assert poi_names == ["新景点"]
    assert job["status"] == "succeeded"


def test_permanent_failure_sets_trip_generation_failed(
    generation_record_factory,
) -> None:
    trip_id, job_id, _token = generation_record_factory(
        job_status="pending",
        attempts=0,
        run_token=None,
    )

    def programming_error(_generation_input):
        raise RuntimeError("private implementation detail")

    assert process_pending_jobs(regenerate=programming_error) == 1

    trip_status, _poi_names, job = _load_result(trip_id, job_id)
    assert trip_status == "generation_failed"
    assert job["status"] == "failed"
    assert job["error_code"] == "INTERNAL_ERROR"


def test_retry_keeps_trip_generating(generation_record_factory) -> None:
    trip_id, job_id, _token = generation_record_factory(
        job_status="pending",
        attempts=0,
        run_token=None,
    )

    def malformed_output(_generation_input):
        raise ValueError("raw malformed model response")

    assert process_pending_jobs(regenerate=malformed_output) == 1

    trip_status, _poi_names, job = _load_result(trip_id, job_id)
    assert trip_status == "generating"
    assert job["status"] == "retry_wait"


def test_stale_exhaustion_sets_trip_generation_failed(
    generation_record_factory,
) -> None:
    trip_id, job_id, token = generation_record_factory(
        job_status="running",
        attempts=3,
        max_attempts=3,
    )
    now = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
    with SessionLocal() as db:
        job = db.get(GenerationJob, job_id)
        job.heartbeat_at = now - timedelta(minutes=11)
        job.run_token = token
        db.commit()

    recovered = generation_jobs.recover_stale_jobs(now=now)
    assert recovered >= 1

    trip_status, poi_names, job = _load_result(trip_id, job_id)
    assert trip_status == "generation_failed"
    assert poi_names == ["旧景点"]
    assert job["status"] == "failed"
    assert job["error_code"] == "WORKER_LOST"


def test_preclaim_exhaustion_sets_trip_generation_failed(
    generation_record_factory,
) -> None:
    trip_id, job_id, _token = generation_record_factory(
        job_status="pending",
        attempts=3,
        max_attempts=3,
        run_token=None,
    )
    now = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)

    assert generation_jobs.claim_next_job(now=now) is None

    trip_status, _poi_names, job = _load_result(trip_id, job_id)
    assert trip_status == "generation_failed"
    assert job["status"] == "failed"
    assert job["error_code"] == "RETRY_EXHAUSTED"
