"""Integration tests for guide_parser agent — loop tool calling."""
import json
import re

import pytest
from langchain_core.messages import AIMessage

from app.agents.guide_parser import create_guide_parser


@pytest.fixture
def agent():
    """Per-test agent — avoids state bleed between tests."""
    return create_guide_parser()


def test_parse_simple_travelogue(agent):
    """Single day — should call geocode_poi for each POI found."""
    text = "早上先去天安门，然后走到故宫，下午去了天坛。"

    result = agent.invoke({"messages": [{"role": "user", "content": text}]})

    geocode_calls = [
        tc["args"]["name"]
        for msg in result["messages"]
        if getattr(msg, "tool_calls", None)
        for tc in msg.tool_calls
        if tc["name"] == "geocode_poi"
    ]
    assert len(geocode_calls) == 3, f"Expected 3 POIs, got {len(geocode_calls)}: {geocode_calls}"
    assert set(geocode_calls) == {"天安门", "故宫", "天坛"}

    final = _get_final_content(result["messages"])
    parsed = json.loads(final)
    assert len(parsed) == 3
    for item in parsed:
        assert "poi_name" in item
        assert item["day_index"] == 1
        assert "lat" in item and "lng" in item


def test_parse_multi_day_travelogue(agent):
    """Text with explicit day separators — agent should infer day_index."""
    text = (
        "第一天：西湖坐船，登上雷峰塔看全景。\n"
        "第二天：灵隐寺烧香，下午逛了逛附近的龙井村。"
    )

    result = agent.invoke({"messages": [{"role": "user", "content": text}]})

    geocode_calls = [
        tc["args"]["name"]
        for msg in result["messages"]
        if getattr(msg, "tool_calls", None)
        for tc in msg.tool_calls
        if tc["name"] == "geocode_poi"
    ]
    assert len(geocode_calls) >= 3, f"Expected >= 3 POIs, got {len(geocode_calls)}: {geocode_calls}"

    final = _get_final_content(result["messages"])
    parsed = json.loads(final)

    day1_pois = [p["poi_name"] for p in parsed if p["day_index"] == 1]
    day2_pois = [p["poi_name"] for p in parsed if p["day_index"] == 2]
    assert "西湖" in day1_pois, f"Day1: {day1_pois}"
    assert "雷峰塔" in day1_pois
    assert "灵隐寺" in day2_pois, f"Day2: {day2_pois}"


def test_parse_named_pois_only(agent):
    """Only POIs in the mock database should have valid coordinates."""
    text = "去杭州必去西湖、灵隐寺和雷峰塔。"

    result = agent.invoke({"messages": [{"role": "user", "content": text}]})

    final = _get_final_content(result["messages"])
    parsed = json.loads(final)

    for item in parsed:
        if item["poi_name"] in ("西湖", "灵隐寺", "雷峰塔"):
            assert item["lat"] != 0.0
            assert item["lng"] != 0.0


def _get_final_content(messages: list) -> str:
    """Extract JSON array from the final AIMessage, robust against think tags."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = getattr(msg, "content", "")
            if not content:
                continue
            # Strip <think>...</think> tags
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
            # Find the JSON array
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end > start:
                return content[start:end + 1]
            return content
    return ""
