"""Seeded generation checkpoints are dropped only when LLM fill is about to run."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.agents import itinerary_gen
from app.db.session import SessionLocal
from app.main import app
from app.models.trip import GenerationJob, Trip
from app.services import job_worker
from app.services.fact_verify import VerifyOutcome
from app.services.job_worker import process_pending_jobs
from app.services.trip_chat import chat_thread_id


PRIOR_FILL = "PRIOR_FILL_DO_NOT_REUSE_兵马俑"
CHAT_NOTE = "CHAT_THREAD_MUST_REMAIN"
OTHER_NOTE = "OTHER_TRIP_MUST_REMAIN"
_VERSION = "00000000000000000000000000000001.0000000000000000"
_CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")

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


def _create_payload(**extra) -> dict:
    body = {
        "destination": f"job-api-{uuid4()}",
        "city": "杭州",
        "start_date": "2031-03-01",
        "end_date": "2031-03-02",
        "people_count": 2,
    }
    body.update(extra)
    return body


def _open_retry(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(GenerationJob, UUID(job_id))
        assert job is not None
        job.next_run_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()


def _seed(thread_id: str, note: str) -> None:
    checkpoint_id = str(uuid4())
    checkpoint = {
        "v": 1,
        "ts": "2024-07-31T20:14:19.804150+00:00",
        "id": checkpoint_id,
        "channel_values": {"messages": [note]},
        "channel_versions": {"messages": _VERSION},
        "versions_seen": {},
    }
    saved = itinerary_gen._checkpointer.put(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
        checkpoint,
        {},
        {"messages": _VERSION},
    )
    itinerary_gen._checkpointer.put_writes(
        saved,
        [("messages", note)],
        task_id="prior-fill",
    )


def _messages(thread_id: str):
    saved = itinerary_gen._checkpointer.get_tuple(
        {"configurable": {"thread_id": thread_id}}
    )
    if saved is None:
        return None
    return (saved.checkpoint.get("channel_values") or {}).get("messages")


def _row_counts(thread_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    with SessionLocal() as db:
        for table in _CHECKPOINT_TABLES:
            counts[table] = db.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE thread_id = :thread_id"),
                {"thread_id": thread_id},
            ).scalar_one()
    return counts


def _wipe(*thread_ids: str) -> None:
    for thread_id in thread_ids:
        itinerary_gen._checkpointer.delete_thread(thread_id)


def test_llm_fill_drops_prior_generation_history_and_keeps_chat(
    api_client: TestClient,
) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()
    trip_id = created["id"]
    generation_thread = f"trip-{trip_id}"
    chat_thread = chat_thread_id(UUID(trip_id))
    other_thread = f"trip-{uuid4()}"
    seen: dict[str, object] = {}

    assert generation_thread != chat_thread
    assert chat_thread.startswith("trip-chat-")

    def fill(**kwargs):
        seen["thread_id"] = kwargs["thread_id"]
        seen["messages_during_fill"] = _messages(generation_thread)
        seen["rows_during_fill"] = _row_counts(generation_thread)
        return GOOD_DRAFT

    _seed(generation_thread, PRIOR_FILL)
    _seed(chat_thread, CHAT_NOTE)
    _seed(other_thread, OTHER_NOTE)
    try:
        assert _messages(generation_thread) == [PRIOR_FILL]
        assert all(count >= 1 for count in _row_counts(generation_thread).values())

        with (
            patch("app.services.job_worker.fill_itinerary_draft", side_effect=fill),
            patch("app.services.job_worker.route_itinerary_draft", side_effect=lambda draft: draft),
            patch(
                "app.services.job_worker.verify_itinerary_draft",
                return_value=VerifyOutcome(),
            ),
        ):
            assert process_pending_jobs() == 1

        assert seen["thread_id"] == generation_thread
        assert seen["messages_during_fill"] is None
        assert seen["rows_during_fill"] == {table: 0 for table in _CHECKPOINT_TABLES}
        assert _messages(generation_thread) is None
        assert _messages(chat_thread) == [CHAT_NOTE]
        assert _messages(other_thread) == [OTHER_NOTE]
        assert all(count >= 1 for count in _row_counts(chat_thread).values())
    finally:
        _wipe(generation_thread, chat_thread, other_thread)


def test_selected_entities_leave_generation_checkpoints_in_place(
    api_client: TestClient,
) -> None:
    entities = [{"poi_name": "西湖", "day_index": 1, "seq": 1}]
    created = api_client.post(
        "/api/v1/trips",
        json=_create_payload(selected_entities=entities),
    ).json()
    generation_thread = f"trip-{created['id']}"
    _seed(generation_thread, PRIOR_FILL)
    try:
        with (
            patch(
                "app.services.itinerary.create_itinerary_gen",
                side_effect=AssertionError("planner must not run when candidates exist"),
            ),
            patch("app.services.job_worker.route_itinerary_draft", side_effect=lambda draft: draft),
            patch(
                "app.services.job_worker.verify_itinerary_draft",
                return_value=VerifyOutcome(),
            ),
        ):
            assert process_pending_jobs() == 1

        assert _messages(generation_thread) == [PRIOR_FILL]
        with SessionLocal() as db:
            trip = db.get(Trip, UUID(created["id"]))
            assert trip is not None
            assert [item.poi_name for day in trip.days for item in day.items] == ["西湖"]
    finally:
        _wipe(generation_thread)


def test_fill_draft_resume_does_not_drop_generation_checkpoints(
    api_client: TestClient,
) -> None:
    created = api_client.post("/api/v1/trips", json=_create_payload()).json()
    generation_thread = f"trip-{created['id']}"
    chat_thread = chat_thread_id(UUID(created["id"]))
    fills = {"count": 0}

    def fill(**_kwargs):
        fills["count"] += 1
        return GOOD_DRAFT

    def route(draft):
        if fills["count"] == 1 and not route.failed:
            route.failed = True
            raise TimeoutError("route timeout")
        return draft

    route.failed = False

    try:
        with (
            patch("app.services.job_worker.fill_itinerary_draft", side_effect=fill),
            patch("app.services.job_worker.route_itinerary_draft", side_effect=route),
            patch(
                "app.services.job_worker.verify_itinerary_draft",
                return_value=VerifyOutcome(),
            ),
        ):
            assert process_pending_jobs() == 1
            _seed(generation_thread, PRIOR_FILL)
            _seed(chat_thread, CHAT_NOTE)
            _open_retry(created["job_id"])
            assert process_pending_jobs() == 1

        assert fills["count"] == 1
        assert _messages(generation_thread) == [PRIOR_FILL]
        assert _messages(chat_thread) == [CHAT_NOTE]
        assert all(count >= 1 for count in _row_counts(generation_thread).values())
    finally:
        _wipe(generation_thread, chat_thread)
