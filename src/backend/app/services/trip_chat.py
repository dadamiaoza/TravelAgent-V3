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
    progress: Callable[[str, str], None] | None = None

    def emit(self, tool: str, message: str) -> None:
        if self.progress:
            self.progress(tool, message)


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
                        "is_locked": bool(getattr(item, "is_locked", False)),
                        "suggested_duration_h": getattr(item, "suggested_duration_h", None),
                        "best_time": getattr(item, "best_time", None),
                        "cost_note": getattr(item, "cost_note", None),
                        "opening_hours": getattr(item, "opening_hours", None),
                        "visit_tips": getattr(item, "visit_tips", None),
                        "fact_warning": getattr(item, "fact_warning", None),
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


def _day_names(context: dict, day_index: int) -> list[str]:
    for day in context.get("days") or []:
        if day.get("day_index") == day_index:
            return [str(item.get("poi_name") or "") for item in (day.get("items") or [])]
    return []


def _route_label(day_index: int, names: list[str]) -> str:
    body = " → ".join(name for name in names if name) or "（空）"
    return f"第{day_index}天：{body}"


def attach_preview(context: dict, delta: ItineraryDelta) -> ItineraryDelta:
    """Fill before/after route text so the UI can show the impact."""
    action = delta.action
    target = delta.target
    payload = delta.payload
    day_index = (target.day_index if target else None) or 0
    names = _day_names(context, day_index) if day_index else []
    poi = (payload.poi_name if payload else None) or ""

    if action == "delete" and target:
        src_day = target.day_index or day_index
        before_names = _day_names(context, src_day)
        after_names = before_names.copy()
        if poi in after_names:
            after_names.remove(poi)
        delta.preview_before = _route_label(src_day, before_names)
        delta.preview_after = _route_label(src_day, after_names)
        return delta

    if action == "add" and day_index:
        after = names.copy()
        pos = (target.seq - 1) if target and target.seq else len(after)
        pos = min(max(pos, 0), len(after))
        after.insert(pos, poi or "新地点")
        delta.preview_before = _route_label(day_index, names)
        delta.preview_after = _route_label(day_index, after)
        return delta

    if action == "replace" and target:
        src_day = target.day_index or day_index
        before_names = _day_names(context, src_day)
        old_name = ""
        item_id = str(target.item_id) if target.item_id else ""
        for day in context.get("days") or []:
            if day.get("day_index") != src_day:
                continue
            for item in day.get("items") or []:
                if item.get("id") == item_id:
                    old_name = item.get("poi_name") or ""
        after_names = [poi if name == old_name else name for name in before_names]
        if old_name and old_name in before_names:
            after_names = before_names.copy()
            idx = after_names.index(old_name)
            after_names[idx] = poi or old_name
        delta.preview_before = _route_label(src_day, before_names)
        delta.preview_after = _route_label(src_day, after_names)
        return delta

    if action == "move" and target and target.item_id:
        item, _err = resolve_item(context, item_id=str(target.item_id))
        src_day = int((item or {}).get("day_index") or 0)
        dest_day = int(target.day_index or 0)
        poi_name = (item or {}).get("poi_name") or poi
        src_before = _day_names(context, src_day)
        dest_before = _day_names(context, dest_day)
        src_after = src_before.copy()
        if poi_name in src_after:
            src_after.remove(poi_name)
        dest_after = dest_before.copy()
        pos = (target.seq - 1) if target.seq else len(dest_after)
        pos = min(max(pos, 0), len(dest_after))
        dest_after.insert(pos, poi_name)
        if src_day == dest_day:
            delta.preview_before = _route_label(src_day, src_before)
            delta.preview_after = _route_label(dest_day, dest_after)
        else:
            delta.preview_before = f"{_route_label(src_day, src_before)} ｜ {_route_label(dest_day, dest_before)}"
            delta.preview_after = f"{_route_label(src_day, src_after)} ｜ {_route_label(dest_day, dest_after)}"
        return delta

    if action == "reorder" and day_index and payload and payload.item_ids:
        id_to_name = {}
        for day in context.get("days") or []:
            for item in day.get("items") or []:
                id_to_name[str(item.get("id"))] = item.get("poi_name") or ""
        after_names = [id_to_name.get(str(item_id), "") for item_id in payload.item_ids]
        delta.preview_before = _route_label(day_index, names)
        delta.preview_after = _route_label(day_index, after_names)
        return delta

    if day_index:
        delta.preview_before = _route_label(day_index, names)
        delta.preview_after = _route_label(day_index, names)
    return delta


