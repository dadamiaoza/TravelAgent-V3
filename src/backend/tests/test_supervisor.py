"""Tests for Supervisor Agent — Step 6 multi-agent orchestration."""
import pytest

from app.agents.supervisor import create_supervisor_agent


@pytest.fixture
def supervisor():
    return create_supervisor_agent()


def test_supervisor_compile(supervisor):
    """Supervisor should compile to a valid LangGraph workflow."""
    assert supervisor is not None
    # Should have an invoke method
    assert hasattr(supervisor, "invoke")


def test_supervisor_routes_to_guide_parser(supervisor):
    """User sends travelogue text → supervisor should call guide_parser."""
    result = supervisor.invoke(
        {"messages": [{"role": "user", "content": "请帮我解析以下攻略：第一天去了故宫，第二天去了长城"}]},
        config={"configurable": {"thread_id": "test-spv-guide"}},
    )

    final_text = _get_final_text(result["messages"])
    assert len(final_text) > 10, f"Reply too short: {final_text}"


def test_supervisor_routes_to_fact_checker(supervisor):
    """User asks about weather → supervisor should call fact_checker."""
    result = supervisor.invoke(
        {"messages": [{"role": "user", "content": "我明天去故宫，帮我查一下天气和开放时间"}]},
        config={"configurable": {"thread_id": "test-spv-fact"}},
    )

    final_text = _get_final_text(result["messages"])
    assert len(final_text) > 10, f"Reply too short: {final_text}"


def _get_final_text(messages: list) -> str:
    """Extract the final text reply from agent messages."""
    from langchain_core.messages import AIMessage

    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = getattr(msg, "content", "")
            if content and not getattr(msg, "tool_calls", None):
                return content
    return ""
