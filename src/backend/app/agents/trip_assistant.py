"""Trip Assistant — one LangGraph agent, tools chosen per turn.

Conversation memory uses PostgresSaver with thread prefix trip-chat-{id},
isolated from generation threads trip-{id}. Itinerary truth is reloaded
from the DB every turn and injected via system_prompt (not checkpointed).
The user message is only the traveler's text.

History resume:
- Checkpointer keeps the full thread.
- Display API returns the most recent DISPLAY_HISTORY_LIMIT user turns
  (HumanMessage boundaries), flattened to user/ai bubbles for the FE.
- Model context is trimmed to MODEL_CONTEXT_TURNS user turns via middleware
  (checkpoint is not pruned).
"""
from __future__ import annotations

import json
import re
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import connect
from psycopg.rows import dict_row

from app.core.config import settings
from app.core.llm import chat_model
from app.services.trip_chat import WRITE_MODE_AUTO

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

# Display user turns (HumanMessage boundaries) returned by GET .../chat/history.
# Each turn includes its AI replies after flatten, so bubble count is typically ~2x.
DISPLAY_HISTORY_LIMIT = 30
# User turns (HumanMessage boundaries) the model sees each invoke.
MODEL_CONTEXT_TURNS = 12

_conn = connect(settings.database_url, autocommit=True, prepare_threshold=0, row_factory=dict_row)
_checkpointer = PostgresSaver(_conn)

TRIP_ASSISTANT_SYSTEM_PROMPT = (
    "你是行程协作助手 Trip Assistant。根据用户消息自己决定调用哪些工具，"
    "一轮可以 0、1 或多个。工具是普通函数，不是其他 Agent。\n"
    "规则：\n"
    "1. 改行程计划必须调用 propose_delta；只提议模式下禁止写库。\n"
    "   - 删除计划节点：action=delete\n"
    "   - 换成另一个景点：action=replace，poi_name=旧点，new_poi_name=新点\n"
    "   - 跨天移动：action=move，poi_name=地点，day_index=目标天\n"
    "   - 同天重排已有节点：action=reorder\n"
    "   - 改某点怎么玩：action=update，visit_tips=一句建议\n"
    "2. 改照片归属或去掉计划外停留，必须调用 propose_photo_change，不要用 propose_delta 删计划节点。\n"
    "   - 去掉计划外停留：action=dismiss_visit_stop，place_name=停留名（如望江公园）\n"
    "   - 把某地的照片改挂到计划节点：action=reassign_photo，place_name=现在所在地（停留名或未归类），poi_name=计划节点。整段计划外停留会并进该节点。\n"
    "   - 用户说「这张」且上下文有 current_photo_id：action=reassign_photo，place_name 留空，poi_name=计划节点\n"
    "   - 从地点拿掉：action=unassign_photo，place_name=现在所在地\n"
    "   - 不要向用户要文件名或照片 ID。禁止猜测 GPS、禁止看图认地、禁止编造上下文里没有的地点。\n"
    "3. 问天气、开放时间、是否闭馆，调用 check_facts。需要先核实再决定是否删除时，"
    "先 check_facts，再按需要 propose_delta。\n"
    "4. 用户粘贴攻略文本要加点，调用 parse_guide(text=攻略原文)。不要搜索网页。\n"
    "5. 仅当写库模式为「授权后自动采纳」且用户明确要求改行程或照片时，才可调用 apply_delta / apply_photo_change。\n"
    "6. 禁止规划整份新行程，禁止调用 itinerary_gen / 路线 Agent / Supervisor。\n"
    "7. 用中文直接回复用户；不要只输出 JSON。忽略历史消息里可能出现的过期行程 JSON，"
    "只以本轮系统提示中的当前行程为准。"
)

def _content_to_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
            elif hasattr(block, "text"):
                parts.append(str(block.text))
        text = "".join(parts)
    else:
        text = str(content)
    text = _THINK_RE.sub("", text).strip()
    return text



class _TrimModelContextMiddleware(AgentMiddleware):
    """Trim what the model sees; leave the checkpointer history intact."""

    def wrap_model_call(self, request: ModelRequest, handler):
        trimmed = trim_messages_to_turns(list(request.messages), MODEL_CONTEXT_TURNS)
        if len(trimmed) == len(request.messages):
            return handler(request)
        return handler(request.override(messages=trimmed))

    async def awrap_model_call(self, request: ModelRequest, handler):
        trimmed = trim_messages_to_turns(list(request.messages), MODEL_CONTEXT_TURNS)
        if len(trimmed) == len(request.messages):
            return await handler(request)
        return await handler(request.override(messages=trimmed))


