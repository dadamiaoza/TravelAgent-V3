"""Worker stops illegal drafts before verify or persist."""
from datetime import date
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.schemas.persist_draft import PERSIST_DRAFT_ERROR_MESSAGE, PersistDraftValidationError
from app.schemas.route_draft import ROUTE_DRAFT_ERROR_MESSAGE, RouteDraftValidationError
from app.services.fact_verify import VerifyOutcome
from app.services.job_worker import (
    GenerationInput,
    _default_generate,
    classify_generation_error,
)
from app.schemas.fill_draft import FillDraftValidationError


def _generation_input() -> GenerationInput:
    return GenerationInput(
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
        thread_id="trip-boundary",
        fill_draft={
            "days": [
                {
                    "day_index": 1,
                    "items": [{"seq": 1, "poi_name": "西湖", "duration_h": 2, "travel_minutes_from_prev": 0}],
                }
            ]
        },
    )


def test_classify_maps_every_draft_boundary_to_malformed_output() -> None:
    cases = [
        FillDraftValidationError("fill"),
        RouteDraftValidationError("route"),
        PersistDraftValidationError("persist"),
    ]
    messages = {
        FillDraftValidationError: "行程草稿的坐标或顺序无效，无法继续排路线",
        RouteDraftValidationError: ROUTE_DRAFT_ERROR_MESSAGE,
        PersistDraftValidationError: PERSIST_DRAFT_ERROR_MESSAGE,
    }
    for exc in cases:
        disposition = classify_generation_error(exc)
        assert disposition.retryable is True
        assert disposition.code == "MALFORMED_MODEL_OUTPUT"
        assert disposition.safe_message == messages[type(exc)]


def test_string_day_index_from_route_stops_before_verify() -> None:
    seen: list[tuple[str, int, str]] = []
    bad = {
        "days": [
            {
                "day_index": "1",
                "items": [{"seq": 1, "poi_name": "西湖", "travel_minutes_from_prev": 0}],
            }
        ]
    }

    with (
        patch("app.services.job_worker.route_itinerary_draft", return_value=bad),
        patch(
            "app.services.job_worker.verify_itinerary_draft",
            side_effect=AssertionError("verify must not run"),
        ) as verify,
    ):
        with pytest.raises(RouteDraftValidationError):
            _default_generate(
                _generation_input(),
                on_stage=lambda key, progress, message: seen.append((key, progress, message)) or True,
                claim=None,
            )

    verify.assert_not_called()
    assert ("error", 80, ROUTE_DRAFT_ERROR_MESSAGE) in seen
    assert all(key != "verify" for key, _progress, _message in seen)


def test_string_leg_minutes_stop_before_verify() -> None:
    bad = {
        "days": [
            {
                "day_index": 1,
                "order_source": "fill",
                "items": [
                    {
                        "seq": 1,
                        "poi_name": "西湖",
                        "duration_h": 2,
                        "travel_minutes_from_prev": "15",
                    }
                ],
            }
        ]
    }
    with (
        patch("app.services.job_worker.route_itinerary_draft", return_value=bad),
        patch(
            "app.services.job_worker.verify_itinerary_draft",
            side_effect=AssertionError("verify must not run"),
        ) as verify,
    ):
        with pytest.raises(RouteDraftValidationError):
            _default_generate(_generation_input(), claim=None)
    verify.assert_not_called()


def test_verify_degradation_still_returns_the_routed_draft() -> None:
    routed = {
        "days": [
            {
                "day_index": 1,
                "order_source": "nearest_neighbor",
                "order_degrade_reason": "cross_city_jump",
                "day_boundary_warning": "跨天衔接偏远",
                "items": [{"seq": 1, "poi_name": "西湖", "duration_h": 1}],
            }
        ]
    }
    with (
        patch("app.services.job_worker.route_itinerary_draft", return_value=routed),
        patch(
            "app.services.job_worker.verify_itinerary_draft",
            return_value=VerifyOutcome(degraded=True, warnings=["时效核对未完成，行程已按路线生成"]),
        ),
    ):
        result = _default_generate(
            _generation_input(),
            on_stage=lambda *_args: True,
            claim=None,
        )
    assert result is routed
