"""Tests for route_optimizer Agent — Step 5 chained agent calling."""
import json
import re

import pytest
from langchain_core.messages import AIMessage

from app.agents.route_optimizer import create_route_optimizer
from app.agents.tools.route_optimizer import optimize_itinerary


# ── 纯 Tool 测试（不经过 Agent，直接测 Tool 函数）──

def test_optimize_itinerary_tool():
    """Tool function: geocode POIs and fill lat/lng, preserve order."""
    input_json = json.dumps({
        "days": [{
            "day_index": 1,
            "theme": "测试",
            "items": [
                {"seq": 1, "poi_name": "西湖", "duration_h": 3, "travel_minutes_from_prev": 0},
                {"seq": 2, "poi_name": "雷峰塔", "duration_h": 1.5, "travel_minutes_from_prev": 20},
            ]
        }]
    }, ensure_ascii=False)

    result_str = optimize_itinerary(input_json)
    result = json.loads(result_str)

    items = result["days"][0]["items"]
    assert len(items) == 2

    # 坐标应被填充
    for item in items:
        assert "lat" in item, f"Missing lat in {item}"
        assert "lng" in item, f"Missing lng in {item}"
        assert isinstance(item["lat"], (int, float))
        assert isinstance(item["lng"], (int, float))

    # 顺序应保持不变
    assert items[0]["poi_name"] == "西湖"
    assert items[1]["poi_name"] == "雷峰塔"

    # 已知 POI 坐标验证
    assert 30.2 <= items[0]["lat"] <= 30.3  # 西湖 ≈ 30.24
    assert 120.1 <= items[0]["lng"] <= 120.2
    assert 30.2 <= items[1]["lat"] <= 30.3  # 雷峰塔 ≈ 30.23
    assert 120.1 <= items[1]["lng"] <= 120.2


def test_optimize_itinerary_tool_unknown_poi():
    """Tool function: unknown POI gets hash-based fallback coordinates."""
    input_json = json.dumps({
        "days": [{
            "day_index": 1,
            "theme": "测试",
            "items": [
                {"seq": 1, "poi_name": "一个不存在的地方名称XYZ", "duration_h": 1, "travel_minutes_from_prev": 0},
            ]
        }]
    }, ensure_ascii=False)

    result_str = optimize_itinerary(input_json)
    result = json.loads(result_str)

    item = result["days"][0]["items"][0]
    # 即使是未知 POI，也应该有坐标（fallback）
    assert isinstance(item["lat"], (int, float))
    assert isinstance(item["lng"], (int, float))


# ── Agent 测试（完整 Agent + Tool 管道）──

@pytest.fixture
def agent():
    return create_route_optimizer()


def test_route_optimizer_agent(agent):
    """Agent: receives itinerary JSON, calls tool, returns JSON with coords."""
    itinerary_json = json.dumps({
        "days": [{
            "day_index": 1,
            "theme": "杭州一日",
            "items": [
                {"seq": 1, "poi_name": "灵隐寺", "duration_h": 2, "travel_minutes_from_prev": 0},
                {"seq": 2, "poi_name": "西湖", "duration_h": 3, "travel_minutes_from_prev": 30},
            ]
        }]
    }, ensure_ascii=False)

    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"请调用 optimize_itinerary 处理：\n{itinerary_json}"}]}
    )

    final = _get_final_json(result["messages"])
    parsed = json.loads(final)

    items = parsed["days"][0]["items"]
    assert len(items) == 2
    assert items[0]["poi_name"] == "灵隐寺"
    assert "lat" in items[0]
    assert "lng" in items[0]


def _get_final_json(messages: list) -> str:
    """Extract JSON from the final AIMessage (no tool_calls)."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = getattr(msg, "content", "")
            if not content:
                continue
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
            for start_ch, end_ch in [("{", "}"), ("[", "]")]:
                start = content.find(start_ch)
                end = content.rfind(end_ch)
                if start != -1 and end > start:
                    return content[start:end + 1]
            return content
    return ""
