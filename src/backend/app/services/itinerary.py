"""Itinerary generation service — powered by LangChain itinerary_gen Agent.

Replaces the mock template generator with real AI-generated itineraries.
"""

import json
import re
from datetime import date, time

from sqlalchemy.orm import Session

from app.agents.itinerary_gen import create_itinerary_gen
from app.agents.route_optimizer import create_route_optimizer
from app.models.trip import Trip
from app.services.itinerary_persistence import persist_itinerary


def _item_duration_minutes(item, default_h: float = 1.5) -> int:
    """从已有 start/end 推导游玩时长；没有时间则用默认时长。"""
    if item.start_time and item.end_time:
        start_min = item.start_time.hour * 60 + item.start_time.minute
        end_min = item.end_time.hour * 60 + item.end_time.minute
        if end_min > start_min:
            return end_min - start_min
    return int(default_h * 60)


def recalculate_day_schedule(day, start_minute: int = 9 * 60):
    """按节点顺序+交通时间重新计算当天的 start_time/end_time。"""
    items = sorted(day.items, key=lambda it: it.seq)
    current_minute = start_minute

    for idx, item in enumerate(items):
        if idx > 0:
            current_minute += item.travel_minutes or 0
        duration_min = _item_duration_minutes(item)
        end_minute = current_minute + duration_min
        item.start_time = time(current_minute // 60 % 24, current_minute % 60)
        item.end_time = time(end_minute // 60 % 24, end_minute % 60)
        current_minute = end_minute

    return day


def generate_itinerary_draft(
    *,
    destination: str,
    city: str = "",
    start_date: date,
    end_date: date,
    people_count: int = 1,
    budget_min: int | None = None,
    budget_max: int | None = None,
    user_prompt: str | None = None,
    must_visit: list[str] | None = None,
    thread_id: str = "itinerary",
) -> dict:
    """Generate a pure itinerary draft. Does NOT touch the database.

    This is the generator strategy used by the application orchestrator.
    """
    agent = create_itinerary_gen()

    day_count = (end_date - start_date).days + 1
    prompt = (
        f"请为{destination}{day_count}日游规划完整行程。"
        f"旅行日期：{start_date} 至 {end_date}。"
        f"人数：{people_count}人。"
    )
    if budget_min and budget_max:
        prompt += f"预算范围：{budget_min}-{budget_max}元。"
    elif budget_min:
        prompt += f"最低预算：{budget_min}元。"
    elif budget_max:
        prompt += f"最高预算：{budget_max}元。"

    if user_prompt:
        prompt += f"\n用户补充需求：{user_prompt}\n"
    if must_visit:
        prompt += f"\n必须包含用户指定的地点：{', '.join(must_visit)}\n"

    result = agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"configurable": {"thread_id": thread_id}},
    )

    itinerary = _parse_agent_output(result["messages"])

    # 把目的地城市写入行程 JSON，让路线优化地理编码时消除同名 POI 歧义
    itinerary["city"] = city or destination

    return _run_route_optimizer(itinerary)


def generate_itinerary(db: Session, trip: Trip) -> Trip:
    """Compatibility wrapper: generate a draft and persist it.

    New code should call trip_editor.regenerate_trip() instead.
    """
    draft = generate_itinerary_draft(
        destination=trip.destination,
        city=trip.city or "",
        start_date=trip.start_date,
        end_date=trip.end_date,
        people_count=trip.people_count,
        budget_min=trip.budget_min,
        budget_max=trip.budget_max,
        user_prompt=trip.user_prompt,
        must_visit=trip.must_visit,
        thread_id=f"trip-{trip.id}",
    )
    persist_itinerary(db, trip, draft, trip.start_date)
    return trip


def _run_route_optimizer(itinerary: dict) -> dict:
    """Pass the itinerary through the route_optimizer Agent to fill lat/lng."""
    agent = create_route_optimizer()
    itinerary_json = json.dumps(itinerary, ensure_ascii=False)
    prompt = (
        "请调用 optimize_itinerary 工具处理以下行程数据。\n"
        f"行程 JSON：\n{itinerary_json}\n\n"
        "将工具返回的 JSON 直接输出，不要添加任何其他文字。"
    )
    result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
    return _parse_agent_output(result["messages"])


def _parse_agent_output(messages: list) -> dict:
    """Extract the itinerary JSON from agent messages. Raises ValueError on failure."""
    from langchain_core.messages import AIMessage

    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            content = getattr(msg, "content", "")
            if not content:
                continue
            content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
            for start_ch, end_ch in [("{", "}"), ("[", "]")]:
                start = content.find(start_ch)
                end = content.rfind(end_ch)
                if start != -1 and end > start:
                    return json.loads(content[start:end + 1])
    raise ValueError("Agent did not return valid itinerary JSON")
