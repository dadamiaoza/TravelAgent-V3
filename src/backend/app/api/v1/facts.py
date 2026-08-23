"""Fact checking API — Agent-powered weather & opening hours validation."""
import json
import re
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage

from app.agents.fact_checker import create_fact_checker
from app.schemas.trip import FactCheckRequest, FactCheckOut, FactCheckResult
from app.services.closure_rules import evaluate_closure_rule

router = APIRouter(prefix="/facts", tags=["facts"])


@router.post("/check", response_model=FactCheckOut)
def check_facts(body: FactCheckRequest):
    """Check weather and opening hours for a list of itinerary items."""
    agent = create_fact_checker()

    poi_list = "\n".join(f"- {item.date}: {item.poi_name}" for item in body.items)

    # 第 1 层：规则引擎是确定性逻辑，由后端预先算好再交给 LLM 汇总，
    # 不依赖 LLM 是否“想起来调用”。
    rule_lines = []
    for item in body.items:
        rule_result = evaluate_closure_rule(item.poi_name, item.date)
        rule_lines.append(
            f"- {item.date} {item.poi_name}: {json.dumps(rule_result, ensure_ascii=False)}"
        )

    prompt = (
        "请检查以下行程节点的时效信息（天气和开放时间）：\n"
        f"{poi_list}\n\n"
        "规则引擎结果（已预计算，第 1 层）：\n"
        f"{chr(10).join(rule_lines)}\n\n"
        "请调用 get_weather 和 get_opening_hours 获取动态信息，"
        "并用统一 JSON 数组输出每个节点的风险汇总。"
        "数组元素字段：poi_name/date/risk/risk_type/reason/source/weather/"
        "opening_hours/needs_manual_confirmation/advice。"
        "产品原则：只输出风险提示和来源，不承诺 100% 准确，"
        "建议出行前再确认。"
    )

    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})

    raw = _extract_json(result["messages"])
    checked_at = datetime.now(timezone.utc).isoformat()
    results = []
    for item in raw:
        results.append(FactCheckResult(
            poi_name=item.get("poi_name", ""),
            date=item.get("date", ""),
            weather=item.get("weather"),
            opening_hours=item.get("opening_hours"),
            risk=item.get("risk"),
            risk_type=item.get("risk_type"),
            reason=item.get("reason"),
            source=item.get("source"),
            needs_manual_confirmation=item.get("needs_manual_confirmation", True),
            advice=item.get("advice"),
            checked_at=checked_at,
        ))

    return FactCheckOut(results=results)


def _extract_json(messages: list) -> list:
    """Extract JSON array from agent messages."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = getattr(msg, "content", "")
            if not content:
                continue
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end > start:
                return json.loads(content[start:end + 1])
    raise HTTPException(status_code=500, detail="Agent did not return valid JSON")
