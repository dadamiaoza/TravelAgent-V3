"""Smoke: legacy POST /api/v1/chat stays ChatOut and is marked deprecated."""

from langchain_core.messages import AIMessage
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_legacy_chat_openapi_marks_learning_endpoint():
    spec = app.openapi()
    operation = spec["paths"]["/api/v1/chat"]["post"]
    assert operation["deprecated"] is True
    text = "\n".join(
        [
            operation.get("summary") or "",
            operation.get("description") or "",
            spec.get("info", {}).get("description") or "",
            next(tag["description"] for tag in spec["tags"] if tag["name"] == "chat"),
        ]
    )
    assert "LEGACY" in text
    assert "学习遗留" in text
    assert "GenerationJob" in text
    assert "/trips/{trip_id}/chat" in text
    header = operation["responses"]["200"]["headers"]["Deprecation"]
    assert header["schema"]["example"] == "true"
    body_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert body_schema["$ref"].endswith("/ChatOut")
    chat_out = spec["components"]["schemas"]["ChatOut"]
    assert set(chat_out["properties"]) == {"reply", "thread_id"}
    chat_in = spec["components"]["schemas"]["ChatRequest"]
    assert set(chat_in["properties"]) == {"message", "thread_id"}
    trip_chat = spec["paths"]["/api/v1/trips/{trip_id}/chat"]["post"]
    assert trip_chat.get("deprecated") is not True


def test_legacy_chat_returns_chat_out_with_deprecation_header(monkeypatch):
    class _FakeSupervisor:
        def invoke(self, payload, config):
            assert payload["messages"][0]["content"] == "你好"
            assert config["configurable"]["thread_id"] == "study-1"
            return {"messages": [AIMessage(content="遗留回复")]}

    monkeypatch.setattr("app.api.v1.chat.create_supervisor_agent", lambda: _FakeSupervisor())
    response = client.post(
        "/api/v1/chat",
        json={"message": "你好", "thread_id": "study-1"},
    )
    assert response.status_code == 200
    assert response.json() == {"reply": "遗留回复", "thread_id": "study-1"}
    assert response.headers["deprecation"] == "true"
