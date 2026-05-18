"""Fact checking API — Agent-powered weather & opening hours validation."""
import json
import re

from fastapi import APIRouter, HTTPException
from langchain_core.messages import AIMessage

from app.agents.fact_checker import create_fact_checker
from app.schemas.trip import FactCheckRequest, FactCheckOut, FactCheckResult

router = APIRouter(prefix="/facts", tags=["facts"])


@router.post("/check", response_model=FactCheckOut)
def check_facts(body: FactCheckRequest):
    """Check weather and opening hours for a list of itinerary items."""
    agent = create_fact_checker()

    poi_list = "\n".join(f"- {item.date}: {item.poi_name}" for item in body.items)
    prompt = f"请检查以下行程节点的时效信息（天气和开放时间）：\n{poi_list}"

    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})

    raw = _extract_json(result["messages"])
    results = []
    for item in raw:
        results.append(FactCheckResult(
            poi_name=item.get("poi_name", ""),
            date=item.get("date", ""),
            weather=item.get("weather"),
            opening_hours=item.get("opening_hours"),
            risk=item.get("risk"),
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
