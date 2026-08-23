"""Fact Checker Agent — Step 2 of agent learning path.

Agent with 2 tools: weather + opening hours. LLM must decide which tool(s) to call.
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from app.agents.tools.weather import get_weather
from app.agents.tools.opening_hours import get_opening_hours
from app.core.config import settings


def create_fact_checker():
    """Create a fact-checking agent with weather + opening hours tools."""
    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )

    return create_agent(
        model=model,
        tools=[get_weather, get_opening_hours],
        system_prompt=(
            "你是一个旅行时效校验助手。根据用户问题，选择合适的工具查询："
            "1. 天气 → 调用 get_weather(city, date)"
            "2. 景点开放时间/门票 → 调用 get_opening_hours(name, date)"
            "用户消息中会附带规则引擎预计算结果，请结合工具查询结果统一汇总。\n\n"
            "输出格式：必须输出 JSON 数组，不要包含任何其他文字。\n"
            '数组元素字段：{"poi_name":"...", "date":"YYYY-MM-DD", '
            '"risk":"low|medium|high", '
            '"risk_type":"weekly_closure|holiday_adjustment|weather_risk|none", '
            '"reason":"...", "source":"...", "weather":"...", "opening_hours":"...", '
            '"needs_manual_confirmation":true, "advice":"..."}\n\n'
            "产品原则：只输出风险提示和来源，不承诺 100% 准确，建议出行前再确认。"
        ),
    )
