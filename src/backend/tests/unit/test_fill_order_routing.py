"""Fill order is primary; nearest-neighbor is the sanity fallback."""
import json
from unittest.mock import patch

from app.agents.tools.route_optimizer import optimize_itinerary


def _geocode_from(coords: dict):
    def fake_geocode(name, city="", mock_fallback=True, nearby=None):
        point = coords[name]
        return {"lat": point["lat"], "lng": point["lng"], "city": point.get("city") or city or "杭州"}

    return fake_geocode


def _run(itinerary: dict, coords: dict, direction, **kwargs) -> dict:
    with (
        patch("app.agents.tools.route_optimizer.settings") as mock_settings,
        patch("app.agents.tools.route_optimizer._amap_direction_direct", side_effect=direction),
        patch("app.agents.tools.route_optimizer.geocode_poi", side_effect=_geocode_from(coords)),
    ):
        mock_settings.amap_api_key = "fake-key"
        return json.loads(optimize_itinerary(json.dumps(itinerary, ensure_ascii=False), **kwargs))


def _day(names: list[str], seqs: list[int] | None = None, estimates: dict | None = None) -> dict:
    items = []
    estimates = estimates or {}
    for index, name in enumerate(names):
        item = {
            "seq": (seqs[index] if seqs else index + 1),
            "poi_name": name,
            "duration_h": 1,
            "travel_minutes_from_prev": 0,
        }
        extra = estimates.get(name)
        if extra:
            item.update(extra)
        items.append(item)
    return {"city": "杭州", "days": [{"day_index": 1, "theme": "测试", "route_type": "city", "items": items}]}


def _ok_direction(*_args, **_kwargs):
    return {"minutes": 12, "mode": "transit", "path": [[120.0, 30.0], [120.01, 30.01]]}


def test_respect_fill_order_keeps_mild_detour() -> None:
    """NN would swap B and C, but the absolute excess is under 30 minutes."""
    coords = {
        "A": {"lat": 30.00, "lng": 120.00},
        "B": {"lat": 30.10, "lng": 120.00},
        "C": {"lat": 30.03, "lng": 120.00},
    }
    result = _run(_day(["A", "B", "C"]), coords, _ok_direction)
    day = result["days"][0]
    assert [item["poi_name"] for item in day["items"]] == ["A", "B", "C"]
    assert day["order_source"] == "fill"
    assert "order_degrade_reason" not in day


def test_large_detour_degrades_to_nearest_neighbor() -> None:
    coords = {
        "A": {"lat": 30.00, "lng": 120.00},
        "B": {"lat": 30.20, "lng": 120.00},
        "C": {"lat": 30.05, "lng": 120.00},
    }
    result = _run(_day(["A", "B", "C"]), coords, _ok_direction)
    day = result["days"][0]
    assert [item["poi_name"] for item in day["items"]] == ["A", "C", "B"]
    assert day["order_source"] == "nearest_neighbor"
    assert day["order_degrade_reason"] == "travel_time"


def test_explicit_respect_fill_order_false_reorders() -> None:
    coords = {
        "A": {"lat": 30.00, "lng": 120.00},
        "B": {"lat": 30.10, "lng": 120.00},
        "C": {"lat": 30.03, "lng": 120.00},
    }
    result = _run(_day(["A", "B", "C"]), coords, _ok_direction, respect_fill_order=False)
    day = result["days"][0]
    assert [item["poi_name"] for item in day["items"]] == ["A", "C", "B"]
    assert day["order_source"] == "nearest_neighbor"


def test_invalid_order_degrades_even_when_detour_is_mild() -> None:
    coords = {
        "A": {"lat": 30.00, "lng": 120.00},
        "B": {"lat": 30.10, "lng": 120.00},
        "C": {"lat": 30.03, "lng": 120.00},
    }
    result = _run(_day(["A", "B", "C"], seqs=[1, 2, 2]), coords, _ok_direction)
    day = result["days"][0]
    assert day["order_source"] == "nearest_neighbor"
    assert day["order_degrade_reason"] == "invalid_order"
    assert [item["poi_name"] for item in day["items"]] == ["A", "C", "B"]


def test_same_day_cross_city_jump_degrades_without_moving_days() -> None:
    coords = {
        "西湖": {"lat": 30.24, "lng": 120.14, "city": "杭州"},
        "故宫": {"lat": 39.90, "lng": 116.40, "city": "北京"},
        "雷峰塔": {"lat": 30.23, "lng": 120.15, "city": "杭州"},
    }
    itinerary = {
        "city": "杭州",
        "days": [{
            "day_index": 1,
            "route_type": "city",
            "items": [
                {"seq": 1, "poi_name": "西湖", "duration_h": 2, "travel_minutes_from_prev": 0},
                {"seq": 2, "poi_name": "故宫", "city": "北京", "duration_h": 2, "travel_minutes_from_prev": 0},
                {"seq": 3, "poi_name": "雷峰塔", "duration_h": 1, "travel_minutes_from_prev": 0},
            ],
        }],
    }
    result = _run(itinerary, coords, _ok_direction)
    names = [item["poi_name"] for item in result["days"][0]["items"]]
    assert names[0] == "西湖"
    assert names[1:] == ["雷峰塔", "故宫"]
    assert result["days"][0]["order_source"] == "nearest_neighbor"
    assert result["days"][0]["order_degrade_reason"] == "cross_city_jump"


