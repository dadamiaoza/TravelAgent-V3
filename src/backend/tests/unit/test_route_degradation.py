"""Route degradation copy, and the worker stages that keep it after persist."""
from datetime import date
from unittest.mock import patch
from uuid import uuid4

from app.services.fact_verify import VerifyOutcome
from app.services.job_worker import GenerationInput, _default_generate
from app.services.route_degradation import (
    collect_route_degradation_messages,
    warning_stage_messages,
)


BOUNDARY = (
    "第1天终点「西湖」与第2天起点「雷峰塔」相距约 300 公里，"
    "跨天衔接偏远。本次不会自动把景点改到另一天。"
)


def _day(day_index: int, **extra) -> dict:
    day = {
        "day_index": day_index,
        "items": [{"seq": 1, "poi_name": f"点{day_index}", "duration_h": 1}],
    }
    day.update(extra)
    return day


def test_collect_groups_nearest_neighbor_reasons_then_boundaries() -> None:
    messages = collect_route_degradation_messages(
        {
            "days": [
                _day(2, order_source="nearest_neighbor", order_degrade_reason="travel_time"),
                _day(1, order_source="nearest_neighbor", order_degrade_reason="travel_time"),
                _day(3, order_source="nearest_neighbor", order_degrade_reason="invalid_order"),
                _day(4, order_source="fill"),
                _day(2, day_boundary_warning=BOUNDARY),
            ]
        }
    )

    assert messages == [
        "第1天、第2天已按最近邻重排（路时明显绕路）",
        "第3天已按最近邻重排（顺序无效）",
        BOUNDARY,
    ]


def test_collect_skips_fill_order_and_unknown_reason_still_says_nearest_neighbor() -> None:
    messages = collect_route_degradation_messages(
        {
            "days": [
                _day(1, order_source="fill", order_degrade_reason="travel_time"),
                _day(2, order_source="nearest_neighbor"),
            ]
        }
    )
    assert messages == ["第2天已按最近邻重排"]


def test_collect_copies_known_degrade_reasons() -> None:
    reasons = {
        "cross_city_jump": "同日跨城过远",
        "amap_unverified": "路段未能核验",
        "explicit_reorder": "指定重排",
    }
    for reason, why in reasons.items():
        messages = collect_route_degradation_messages(
            {"days": [_day(1, order_source="nearest_neighbor", order_degrade_reason=reason)]}
        )
        assert messages == [f"第1天已按最近邻重排（{why}）"]


def test_warning_stage_messages_keep_order_and_drop_other_keys() -> None:
    assert warning_stage_messages(
        [
            {"key": "route", "message": "正在补路线..."},
            {"key": "warning", "message": "第1天已按最近邻重排"},
            {"key": "warning", "message": " 第1天已按最近邻重排 "},
            {"key": "warning", "message": "时效核对未完成，行程已按路线生成"},
            {"key": "done", "message": "行程生成完成"},
        ]
    ) == [
        "第1天已按最近邻重排",
        "时效核对未完成，行程已按路线生成",
    ]
    assert warning_stage_messages(None) == []


def test_default_generate_records_route_warnings_before_verify() -> None:
    routed = {
        "days": [
            _day(1, order_source="nearest_neighbor", order_degrade_reason="cross_city_jump"),
            _day(2, order_source="fill", day_boundary_warning=BOUNDARY),
        ]
    }
    seen: list[tuple[str, int, str]] = []

    def on_stage(key: str, progress: int, message: str) -> bool:
        seen.append((key, progress, message))
        return True

    generation_input = GenerationInput(
        trip_id=uuid4(),
        destination="杭州",
        city="杭州",
        start_date=date(2031, 3, 1),
        end_date=date(2031, 3, 2),
        people_count=2,
        budget_min=None,
        budget_max=None,
        user_prompt=None,
        must_visit=(),
        selected_entities=(),
        thread_id="trip-degrade",
        fill_draft={
            "days": [
                {"day_index": 1, "items": [{"seq": 1, "poi_name": "西湖"}]},
                {"day_index": 2, "items": [{"seq": 1, "poi_name": "雷峰塔"}]},
            ]
        },
    )

    with (
        patch("app.services.job_worker.route_itinerary_draft", return_value=routed),
        patch(
            "app.services.job_worker.verify_itinerary_draft",
            return_value=VerifyOutcome(degraded=True, warnings=["开放时间查询失败"]),
        ),
    ):
        result = _default_generate(generation_input, on_stage=on_stage, claim=None)

    assert result is routed
    warnings = [(progress, message) for key, progress, message in seen if key == "warning"]
    assert warnings == [
        (75, "第1天已按最近邻重排（同日跨城过远）"),
        (75, BOUNDARY),
        (95, "开放时间查询失败"),
    ]
    route_at = next(index for index, item in enumerate(seen) if item[0] == "route")
    verify_at = next(index for index, item in enumerate(seen) if item[0] == "verify")
    first_warning = next(index for index, item in enumerate(seen) if item[0] == "warning")
    assert route_at < first_warning < verify_at


def test_default_generate_verify_exception_still_records_route_warning() -> None:
    routed = {"days": [_day(1, order_source="nearest_neighbor", order_degrade_reason="amap_unverified")]}
    seen: list[str] = []

    with (
        patch("app.services.job_worker.route_itinerary_draft", return_value=routed),
        patch("app.services.job_worker.verify_itinerary_draft", side_effect=RuntimeError("verify exploded")),
    ):
        result = _default_generate(
            GenerationInput(
                trip_id=uuid4(),
                destination="杭州",
                city="杭州",
                start_date=date(2031, 3, 1),
                end_date=date(2031, 3, 2),
                people_count=1,
                budget_min=None,
                budget_max=None,
                user_prompt=None,
                must_visit=(),
                selected_entities=(),
                thread_id="trip-verify",
                fill_draft={"days": [{"day_index": 1, "items": [{"seq": 1, "poi_name": "西湖"}]}]},
            ),
            on_stage=lambda key, _progress, message: seen.append(f"{key}:{message}") or True,
            claim=None,
        )

    assert result is routed
    assert "warning:第1天已按最近邻重排（路段未能核验）" in seen
    assert "warning:时效核对未完成，行程已按路线生成" in seen


def test_clean_route_records_no_warning_stage() -> None:
    seen: list[str] = []
    with (
        patch(
            "app.services.job_worker.route_itinerary_draft",
            side_effect=lambda draft: draft,
        ),
        patch("app.services.job_worker.verify_itinerary_draft", return_value=VerifyOutcome()),
    ):
        _default_generate(
            GenerationInput(
                trip_id=uuid4(),
                destination="杭州",
                city="杭州",
                start_date=date(2031, 3, 1),
                end_date=date(2031, 3, 2),
                people_count=1,
                budget_min=None,
                budget_max=None,
                user_prompt=None,
                must_visit=(),
                selected_entities=(),
                thread_id="trip-clean",
                fill_draft={"days": [{"day_index": 1, "items": [{"seq": 1, "poi_name": "西湖"}]}]},
            ),
            on_stage=lambda key, _progress, message: seen.append(key) or True,
            claim=None,
        )
    assert "warning" not in seen
