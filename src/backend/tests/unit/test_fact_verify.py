"""Generation-path verify is a service: risks only, never a hard failure."""
from datetime import date
from unittest.mock import patch

from app.services.fact_verify import apply_verify_to_draft, verify_itinerary_draft


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


def test_apply_verify_stamps_hours_and_warning_onto_draft() -> None:
    draft = _one_poi_draft("西湖")
    draft["days"][0]["items"][0]["visit_tips"] = "沿湖散步。"
    with (
        patch("app.services.fact_verify.get_weather", return_value="晴"),
        patch("app.services.fact_verify.get_opening_hours", return_value="08:00-18:00"),
        patch(
            "app.services.fact_verify.evaluate_closure_rule",
            return_value={"matched": True, "risk": "high", "reason": "周一闭馆", "rule_type": "weekly_closure", "source": "规则"},
        ),
    ):
        outcome = verify_itinerary_draft(
            draft,
            city="杭州",
            start_date=date(2030, 1, 5),  # Monday
        )
    apply_verify_to_draft(draft, outcome)
    item = draft["days"][0]["items"][0]
    assert item["opening_hours"] == "08:00-18:00"
    assert "闭馆" in (item.get("fact_warning") or "")
    assert item["visit_tips"] == "沿湖散步。"
