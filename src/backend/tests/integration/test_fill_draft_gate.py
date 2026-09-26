"""A bad fill draft must not quietly succeed into route."""
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.trip import GenerationJob, Trip
from app.schemas.fill_draft import FILL_DRAFT_ERROR_MESSAGE
from app.services import job_worker
from app.services.job_worker import process_pending_jobs


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


def test_invalid_fill_draft_records_stage_error_and_skips_route(api_client: TestClient) -> None:
    """Missing coordinate pair plus duplicate seq must not finalize as success."""
    bad_draft = {
        "city": "杭州",
        "days": [
            {
                "day_index": "1",
                "theme": "坏草稿",
                "items": [
                    {
                        "seq": 1,
                        "poi_name": "西湖",
                        "lat": None,
                        "lng": 120.15,
                    },
                    {
                        "seq": 1,
                        "poi_name": "雷峰塔",
                        "lat": 30.23,
                        "lng": 120.14,
                    },
                ],
            }
        ],
    }
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()

    with (
        patch(
            "app.services.job_worker.fill_itinerary_draft",
            return_value=bad_draft,
        ),
        patch(
            "app.services.job_worker.route_itinerary_draft",
            side_effect=AssertionError("route must not run on an invalid fill draft"),
        ) as route,
    ):
        assert process_pending_jobs() == 1

    route.assert_not_called()
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        trip = db.get(Trip, UUID(created["id"]))
        assert job is not None and trip is not None
        assert job.status != "succeeded"
        assert job.status == "retry_wait"
        assert job.error_code == "MALFORMED_MODEL_OUTPUT"
        assert job.message == FILL_DRAFT_ERROR_MESSAGE
        assert job.error_code
        keys = [stage["key"] for stage in (job.stages or [])]
        assert "error" in keys
        assert "done" not in keys
        assert "route" not in keys
        error_stage = next(stage for stage in job.stages if stage["key"] == "error")
        assert error_stage["message"] == FILL_DRAFT_ERROR_MESSAGE
        assert trip.status != "generated"
        assert [item.poi_name for day in trip.days for item in day.items] == []
