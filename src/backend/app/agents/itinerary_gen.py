"""Itinerary Generator Agent — Step 4 of agent learning path.

Agent with MEMORY (LangGraph PostgresSaver) — remembers prior planning
decisions across multi-turn conversations and across server restarts.
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import connect
from psycopg.rows import dict_row

from app.agents.tools.attractions import search_attractions, get_travel_time
from app.core.config import settings

_conn = connect(settings.database_url, autocommit=True, prepare_threshold=0, row_factory=dict_row)
_checkpointer = PostgresSaver(_conn)


def create_itinerary_gen():
    """Create an itinerary planning agent with PostgresSaver checkpointer."""
    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )

    return create_agent(
        model=model,
        tools=[search_attractions, get_travel_time],
        checkpointer=_checkpointer,
        system_prompt=(
            "你是一个旅行行程规划助手。你的工作流程：\n"
            "1. 收到用户请求后，先调用 search_attractions 获取目的地景点池\n"
            "2. 根据用户的天数要求，将景点合理分配到每一天\n"
            "3. 对每天内相邻景点，调用 get_travel_time 估算交通时间\n"
            "4. 确保：每天 3-5 个景点、类型多样化、节奏合理（总时长含交通 < 10h）\n"
            "5. 多轮对话时，查看历史记录避免与已规划天重复使用景点\n\n"
            "输出 JSON 格式（不要包含其他文字）：\n"
            '{"days": [{"day_index": 1, "theme": "主题概括", "items": ['
            '{"seq": 1, "poi_name": "...", "duration_h": 0, "travel_minutes_from_prev": 0}, ...]}]}\n\n'
            "规则：\n"
            "- theme 用简短中文概括当天主题（如「西湖经典一日」「皇城文化深度」）\n"
            "- travel_minutes_from_prev 是到上一个景点的交通时间，第一个景点为 0\n"
            "- 如果用户分多次规划（多轮对话），务必检查历史消息已分配的景点，不要重复"
        ),
    )