def _build_delta(
    action: str,
    *,
    item: dict | None = None,
    day_index: int = 0,
    seq: int = 0,
    poi_name: str = "",
    new_poi_name: str = "",
    notes: str = "",
    visit_tips: str = "",
    best_time: str = "",
    cost_note: str = "",
    item_ids: str = "",
) -> tuple[ItineraryDelta | None, str]:
    action = (action or "").strip().lower()
    if action not in {"add", "update", "delete", "reorder", "move", "replace"}:
        return None, f"不支持的 action={action}。可用：add / update / delete / reorder / move / replace"

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
                payload=ItineraryDeltaPayload(
                    poi_name=name,
                    notes=notes or None,
                    visit_tips=visit_tips or None,
                    best_time=best_time or None,
                    cost_note=cost_note or None,
                ),
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

    if action == "move":
        if item is None:
            return None, "move 需要定位已有节点"
        target_day = day_index or 0
        if not target_day:
            return None, "move 需要目标 day_index"
        return (
            ItineraryDelta(
                suggestion_id=uuid4(),
                action="move",
                target=ItineraryDeltaTarget(
                    day_index=int(target_day),
                    item_id=_parse_item_id(str(item.get("id") or "")),
                    seq=seq or None,
                ),
                payload=ItineraryDeltaPayload(poi_name=item.get("poi_name") or poi_name or None),
            ),
            "",
        )

    if action == "replace":
        if item is None:
            return None, "replace 需要定位已有节点"
        replacement = (new_poi_name or "").strip()
        if not replacement:
            return None, "replace 需要 new_poi_name"
        return (
            ItineraryDelta(
                suggestion_id=uuid4(),
                action="replace",
                target=ItineraryDeltaTarget(
                    day_index=item.get("day_index"),
                    item_id=_parse_item_id(str(item.get("id") or "")),
                    seq=item.get("seq"),
                ),
                payload=ItineraryDeltaPayload(poi_name=replacement, notes=notes or None),
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
                visit_tips=visit_tips or None,
                best_time=best_time or None,
                cost_note=cost_note or None,
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
    visit_tips: str = "",
    best_time: str = "",
    cost_note: str = "",
    item_ids: str = "",
    new_poi_name: str = "",
) -> str:
    session.emit("propose_delta", "正在整理行程建议…")
    item = None
    err = ""
    action_key = (action or "").strip().lower()
    if action_key in {"update", "delete", "move", "replace"} or item_id or (
        poi_name and action_key != "add"
    ):
        if action_key != "add":
            item, err = resolve_item(
                session.context,
                poi_name=poi_name,
                item_id=item_id,
                day_index=day_index if action_key not in {"move"} else 0,
            )
            if err and action_key in {"update", "delete", "move", "replace"}:
                return err
    if item and item.get("is_locked") and action_key in {"delete", "move", "replace"}:
        return f"「{item.get('poi_name')}」已锁定，不能{action_key}"
    delta, err = _build_delta(
        action,
        item=item,
        day_index=day_index,
        seq=seq,
        poi_name=poi_name,
        new_poi_name=new_poi_name,
        notes=notes,
        visit_tips=visit_tips,
        best_time=best_time,
        cost_note=cost_note,
        item_ids=item_ids,
    )
    if err or delta is None:
        return err or "无法生成建议"
    attach_preview(session.context, delta)
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
    visit_tips: str = "",
    best_time: str = "",
    cost_note: str = "",
    item_ids: str = "",
    new_poi_name: str = "",
) -> str:
    session.emit("apply_delta", "正在写入行程…")
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
        visit_tips=visit_tips,
        best_time=best_time,
        cost_note=cost_note,
        item_ids=item_ids,
        new_poi_name=new_poi_name,
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
    session.emit("check_facts", "正在查询天气和开放时间…")
    context = session.context
    item = None
    resolve_note = ""
    if poi_name:
        item, err = resolve_item(context, poi_name=poi_name, day_index=day_index)
        if err:
            resolve_note = err
            item = None
    target_day = day_index or (item.get("day_index") if item else context.get("current_day_index") or 1)
    try:
        target_day = int(target_day or 1)
    except (TypeError, ValueError):
        target_day = 1
    date_key = _day_date(context, target_day)
    city = context.get("city") or context.get("destination") or ""
    lines = [f"核验范围：{city} 第{target_day}天（{date_key}）"]
    if resolve_note:
        lines.append(resolve_note)
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


