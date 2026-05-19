"""Supervisor Agent — Step 6 of agent learning path.

MULTI-AGENT ORCHESTRATION: A supervisor agent that manages 4 specialized
sub-agents. The supervisor uses Tool Calling to decide which sub-agent to
hand off to based on the user's request.

Sub-agents:
  - guide_parser:    Parse travelogue text → structured POI list
  - itinerary_gen:   Generate full itinerary (with PostgresSaver memory)
  - route_optimizer: Fill lat/lng coordinates (thin, one-shot)
  - fact_checker:    Check weather & opening hours

Architecture:
  The supervisor is itself an Agent where the "tools" are other Agents.
  langgraph_supervisor.create_supervisor auto-generates handoff tools.
"""
from langchain_openai import ChatOpenAI
from langgraph_supervisor import create_supervisor
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import connect
from psycopg.rows import dict_row

from app.agents.guide_parser import create_guide_parser
from app.agents.itinerary_gen import create_itinerary_gen
from app.agents.route_optimizer import create_route_optimizer
from app.agents.fact_checker import create_fact_checker
from app.core.config import settings

# ── Module-level DB connection for supervisor's own PostgresSaver ──
_conn = connect(settings.database_url, autocommit=True, prepare_threshold=0, row_factory=dict_row)
_supervisor_checkpointer = PostgresSaver(_conn)


def create_supervisor_agent():
    """Create the multi-agent supervisor.

    Returns a compiled LangGraph workflow that manages all 4 sub-agents.
    The supervisor decides which agent(s) to invoke based on user input.
    """
    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )

    # ── Create sub-agents with unique names ──
    guide_parser = create_guide_parser()
    guide_parser.name = "guide_parser"

    itinerary_gen = create_itinerary_gen()
    itinerary_gen.name = "itinerary_gen"

    route_optimizer = create_route_optimizer()
    route_optimizer.name = "route_optimizer"

    fact_checker = create_fact_checker()
    fact_checker.name = "fact_checker"

    # ── Create supervisor workflow ──
    workflow = create_supervisor(
        agents=[guide_parser, itinerary_gen, route_optimizer, fact_checker],
        model=model,
        prompt=(
            "你是一个旅行规划团队的主管（Supervisor），管理以下 4 个专家 Agent：\n\n"
            "1. **guide_parser**（攻略解析专家）\n"
            "   - 能力：把游记、攻略等纯文本解析成结构化的景点列表\n"
            "   - 何时调用：用户提供了一段游记/攻略文本，需要提取景点信息\n"
            "   - 触发词：解析、提取景点、攻略、游记、这篇帖子\n\n"
            "2. **itinerary_gen**（行程生成专家）\n"
            "   - 能力：根据目的地、天数、偏好生成完整的每日行程计划\n"
            "   - 何时调用：用户想规划一趟旅行，指定了目的地和天数\n"
            "   - 触发词：规划行程、帮我安排、几日游、去XX玩\n\n"
            "3. **route_optimizer**（路线优化专家）\n"
            "   - 能力：为已有行程的每个景点填充地理坐标（lat/lng）\n"
            "   - 何时调用：行程已生成，需要补坐标或优化游览顺序\n"
            "   - 注意：通常在 itinerary_gen 之后调用\n\n"
            "4. **fact_checker**（时效校验专家）\n"
            "   - 能力：检查景点的天气和开放时间，评估出行风险\n"
            "   - 何时调用：用户关心天气、开放时间、能不能去\n"
            "   - 触发词：天气、开放时间、会不会下雨、能不能去\n\n"
            "规则：\n"
            "- 分析用户意图，选择合适的专家处理\n"
            "- 如果用户需求涉及多个专家，按逻辑顺序逐一调用\n"
            "- 规划行程时，先调 itinerary_gen 生成，再调 route_optimizer 补坐标\n"
            "- 一次性需求只调一个专家即可\n"
            "- 用中文回复用户"
        ),
    )

    # ── Compile with supervisor's own checkpointer for conversation memory ──
    app = workflow.compile(checkpointer=_supervisor_checkpointer)
    return app
