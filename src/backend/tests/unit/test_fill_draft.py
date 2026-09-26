"""Fill-exit draft validation: soft defects stop before route."""
import pytest

from app.schemas.fill_draft import (
    FILL_DRAFT_ERROR_MESSAGE,
    FillDraftValidationError,
    gate_fill_draft,
    validate_fill_draft,
)


def _draft(**overrides) -> dict:
    day = {
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
    day.update(overrides.pop("day", {}))
    draft = {"city": "杭州", "days": [day]}
    draft.update(overrides)
    return draft


def test_minimal_valid_draft_passes_without_coordinates() -> None:
    draft = _draft()
    assert validate_fill_draft(draft) is draft


def test_finite_coordinates_pass() -> None:
    draft = _draft(
        day={
            "items": [
                {"seq": 1, "poi_name": "西湖", "lat": 30, "lng": 120.1},
                {"seq": 2, "poi_name": "雷峰塔", "lat": 30.23, "lng": 120.14},
            ]
        }
    )
    assert validate_fill_draft(draft)["days"][0]["items"][1]["poi_name"] == "雷峰塔"


@pytest.mark.parametrize(
    "day",
    [
        {
            "items": [
                {"seq": 1, "poi_name": "西湖", "lat": None, "lng": 120.1},
            ]
        },
        {
            "items": [
                {"seq": 1, "poi_name": "西湖", "lat": 30.2},
            ]
        },
        {
            "items": [
                {"seq": 1, "poi_name": "西湖", "lat": "30.2", "lng": "120.1"},
            ]
        },
        {
            "items": [
                {"seq": 1, "poi_name": "西湖", "lat": float("nan"), "lng": 120.1},
            ]
        },
        {
            "items": [
                {"seq": 1, "poi_name": "西湖"},
                {"seq": 1, "poi_name": "雷峰塔"},
            ]
        },
        {
            "items": [
                {"seq": 0, "poi_name": "西湖"},
            ]
        },
        {
            "items": [
                {"seq": "1", "poi_name": "西湖"},
            ]
        },
        {
            "day_index": "1",
            "items": [
                {"seq": 1, "poi_name": "西湖"},
            ],
        },
    ],
)
def test_soft_defects_fail_validation(day: dict) -> None:
    with pytest.raises(FillDraftValidationError) as caught:
        validate_fill_draft(_draft(day=day))
    assert caught.value.safe_message == FILL_DRAFT_ERROR_MESSAGE


def test_duplicate_day_index_fails() -> None:
    draft = {
        "days": [
            {"day_index": 1, "items": [{"seq": 1, "poi_name": "西湖"}]},
            {"day_index": 1, "items": [{"seq": 1, "poi_name": "灵隐寺"}]},
        ]
    }
    with pytest.raises(FillDraftValidationError):
        validate_fill_draft(draft)


def test_null_coordinate_pair_is_omitted_and_passes() -> None:
    draft = _draft(
        day={
            "items": [
                {"seq": 1, "poi_name": "西湖", "lat": None, "lng": None},
            ]
        }
    )
    assert validate_fill_draft(draft) is draft


def test_gate_records_error_stage_and_does_not_swallow() -> None:
    seen: list[tuple[str, int, str]] = []
    bad = _draft(
        day={
            "items": [
                {"seq": 1, "poi_name": "西湖", "lat": None, "lng": 120.1},
                {"seq": 1, "poi_name": "雷峰塔"},
            ]
        }
    )

    with pytest.raises(FillDraftValidationError):
        gate_fill_draft(bad, on_stage=lambda key, progress, message: seen.append((key, progress, message)))

    assert seen == [("error", 40, FILL_DRAFT_ERROR_MESSAGE)]
