"""SSE chat stream emits applied events without calling the LLM."""
import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.db.session import get_db
from app.main import app
from app.schemas.trip import ItineraryDelta, ItineraryDeltaPayload, ItineraryDeltaTarget, TripChatOut


def _parse_sse(text: str) -> dict[str, dict]:
    events: dict[str, dict] = {}
    event_name = "message"
    data_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if line == "":
            if data_lines:
                events[event_name] = json.loads("\n".join(data_lines))
            event_name = "message"
            data_lines = []
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
    if data_lines:
        events[event_name] = json.loads("\n".join(data_lines))
    return events


def test_chat_stream_emits_applied_event() -> None:
    trip_id = uuid4()
    result = TripChatOut(
        reply="已删除雷峰塔",
        thread_id=f"trip-chat-{trip_id}",
        suggestions=[],
        applied=[
            ItineraryDelta(
                action="delete",
                target=ItineraryDeltaTarget(day_index=1, item_id=uuid4()),
                payload=ItineraryDeltaPayload(poi_name="雷峰塔"),
            )
        ],
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = MagicMock(id=trip_id, days=[])
    original = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with patch("app.api.v1.trips.run_trip_chat", return_value=result):
            response = TestClient(app).post(
                f"/api/v1/trips/{trip_id}/chat/stream",
                json={"message": "删掉雷峰塔", "write_mode": "auto_apply"},
            )
    finally:
        if original is not None:
            app.dependency_overrides[get_db] = original
        else:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events["applied"]["deltas"][0]["payload"]["poi_name"] == "雷峰塔"
    assert events["done"]["thread_id"].startswith("trip-chat-")
    assert events["done"]["applied"]
