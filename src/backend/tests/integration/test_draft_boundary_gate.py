"""Illegal drafts fail in the worker before persist, as malformed output."""
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.trip import GenerationJob, Trip
from app.schemas.persist_draft import PERSIST_DRAFT_ERROR_MESSAGE
from app.schemas.route_draft import ROUTE_DRAFT_ERROR_MESSAGE
from app.services import job_worker
from app.services.fact_verify import VerifyOutcome
from app.services.job_worker import GenerationInput, process_pending_jobs


@pytest.fixture(scope="module", autouse=True)
def suspend_application_worker():
    original = job_worker.process_pending_jobs
    job_worker.process_pending_jobs = lambda max_jobs=1, **_kwargs: 0
    try:
        yield
    finally:
        job_worker.process_pending_jobs = original


@pytest.fixture
def api_client():
    created_trip_ids: list[str] = []
    client = TestClient(app)
    original_post = client.post

    def tracking_post(url, *args, **kwargs):
        response = original_post(url, *args, **kwargs)
        if url == "/api/v1/trips" and response.status_code == 201:
            created_trip_ids.append(response.json()["id"])
        return response

    client.post = tracking_post  # type: ignore[method-assign]
    try:
        yield client
    finally:
        with SessionLocal() as db:
            if created_trip_ids:
                db.query(Trip).filter(Trip.id.in_(created_trip_ids)).delete(
                    synchronize_session=False
                )
                db.commit()


def _create_payload() -> dict:
    return {
        "destination": f"job-api-{uuid4()}",
        "city": "杭州",
        "start_date": "2031-03-01",
        "end_date": "2031-03-02",
        "people_count": 2,
    }


_GOOD = {
    "city": "杭州",
    "days": [
        {
            "day_index": 1,
            "route_type": "city",
            "order_source": "fill",
            "items": [
                {
                    "seq": 1,
                    "poi_name": "西湖",
                    "duration_h": 2,
                    "travel_minutes_from_prev": 0,
                }
            ],
        }
    ],
}


def test_string_day_index_from_route_does_not_reach_persist(api_client: TestClient) -> None:
    bad = {
        "days": [
            {
                "day_index": "1",
                "items": [{"seq": 1, "poi_name": "西湖", "travel_minutes_from_prev": 0}],
            }
        ]
    }
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()

    with (
        patch("app.services.job_worker.fill_itinerary_draft", return_value=_GOOD),
        patch("app.services.job_worker.route_itinerary_draft", return_value=bad),
        patch(
            "app.services.job_worker.verify_itinerary_draft",
            side_effect=AssertionError("verify must not run"),
        ) as verify,
        patch(
            "app.services.generation_jobs.persist_itinerary",
            side_effect=AssertionError("persist must not run"),
        ) as persist,
    ):
        assert process_pending_jobs() == 1

    verify.assert_not_called()
    persist.assert_not_called()
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        trip = db.get(Trip, UUID(created["id"]))
        assert job is not None and trip is not None
        assert job.status == "retry_wait"
        assert job.error_code == "MALFORMED_MODEL_OUTPUT"
        assert job.message == ROUTE_DRAFT_ERROR_MESSAGE
        assert trip.status != "generated"
        error_stage = next(stage for stage in job.stages if stage["key"] == "error")
        assert error_stage["message"] == ROUTE_DRAFT_ERROR_MESSAGE
        assert error_stage["progress"] == 80
        assert "done" not in [stage["key"] for stage in job.stages]


def test_bad_leg_after_verify_fails_before_persist(api_client: TestClient) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()

    def corrupt(draft, _outcome):
        draft["days"][0]["items"][0]["travel_minutes_from_prev"] = "15"
        return draft

    with (
        patch("app.services.job_worker.fill_itinerary_draft", return_value=_GOOD),
        patch("app.services.job_worker.route_itinerary_draft", side_effect=lambda draft: draft),
        patch(
            "app.services.job_worker.verify_itinerary_draft",
            return_value=VerifyOutcome(),
        ) as verify,
        patch("app.services.job_worker.apply_verify_to_draft", side_effect=corrupt),
        patch(
            "app.services.generation_jobs.persist_itinerary",
            side_effect=AssertionError("persist must not run"),
        ) as persist,
    ):
        assert process_pending_jobs() == 1

    verify.assert_called_once()
    persist.assert_not_called()
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        trip = db.get(Trip, UUID(created["id"]))
        assert job is not None and trip is not None
        assert job.status == "retry_wait"
        assert job.error_code == "MALFORMED_MODEL_OUTPUT"
        assert job.message == PERSIST_DRAFT_ERROR_MESSAGE
        assert trip.status != "generated"
        error_stage = next(stage for stage in job.stages if stage["key"] == "error")
        assert error_stage["progress"] == 96
        assert error_stage["message"] == PERSIST_DRAFT_ERROR_MESSAGE


def test_custom_regenerate_string_day_index_fails_before_persist(api_client: TestClient) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()

    def regenerate(_generation_input: GenerationInput) -> dict:
        return {
            "days": [
                {
                    "day_index": "1",
                    "items": [{"seq": 1, "poi_name": "西湖"}],
                }
            ]
        }

    with patch(
        "app.services.generation_jobs.persist_itinerary",
        side_effect=AssertionError("persist must not run"),
    ) as persist:
        assert process_pending_jobs(regenerate=regenerate) == 1

    persist.assert_not_called()
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        trip = db.get(Trip, UUID(created["id"]))
        assert job is not None and trip is not None
        assert job.status == "retry_wait"
        assert job.error_code == "MALFORMED_MODEL_OUTPUT"
        assert job.message == PERSIST_DRAFT_ERROR_MESSAGE
        assert trip.status != "generated"
