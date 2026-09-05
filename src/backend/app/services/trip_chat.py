"""Trip-side chat orchestration: one assistant, tools as services."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Literal
from uuid import UUID, uuid4

from app.agents.tools.opening_hours import get_opening_hours
from app.agents.tools.weather import get_weather
from app.schemas.trip import (
    ItineraryDelta,
    ItineraryDeltaPayload,
    ItineraryDeltaTarget,
    TripChatContext,
    TripChatOut,
    TripChatRequest,
)
from app.services import trip_editor
from app.services.closure_rules import evaluate_closure_rule

logger = logging.getLogger(__name__)

WRITE_MODE_PROPOSE = "propose"
WRITE_MODE_AUTO = "auto_apply"
WriteMode = Literal["propose", "auto_apply"]

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


@dataclass
class TripChatSession:
    trip_id: UUID
    context: dict
    write_mode: str
    db: object | None = None
    suggestions: list[ItineraryDelta] = field(default_factory=list)
    applied: list[ItineraryDelta] = field(default_factory=list)


def chat_thread_id(trip_id: UUID) -> str:
    return f"trip-chat-{trip_id}"


def build_trip_context(trip, focus: TripChatContext | None = None) -> dict:
    """Compact itinerary JSON. Reloaded from DB every turn."""
    start = trip.start_date
    context = {
        "destination": trip.destination,
        "city": getattr(trip, "city", None) or "",
        "start_date": start.isoformat() if hasattr(start, "isoformat") else str(start or ""),
        "days": [
            {
                "day_index": day.day_index,
                "date": day.date.isoformat() if getattr(day, "date", None) else None,
                "route_type": day.route_type or "city",
                "items": [
                    {
                        "id": str(item.id),
                        "seq": item.seq,
                        "poi_name": item.poi_name,
                        "start_time": str(item.start_time) if item.start_time else None,
                        "end_time": str(item.end_time) if item.end_time else None,
                        "travel_minutes": item.travel_minutes,
                    }
                    for item in sorted(day.items, key=lambda it: it.seq)
                ],
            }
            for day in sorted(trip.days, key=lambda d: d.day_index)
        ],
    }
    if focus:
        context["current_day_index"] = focus.day_index
        if focus.item_id:
            context["current_item_id"] = str(focus.item_id)
    return context


def _poi_key(name: str) -> str:
    return re.sub(r"\s+", "", name or "").lower()


def find_items(context: dict, poi_name: str) -> list[dict]:
    key = _poi_key(poi_name)
    if not key:
        return []
    hits: list[dict] = []
    exact: list[dict] = []
    for day in context.get("days") or []:
        for item in day.get("items") or []:
            name_key = _poi_key(item.get("poi_name") or "")
            if key == name_key or key in name_key or name_key in key:
                row = {**item, "day_index": day.get("day_index")}
                hits.append(row)
                if key == name_key:
                    exact.append(row)
    return exact or hits


def _parse_item_id(item_id: str) -> UUID | None:
    text = (item_id or "").strip()
    if not text:
        return None
    try:
        return UUID(text)
    except ValueError:
        return None


def resolve_item(
    context: dict,
    *,
    poi_name: str = "",
    item_id: str = "",
    day_index: int = 0,
) -> tuple[dict | None, str]:
    parsed_id = _parse_item_id(item_id)
    if parsed_id:
        for day in context.get("days") or []:
            if day_index and day.get("day_index") != day_index:
                continue
            for item in day.get("items") or []:
                if item.get("id") == str(parsed_id):
                    return {**item, "day_index": day.get("day_index")}, ""
        return None, f"行程里找不到 id={item_id} 的节点"

    hits = find_items(context, poi_name)
    if day_index:
        hits = [row for row in hits if row.get("day_index") == day_index]
    if not hits:
        return None, f"行程里找不到「{poi_name or item_id}」"
    if len(hits) > 1:
        names = "、".join(f"{row.get('poi_name')}(第{row.get('day_index')}天)" for row in hits[:5])
        return None, f"匹配到多个地点：{names}。请说得更具体，或带上天数。"
    return hits[0], ""


def _day_date(context: dict, day_index: int) -> str:
    for day in context.get("days") or []:
        if day.get("day_index") == day_index and day.get("date"):
            return str(day["date"])
    start = context.get("start_date") or ""
    if start and day_index >= 1:
        try:
            return (date.fromisoformat(str(start)) + timedelta(days=day_index - 1)).isoformat()
        except ValueError:
            return str(start)
    return str(start)


def _parse_item_ids(raw: str) -> list[UUID] | None:
    text = (raw or "").strip()
    if not text:
        return None
    ids: list[UUID] = []
    for part in re.split(r"[,\s]+", text):
        parsed = _parse_item_id(part)
        if parsed:
            ids.append(parsed)
    return ids or None


def _build_delta(
    action: str,
    *,
    item: dict | None = None,
    day_index: int = 0,
    seq: int = 0,
    poi_name: str = "",
    notes: str = "",
    item_ids: str = "",
) -> tuple[ItineraryDelta | None, str]:
    action = (action or "").strip().lower()
    if action not in {"add", "update", "delete", "reorder"}:
        return None, f"不支持的 action={action}。可用：add / update / delete / reorder"

    if action == "add":
        target_day = day_index or (item.get("day_index") if item else 0)
        name = poi_name or (item.get("poi_name") if item else "")
        if not target_day or not name:
            return None, "add 需要 day_index 和 poi_name"
        return (
            ItineraryDelta(
                suggestion_id=uuid4(),
                action="add",
                target=ItineraryDeltaTarget(day_index=int(target_day), seq=seq or None),
                payload=ItineraryDeltaPayload(poi_name=name, notes=notes or None),
            ),
            "",
        )

    if action == "reorder":
        target_day = day_index or (item.get("day_index") if item else 0)
        ids = _parse_item_ids(item_ids)
        if not target_day or not ids:
            return None, "reorder 需要 day_index 和 item_ids（逗号分隔）"
        return (
            ItineraryDelta(
                suggestion_id=uuid4(),
                action="reorder",
                target=ItineraryDeltaTarget(day_index=int(target_day)),
                payload=ItineraryDeltaPayload(item_ids=ids),
            ),
            "",
        )

    if item is None:
        return None, "缺少要修改的行程节点"
    return (
        ItineraryDelta(
            suggestion_id=uuid4(),
            action=action,
            target=ItineraryDeltaTarget(
                day_index=item.get("day_index"),
                item_id=_parse_item_id(str(item.get("id") or "")),
                seq=item.get("seq"),
            ),
            payload=ItineraryDeltaPayload(
                poi_name=item.get("poi_name") or poi_name or None,
                notes=notes or None,
            ),
        ),
        "",
    )


def propose_itinerary_delta(
    session: TripChatSession,
    *,
    action: str,
    poi_name: str = "",
    day_index: int = 0,
    item_id: str = "",
    seq: int = 0,
    notes: str = "",
    item_ids: str = "",
) -> str:
    item = None
    err = ""
    if action in {"update", "delete"} or item_id or poi_name:
        if action != "add":
            item, err = resolve_item(
                session.context,
                poi_name=poi_name,
                item_id=item_id,
                day_index=day_index,
            )
            if err and action in {"update", "delete"}:
                return err
    delta, err = _build_delta(
        action,
        item=item,
        day_index=day_index,
        seq=seq,
        poi_name=poi_name,
        notes=notes,
        item_ids=item_ids,
    )
    if err or delta is None:
        return err or "无法生成建议"
    session.suggestions.append(delta)
    return json.dumps(delta.model_dump(mode="json"), ensure_ascii=False)


def apply_itinerary_delta(
    session: TripChatSession,
    *,
    action: str,
    poi_name: str = "",
    day_index: int = 0,
    item_id: str = "",
    seq: int = 0,
    notes: str = "",
    item_ids: str = "",
) -> str:
    if session.write_mode != WRITE_MODE_AUTO:
        return "当前是「只提议」模式，不能写库。请调用 propose_delta，让用户点采纳。"
    if session.db is None:
        return "写库失败：没有数据库会话"
    proposed = propose_itinerary_delta(
        session,
        action=action,
        poi_name=poi_name,
        day_index=day_index,
        item_id=item_id,
        seq=seq,
        notes=notes,
        item_ids=item_ids,
    )
    if not session.suggestions:
        return proposed
    delta = session.suggestions[-1]
    try:
        trip_editor.apply_delta(session.db, session.trip_id, delta)
    except Exception as exc:
        logger.exception("apply_delta tool failed")
        session.suggestions.pop()
        return f"写库失败：{exc}"
    session.suggestions.pop()
    session.applied.append(delta)
    return f"已写入行程：{delta.action} {((delta.payload.poi_name if delta.payload else None) or '')}".strip()


def check_itinerary_facts(
    session: TripChatSession,
    *,
    poi_name: str = "",
    day_index: int = 0,
) -> str:
    context = session.context
    item = None
    if poi_name:
        item, err = resolve_item(context, poi_name=poi_name, day_index=day_index)
        if err:
            return err
    target_day = day_index or (item.get("day_index") if item else context.get("current_day_index") or 1)
    try:
        target_day = int(target_day or 1)
    except (TypeError, ValueError):
        target_day = 1
    date_key = _day_date(context, target_day)
    city = context.get("city") or context.get("destination") or ""
    lines = [f"核验范围：{city} 第{target_day}天（{date_key}）"]
    try:
        weather = get_weather(city, date_key)
        lines.append(f"天气：{weather}")
    except Exception:
        logger.exception("trip chat weather lookup failed")
        lines.append("天气：查询失败")
    target_name = (item or {}).get("poi_name") or poi_name
    if target_name:
        try:
            hours = get_opening_hours(target_name, date_key)
            lines.append(f"{target_name} 开放时间：{hours}")
        except Exception:
            logger.exception("trip chat opening hours lookup failed")
            lines.append(f"{target_name} 开放时间：查询失败")
        try:
            rule = evaluate_closure_rule(target_name, date.fromisoformat(date_key))
            if rule.get("matched"):
                lines.append(
                    f"规则：{rule.get('reason') or '命中闭馆规则'}（风险 {rule.get('risk') or 'unknown'}，来源 {rule.get('source') or '规则引擎'}）"
                )
        except Exception:
            logger.exception("trip chat closure rule failed")
    return "\n".join(lines)


def build_tools(session: TripChatSession) -> list[Callable]:
    def propose_delta(
        action: str,
        poi_name: str = "",
        day_index: int = 0,
        item_id: str = "",
        seq: int = 0,
        notes: str = "",
        item_ids: str = "",
    ) -> str:
        """提出行程修改建议，不写数据库。action: add / update / delete / reorder。删除或修改时用 poi_name 或 item_id 定位已有节点。"""
        return propose_itinerary_delta(
            session,
            action=action,
            poi_name=poi_name,
            day_index=day_index,
            item_id=item_id,
            seq=seq,
            notes=notes,
            item_ids=item_ids,
        )

    def check_facts(poi_name: str = "", day_index: int = 0) -> str:
        """查询行程相关天气、开放时间和闭馆规则。可以只问天气（给 day_index），或指定 poi_name。"""
        return check_itinerary_facts(session, poi_name=poi_name, day_index=day_index)

    tools: list[Callable] = [propose_delta, check_facts]
    if session.write_mode == WRITE_MODE_AUTO:
        def apply_delta(
            action: str,
            poi_name: str = "",
            day_index: int = 0,
            item_id: str = "",
            seq: int = 0,
            notes: str = "",
            item_ids: str = "",
        ) -> str:
            """用户已授权自动采纳时，把修改写入行程。参数与 propose_delta 相同。只提议模式不要调用本工具。"""
            return apply_itinerary_delta(
                session,
                action=action,
                poi_name=poi_name,
                day_index=day_index,
                item_id=item_id,
                seq=seq,
                notes=notes,
                item_ids=item_ids,
            )

        tools.append(apply_delta)
    return tools


def _soften_json_reply(text: str) -> str:
    """If the model still wraps a spoken reply in JSON, show the reply field."""
    cleaned = _THINK_RE.sub("", text).strip()
    fence = re.search(r"```json\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        return text
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return text
    if isinstance(data, dict) and isinstance(data.get("reply"), str) and data["reply"].strip():
        return data["reply"].strip()
    return text


def _default_invoke(**kwargs) -> str:
    from app.agents.trip_assistant import invoke_trip_assistant

    return invoke_trip_assistant(**kwargs)


def run_trip_chat(
    *,
    trip,
    body: TripChatRequest,
    thread_id: str,
    db=None,
    invoker: Callable | None = None,
) -> TripChatOut:
    context = build_trip_context(trip, body.context)
    write_mode = getattr(body, "write_mode", None) or WRITE_MODE_PROPOSE
    if write_mode not in {WRITE_MODE_PROPOSE, WRITE_MODE_AUTO}:
        write_mode = WRITE_MODE_PROPOSE
    session = TripChatSession(
        trip_id=trip.id,
        context=context,
        write_mode=write_mode,
        db=db,
    )
    tools = build_tools(session)
    invoke = invoker or _default_invoke
    try:
        reply = invoke(
            tools=tools,
            context=context,
            message=body.message,
            thread_id=thread_id,
            write_mode=write_mode,
        )
    except Exception:
        logger.exception("trip assistant invoke failed")
        reply = "AI 对话服务暂时不可用，请稍后再试。"
    reply = _soften_json_reply((reply or "").strip()) or "抱歉，我暂时没有理解你的需求。"
    return TripChatOut(
        reply=reply,
        thread_id=thread_id,
        suggestions=session.suggestions,
        applied=session.applied,
    )
