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
    assert len(geocode_calls) >= 3, f"Expected >= 3 unique POI calls, got {len(geocode_calls)}: {geocode_calls}"
    assert {"天安门", "故宫", "天坛"}.issubset(set(geocode_calls)), f"Missing expected POIs in {geocode_calls}"

    parsed = _extract_parsed_json(result["messages"])
    assert len(parsed) == 3
    for item in parsed:
        assert "poi_name" in item
        assert item["day_index"] == 1
        assert "lat" in item and "lng" in item
        # S9: new fields must exist (nullable, so don't assert specific values)
        assert "suggested_duration_h" in item
        assert "best_time" in item
        assert "cost_estimate" in item


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

    parsed = _extract_parsed_json(result["messages"])

    day1_pois = [p["poi_name"] for p in parsed if p["day_index"] == 1]
    day2_pois = [p["poi_name"] for p in parsed if p["day_index"] == 2]
    assert "西湖" in day1_pois, f"Day1: {day1_pois}"
    assert "雷峰塔" in day1_pois
    assert "灵隐寺" in day2_pois, f"Day2: {day2_pois}"


def test_parse_named_pois_only(agent):
    """Only POIs in the mock database should have valid coordinates."""
    text = "去杭州必去西湖、灵隐寺和雷峰塔。"

    result = agent.invoke({"messages": [{"role": "user", "content": text}]})

    parsed = _extract_parsed_json(result["messages"])

    for item in parsed:
        if item["poi_name"] in ("西湖", "灵隐寺", "雷峰塔"):
            assert item["lat"] != 0.0, f"Missing lat for {item['poi_name']}"
            assert item["lng"] != 0.0, f"Missing lng for {item['poi_name']}"
        # S9: new fields must exist
        assert "suggested_duration_h" in item
        assert "best_time" in item
        assert "cost_estimate" in item


def _extract_final_text(messages: list) -> str:
    """Extract text content from the final non-tool-call AIMessage, stripping think tags."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = getattr(msg, "content", "")
            if not content:
                continue
            return re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
    return ""


def _extract_parsed_json(messages: list) -> list:
    """Extract and parse JSON array from agent messages, with fallback strategies."""
    content = _extract_final_text(messages)

    # Strategy 1: bracket-delimited JSON array
    start = content.find("[")
    end = content.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(content[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Strategy 2: regex search for any JSON array (handles malformed wrapping)
    match = re.search(r"\[.*\]", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Strategy 3: try the full content as-is (agent may have output pure JSON)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    raise AssertionError(f"Could not extract valid JSON array from agent output: {content[:300]}")
