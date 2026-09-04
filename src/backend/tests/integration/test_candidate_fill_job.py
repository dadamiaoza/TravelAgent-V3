"""P1 candidate fill + verify-does-not-block-success on the generation job path."""
from datetime import date
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.trip import GenerationJob, Trip
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


_FILLED_DRAFT = {
    "city": "杭州",
    "days": [
        {
            "day_index": 1,
            "theme": "攻略勾选",
            "route_type": "city",
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


def _create_payload(**extra) -> dict:
    body = {
        "destination": extra.pop("destination", f"job-api-{uuid4()}"),
        "city": "杭州",
        "start_date": "2031-03-01",
        "end_date": "2031-03-02",
        "people_count": 2,
    }
    body.update(extra)
    return body


def _load_job(job_id: str | UUID) -> GenerationJob:
    with SessionLocal() as db:
        return db.get(GenerationJob, job_id)


def test_create_trip_stores_selected_entities_on_job(api_client: TestClient) -> None:
    entities = [
        {"poi_name": "西湖", "day_index": 1, "seq": 1},
        {"poi_name": "灵隐寺", "day_index": 2, "seq": 1},
    ]
    response = api_client.post(
        "/api/v1/trips",
        json=_create_payload(selected_entities=entities),
    )

    assert response.status_code == 201, response.text
    job = _load_job(response.json()["job_id"])
    stored = (job.payload or {}).get("selected_entities")
    assert stored is not None
    assert [item["poi_name"] for item in stored] == ["西湖", "灵隐寺"]


def test_worker_fill_skips_planner_when_candidates_present(
    api_client: TestClient,
) -> None:
    entities = [
        {"poi_name": "西湖", "day_index": 1, "seq": 1},
        {"poi_name": "雷峰塔", "day_index": 1, "seq": 2},
    ]
    created = api_client.post(
        "/api/v1/trips",
        json=_create_payload(selected_entities=entities),
    ).json()

    with (
        patch(
            "app.services.itinerary.create_itinerary_gen",
            side_effect=AssertionError("planner must not run when candidates exist"),
        ),
        patch(
            "app.services.job_worker.route_itinerary_draft",
            side_effect=lambda draft: draft,
        ) as route,
        patch(
            "app.services.job_worker.verify_itinerary_draft",
            return_value=type(
                "Outcome",
                (),
                {"warnings": [], "summary": "时效核对完成"},
            )(),
        ),
    ):
        assert process_pending_jobs() == 1

    route.assert_called_once()
    job = _load_job(created["job_id"])
    assert job.status == "succeeded"
    keys = [stage["key"] for stage in (job.stages or [])]
    assert keys[0] == "prepare"
    assert "fill" in keys
    assert "route" in keys
    assert "verify" in keys
    assert keys[-1] == "done"
    with SessionLocal() as db:
        trip = db.get(Trip, UUID(created["id"]))
        names = [item.poi_name for day in trip.days for item in day.items]
    assert names == ["西湖", "雷峰塔"]


def test_worker_verify_error_does_not_block_succeeded(api_client: TestClient) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()

    with (
        patch(
            "app.services.job_worker.fill_itinerary_draft",
            return_value=_FILLED_DRAFT,
        ),
        patch(
            "app.services.job_worker.route_itinerary_draft",
            side_effect=lambda draft: draft,
        ),
        patch(
            "app.services.job_worker.verify_itinerary_draft",
            side_effect=RuntimeError("verify exploded"),
        ),
    ):
        assert process_pending_jobs() == 1

    job = _load_job(created["job_id"])
    assert job.status == "succeeded"
    keys = [stage["key"] for stage in (job.stages or [])]
    assert "warning" in keys
    assert job.error_code is None
    with SessionLocal() as db:
        trip = db.get(Trip, UUID(created["id"]))
        assert trip.status == "generated"
        assert [item.poi_name for day in trip.days for item in day.items] == ["西湖"]