def _existing_poi_keys(context: dict) -> set[str]:
    keys: set[str] = set()
    for day in context.get("days") or []:
        for item in day.get("items") or []:
            keys.add(_poi_key(item.get("poi_name") or ""))
    return keys


def _available_days(context: dict) -> list[int]:
    days = [int(day.get("day_index") or 0) for day in context.get("days") or []]
    return [day for day in days if day >= 1] or [1]


def parse_guide_into_deltas(session: TripChatSession, text: str, day_index: int = 0) -> str:
    """Turn pasted guide text into add suggestions. Does not write the DB."""
    session.emit("parse_guide", "正在解析攻略…")
    from app.services.guide_extract import extract_guide_entities

    entities = extract_guide_entities(text)
    if not entities:
        return "没有从这段文本里解析到景点。"
    available = _available_days(session.context)
    existing = _existing_poi_keys(session.context)
    added = 0
    skipped = 0
    for entity in entities:
        name = entity.get("poi_name") or ""
        if _poi_key(name) in existing:
            skipped += 1
            continue
        raw_day = int(entity.get("day_index") or 0) or day_index or session.context.get("current_day_index") or available[0]
        try:
            raw_day = int(raw_day)
        except (TypeError, ValueError):
            raw_day = available[0]
        if raw_day not in available:
            raw_day = min(available, key=lambda day: abs(day - raw_day))
        proposed = propose_itinerary_delta(
            session,
            action="add",
            poi_name=name,
            day_index=raw_day,
            seq=int(entity.get("seq") or 0),
            visit_tips=entity.get("visit_tips") or "",
            best_time=entity.get("best_time") or "",
            cost_note=entity.get("cost_note") or entity.get("cost_estimate") or "",
        )
        if "无法" in proposed or proposed.startswith("不支持"):
            skipped += 1
            continue
        existing.add(_poi_key(name))
        added += 1
    return f"从攻略解析出 {added} 个可添加景点" + (f"，跳过 {skipped} 个已在行程中或无效项" if skipped else "") + "。"


def build_tools(session: TripChatSession) -> list[Callable]:
    def propose_delta(
        action: str,
        poi_name: str = "",
        day_index: int = 0,
        item_id: str = "",
        seq: int = 0,
        notes: str = "",
        visit_tips: str = "",
        best_time: str = "",
        cost_note: str = "",
        item_ids: str = "",
        new_poi_name: str = "",
    ) -> str:
        """提出行程修改建议，不写数据库。action: add / update / delete / reorder / move / replace。
        删除、移动、替换时用 poi_name 或 item_id 定位已有节点。
        换成某点时 action=replace 且 new_poi_name=新景点。
        跨天移动时 action=move，day_index=目标天。
        改怎么玩时 action=update 且 visit_tips=一句建议。"""
        return propose_itinerary_delta(
            session,
            action=action,
            poi_name=poi_name,
            day_index=day_index,
            item_id=item_id,
            seq=seq,
            notes=notes,
            visit_tips=visit_tips,
            best_time=best_time,
            cost_note=cost_note,
            item_ids=item_ids,
            new_poi_name=new_poi_name,
        )

    def check_facts(poi_name: str = "", day_index: int = 0) -> str:
        """查询行程相关天气、开放时间和闭馆规则。可以只问天气（给 day_index），或指定 poi_name。"""
        return check_itinerary_facts(session, poi_name=poi_name, day_index=day_index)

    def parse_guide(text: str, day_index: int = 0) -> str:
        """把用户粘贴的攻略文本解析成新增景点建议。只解析这段文本，不要搜索网页。"""
        return parse_guide_into_deltas(session, text, day_index=day_index)

    tools: list[Callable] = [propose_delta, check_facts, parse_guide]
    if session.write_mode == WRITE_MODE_AUTO:
        def apply_delta(
            action: str,
            poi_name: str = "",
            day_index: int = 0,
            item_id: str = "",
            seq: int = 0,
            notes: str = "",
            visit_tips: str = "",
            best_time: str = "",
            cost_note: str = "",
            item_ids: str = "",
            new_poi_name: str = "",
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
                visit_tips=visit_tips,
                best_time=best_time,
                cost_note=cost_note,
                item_ids=item_ids,
                new_poi_name=new_poi_name,
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
    progress: Callable[[str, str], None] | None = None,
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
        progress=progress,
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
