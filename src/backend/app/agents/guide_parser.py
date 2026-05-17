"""Guide Parser Agent — Step 3 of agent learning path.

Parses unstructured travelogue text into structured Source Entities.
Agent calls geocode_poi in a LOOP — LLM decides how many calls to make.
"""

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from app.agents.tools.geo import geocode_poi
from app.core.config import settings


def create_guide_parser():
    """Create a guide-parsing agent that extracts POIs from travelogues."""
    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )

    return create_agent(
        model=model,
        tools=[geocode_poi],
        system_prompt=(
            "你是一个旅行攻略解析助手。你的工作流程：\n"
            "1. 阅读用户提供的游记/攻略文本\n"
            "2. 提取文中提到的所有景点（POI）\n"
            "3. 推断每个景点属于第几天（day_index），从 1 开始；同一天内的景点按出现顺序编号（seq）\n"
            "4. 对每个景点调用 geocode_poi 获取坐标\n"
            "5. 收集所有结果后，按 JSON 数组格式输出候选列表\n\n"
            "输出 JSON 格式（不要包含其他文字）：\n"
            '[{"poi_name": "...", "day_index": 1, "seq": 1, "lat": 0.0, "lng": 0.0}, ...]\n\n'
            "规则：\n"
            "- 如果原文没有明确分天，则所有景点归入 day_index=1\n"
            "- 如果同一个景点出现多次，只保留第一次\n"
            "- 坐标使用 geocode_poi 返回的值"
        ),
    )
