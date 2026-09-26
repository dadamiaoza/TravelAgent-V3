"""Retries reuse a gated fill draft and skip another itinerary fill."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.trip import GenerationJob, Trip
from app.schemas.fill_draft import FILL_DRAFT_ERROR_MESSAGE
from app.services import job_worker
from app.services.fact_verify import VerifyOutcome
from app.services.generation_jobs import FILL_DRAFT_PAYLOAD_KEY
from app.services.job_worker import RESUME_ROUTE_MESSAGE, ROUTE_STAGE_MESSAGE, process_pending_jobs


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


GOOD_DRAFT = {
    "city": "杭州",
    "days": [
        {
            "day_index": 1,
            "theme": "西湖",
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

BAD_DRAFT = {
    "city": "杭州",
    "days": [
        {
            "day_index": "1",
            "theme": "坏草稿",
            "items": [
                {"seq": 1, "poi_name": "西湖", "lat": None, "lng": 120.15},
                {"seq": 1, "poi_name": "雷峰塔", "lat": 30.23, "lng": 120.14},
            ],
        }
    ],
}


def _create_payload(**extra) -> dict:
    body = {
        "destination": f"job-api-{uuid4()}",
        "city": "杭州",
        "start_date": "2031-03-01",
        "end_date": "2031-03-02",
        "people_count": 2,
        "selected_entities": [{"poi_name": "西湖", "day_index": 1, "seq": 1}],
    }
    body.update(extra)
    return body


def _open_retry(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(GenerationJob, UUID(job_id))
        assert job is not None
        job.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()


def _stage_messages(job: GenerationJob) -> list[str]:
    return [stage["message"] for stage in (job.stages or [])]


def _poi_names(draft: dict) -> list[str]:
    return [
        item["poi_name"]
        for day in draft.get("days") or []
        for item in day.get("items") or []
    ]


@pytest.fixture
def pipeline():
    """Patch fill, route, and verify. Route failures are injected by the test."""
    state = {"fill": 0, "routed": []}

    def fill(**_kwargs):
        state["fill"] += 1
        producer = state.get("fill_producer")
        if producer is not None:
            return producer(state["fill"])
        return deepcopy(GOOD_DRAFT)

    def route(draft):
        state["routed"].append(deepcopy(draft))
        if state.get("fail_route_times", 0) >= len(state["routed"]):
            raise TimeoutError("route timeout")
        return draft

    with (
        patch("app.services.job_worker.fill_itinerary_draft", side_effect=fill),
        patch("app.services.job_worker.route_itinerary_draft", side_effect=route),
        patch(
            "app.services.job_worker.verify_itinerary_draft",
            return_value=VerifyOutcome(),
        ),
    ):
        yield state


def test_route_failure_retry_skips_fill_and_reuses_the_same_draft(
    api_client: TestClient,
    pipeline: dict,
) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()
    pipeline["fail_route_times"] = 1

    assert process_pending_jobs() == 1

    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        assert job is not None
        assert job.status == "retry_wait"
        assert job.error_code == "TRANSIENT_DEPENDENCY_ERROR"
        stored = job.payload[FILL_DRAFT_PAYLOAD_KEY]
        assert _poi_names(stored) == ["西湖"]
        assert job.payload["selected_entities"][0]["poi_name"] == "西湖"
        assert ROUTE_STAGE_MESSAGE in _stage_messages(job)
        assert RESUME_ROUTE_MESSAGE not in _stage_messages(job)

    _open_retry(created["job_id"])
    assert process_pending_jobs() == 1

    assert pipeline["fill"] == 1
    assert len(pipeline["routed"]) == 2
    assert pipeline["routed"][0] == pipeline["routed"][1]
    assert _poi_names(pipeline["routed"][1]) == ["西湖"]

    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        trip = db.get(Trip, UUID(created["id"]))
        assert job is not None and trip is not None
        assert job.status == "succeeded"
        assert job.attempts == 2
        assert trip.status == "generated"
        assert [item.poi_name for day in trip.days for item in day.items] == ["西湖"]
        messages = _stage_messages(job)
        assert RESUME_ROUTE_MESSAGE in messages
        assert "正在规划景点..." not in messages
        assert "正在按勾选排行程..." not in messages
        assert job.payload["selected_entities"][0]["poi_name"] == "西湖"


def test_retry_without_stored_draft_runs_fill_again(
    api_client: TestClient,
    pipeline: dict,
) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()

    def produce(attempt: int):
        if attempt == 1:
            raise ValueError("truncated json")
        return deepcopy(GOOD_DRAFT)

    pipeline["fill_producer"] = produce

    assert process_pending_jobs() == 1
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        assert job is not None
        assert job.status == "retry_wait"
        assert job.error_code == "MALFORMED_MODEL_OUTPUT"
        assert FILL_DRAFT_PAYLOAD_KEY not in (job.payload or {})

    _open_retry(created["job_id"])
    assert process_pending_jobs() == 1

    assert pipeline["fill"] == 2
    assert len(pipeline["routed"]) == 1
    assert _poi_names(pipeline["routed"][0]) == ["西湖"]
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        trip = db.get(Trip, UUID(created["id"]))
        assert job is not None and trip is not None
        assert job.status == "succeeded"
        assert trip.status == "generated"
        assert _poi_names(job.payload[FILL_DRAFT_PAYLOAD_KEY]) == ["西湖"]
        assert ROUTE_STAGE_MESSAGE in _stage_messages(job)
        assert RESUME_ROUTE_MESSAGE not in _stage_messages(job)


def test_fill_gate_failure_stores_nothing_and_retries_fill(
    api_client: TestClient,
    pipeline: dict,
) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()

    def produce(attempt: int):
        if attempt == 1:
            return deepcopy(BAD_DRAFT)
        return deepcopy(GOOD_DRAFT)

    pipeline["fill_producer"] = produce

    assert process_pending_jobs() == 1
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        assert job is not None
        assert job.status == "retry_wait"
        assert job.error_code == "MALFORMED_MODEL_OUTPUT"
        assert job.message == FILL_DRAFT_ERROR_MESSAGE
        assert FILL_DRAFT_PAYLOAD_KEY not in (job.payload or {})
        assert "route" not in [stage["key"] for stage in job.stages or []]
    assert pipeline["routed"] == []

    _open_retry(created["job_id"])
    assert process_pending_jobs() == 1

    assert pipeline["fill"] == 2
    assert len(pipeline["routed"]) == 1
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        assert job is not None
        assert job.status == "succeeded"
        assert _poi_names(job.payload[FILL_DRAFT_PAYLOAD_KEY]) == ["西湖"]


def test_http_retry_reuses_fill_draft_and_skips_fill(
    api_client: TestClient,
    pipeline: dict,
) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        assert job is not None
        job.max_attempts = 1
        db.commit()
    pipeline["fail_route_times"] = 1

    assert process_pending_jobs() == 1
    with SessionLocal() as db:
        trip = db.get(Trip, UUID(created["id"]))
        job = db.get(GenerationJob, created["job_id"])
        assert trip is not None and job is not None
        assert trip.status == "generation_failed"
        assert job.status == "failed"
        stored_days = job.payload[FILL_DRAFT_PAYLOAD_KEY]["days"]

    retried = api_client.post(f"/api/v1/trips/{created['id']}/retry")
    assert retried.status_code == 200, retried.text
    new_job_id = retried.json()["job_id"]
    assert new_job_id != created["job_id"]

    with SessionLocal() as db:
        new_job = db.get(GenerationJob, new_job_id)
        assert new_job is not None
        assert new_job.status == "pending"
        assert new_job.payload[FILL_DRAFT_PAYLOAD_KEY]["days"] == stored_days
        assert new_job.payload["selected_entities"][0]["poi_name"] == "西湖"

    assert process_pending_jobs() == 1
    assert pipeline["fill"] == 1
    assert len(pipeline["routed"]) == 2
    assert pipeline["routed"][0] == pipeline["routed"][1]

    with SessionLocal() as db:
        job = db.get(GenerationJob, new_job_id)
        trip = db.get(Trip, UUID(created["id"]))
        assert job is not None and trip is not None
        assert job.status == "succeeded"
        assert trip.status == "generated"
        assert RESUME_ROUTE_MESSAGE in _stage_messages(job)
        assert [item.poi_name for day in trip.days for item in day.items] == ["西湖"]


REFILL_DRAFT = {
    "city": "杭州",
    "days": [
        {
            "day_index": 1,
            "theme": "雷峰",
            "route_type": "city",
            "items": [
                {
                    "seq": 1,
                    "poi_name": "雷峰塔",
                    "duration_h": 1,
                    "travel_minutes_from_prev": 0,
                }
            ],
        }
    ],
}


def test_http_discard_fill_draft_runs_fill_again_and_routes_the_new_draft(
    api_client: TestClient,
    pipeline: dict,
) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        assert job is not None
        job.max_attempts = 1
        db.commit()

    def produce(attempt: int):
        if attempt == 1:
            return deepcopy(GOOD_DRAFT)
        return deepcopy(REFILL_DRAFT)

    pipeline["fill_producer"] = produce
    pipeline["fail_route_times"] = 1

    assert process_pending_jobs() == 1
    with SessionLocal() as db:
        trip = db.get(Trip, UUID(created["id"]))
        job = db.get(GenerationJob, created["job_id"])
        assert trip is not None and job is not None
        assert trip.status == "generation_failed"
        assert _poi_names(job.payload[FILL_DRAFT_PAYLOAD_KEY]) == ["西湖"]

    progress = api_client.get(f"/api/v1/trips/{created['id']}/progress")
    assert progress.json()["has_fill_draft"] is True

    retried = api_client.post(
        f"/api/v1/trips/{created['id']}/retry",
        json={"discard_fill_draft": True},
    )
    assert retried.status_code == 200, retried.text
    new_job_id = retried.json()["job_id"]
    with SessionLocal() as db:
        new_job = db.get(GenerationJob, new_job_id)
        assert new_job is not None
        assert FILL_DRAFT_PAYLOAD_KEY not in (new_job.payload or {})
        assert new_job.payload["selected_entities"][0]["poi_name"] == "西湖"

    assert process_pending_jobs() == 1
    assert pipeline["fill"] == 2
    assert len(pipeline["routed"]) == 2
    assert _poi_names(pipeline["routed"][0]) == ["西湖"]
    assert _poi_names(pipeline["routed"][1]) == ["雷峰塔"]
    assert pipeline["routed"][0] != pipeline["routed"][1]

    with SessionLocal() as db:
        job = db.get(GenerationJob, new_job_id)
        trip = db.get(Trip, UUID(created["id"]))
        assert job is not None and trip is not None
        assert job.status == "succeeded"
        assert trip.status == "generated"
        assert _poi_names(job.payload[FILL_DRAFT_PAYLOAD_KEY]) == ["雷峰塔"]
        assert job.payload["selected_entities"][0]["poi_name"] == "西湖"
        messages = _stage_messages(job)
        assert "正在按勾选排行程..." in messages
        assert RESUME_ROUTE_MESSAGE not in messages
        assert ROUTE_STAGE_MESSAGE in messages
        assert [item.poi_name for day in trip.days for item in day.items] == ["雷峰塔"]


def test_invalid_stored_draft_is_dropped_and_the_next_attempt_fills(
    api_client: TestClient,
    pipeline: dict,
) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        assert job is not None
        job.payload = {
            "selected_entities": [{"poi_name": "西湖", "day_index": 1, "seq": 1}],
            FILL_DRAFT_PAYLOAD_KEY: deepcopy(BAD_DRAFT),
        }
        db.commit()

    assert process_pending_jobs() == 1
    assert pipeline["fill"] == 0
    assert pipeline["routed"] == []
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        assert job is not None
        assert job.status == "retry_wait"
        assert job.error_code == "MALFORMED_MODEL_OUTPUT"
        assert FILL_DRAFT_PAYLOAD_KEY not in (job.payload or {})
        assert job.payload["selected_entities"][0]["poi_name"] == "西湖"

    _open_retry(created["job_id"])
    assert process_pending_jobs() == 1
    assert pipeline["fill"] == 1
    assert len(pipeline["routed"]) == 1
    with SessionLocal() as db:
        job = db.get(GenerationJob, created["job_id"])
        assert job is not None
        assert job.status == "succeeded"
        assert "正在按勾选排行程..." in _stage_messages(job)
        assert RESUME_ROUTE_MESSAGE not in _stage_messages(job)
