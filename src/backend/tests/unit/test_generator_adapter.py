"""Unit tests for LangGraphTripGenerator day extraction."""
from app.infrastructure.itinerary_generator import LangGraphTripGenerator


def test_generate_day_extracts_matching_day(monkeypatch):
    draft = {
        "days": [
            {"day_index": 1, "items": [{"poi_name": "A"}]},
            {"day_index": 2, "items": [{"poi_name": "B"}]},
        ]
    }

    monkeypatch.setattr(
        "app.infrastructure.itinerary_generator.generate_itinerary_draft",
        lambda **kwargs: draft,
    )

    generator = LangGraphTripGenerator()
    day = generator.generate_day(
        destination="杭州",
        start_date="2026-06-01",
        end_date="2026-06-03",
        people_count=2,
        day_index=2,
    )

    assert day["day_index"] == 2
    assert day["items"][0]["poi_name"] == "B"


def test_generate_day_raises_when_missing(monkeypatch):
    draft = {"days": [{"day_index": 1, "items": []}]}
    monkeypatch.setattr(
        "app.infrastructure.itinerary_generator.generate_itinerary_draft",
        lambda **kwargs: draft,
    )

    generator = LangGraphTripGenerator()
    try:
        generator.generate_day(day_index=99)
    except ValueError as exc:
        assert "99" in str(exc)
    else:
        raise AssertionError("expected ValueError")