def trim_messages_to_turns(
    messages: list[Any],
    max_turns: int = MODEL_CONTEXT_TURNS,
) -> list[Any]:
    """Keep the last ``max_turns`` user turns (from that HumanMessage onward).

    ToolMessage groups stay attached because we only cut at HumanMessage
    boundaries. Empty / non-positive limits return a shallow copy.
    """
    if max_turns <= 0 or not messages:
        return list(messages)
    human_indices = [i for i, msg in enumerate(messages) if _is_human(msg)]
    if len(human_indices) <= max_turns:
        return list(messages)
    start = human_indices[-max_turns]
    return list(messages[start:])


def _is_human(msg: Any) -> bool:
    if isinstance(msg, HumanMessage):
        return True
    if isinstance(msg, dict):
        return msg.get("role") in {"user", "human"} or msg.get("type") == "human"
    return getattr(msg, "type", None) == "human"


def _is_ai(msg: Any) -> bool:
    if isinstance(msg, AIMessage):
        return True
    if isinstance(msg, dict):
        return msg.get("role") in {"ai", "assistant"} or msg.get("type") == "ai"
    return getattr(msg, "type", None) == "ai"


def _is_tool_or_system(msg: Any) -> bool:
    if isinstance(msg, (ToolMessage, SystemMessage)):
        return True
    if isinstance(msg, dict):
        role = msg.get("role") or msg.get("type")
        return role in {"tool", "system"}
    return getattr(msg, "type", None) in {"tool", "system"}


def load_thread_messages(thread_id: str) -> list[Any]:
    """Load checkpoint messages for a trip-chat thread (may be empty)."""
    if not thread_id:
        return []
    config = {"configurable": {"thread_id": thread_id}}
    try:
        tup = _checkpointer.get_tuple(config)
    except Exception:
        return []
    if tup is None:
        return []
    checkpoint = getattr(tup, "checkpoint", None) or {}
    channel_values = checkpoint.get("channel_values") or {}
    messages = channel_values.get("messages") or []
    return list(messages)


def messages_for_display(
    messages: list[Any],
    *,
    limit: int = DISPLAY_HISTORY_LIMIT,
) -> list[dict[str, str]]:
    """Filter tool/system noise; keep the most recent ``limit`` user turns as bubbles.

    Truncates at HumanMessage boundaries (same as model-context trim), then
    flattens to role user|ai for the FE. Intervening AI replies that belong to
    those turns are kept; tool/system messages are dropped.
    """
    scoped = trim_messages_to_turns(messages, max_turns=limit) if limit > 0 else list(messages)
    bubbles: list[dict[str, str]] = []
    for msg in scoped:
        if _is_tool_or_system(msg):
            continue
        if _is_human(msg):
            raw = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
            content = _content_to_text(raw)
            if content:
                bubbles.append({"role": "user", "content": content})
            continue
        if _is_ai(msg):
            raw = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
            content = _content_to_text(raw)
            if not content:
                # Pure tool-call AI messages (empty content) are not bubbles.
                continue
            bubbles.append({"role": "ai", "content": content})
    return bubbles


def get_chat_history(thread_id: str, *, limit: int = DISPLAY_HISTORY_LIMIT) -> dict[str, Any]:
    """Return display-ready history for a checkpointer thread."""
    raw = load_thread_messages(thread_id)
    return {
        "thread_id": thread_id,
        "messages": messages_for_display(raw, limit=limit),
    }


def create_trip_assistant(tools, write_mode: str = "propose", itinerary_json: str = ""):
    model = chat_model()
    mode_line = (
        "当前写库模式：授权后自动采纳，允许 apply_delta / apply_photo_change。"
        if write_mode == WRITE_MODE_AUTO
        else "当前写库模式：只提议，禁止 apply_delta / apply_photo_change。"
    )
    itinerary_block = (
        f"\n当前行程（真源，每轮刷新；不要把这段存进对用户的回复）：\n{itinerary_json}"
        if itinerary_json
        else ""
    )
    return create_agent(
        model=model,
        tools=tools,
        checkpointer=_checkpointer,
        system_prompt=f"{TRIP_ASSISTANT_SYSTEM_PROMPT}\n{mode_line}{itinerary_block}",
        middleware=[_TrimModelContextMiddleware()],
    )



def invoke_trip_assistant(
    *,
    tools,
    context: dict,
    message: str,
    thread_id: str,
    write_mode: str = "propose",
) -> str:
    agent = create_trip_assistant(
        tools,
        write_mode,
        itinerary_json=json.dumps(context, ensure_ascii=False),
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": message}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    messages = result.get("messages") if isinstance(result, dict) else None
    last = messages[-1] if messages else result
    return _content_to_text(getattr(last, "content", last))
