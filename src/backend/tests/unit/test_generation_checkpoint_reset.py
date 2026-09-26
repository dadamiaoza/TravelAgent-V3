"""LLM fill clears generation checkpoints; resume and chat do not."""
from datetime import date
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.agents.itinerary_gen import clear_itinerary_gen_thread
from app.services.fact_verify import VerifyOutcome
from app.services.job_worker import GenerationInput, _default_generate
from app.services.trip_chat import chat_thread_id


GOOD_DRAFT = {
    "city": "杭州",
    "days": [
        {
            "day_index": 1,
            "theme": "西湖",
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


def _generation_input(**overrides) -> GenerationInput:
    fields = {
        "trip_id": uuid4(),
        "destination": "杭州",
        "city": "杭州",
        "start_date": date(2031, 3, 1),
        "end_date": date(2031, 3, 2),
        "people_count": 2,
        "budget_min": None,
        "budget_max": None,
        "user_prompt": None,
        "must_visit": (),
        "selected_entities": (),
        "thread_id": "trip-unit",
        "fill_draft": None,
    }
    fields.update(overrides)
    return GenerationInput(**fields)


def test_clear_uses_delete_thread_for_generation_ids() -> None:
    with patch("app.agents.itinerary_gen._checkpointer") as saver:
        clear_itinerary_gen_thread("trip-abc")
    saver.delete_thread.assert_called_once_with("trip-abc")


def test_chat_thread_id_stays_distinct_and_is_not_cleared() -> None:
    trip_id = uuid4()
    chat_thread = chat_thread_id(trip_id)
    generation_thread = f"trip-{trip_id}"

    assert chat_thread == f"trip-chat-{trip_id}"
    assert chat_thread != generation_thread

    with patch("app.agents.itinerary_gen._checkpointer") as saver:
        with pytest.raises(ValueError, match="non-generation"):
            clear_itinerary_gen_thread(chat_thread)
    saver.delete_thread.assert_not_called()


def test_llm_fill_clears_generation_thread_before_invoke() -> None:
    order: list[str] = []
    generation_input = _generation_input(thread_id="trip-fresh")

    def clear(thread_id: str) -> None:
        order.append(f"clear:{thread_id}")

    def fill(**kwargs):
        order.append(f"fill:{kwargs['thread_id']}")
        assert kwargs["selected_entities"] is None
        return GOOD_DRAFT

    with (
        patch("app.services.job_worker.clear_itinerary_gen_thread", side_effect=clear),
        patch("app.services.job_worker.fill_itinerary_draft", side_effect=fill),
        patch("app.services.job_worker.route_itinerary_draft", side_effect=lambda draft: draft),
        patch(
            "app.services.job_worker.verify_itinerary_draft",
            return_value=VerifyOutcome(),
        ),
    ):
        routed = _default_generate(generation_input, claim=None)

    assert routed is not None
    assert order == ["clear:trip-fresh", "fill:trip-fresh"]


def test_selected_entities_do_not_clear_or_require_planner() -> None:
    generation_input = _generation_input(
        selected_entities=({"poi_name": "西湖", "day_index": 1, "seq": 1},),
    )
    with (
        patch("app.services.job_worker.clear_itinerary_gen_thread") as clear,
        patch(
            "app.services.itinerary.create_itinerary_gen",
            side_effect=AssertionError("planner must not run for selected entities"),
        ),
        patch("app.services.job_worker.route_itinerary_draft", side_effect=lambda draft: draft),
        patch(
            "app.services.job_worker.verify_itinerary_draft",
            return_value=VerifyOutcome(),
        ),
    ):
        routed = _default_generate(generation_input, claim=None)

    clear.assert_not_called()
    assert routed is not None
    assert routed["days"][0]["items"][0]["poi_name"] == "西湖"


def test_fill_draft_resume_does_not_clear_or_fill() -> None:
    generation_input = _generation_input(fill_draft=GOOD_DRAFT)
    with (
        patch("app.services.job_worker.clear_itinerary_gen_thread") as clear,
        patch("app.services.job_worker.fill_itinerary_draft") as fill,
        patch("app.services.job_worker.route_itinerary_draft", side_effect=lambda draft: draft) as route,
        patch(
            "app.services.job_worker.verify_itinerary_draft",
            return_value=VerifyOutcome(),
        ),
    ):
        routed = _default_generate(generation_input, claim=None)

    clear.assert_not_called()
    fill.assert_not_called()
    route.assert_called_once()
    assert routed["days"][0]["items"][0]["poi_name"] == "西湖"
