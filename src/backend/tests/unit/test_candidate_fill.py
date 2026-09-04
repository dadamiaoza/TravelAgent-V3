"""Candidate fill: selected entities skip the planning agent."""
from datetime import date
from unittest.mock import patch

from langchain_core.messages import AIMessage

from app.services import itinerary as itinerary_service


def _planned_draft() -> dict:
    return {
        "days": [
            {
                "day_index": 1,
                "theme": "模型发明",
                "route_type": "city",
                "items": [
                    {
                        "seq": 1,
                        "poi_name": "模型景点",
                        "duration_h": 2,
                        "travel_minutes_from_prev": 0,
                    }
                ],
            }
        ]
    }


def test_fill_with_candidates_skips_planner() -> None:
    entities = [
        {"poi_name": "灵隐寺", "day_index": 2, "seq": 1},
        {"poi_name": "西湖", "day_index": 1, "seq": 1, "suggested_duration_h": 3},
        {"poi_name": "雷峰塔", "day_index": 1, "seq": 2, "lat": 30.2, "lng": 120.1},
    ]

    with patch.object(
        itinerary_service,
        "create_itinerary_gen",
        side_effect=AssertionError("planner must not run when candidates exist"),
    ):
        draft = itinerary_service.fill_itinerary_draft(
            destination="杭州",
            city="杭州",
            start_date=date(2030, 1, 1),
            end_date=date(2030, 1, 3),
            selected_entities=entities,
        )

    assert draft["city"] == "杭州"
    assert [day["day_index"] for day in draft["days"]] == [1, 2]
    assert [item["poi_name"] for item in draft["days"][0]["items"]] == ["西湖", "雷峰塔"]
    assert draft["days"][0]["items"][0]["duration_h"] == 3
    assert draft["days"][0]["items"][1]["lat"] == 30.2
    assert draft["days"][1]["items"][0]["poi_name"] == "灵隐寺"


def test_fill_without_candidates_calls_planner() -> None:
    class FakePlanner:
        def invoke(self, *_args, **_kwargs):
            return {
                "messages": [
                    AIMessage(content='{"days": [{"day_index": 1, "theme": "西湖", "route_type": "city", "items": [{"seq": 1, "poi_name": "西湖", "duration_h": 3, "travel_minutes_from_prev": 0}]}]}')
                ]
            }

    with patch.object(
        itinerary_service, "create_itinerary_gen", return_value=FakePlanner()
    ) as factory:
        draft = itinerary_service.fill_itinerary_draft(
            destination="杭州",
            city="杭州",
            start_date=date(2030, 1, 1),
            end_date=date(2030, 1, 1),
        )

    factory.assert_called_once()
    assert draft["city"] == "杭州"
    assert draft["days"][0]["items"][0]["poi_name"] == "西湖"


def test_fill_empty_candidate_list_still_calls_planner() -> None:
    class FakePlanner:
        def invoke(self, *_args, **_kwargs):
            return {
                "messages": [
                    AIMessage(
                        content='{"days": [{"day_index": 1, "theme": "西湖", "route_type": "city", "items": [{"seq": 1, "poi_name": "西湖", "duration_h": 2, "travel_minutes_from_prev": 0}]}]}'
                    )
                ]
            }

    with patch.object(
        itinerary_service, "create_itinerary_gen", return_value=FakePlanner()
    ) as factory:
        itinerary_service.fill_itinerary_draft(
            destination="杭州",
            city="杭州",
            start_date=date(2030, 1, 1),
            end_date=date(2030, 1, 1),
            selected_entities=[],
        )

    factory.assert_called_once()
