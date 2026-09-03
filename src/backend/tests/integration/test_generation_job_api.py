"""API coverage for durable job query, progress recovery, and notification SSE."""

import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.trip import GenerationJob, Trip
from app.services import job_worker
from app.services.generation_jobs import GenerationJobStatus, transition_job


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


def _create_payload(destination: str | None = None) -> dict:
    return {
        "destination": destination or f"job-api-{uuid4()}",
        "city": "杭州",
        "start_date": "2031-03-01",
        "end_date": "2031-03-02",
        "people_count": 2,
        "user_prompt": "西湖一日游",
        "must_visit": ["西湖"],
    }


def _parse_sse_events(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    data_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if line == "":
            if data_lines:
                events.append((event_name, json.loads("\n".join(data_lines))))
            event_name = "message"
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line[len("event:") :].strip()
        elif line.startswith("data:"):
            data_lines.append(line[len("data:") :].strip())
    if data_lines:
        events.append((event_name, json.loads("\n".join(data_lines))))
    return events


def test_create_trip_returns_201_with_job_id(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/trips", json=_create_payload())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["destination"].startswith("job-api-")
    assert body["status"] == "generating"
    assert body["days"] == []
    assert body["job_id"]
    job_response = api_client.get(f"/api/v1/jobs/{body['job_id']}")
    assert job_response.status_code == 200
    assert job_response.json()["trip_id"] == body["id"]


def test_get_trip_remains_compatible_without_requiring_job_id(
    api_client: TestClient,
) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()

    response = api_client.get(f"/api/v1/trips/{created['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["destination"] == created["destination"]
    assert "status" in body
    assert "days" in body


def test_progress_includes_job_id_for_refresh_recovery(api_client: TestClient) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()

    response = api_client.get(f"/api/v1/trips/{created['id']}/progress")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == created["job_id"]
    assert body["status"] == "pending"
    assert body["progress"] == 0
    assert body["message"]


def test_get_job_returns_public_snapshot_and_hides_internal_fields(
    api_client: TestClient,
) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()

    response = api_client.get(f"/api/v1/jobs/{created['job_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["job_id"]
    assert body["trip_id"] == created["id"]
    assert body["status"] == "pending"
    assert body["progress"] == 0
    assert body["message"]
    assert body["attempts"] == 0
    assert body["max_attempts"] == 3
    assert body["error_code"] is None
    assert "status_version" in body
    assert "created_at" in body
    assert "run_token" not in body
    assert "error" not in body
    assert "heartbeat_at" not in body


def test_get_job_returns_404_for_unknown_id(api_client: TestClient) -> None:
    response = api_client.get(f"/api/v1/jobs/{uuid4()}")

    assert response.status_code == 404


def _complete_job(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(GenerationJob, job_id)
        assert job is not None
        transition_job(db, job, GenerationJobStatus.RUNNING)
        job = db.get(GenerationJob, job_id)
        assert job is not None
        transition_job(db, job, GenerationJobStatus.SUCCEEDED)


def test_job_events_start_with_snapshot_matching_get(api_client: TestClient) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()
    _complete_job(created["job_id"])
    snapshot = api_client.get(f"/api/v1/jobs/{created['job_id']}").json()

    with api_client.stream("GET", f"/api/v1/jobs/{created['job_id']}/events") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = "".join(response.iter_text())

    events = _parse_sse_events(body)
    assert events
    event_name, payload = events[0]
    assert event_name == "snapshot"
    assert payload == snapshot
    assert payload["status"] == "succeeded"


def test_job_events_404_for_unknown_id(api_client: TestClient) -> None:
    response = api_client.get(f"/api/v1/jobs/{uuid4()}/events")

    assert response.status_code == 404


def test_disconnect_falls_back_to_durable_job_get(api_client: TestClient) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()
    _complete_job(created["job_id"])

    with api_client.stream("GET", f"/api/v1/jobs/{created['job_id']}/events") as response:
        assert response.status_code == 200
        next(response.iter_text(), None)

    fallback = api_client.get(f"/api/v1/jobs/{created['job_id']}")
    assert fallback.status_code == 200
    assert fallback.json()["id"] == created["job_id"]
    assert fallback.json()["trip_id"] == created["id"]
    assert fallback.json()["status"] == "succeeded"


def test_idempotency_key_replays_the_same_trip_and_job(api_client: TestClient) -> None:
    key = f"create-{uuid4()}"
    first = api_client.post(
        "/api/v1/trips",
        json=_create_payload("job-api-idem-source"),
        headers={"Idempotency-Key": key},
    )
    second = api_client.post(
        "/api/v1/trips",
        json=_create_payload("job-api-idem-other"),
        headers={"Idempotency-Key": key},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["destination"] == "job-api-idem-source"


def test_distinct_idempotency_keys_create_distinct_trips(
    api_client: TestClient,
) -> None:
    first = api_client.post(
        "/api/v1/trips",
        json=_create_payload(),
        headers={"Idempotency-Key": f"key-{uuid4()}"},
    )
    second = api_client.post(
        "/api/v1/trips",
        json=_create_payload(),
        headers={"Idempotency-Key": f"key-{uuid4()}"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["job_id"] != second.json()["job_id"]
