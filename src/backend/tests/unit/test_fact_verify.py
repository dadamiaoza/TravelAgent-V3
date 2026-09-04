"""Generation-path verify is a service: risks only, never a hard failure."""
from datetime import date
from unittest.mock import patch

from app.services.fact_verify import verify_itinerary_draft


def _one_poi_draft(poi_name: str = "西湖") -> dict:
    return {
        "days": [
            {
                "day_index": 1,
                "items": [{"seq": 1, "poi_name": poi_name}],
            }
        ]
    }


def test_verify_weather_error_returns_degraded_warnings() -> None:
    with (
        patch("app.services.fact_verify.get_weather", side_effect=RuntimeError("weather down")),
        patch("app.services.fact_verify.get_opening_hours", return_value="09:00-17:00"),
    ):
        outcome = verify_itinerary_draft(
            _one_poi_draft(),
            city="杭州",
            start_date=date(2030, 1, 1),
        )

    assert outcome.degraded is True
    assert outcome.warnings
    assert any("未完成" in warning or "失败" in warning or "weather" in warning.lower() or "天气" in warning for warning in outcome.warnings)


def test_verify_closed_rule_records_high_risk_without_raising() -> None:
    with (
        patch("app.services.fact_verify.get_weather", return_value="晴"),
        patch("app.services.fact_verify.get_opening_hours", return_value="闭馆"),
    ):
        outcome = verify_itinerary_draft(
            _one_poi_draft("萍乡博物馆"),
            city="萍乡",
            start_date=date(2026, 8, 24),
        )

    assert outcome.degraded is False
    assert any("萍乡博物馆" in warning for warning in outcome.warnings)
    assert any(item.get("risk") == "high" for item in outcome.results)
