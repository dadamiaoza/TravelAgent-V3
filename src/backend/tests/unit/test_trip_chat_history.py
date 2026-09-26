"""Chat history resume: display filter, model trim, and history API."""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.trip_assistant import (
    DISPLAY_HISTORY_LIMIT,
    MODEL_CONTEXT_TURNS,
    get_chat_history,
    messages_for_display,
    trim_messages_to_turns,
)
from app.db.session import get_db
from app.main import app


def test_trim_messages_to_turns_keeps_last_n_human_turns() -> None:
    messages = []
    for i in range(15):
        messages.append(HumanMessage(content=f"u{i}"))
        messages.append(AIMessage(content=f"a{i}"))
    trimmed = trim_messages_to_turns(messages, max_turns=12)
    humans = [m for m in trimmed if isinstance(m, HumanMessage)]
    assert len(humans) == 12
    assert humans[0].content == "u3"
    assert trimmed[-1].content == "a14"


def test_trim_messages_to_turns_keeps_tool_groups() -> None:
    messages = [
        HumanMessage(content="old"),
        AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": "1"}]),
        ToolMessage(content="tool-old", tool_call_id="1"),
        AIMessage(content="old-reply"),
    ]
    for i in range(12):
        messages.append(HumanMessage(content=f"u{i}"))
        messages.append(AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": str(i)}]))
        messages.append(ToolMessage(content=f"tool-{i}", tool_call_id=str(i)))
        messages.append(AIMessage(content=f"a{i}"))
    trimmed = trim_messages_to_turns(messages, max_turns=MODEL_CONTEXT_TURNS)
    assert isinstance(trimmed[0], HumanMessage)
    assert trimmed[0].content == "u0"
    assert not any(isinstance(m, HumanMessage) and m.content == "old" for m in trimmed)
    # tool message for u0 still present
    assert any(isinstance(m, ToolMessage) and m.content == "tool-0" for m in trimmed)


def test_trim_under_limit_is_noop_copy() -> None:
    messages = [HumanMessage(content="u"), AIMessage(content="a")]
    trimmed = trim_messages_to_turns(messages, max_turns=12)
    assert len(trimmed) == 2
    assert trimmed[0].content == "u"


def test_messages_for_display_filters_noise_and_caps() -> None:
    messages: list = [SystemMessage(content="sys")]
    for i in range(40):
        messages.append(HumanMessage(content=f"user-{i}"))
        messages.append(AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": str(i)}]))
        messages.append(ToolMessage(content=f"tool-{i}", tool_call_id=str(i)))
        messages.append(AIMessage(content=f"ai-{i}"))
    bubbles = messages_for_display(messages, limit=DISPLAY_HISTORY_LIMIT)
    users = [b for b in bubbles if b["role"] == "user"]
    ais = [b for b in bubbles if b["role"] == "ai"]
    # 40 user turns → keep last 30 turns → 30 user + 30 ai bubbles (tools filtered)
    assert len(users) == DISPLAY_HISTORY_LIMIT
    assert len(ais) == DISPLAY_HISTORY_LIMIT
    assert len(bubbles) == DISPLAY_HISTORY_LIMIT * 2
    assert bubbles[0]["role"] == "user"
    assert bubbles[0]["content"] == "user-10"  # last 30 of 40 starts at index 10
    assert bubbles[-1] == {"role": "ai", "content": "ai-39"}
    assert all(b["role"] in {"user", "ai"} for b in bubbles)
    assert not any("tool-" in b["content"] for b in bubbles)


def test_messages_for_display_keeps_exactly_n_user_turns() -> None:
    """Display cap is user turns, not total bubbles."""
    messages: list = []
    for i in range(35):
        messages.append(HumanMessage(content=f"u{i}"))
        messages.append(AIMessage(content=f"a{i}"))
    bubbles = messages_for_display(messages, limit=30)
    users = [b for b in bubbles if b["role"] == "user"]
    ais = [b for b in bubbles if b["role"] == "ai"]
    assert len(users) == 30
    assert len(ais) == 30
    assert users[0]["content"] == "u5"
    assert ais[-1]["content"] == "a34"
    # Multi-AI within a turn still counts as one user turn
    multi = [
        HumanMessage(content="old"),
        AIMessage(content="old-a"),
    ]
    for i in range(30):
        multi.append(HumanMessage(content=f"keep-{i}"))
        multi.append(AIMessage(content="", tool_calls=[{"name": "t", "args": {}, "id": str(i)}]))
        multi.append(ToolMessage(content=f"tool-{i}", tool_call_id=str(i)))
        multi.append(AIMessage(content=f"keep-ai-{i}"))
    multi_bubbles = messages_for_display(multi, limit=30)
    multi_users = [b for b in multi_bubbles if b["role"] == "user"]
    assert len(multi_users) == 30
    assert multi_users[0]["content"] == "keep-0"
    assert not any(b["content"] == "old" for b in multi_bubbles)


def test_messages_for_display_empty() -> None:
    assert messages_for_display([]) == []


def test_get_chat_history_empty_thread() -> None:
    with patch("app.agents.trip_assistant.load_thread_messages", return_value=[]):
        out = get_chat_history("trip-chat-00000000-0000-0000-0000-000000000000")
    assert out["messages"] == []
    assert out["thread_id"].startswith("trip-chat-")


def test_history_api_empty() -> None:
    trip_id = uuid4()
    db = MagicMock()
    trip = MagicMock(id=trip_id, days=[])
    db.query.return_value.filter.return_value.first.return_value = trip

    original = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with (
            patch("app.api.v1.trips._owned_or_404", return_value=trip),
            patch(
                "app.api.v1.trips.get_chat_history",
                return_value={"thread_id": f"trip-chat-{trip_id}", "messages": []},
            ),
        ):
            response = TestClient(app).get(f"/api/v1/trips/{trip_id}/chat/history")
    finally:
        if original is not None:
            app.dependency_overrides[get_db] = original
        else:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert body["thread_id"] == f"trip-chat-{trip_id}"
    assert body["messages"] == []


def test_history_api_returns_capped_bubbles() -> None:
    trip_id = uuid4()
    db = MagicMock()
    trip = MagicMock(id=trip_id, days=[])
    messages = [{"role": "user", "content": f"u{i}"} for i in range(5)]
    messages += [{"role": "ai", "content": f"a{i}"} for i in range(5)]

    original = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with (
            patch("app.api.v1.trips._owned_or_404", return_value=trip),
            patch(
                "app.api.v1.trips.get_chat_history",
                return_value={"thread_id": f"trip-chat-{trip_id}", "messages": messages},
            ),
        ):
            response = TestClient(app).get(f"/api/v1/trips/{trip_id}/chat/history")
    finally:
        if original is not None:
            app.dependency_overrides[get_db] = original
        else:
            app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    body = response.json()
    assert len(body["messages"]) == 10
    assert body["messages"][0]["role"] == "user"
