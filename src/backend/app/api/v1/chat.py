"""LEGACY / 学习遗留 — POST /api/v1/chat（Supervisor 学习入口）。

不是生产助手。保留以便学习主管如何把请求交给子 Agent。
请勿接入行程页、我的行程、GenerationJob 或 trip_assistant。

生产替代：
- 生成：GenerationJob Worker（fill → route → verify → persist）
- 协作聊天：POST /trips/{id}/chat 与 /chat/stream（trip_assistant，线程 trip-chat-{id}）
"""
import uuid

from fastapi import APIRouter, Response
from langchain_core.messages import AIMessage

from app.agents.supervisor import create_supervisor_agent
from app.schemas.trip import ChatRequest, ChatOut

_LEGACY_DESCRIPTION = """LEGACY / 学习遗留，不是生产入口。

本接口仍可调用，请求与响应仍是 ChatRequest / ChatOut。它调用
create_supervisor_agent，只供学习多 Agent 编排。

生产路径：
- 行程生成：GenerationJob Worker（fill → route → verify → persist）
- 行程内协作聊天：POST /trips/{trip_id}/chat 与 /chat/stream
  （trip_assistant，线程 trip-chat-{id}）

不要把本接口接进行程页、我的行程、GenerationJob 或 trip_assistant。
"""

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    deprecated=True,
)


@router.post(
    "",
    response_model=ChatOut,
    deprecated=True,
    summary="[LEGACY] 学习遗留：Supervisor 聊天",
    description=_LEGACY_DESCRIPTION,
    responses={
        200: {
            "headers": {
                "Deprecation": {
                    "description": (
                        "此学习端点已弃用并保留。值为 true。"
                        "生产协作聊天是 POST /trips/{trip_id}/chat；"
                        "生产生成是 GenerationJob Worker。"
                    ),
                    "schema": {"type": "string", "example": "true"},
                }
            }
        }
    },
)
def chat(body: ChatRequest, response: Response):
    """LEGACY / 学习遗留。Supervisor 学习聊天，返回 ChatOut。

    生产协作聊天请用 POST /trips/{trip_id}/chat。生产生成走 GenerationJob Worker。
    """
    response.headers["Deprecation"] = "true"
    supervisor = create_supervisor_agent()

    # Each conversation has a unique thread_id for memory
    thread_id = body.thread_id or f"chat-{uuid.uuid4().hex[:8]}"

    result = supervisor.invoke(
        {"messages": [{"role": "user", "content": body.message}]},
        config={"configurable": {"thread_id": thread_id}},
    )

    # Extract the final text reply from the last AI message
    reply = _extract_reply(result["messages"])

    return ChatOut(reply=reply, thread_id=thread_id)


def _extract_reply(messages: list) -> str:
    """Extract the final text reply from agent messages."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = getattr(msg, "content", "")
            if content and not getattr(msg, "tool_calls", None):
                return content
    return "抱歉，Agent 没有返回有效的回复。"
