"""Itinerary generation service — powered by LangChain itinerary_gen Agent.

Replaces the mock template generator with real AI-generated itineraries.
"""

import json
import re
from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.agents.itinerary_gen import create_itinerary_gen
from app.agents.route_optimizer import create_route_optimizer
from app.models.trip import Trip, ItineraryDay, ItineraryItem


def generate_itinerary(db: Session, trip: Trip) -> Trip:
    """Generate an itinerary using the LangChain agent, then persist to DB."""
    agent = create_itinerary_gen()

    day_count = (trip.end_date - trip.start_date).days + 1
    prompt = (
        f"请为{trip.destination}{day_count}日游规划完整行程。"
        f"旅行日期：{trip.start_date} 至 {trip.end_date}。"
        f"人数：{trip.people_count}人。"
    )
    if trip.budget_min and trip.budget_max:
        prompt += f"预算范围：{trip.budget_min}-{trip.budget_max}元。"
    elif trip.budget_min:
        prompt += f"最低预算：{trip.budget_min}元。"
    elif trip.budget_max:
        prompt += f"最高预算：{trip.budget_max}元。"

    if trip.user_prompt:
        prompt += f"\n用户补充需求：{trip.user_prompt}\n"
    if trip.must_visit:
        prompt += f"\n必须包含用户指定的地点：{', '.join(trip.must_visit)}\n"


    result = agent.invoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"configurable": {"thread_id": f"trip-{trip.id}"}},
    )

    itinerary = _parse_agent_output(result["messages"])

    # 把目的地城市写入行程 JSON，让路线优化地理编码时消除同名 POI 歧义（如“玉湖湿地公园”）
    itinerary["city"] = trip.city or trip.destination

    itinerary = _run_route_optimizer(itinerary)
    _persist_itinerary(db, trip, itinerary, trip.start_date)
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


def _persist_itinerary(db: Session, trip: Trip, itinerary: dict, start_date: date):
    """Convert agent JSON to ORM objects and write to DB."""
    # Clear old items if re-generating
    if trip.days:
        for day in trip.days:
            db.delete(day)
        db.flush()

    days_data = itinerary.get("days", [])
    for day_data in days_data:
        day_idx = day_data["day_index"]
        day = ItineraryDay(
            trip_id=trip.id,
            day_index=day_idx,
            date=start_date + timedelta(days=day_idx - 1),
        )
        db.add(day)
        db.flush()

        accumulated_minutes = 9 * 60  # Start at 09:00
        for item_data in day_data.get("items", []):
            duration_m = int(item_data.get("duration_h", 1.5) * 60)
            travel_m = item_data.get("travel_minutes_from_prev", 0)

            start_minutes = accumulated_minutes + travel_m
            start_t = time(start_minutes // 60 % 24, start_minutes % 60)
            end_t = time((start_minutes + duration_m) // 60 % 24, (start_minutes + duration_m) % 60)

            item = ItineraryItem(
                day_id=day.id,
                seq=item_data["seq"],
                poi_name=item_data["poi_name"],
                start_time=start_t,
                end_time=end_t,
                lat=item_data.get("lat"),
                lng=item_data.get("lng"),
                transport_mode=item_data.get("transport_mode"),
                travel_minutes=travel_m,
                route_polyline=item_data.get("route_polyline"),
            )
            db.add(item)
            accumulated_minutes = start_minutes + duration_m

    trip.status = "generated"
    db.commit()
    db.refresh(trip)
