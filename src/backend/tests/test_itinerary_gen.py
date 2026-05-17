"""Integration tests for itinerary_gen agent — Memory/Checkpointer."""
import json
import re

import pytest
from langchain_core.messages import AIMessage

from app.agents.itinerary_gen import create_itinerary_gen


@pytest.fixture
def agent():
    return create_itinerary_gen()


def test_generate_full_itinerary(agent):
    """Single turn: plan a complete 2-day trip."""
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "请为杭州2日游规划完整行程，我偏好自然风光"}]},
        config={"configurable": {"thread_id": "test_full"}},
    )

    final = _get_final_json(result["messages"])
    parsed = json.loads(final)
    assert "days" in parsed, f"No 'days' key in {parsed}"
    assert len(parsed["days"]) == 2

    # Each day should have 3-5 items
    all_pois = []
    for day in parsed["days"]:
        assert "day_index" in day
        assert "theme" in day
        assert "items" in day
        assert 2 <= len(day["items"]) <= 5, f"Day {day['day_index']}: {len(day['items'])} items"
        for item in day["items"]:
            assert "poi_name" in item
            assert "duration_h" in item
            assert item["duration_h"] > 0
            all_pois.append(item["poi_name"])

    # No duplicate POIs across days
    assert len(all_pois) == len(set(all_pois)), f"Duplicates: {all_pois}"


def test_multi_turn_memory(agent):
    """Multi-turn: plan day by day — agent remembers what was assigned."""
    thread = {"configurable": {"thread_id": "test_memory"}}

    # Turn 1: Plan day 1
    r1 = agent.invoke(
        {"messages": [{"role": "user", "content": "请为北京2日游规划第一天的行程"}]},
        config=thread,
    )
    j1 = json.loads(_get_final_json(r1["messages"]))
    day1_pois = {item["poi_name"] for day in j1["days"] for item in day["items"]}
    assert len(day1_pois) >= 2, f"Day1 too few POIs: {day1_pois}"

    # Turn 2: Plan day 2 — should NOT reuse day 1's POIs
    r2 = agent.invoke(
        {"messages": [{"role": "user", "content": "现在规划第二天"}]},
        config=thread,
    )
    j2 = json.loads(_get_final_json(r2["messages"]))
    day2_pois = {item["poi_name"] for day in j2["days"] for item in day["items"]}
    assert len(day2_pois) >= 2, f"Day2 too few POIs: {day2_pois}"

    # Day 2 should not reuse Day 1 POIs
    overlap = day1_pois & day2_pois
    assert not overlap, f"Memory leak — these POIs appear in both days: {overlap}"


def test_cross_restart_persistence():
    """Simulate server restart: a NEW agent instance recovers old memory."""
    thread = {"configurable": {"thread_id": "test_restart"}}

    # "Before restart" — agent instance 1
    agent1 = create_itinerary_gen()
    r1 = agent1.invoke(
        {"messages": [{"role": "user", "content": "请为上海1日游规划第一天的行程"}]},
        config=thread,
    )
    j1 = json.loads(_get_final_json(r1["messages"]))
    day1_pois = {item["poi_name"] for day in j1["days"] for item in day["items"]}

    # "After restart" — agent instance 2 (same thread_id)
    agent2 = create_itinerary_gen()
    r2 = agent2.invoke(
        {"messages": [{"role": "user", "content": "现在规划第二天"}]},
        config=thread,
    )
    j2 = json.loads(_get_final_json(r2["messages"]))
    day2_pois = {item["poi_name"] for day in j2["days"] for item in day["items"]}

    # Day 2 must not reuse Day 1 POIs — persistence worked
    overlap = day1_pois & day2_pois
    assert not overlap, f"Restart persistence failed — overlap: {overlap}"
    assert len(day2_pois) >= 2, f"Day2 too few POIs: {day2_pois}"


def test_search_before_plan(agent):
    """Agent must call search_attractions before assigning POIs."""
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "规划一个上海1日游"}]},
        config={"configurable": {"thread_id": "test_search"}},
    )

    tool_calls = [
        tc["name"]
        for msg in result["messages"]
        if getattr(msg, "tool_calls", None)
        for tc in msg.tool_calls
    ]
    assert "search_attractions" in tool_calls, f"Agent skipped search: {tool_calls}"


def _get_final_json(messages: list) -> str:
    """Extract JSON object/array from the final AIMessage."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = getattr(msg, "content", "")
            if not content:
                continue
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
            # Find JSON by brace/bracket
            for start_ch, end_ch in [("{", "}"), ("[", "]")]:
                start = content.find(start_ch)
                end = content.rfind(end_ch)
                if start != -1 and end > start:
                    return content[start:end + 1]
            return content
    return ""
