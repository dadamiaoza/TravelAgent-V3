"""Route and verify degradations survive on the job and the library list."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.trip import GenerationJob, Trip
from app.services import job_worker
from app.services.fact_verify import VerifyOutcome
from app.services.itinerary_persistence import persist_itinerary
from app.services.job_worker import process_pending_jobs
from app.services.route_degradation import warning_stage_messages


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


BOUNDARY = (
    "第1天终点「西湖」与第2天起点「雷峰塔」相距约 300 公里，"
    "跨天衔接偏远。本次不会自动把景点改到另一天。"
)

_FILLED = {
    "city": "杭州",
    "days": [
        {"day_index": 1, "items": [{"seq": 1, "poi_name": "西湖", "duration_h": 2}]},
        {"day_index": 2, "items": [{"seq": 1, "poi_name": "雷峰塔", "duration_h": 1}]},
    ],
}

_DEGRADED = {
    "days": [
        {
            "day_index": 1,
            "order_source": "nearest_neighbor",
            "order_degrade_reason": "travel_time",
            "items": [{"seq": 1, "poi_name": "西湖", "duration_h": 2, "travel_minutes_from_prev": 0}],
        },
        {
            "day_index": 2,
            "order_source": "fill",
            "day_boundary_warning": BOUNDARY,
            "items": [{"seq": 1, "poi_name": "雷峰塔", "duration_h": 1, "travel_minutes_from_prev": 0}],
        },
    ]
}

_CLEAN = {
    "days": [
        {
            "day_index": 1,
            "order_source": "fill",
            "items": [{"seq": 1, "poi_name": "西湖", "duration_h": 2, "travel_minutes_from_prev": 0}],
        }
    ]
}


def _create_payload() -> dict:
    from uuid import uuid4

    return {
        "destination": f"job-api-{uuid4()}",
        "city": "杭州",
        "start_date": "2031-03-01",
        "end_date": "2031-03-02",
        "people_count": 2,
    }


def _listed(client: TestClient, trip_id: str) -> dict:
    body = client.get("/api/v1/trips").json()
    return next(row for row in body if row["id"] == trip_id)


def test_succeeded_job_exposes_route_and_verify_warnings(api_client: TestClient) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()
    expected = [
        "第1天已按最近邻重排（路时明显绕路）",
        BOUNDARY,
        "时效核对未完成，行程已按路线生成",
    ]

    with (
        patch("app.services.job_worker.fill_itinerary_draft", return_value=_FILLED),
        patch("app.services.job_worker.route_itinerary_draft", return_value=_DEGRADED),
        patch("app.services.job_worker.verify_itinerary_draft", side_effect=RuntimeError("verify exploded")),
    ):
        assert process_pending_jobs() == 1

    job = api_client.get(f"/api/v1/jobs/{created['job_id']}").json()
    progress = api_client.get(f"/api/v1/trips/{created['id']}/progress").json()
    assert job["status"] == "succeeded"
    assert warning_stage_messages(job["stages"]) == expected
    assert warning_stage_messages(progress["stages"]) == expected
    assert _listed(api_client, created["id"])["degradations"] == expected

    with SessionLocal() as db:
        trip = db.get(Trip, UUID(created["id"]))
        assert trip is not None
        assert trip.status == "generated"


def test_clean_generation_leaves_degradations_empty(api_client: TestClient) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()

    with (
        patch("app.services.job_worker.fill_itinerary_draft", return_value=_FILLED),
        patch("app.services.job_worker.route_itinerary_draft", return_value=_CLEAN),
        patch("app.services.job_worker.verify_itinerary_draft", return_value=VerifyOutcome()),
    ):
        assert process_pending_jobs() == 1

    job = api_client.get(f"/api/v1/jobs/{created['job_id']}").json()
    assert job["status"] == "succeeded"
    assert warning_stage_messages(job["stages"]) == []
    assert _listed(api_client, created["id"])["degradations"] == []


def test_retry_after_persist_failure_replaces_stale_route_warnings(api_client: TestClient) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()
    calls = {"route": 0, "persist": 0}

    def route(_draft):
        calls["route"] += 1
        return _DEGRADED if calls["route"] == 1 else _CLEAN

    def persist(*args, **kwargs):
        calls["persist"] += 1
        if calls["persist"] == 1:
            raise TimeoutError("persist once")
        return persist_itinerary(*args, **kwargs)

    with (
        patch("app.services.job_worker.fill_itinerary_draft", return_value=_FILLED),
        patch("app.services.job_worker.route_itinerary_draft", side_effect=route),
        patch("app.services.job_worker.verify_itinerary_draft", return_value=VerifyOutcome()),
        patch("app.services.generation_jobs.persist_itinerary", side_effect=persist),
    ):
        assert process_pending_jobs() == 1
        with SessionLocal() as db:
            waiting = db.get(GenerationJob, UUID(created["job_id"]))
            assert waiting is not None
            assert waiting.status == "retry_wait"
            assert warning_stage_messages(waiting.stages) == [
                "第1天已按最近邻重排（路时明显绕路）",
                BOUNDARY,
            ]
            waiting.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.commit()
        assert process_pending_jobs() == 1

    job = api_client.get(f"/api/v1/jobs/{created['job_id']}").json()
    assert job["status"] == "succeeded"
    assert warning_stage_messages(job["stages"]) == []
    assert _listed(api_client, created["id"])["degradations"] == []
    assert calls["route"] == 2