def test_amap_failure_fallback_chain_does_not_average_sources() -> None:
    coords = {
        "甲": {"lat": 30.24, "lng": 120.14},
        "乙": {"lat": 30.25, "lng": 120.15},
    }

    def fail(*_args, **_kwargs):
        return None

    guide = _run(
        _day(["甲", "乙"], estimates={"乙": {
            "travel_minutes_from_prev": 45,
            "travel_estimate_minutes": 45,
            "travel_estimate_source": "guide",
        }}),
        coords,
        fail,
    )
    guide_leg = guide["days"][0]["items"][1]
    assert guide_leg["travel_minutes_from_prev"] == 45
    assert guide_leg["travel_minutes"] == 45
    assert guide_leg["travel_amap_minutes"] is None
    assert guide_leg["travel_estimate_source"] == "guide"
    assert guide_leg["route_verified"] is False
    assert guide_leg["travel_discrepancy"] is None

    llm = _run(
        _day(["甲", "乙"], estimates={"乙": {
            "travel_minutes_from_prev": 40,
            "travel_estimate_source": "llm",
        }}),
        coords,
        fail,
    )
    llm_leg = llm["days"][0]["items"][1]
    assert llm_leg["travel_minutes_from_prev"] == 40
    assert llm_leg["travel_estimate_source"] == "llm"
    assert llm_leg["route_verified"] is False

    haversine = _run(_day(["甲", "乙"]), coords, fail)
    bare = haversine["days"][0]["items"][1]
    assert bare["route_verified"] is False
    assert bare["travel_amap_minutes"] is None
    assert bare["travel_estimate_source"] is None
    assert bare["travel_minutes_from_prev"] > 0
    assert bare["travel_minutes_from_prev"] != 45

    verified = _run(
        _day(["甲", "乙"], estimates={"乙": {
            "travel_minutes_from_prev": 45,
            "travel_estimate_minutes": 45,
            "travel_estimate_source": "guide",
        }}),
        coords,
        lambda *_args, **_kwargs: {"minutes": 15, "mode": "walking", "path": [[120.14, 30.24], [120.15, 30.25]]},
    )
    adopted = verified["days"][0]["items"][1]
    assert adopted["travel_minutes_from_prev"] == 15
    assert adopted["travel_amap_minutes"] == 15
    assert adopted["travel_estimate_minutes"] == 45
    assert adopted["route_verified"] is True
    assert adopted["travel_minutes_from_prev"] != 30  # not the average of 15 and 45
    assert adopted["travel_discrepancy"]
    assert "45" in adopted["travel_discrepancy"]
    assert "15" in adopted["travel_discrepancy"]


def test_cross_day_boundary_warns_without_moving_pois() -> None:
    coords = {
        "西湖": {"lat": 30.24, "lng": 120.14, "city": "杭州"},
        "雷峰塔": {"lat": 30.23, "lng": 120.15, "city": "杭州"},
        "故宫": {"lat": 39.90, "lng": 116.40, "city": "北京"},
    }
    itinerary = {
        "city": "杭州",
        "days": [
            {
                "day_index": 1,
                "route_type": "city",
                "day_continuity_note": "次日转北京",
                "items": [
                    {"seq": 1, "poi_name": "西湖", "duration_h": 2, "travel_minutes_from_prev": 0},
                    {"seq": 2, "poi_name": "雷峰塔", "duration_h": 1, "travel_minutes_from_prev": 0},
                ],
            },
            {
                "day_index": 2,
                "route_type": "city",
                "items": [
                    {"seq": 1, "poi_name": "故宫", "city": "北京", "duration_h": 3, "travel_minutes_from_prev": 0},
                ],
            },
        ],
    }
    result = _run(itinerary, coords, _ok_direction)
    assert [item["poi_name"] for item in result["days"][0]["items"]] == ["西湖", "雷峰塔"]
    assert [item["poi_name"] for item in result["days"][1]["items"]] == ["故宫"]
    assert result["days"][0]["day_continuity_note"] == "次日转北京"
    warning = result["days"][1]["day_boundary_warning"]
    assert "故宫" in warning
    assert "雷峰塔" in warning
    assert "不会自动" in warning
    assert warning in (result["days"][1]["items"][0].get("travel_advice") or "")
