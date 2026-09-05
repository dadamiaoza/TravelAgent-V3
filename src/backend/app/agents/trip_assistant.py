"""Trip Assistant — one LangGraph agent, tools chosen per turn.

Conversation memory uses PostgresSaver with thread prefix trip-chat-{id},
isolated from generation threads trip-{id}. Itinerary truth is reloaded
from the DB every turn and passed in the user message, not from memory.
"""
from __future__ import annotations

import json
import re

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import connect
from psycopg.rows import dict_row

from app.core.config import settings
from app.services.trip_chat import WRITE_MODE_AUTO

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)

_conn = connect(settings.database_url, autocommit=True, prepare_threshold=0, row_factory=dict_row)
_checkpointer = PostgresSaver(_conn)

TRIP_ASSISTANT_SYSTEM_PROMPT = (
    "你是行程协作助手 Trip Assistant。根据用户消息自己决定调用哪些工具，"
    "一轮可以 0、1 或多个。工具是普通函数，不是其他 Agent。\n"
    "规则：\n"
    "1. 改行程（删点、加点、改时间、重排当天已有节点）必须调用 propose_delta；"
    "只提议模式下禁止写库。\n"
    "2. 问天气、开放时间、是否闭馆，调用 check_facts。需要先核实再决定是否删除时，"
    "先 check_facts，再按需要 propose_delta。\n"
    "3. 仅当写库模式为「授权后自动采纳」且用户明确要求改行程时，才可调用 apply_delta。\n"
    "4. 禁止规划整份新行程，禁止调用 itinerary_gen / 路线 Agent / Supervisor。\n"
    "5. 当天重排只针对已有节点（reorder），不要发明一套新景点。\n"
    "6. 用中文直接回复用户，说明你查到的事实或建议；不要只输出 JSON。"
)


def create_trip_assistant(tools, write_mode: str = "propose"):
    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )
    mode_line = (
        "当前写库模式：授权后自动采纳，允许 apply_delta。"
        if write_mode == WRITE_MODE_AUTO
        else "当前写库模式：只提议，禁止 apply_delta。"
    )
    return create_agent(
        model=model,
        tools=tools,
        checkpointer=_checkpointer,
        system_prompt=f"{TRIP_ASSISTANT_SYSTEM_PROMPT}\n{mode_line}",
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


def invoke_trip_assistant(
    *,
    tools,
    context: dict,
    message: str,
    thread_id: str,
    write_mode: str = "propose",
) -> str:
    agent = create_trip_assistant(tools, write_mode)
    mode_label = (
        "授权后自动采纳（可以 apply_delta 写库）"
        if write_mode == WRITE_MODE_AUTO
        else "只提议（不得写库，修改一律 propose_delta）"
    )
    user_content = (
        f"写库模式：{mode_label}\n"
        f"当前行程 JSON：\n{json.dumps(context, ensure_ascii=False)}\n\n"
        f"用户消息：{message}"
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_content}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    messages = result.get("messages") if isinstance(result, dict) else None
    last = messages[-1] if messages else result
    return _content_to_text(getattr(last, "content", last))
