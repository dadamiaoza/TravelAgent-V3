"""Persist-input draft validation, aligned with persist_itinerary reads."""
import pytest

from app.schemas.persist_draft import (
    PERSIST_DRAFT_ERROR_MESSAGE,
    PERSIST_DRAFT_ERROR_PROGRESS,
    PersistDraftValidationError,
    gate_persist_draft,
    validate_persist_draft,
)
from app.schemas.route_draft import RouteDraftValidationError, validate_route_draft


def _draft() -> dict:
    return {
        "city": "杭州",
        "days": [
            {
                "day_index": 1,
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


def test_minimal_draft_passes_and_is_not_rewritten() -> None:
    draft = _draft()
    assert validate_persist_draft(draft) is draft


def test_float_duration_and_null_coordinate_pair_pass() -> None:
    draft = _draft()
    draft["days"][0]["items"][0]["duration_h"] = 1.5
    draft["days"][0]["items"][0]["lat"] = None
    draft["days"][0]["items"][0]["lng"] = None
    assert validate_persist_draft(draft) is draft


def test_route_only_types_are_not_persist_failures() -> None:
    """persist_itinerary does not read order_source or travel_amap_minutes."""
    draft = _draft()
    draft["days"][0]["order_source"] = 1
    draft["days"][0]["items"][0]["travel_amap_minutes"] = "12"
    assert validate_persist_draft(draft) is draft
    with pytest.raises(RouteDraftValidationError):
        validate_route_draft(draft)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda draft: draft["days"][0].__setitem__("day_index", "1"),
        lambda draft: draft["days"][0]["items"][0].__setitem__("seq", "1"),
        lambda draft: draft["days"][0]["items"][0].__setitem__("travel_minutes_from_prev", "15"),
        lambda draft: draft["days"][0]["items"][0].__setitem__("travel_minutes_from_prev", 12.0),
        lambda draft: draft["days"][0]["items"][0].__setitem__("travel_minutes_from_prev", None),
        lambda draft: draft["days"][0]["items"][0].__setitem__("lat", 30.2),
        lambda draft: draft["days"][0]["items"][0].__setitem__("duration_h", None),
        lambda draft: draft["days"][0]["items"][0].__setitem__("poi_name", ""),
        lambda draft: draft["days"][0]["items"][0].__setitem__("route_verified", "false"),
        lambda draft: draft["days"][0].__setitem__("route_type", 1),
    ],
)
def test_types_that_break_persist_fail(mutate) -> None:
    draft = _draft()
    mutate(draft)
    with pytest.raises(PersistDraftValidationError) as caught:
        validate_persist_draft(draft)
    assert caught.value.safe_message == PERSIST_DRAFT_ERROR_MESSAGE


def test_gate_records_error_stage() -> None:
    seen: list[tuple[str, int, str]] = []
    draft = _draft()
    draft["days"][0]["day_index"] = "1"
    with pytest.raises(PersistDraftValidationError):
        gate_persist_draft(draft, on_stage=lambda key, progress, message: seen.append((key, progress, message)))
    assert seen == [("error", PERSIST_DRAFT_ERROR_PROGRESS, PERSIST_DRAFT_ERROR_MESSAGE)]
