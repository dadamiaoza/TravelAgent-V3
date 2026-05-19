"""Chat API — Supervisor-powered multi-agent conversation endpoint.

A single entry point that replaces calling individual agent endpoints.
The Supervisor decides which specialized agent(s) to invoke based on
the user's natural language request.
"""
import uuid

from fastapi import APIRouter
from langchain_core.messages import AIMessage

from app.agents.supervisor import create_supervisor_agent
from app.schemas.trip import ChatRequest, ChatOut

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatOut)
def chat(body: ChatRequest):
    """Send a message to the AI travel assistant.

    The Supervisor agent will automatically decide which specialized
    agent (guide_parser, itinerary_gen, route_optimizer, fact_checker)
    to invoke based on the message content.
    """
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
