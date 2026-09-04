"""One-shot from-scratch generation: plan once, then route in Python."""
import json
from datetime import date
from unittest.mock import patch

from langchain_core.messages import AIMessage

from app.agents.itinerary_gen import ITINERARY_GEN_SYSTEM_PROMPT, ITINERARY_GEN_TOOLS
from app.services import itinerary as itinerary_service


def _tool_name(tool) -> str:
    return getattr(tool, "name", None) or getattr(tool, "__name__", "")


def test_itinerary_gen_does_not_bind_travel_time_tool() -> None:
    names = [_tool_name(tool) for tool in ITINERARY_GEN_TOOLS]
    assert names == ["search_attractions"]
    assert "get_travel_time" not in ITINERARY_GEN_SYSTEM_PROMPT


def test_draft_calls_optimize_itinerary_directly() -> None:
    planned = {
        "days": [
            {
                "day_index": 1,
                "theme": "西湖",
                "route_type": "city",
                "items": [
                    {
                        "seq": 1,
                        "poi_name": "西湖",
                        "duration_h": 3,
                        "travel_minutes_from_prev": 0,
                    }
                ],
            }
        ]
    }
    stages: list[str] = []

    class FakePlanner:
        def invoke(self, *_args, **_kwargs):
            return {"messages": [AIMessage(content=json.dumps(planned, ensure_ascii=False))]}

    def fake_optimize(payload: str, reorder: bool = True) -> str:
        data = json.loads(payload)
        assert data["city"] == "杭州"
        data["days"][0]["items"][0]["lat"] = 30.2
        data["days"][0]["items"][0]["lng"] = 120.1
        return json.dumps(data, ensure_ascii=False)

    with (
        patch.object(itinerary_service, "create_itinerary_gen", return_value=FakePlanner()),
        patch.object(itinerary_service, "optimize_itinerary", side_effect=fake_optimize) as opt,
        patch(
            "app.agents.route_optimizer.create_route_optimizer",
            side_effect=AssertionError("route optimizer agent must not run"),
        ),
    ):
        draft = itinerary_service.generate_itinerary_draft(
            destination="杭州",
            city="杭州",
            start_date=date(2030, 1, 1),
            end_date=date(2030, 1, 1),
            on_stage=lambda key, _progress, _message: stages.append(key),
        )

    assert opt.called
    assert draft["days"][0]["items"][0]["lat"] == 30.2
    assert "route" in stages
