"""Route-exit draft validation, including real optimize_itinerary output."""
import json
from unittest.mock import patch

import pytest

from app.agents.tools.route_optimizer import optimize_itinerary
from app.schemas.route_draft import (
    ROUTE_DRAFT_ERROR_MESSAGE,
    ROUTE_DRAFT_ERROR_PROGRESS,
    RouteDraftValidationError,
    gate_route_draft,
    validate_route_draft,
)


def _item(**extra) -> dict:
    item = {
        "seq": 1,
        "poi_name": "西湖",
        "duration_h": 1.5,
        "travel_minutes_from_prev": 0,
    }
    item.update(extra)
    return item


def _draft(**day_extra) -> dict:
    day = {
        "day_index": 1,
        "route_type": "city",
        "items": [_item()],
    }
    day.update(day_extra)
    return {"city": "杭州", "days": [day]}


def test_fill_shaped_stub_passes_without_route_metadata() -> None:
    """Identity route stubs omit coords and order_source. That is still legal."""
    draft = _draft()
    assert validate_route_draft(draft) is draft


def test_missing_leg_minutes_pass() -> None:
    draft = _draft()
    del draft["days"][0]["items"][0]["travel_minutes_from_prev"]
    assert validate_route_draft(draft) is draft


def test_soft_route_degradations_are_not_schema_failures() -> None:
    warning = "第1天终点「西湖」与第2天起点「雷峰塔」相距约 300 公里，跨天衔接偏远。"
    draft = {
        "days": [
            {
                "day_index": 1,
                "order_source": "nearest_neighbor",
                "order_degrade_reason": "travel_time",
                "items": [_item(poi_name="西湖")],
            },
            {
                "day_index": 2,
                "order_source": "fill",
                "day_boundary_warning": warning,
                "items": [_item(poi_name="雷峰塔", seq=1)],
            },
        ]
    }
    assert validate_route_draft(draft) is draft
    assert draft["days"][1]["day_boundary_warning"] == warning


def test_optimize_itinerary_output_passes_without_reshape() -> None:
    def fake_geocode(name, city="", mock_fallback=True, nearby=None):
        table = {
            "西湖": {"lat": 30.24, "lng": 120.14},
            "雷峰塔": {"lat": 30.23, "lng": 120.15},
            "故宫": {"lat": 39.92, "lng": 116.40},
        }
        point = table[name]
        return {
            "lat": point["lat"],
            "lng": point["lng"],
            "city": city or "杭州",
            "amap_poi_id": "B0",
            "poi_address": "addr",
            "poi_type": "风景名胜",
        }

    itinerary = {
        "city": "杭州",
        "days": [
            {
                "day_index": 1,
                "theme": "西湖",
                "route_type": "city",
                "items": [
                    {"seq": 1, "poi_name": "西湖", "duration_h": 1.5, "travel_minutes_from_prev": 0},
                    {
                        "seq": 2,
                        "poi_name": "雷峰塔",
                        "duration_h": 1,
                        "travel_minutes_from_prev": 20,
                        "travel_estimate_minutes": 20,
                        "travel_estimate_source": "llm",
                    },
                ],
            },
            {
                "day_index": 2,
                "items": [
                    {
                        "seq": 1,
                        "poi_name": "故宫",
                        "duration_h": 3,
                        "travel_minutes_from_prev": 0,
                        "city": "北京",
                    }
                ],
            },
        ],
    }
    with (
        patch("app.agents.tools.route_optimizer.settings") as mock_settings,
        patch(
            "app.agents.tools.route_optimizer._amap_direction_direct",
            return_value={"minutes": 12, "mode": "transit", "path": [[120.14, 30.24], [120.15, 30.23]]},
        ),
        patch("app.agents.tools.route_optimizer.geocode_poi", side_effect=fake_geocode),
    ):
        mock_settings.amap_api_key = "fake-key"
        routed = json.loads(optimize_itinerary(json.dumps(itinerary, ensure_ascii=False)))

    assert validate_route_draft(routed) is routed
    assert routed["days"][0]["order_source"] == "fill"
    assert isinstance(routed["days"][0]["items"][1]["travel_minutes_from_prev"], int)
    assert routed["days"][1]["day_boundary_warning"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda day: day.__setitem__("day_index", "1"),
        lambda day: day["items"][0].__setitem__("seq", "1"),
        lambda day: day["items"][0].__setitem__("travel_minutes_from_prev", "15"),
        lambda day: day["items"][0].__setitem__("travel_minutes_from_prev", 12.5),
        lambda day: day["items"][0].__setitem__("travel_minutes_from_prev", None),
        lambda day: day["items"][0].__setitem__("travel_minutes", "15"),
        lambda day: day["items"][0].__setitem__("travel_amap_minutes", "12"),
        lambda day: day["items"][0].__setitem__("lat", None) or day["items"][0].__setitem__("lng", 120.1),
        lambda day: day["items"][0].__setitem__("lat", "30.2") or day["items"][0].__setitem__("lng", "120.1"),
        lambda day: day["items"][0].__setitem__("duration_h", "2"),
        lambda day: day["items"][0].__setitem__("duration_h", None),
        lambda day: day["items"][0].__setitem__("route_verified", "true"),
        lambda day: day.__setitem__("order_source", 1),
        lambda day: day.__setitem__("day_boundary_warning", 300),
        lambda day: day["items"][0].__setitem__("poi_name", ""),
    ],
)
def test_illegal_route_types_fail(mutate) -> None:
    draft = _draft()
    mutate(draft["days"][0])
    with pytest.raises(RouteDraftValidationError) as caught:
        validate_route_draft(draft)
    assert caught.value.safe_message == ROUTE_DRAFT_ERROR_MESSAGE


def test_gate_records_error_stage_and_does_not_swallow() -> None:
    seen: list[tuple[str, int, str]] = []
    draft = _draft()
    draft["days"][0]["day_index"] = "1"

    with pytest.raises(RouteDraftValidationError):
        gate_route_draft(draft, on_stage=lambda key, progress, message: seen.append((key, progress, message)))

    assert seen == [("error", ROUTE_DRAFT_ERROR_PROGRESS, ROUTE_DRAFT_ERROR_MESSAGE)]
