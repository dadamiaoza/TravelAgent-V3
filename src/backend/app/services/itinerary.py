"""Itinerary generation service — powered by LangChain itinerary_gen Agent.

Replaces the mock template generator with real AI-generated itineraries.
"""

import json
import re
from collections.abc import Callable
from datetime import date, time

from sqlalchemy.orm import Session

from app.agents.itinerary_gen import create_itinerary_gen
from app.agents.tools.route_optimizer import optimize_itinerary
from app.models.trip import Trip
from app.schemas.fill_draft import gate_fill_draft
from app.schemas.persist_draft import gate_persist_draft
from app.schemas.route_draft import gate_route_draft
from app.services.itinerary_persistence import persist_itinerary
from app.services.visit_fields import copy_visit_fields

StageCallback = Callable[[str, int, str], None]


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


def _emit_stage(on_stage: StageCallback | None, key: str, progress: int, message: str) -> None:
    if on_stage is not None:
        on_stage(key, progress, message)


def _positive_leg_minutes(value) -> int | None:
    """A positive travel-leg minute count. Stay duration is not a leg."""
    if value is None or value is False or value == "":
        return None
    try:
        minutes = int(float(value))
    except (TypeError, ValueError):
        return None
    if minutes <= 0:
        return None
    return minutes


def _guide_leg_minutes(item: dict) -> int | None:
    """Explicit A→B minutes from a guide or selected candidate.

    suggested_duration_h / duration_h are time spent at the POI, not the leg.
    """
    for key in (
        "travel_estimate_minutes",
        "travel_minutes_from_prev",
        "travel_minutes",
        "leg_minutes",
    ):
        minutes = _positive_leg_minutes(item.get(key))
        if minutes is not None:
            return minutes
    return None


def assemble_days_from_entities(
    entities: list[dict],
    *,
    city: str,
) -> dict:
    """Build itinerary JSON from user-selected candidates. No LLM."""
    grouped: dict[int, list[dict]] = {}
    for entity in entities:
        name = (entity.get("poi_name") or "").strip()
        if not name:
            continue
        day_index = int(entity.get("day_index") or 1)
        grouped.setdefault(day_index, []).append(entity)

    days = []
    for day_index in sorted(grouped):
        ordered = sorted(
            grouped[day_index],
            key=lambda item: int(item.get("seq") or 0),
        )
        items = []
        for seq, item in enumerate(ordered, start=1):
            entry = {
                "seq": seq,
                "poi_name": item["poi_name"].strip(),
                "duration_h": item.get("suggested_duration_h") or 1.5,
                "travel_minutes_from_prev": 0,
            }
            if seq > 1:
                guide_minutes = _guide_leg_minutes(item)
                if guide_minutes is not None:
                    entry["travel_minutes_from_prev"] = guide_minutes
                    entry["travel_estimate_minutes"] = guide_minutes
                    entry["travel_estimate_source"] = "guide"
            if item.get("lat") is not None:
                entry["lat"] = item["lat"]
            if item.get("lng") is not None:
                entry["lng"] = item["lng"]
            entry.update(copy_visit_fields(item))
            items.append(entry)
        days.append(
            {
                "day_index": day_index,
                "theme": "攻略勾选",
                "route_type": "city",
                "items": items,
            }
        )
    return {"city": city, "days": days}


def fill_itinerary_draft(
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
    selected_entities: list[dict] | None = None,
    thread_id: str = "itinerary",
) -> dict:
    """Fill days JSON: selected candidates skip the planner agent."""
    resolved_city = city or destination
    if selected_entities:
        return assemble_days_from_entities(selected_entities, city=resolved_city)

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
    itinerary["city"] = resolved_city
    return itinerary


def route_itinerary_draft(itinerary: dict, *, respect_fill_order: bool = True) -> dict:
    """Always run the Python route optimizer. Never an agent.

    Production generation keeps fill order unless sanity checks fail.
    Pass respect_fill_order=False to force nearest-neighbor reordering.
    The default call stays a single positional argument so existing stubs
    that only accept the JSON payload continue to work.
    """
    payload = json.dumps(itinerary, ensure_ascii=False)
    if respect_fill_order:
        routed = optimize_itinerary(payload)
    else:
        routed = optimize_itinerary(payload, respect_fill_order=False)
    return json.loads(routed)


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
    selected_entities: list[dict] | None = None,
    thread_id: str = "itinerary",
    on_stage: StageCallback | None = None,
) -> dict:
    """Generate a pure itinerary draft. Does NOT touch the database.

    This is the generator strategy used by the application orchestrator.
    """
    itinerary = fill_itinerary_draft(
        destination=destination,
        city=city,
        start_date=start_date,
        end_date=end_date,
        people_count=people_count,
        budget_min=budget_min,
        budget_max=budget_max,
        user_prompt=user_prompt,
        must_visit=must_visit,
        selected_entities=selected_entities,
        thread_id=thread_id,
    )
    gate_fill_draft(itinerary, on_stage)

    _emit_stage(on_stage, "route", 70, "正在补路线...")
    routed = route_itinerary_draft(itinerary)
    gate_route_draft(routed, on_stage)
    return routed


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
    gate_persist_draft(draft)
    persist_itinerary(db, trip, draft, trip.start_date)
    return trip


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
