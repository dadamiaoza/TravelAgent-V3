"""Route Optimizer Agent — Step 5 + Step 7.6 of agent learning path.

CHAINED Agent: receives itinerary_gen's output → geocodes + route-optimizes → returns
itinerary with lat/lng filled, POIs reordered by real travel times, and accurate
travel_minutes_from_prev.

This agent does NOT use a Checkpointer (no multi-turn memory needed — it's a
one-shot transformation).
"""
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from app.agents.tools.route_optimizer import optimize_itinerary
from app.core.config import settings


def create_route_optimizer():
    """Create a route optimizer agent with the optimize_itinerary tool."""
    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )

    return create_agent(
        model=model,
        tools=[optimize_itinerary],
        system_prompt=(
            "你是一个路线优化助手。你的工作流程：\n"
            "1. 收到行程 JSON 后，调用 optimize_itinerary 工具处理\n"
            "2. 工具会自动：地理编码 → 路径规划 → POI 重排序 → 交通时间填充\n"
            "3. 将工具返回的结果直接输出给用户，不要修改任何内容\n\n"
            "输出格式：直接输出工具返回的 JSON，不要添加任何额外文字或解释。\n"
            "重要：必须调用 optimize_itinerary 工具，不要跳过。"
        ),
    )
