"""Itinerary Generator Agent — Step 4 of agent learning path.

Agent with MEMORY (LangGraph PostgresSaver) — remembers prior planning
decisions across multi-turn conversations and across server restarts.
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import connect
from psycopg.rows import dict_row

from app.agents.tools.attractions import search_attractions
from app.core.config import settings

_conn = connect(settings.database_url, autocommit=True, prepare_threshold=0, row_factory=dict_row)
_checkpointer = PostgresSaver(_conn)

ITINERARY_GEN_TOOLS = [search_attractions]
ITINERARY_GEN_SYSTEM_PROMPT = (
    "你是一个旅行行程规划助手。你的工作流程：\n"
    "1. 收到用户请求后，最多调用一次 search_attractions 获取目的地景点池\n"
    "2. 根据用户的天数要求，将景点合理分配到每一天，然后直接输出完整 JSON\n"
    "3. 不要估算或查询交通时间；travel_minutes_from_prev 一律填 0，后续由路线优化补全\n"
    "4. 确保：每天 3-5 个景点、类型多样化、节奏合理（总时长含交通 < 10h）\n"
    "5. 多轮对话时，查看历史记录避免与已规划天重复使用景点\n\n"
    "输出 JSON 格式（不要包含其他文字）：\n"
    '{"days": [{"day_index": 1, "theme": "主题概括", "route_type": "city", "items": ['
    '{"seq": 1, "poi_name": "...", "city": "所在城市", "duration_h": 0, '
    '"best_time": null, "cost_note": null, "tips": null, "travel_minutes_from_prev": 0}, ...]}]}\n\n'
    "规则：\n"
    "- theme 用简短中文概括当天主题（如「西湖经典一日」「皇城文化深度」）\n"
    "- route_type 只能是 city 或 scenic：city = 城市常规景点，按城市道路/公交可达；scenic = 景区内部（如山地景区、森林公园），内部需要步道/索道/接驳车往返\n"
    "- 如果某天主要活动都在同一个景区内（如武功山、黄山、张家界），必须标记为 scenic，不能标成 city\n"
    "- 如果一天内同时有城市点和多个景区，route_type 只作为默认值，系统会按每个 POI 是否属于景区来分路段选择步行/驾车或公交\n"
    "- 大型景区（武功山、黄山、张家界等）不要只写一个“XX景区 8小时”，必须拆成 3-5 个具体节点：游客中心、索道站、观景台、核心景点等\n"
    "- 同一天尽量安排地理上相邻的景点；如果两个景点距离很远，不要硬塞在同一天\n"
    "- 如果当天需要从上一个城市/景区转场，请在 theme 中简单说明，例如“Day3 武功山（从市区约1.5小时车程）”\n"
    "- city 填写该景点实际所在城市；与行程目的地相同可省略，跨城景点必须填写\n"
    "- best_time 只能是 morning / afternoon / evening / all_day 或 null，不要猜\n"
    "- cost_note 仅在确知门票/花费时填写短中文，否则 null；不要编造价格\n"
    "- tips 一句中文怎么玩（亮点或注意），不要写成段落，不要把开馆时间写进 tips\n"
    "- travel_minutes_from_prev 一律填 0\n"
    "- 如果用户分多次规划（多轮对话），务必检查历史消息已分配的景点，不要重复"
)


def create_itinerary_gen():
    """Create an itinerary planning agent with PostgresSaver checkpointer."""
    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )

    return create_agent(
        model=model,
        tools=ITINERARY_GEN_TOOLS,
        checkpointer=_checkpointer,
        system_prompt=ITINERARY_GEN_SYSTEM_PROMPT,
    )
