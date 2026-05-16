"""Fact Checker Agent — Step 1 of agent learning path.

Simplest agent: 1 tool (weather), 1 model (MiniMax), 1 system_prompt.
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from app.agents.tools.weather import get_weather
from app.core.config import settings


def create_fact_checker():
    """Create a fact-checking agent with weather tool."""
    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )

    return create_agent(
        model=model,
        tools=[get_weather],
        system_prompt=(
            "你是一个旅行时效校验助手。你的任务是："
            "1. 当用户询问某地某日天气时，调用 get_weather 工具查询"
            "2. 将查询结果用中文简洁地告诉用户"
            "3. 如果有风险提示（如暴雨、高温），主动提醒用户"
        ),
    )
