"""Agent integration tests — LangChain fact_checker with multi-tool routing."""
from app.agents.fact_checker import create_fact_checker


def test_agent_weather_tool():
    """LLM should choose get_weather for weather queries."""
    agent = create_fact_checker()
    result = agent.invoke({"messages": [{"role": "user", "content": "北京 2026-06-01 天气如何？"}]})
    called = [
        tc["name"]
        for msg in result["messages"]
        for tc in (getattr(msg, "tool_calls", None) or [])
    ]
    assert "get_weather" in called, f"Expected get_weather, got {called}"


def test_agent_opening_hours_tool():
    """LLM should choose get_opening_hours for attraction queries."""
    agent = create_fact_checker()
    result = agent.invoke({"messages": [{"role": "user", "content": "故宫博物院 2026-06-01 开门吗？门票多少钱？"}]})
    called = [
        tc["name"]
        for msg in result["messages"]
        for tc in (getattr(msg, "tool_calls", None) or [])
    ]
    assert "get_opening_hours" in called, f"Expected get_opening_hours, got {called}"


def test_agent_multi_tool():
    """LLM should call both tools for combined queries."""
    agent = create_fact_checker()
    result = agent.invoke({"messages": [{"role": "user", "content": "我计划 2026-06-01 去故宫，当天的天气和开放时间分别怎样？"}]})
    called = [
        tc["name"]
        for msg in result["messages"]
        for tc in (getattr(msg, "tool_calls", None) or [])
    ]
    assert "get_weather" in called, f"Missing get_weather in {called}"
    assert "get_opening_hours" in called, f"Missing get_opening_hours in {called}"
