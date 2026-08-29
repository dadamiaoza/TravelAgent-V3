"""Unit tests for trip editor application orchestration with fake ports."""
from datetime import date
from types import SimpleNamespace

from app.services import trip_editor
from tests.fakes import FakeTripGenerator


def _fake_trip():
    return SimpleNamespace(
        id="trip-1",
        destination="杭州",
        city="杭州",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 3),
        people_count=2,
        budget_min=None,
        budget_max=None,
        user_prompt=None,
        must_visit=None,
    )


def test_regenerate_segment_uses_generator_and_replace_day(monkeypatch):
    calls = []

    def fake_replace(db, trip, day_index, day_data, start_date):
        calls.append((db, trip, day_index, day_data, start_date))

    monkeypatch.setattr(trip_editor, "replace_day", fake_replace)

    fake_db = SimpleNamespace(commit=lambda: None, refresh=lambda obj: None)
    trip = _fake_trip()
    generator = FakeTripGenerator(day_draft={
        "day_index": 2,
        "route_type": "city",
        "items": [{"seq": 1, "poi_name": "新景点"}],
    })

    result = trip_editor.regenerate_segment(fake_db, trip, 2, generator=generator)

    assert result is trip
    assert generator.generate_day_calls
    assert generator.generate_day_calls[0]["day_index"] == 2
    assert calls[0][0] is fake_db
    assert calls[0][2] == 2
    assert calls[0][3]["day_index"] == 2
