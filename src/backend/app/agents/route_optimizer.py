"""Route Optimizer Agent — Step 5 + Step 7.6 of agent learning path.

CHAINED Agent: receives itinerary_gen's output → geocodes + times the route.
Fill order stays unless it fails sanity checks; nearest-neighbor is the fallback.
travel_minutes_from_prev is the adopted schedule leg (Amap when verified).

This agent does NOT use a Checkpointer (no multi-turn memory needed — it's a
one-shot transformation).
"""
from langchain.agents import create_agent

from app.agents.tools.route_optimizer import optimize_itinerary
from app.core.llm import chat_model


def create_route_optimizer():
    """Create a route optimizer agent with the optimize_itinerary tool."""
    model = chat_model()

    return create_agent(
        model=model,
        tools=[optimize_itinerary],
        system_prompt=(
            "你是一个路线优化助手。你的工作流程：\n"
            "1. 收到行程 JSON 后，调用 optimize_itinerary 工具处理\n"
            "2. 工具会自动：地理编码 → 按原顺序计时；只在绕路或顺序无效时才最近邻重排\n"
            "3. 将工具返回的结果直接输出给用户，不要修改任何内容\n\n"
            "输出格式：直接输出工具返回的 JSON，不要添加任何额外文字或解释。\n"
            "重要：必须调用 optimize_itinerary 工具，不要跳过。"
        ),
    )
