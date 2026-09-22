"""Propose/apply photo assignment changes from Trip Assistant. Never guess GPS."""
from __future__ import annotations

import json
import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.photo import PhotoAsset, PhotoAssignment, VisitStop
from app.models.trip import ItineraryDay, ItineraryItem
from app.schemas.trip import ItineraryDelta, ItineraryDeltaPayload, ItineraryDeltaTarget
from app.services.photo_pipeline import attach_visit_stop_to_item, dismiss_visit_stop

_UNASSIGNED_NAMES = ("未归类", "未定点", "空档", "待确认", "没有地点", "没地点", "未挂")
PHOTO_ACTIONS = frozenset(
    {
        "reassign_photo",
        "unassign_photo",
        "dismiss_visit_stop",
        "attach_visit_stop",
    }
)

_ACTION_ALIASES = {
    "dismiss": "dismiss_visit_stop",
    "remove_stop": "dismiss_visit_stop",
    "reassign": "reassign_photo",
    "unassign": "unassign_photo",
    "attach": "attach_visit_stop",
    "attach_item": "attach_visit_stop",
}


def _name_key(name: str) -> str:
    return re.sub(r"\s+", "", name or "").lower()


def _parse_uuid(value: str) -> UUID | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return UUID(text)
    except ValueError:
        return None


def _primary(photo: PhotoAsset) -> PhotoAssignment | None:
    for assignment in photo.assignments or []:
        if assignment.is_primary:
            return assignment
    return photo.assignments[0] if photo.assignments else None


def _is_unassigned_row(row: dict) -> bool:
    return not row.get("place") and not row.get("item_id") and not row.get("visit_stop_id")


def _is_unassigned_name(place_name: str) -> bool:
    key = _name_key(place_name)
    if not key:
        return False
    return any(key == _name_key(name) or _name_key(name) in key for name in _UNASSIGNED_NAMES)


def _photo_batch_label(photos: list[dict]) -> str:
    count = len(photos)
    places = {(row.get("place") or "未归类") for row in photos}
    if len(places) == 1:
        return f"{next(iter(places))}的 {count} 张"
    return f"{count} 张照片"


def load_photo_context(db: Session, trip_id: UUID) -> dict:
    items = (
        db.query(ItineraryItem)
        .join(ItineraryDay)
        .filter(ItineraryDay.trip_id == trip_id)
        .all()
    )
    item_names = {item.id: item.poi_name for item in items}
    stops = (
        db.query(VisitStop)
        .filter(
            VisitStop.trip_id == trip_id,
            VisitStop.status.in_(("suggested", "confirmed")),
        )
        .all()
    )
    photos = (
        db.query(PhotoAsset)
        .options(joinedload(PhotoAsset.assignments).joinedload(PhotoAssignment.visit_stop))
        .filter(PhotoAsset.trip_id == trip_id, PhotoAsset.status != "failed")
        .all()
    )
    photo_rows = []
    stop_photos: dict[UUID, list[str]] = {}
    for photo in photos[:120]:
        assignment = _primary(photo)
        item_id = assignment.item_id if assignment else None
        visit_stop_id = assignment.visit_stop_id if assignment else None
        place = None
        if item_id and item_id in item_names:
            place = item_names[item_id]
        elif assignment and assignment.visit_stop is not None:
            place = assignment.visit_stop.place_name
        captured = None
        if photo.captured_at is not None:
            captured = photo.captured_at.date().isoformat()
        photo_rows.append(
            {
                "id": str(photo.id),
                "filename": photo.original_filename,
                "captured_at": captured,
                "place": place,
                "item_id": str(item_id) if item_id else None,
                "visit_stop_id": str(visit_stop_id) if visit_stop_id else None,
            }
        )
        if visit_stop_id is not None:
            stop_photos.setdefault(visit_stop_id, []).append(str(photo.id))
    visit_rows = []
    for stop in stops:
        ids = stop_photos.get(stop.id) or [str(row.photo_id) for row in stop.assignments if row.is_primary]
        visit_rows.append(
            {
                "id": str(stop.id),
                "place_name": stop.place_name,
                "status": stop.status,
                "photo_count": len(ids),
                "photo_ids": ids,
            }
        )
    groups: dict[str, int] = {}
    for row in photo_rows:
        label = row.get("place") or "未归类"
        groups[label] = groups.get(label, 0) + 1
    photo_groups = [{"label": label, "count": count} for label, count in groups.items()]
    return {"visit_stops": visit_rows, "photos": photo_rows, "photo_groups": photo_groups}


def find_visit_stops(context: dict, *, place_name: str = "", visit_stop_id: str = "") -> list[dict]:
    stops = list(context.get("visit_stops") or [])
    parsed = _parse_uuid(visit_stop_id)
    if parsed is not None:
        hit = [row for row in stops if row.get("id") == str(parsed)]
        return hit
    key = _name_key(place_name)
    if not key:
        return []
    exact = [row for row in stops if _name_key(row.get("place_name") or "") == key]
    if exact:
        return exact
    return [
        row
        for row in stops
        if key in _name_key(row.get("place_name") or "") or _name_key(row.get("place_name") or "") in key
    ]


def find_photos(
    context: dict,
    *,
    photo_id: str = "",
    filename: str = "",
    place_name: str = "",
) -> list[dict]:
    photos = list(context.get("photos") or [])
    parsed = _parse_uuid(photo_id)
    if parsed is not None:
        return [row for row in photos if row.get("id") == str(parsed)]
    if filename.strip():
        needle = filename.strip().lower()
        return [row for row in photos if needle in (row.get("filename") or "").lower()]
    if _is_unassigned_name(place_name):
        return [row for row in photos if _is_unassigned_row(row)]
    key = _name_key(place_name)
    if key:
        return [
            row
            for row in photos
            if key in _name_key(row.get("place") or "") or _name_key(row.get("place") or "") in key
        ]
    current = str(context.get("current_photo_id") or "").strip()
    if current:
        return [row for row in photos if row.get("id") == current]
    return []


def _find_plan_item(context: dict, *, poi_name: str = "", item_id: str = "") -> dict | None:
    parsed = _parse_uuid(item_id)
    days = context.get("days") or []
    if parsed is not None:
        for day in days:
            for item in day.get("items") or []:
                if item.get("id") == str(parsed):
                    return {**item, "day_index": day.get("day_index")}
        return None
    key = _name_key(poi_name)
    if not key:
        return None
    hits: list[dict] = []
    exact: list[dict] = []
    for day in days:
        for item in day.get("items") or []:
            name_key = _name_key(item.get("poi_name") or "")
            if key == name_key or key in name_key or name_key in key:
                row = {**item, "day_index": day.get("day_index")}
                hits.append(row)
                if key == name_key:
                    exact.append(row)
    matched = exact or hits
    if len(matched) == 1:
        return matched[0]
    if len(matched) > 1:
        return None
    return None


def propose_photo_change(
    session,
    *,
    action: str,
    place_name: str = "",
    poi_name: str = "",
    photo_id: str = "",
    filename: str = "",
    item_id: str = "",
    visit_stop_id: str = "",
) -> str:
    session.emit("propose_photo_change", "正在整理照片建议…")
    action_key = _ACTION_ALIASES.get((action or "").strip().lower(), (action or "").strip().lower())
    if action_key not in PHOTO_ACTIONS:
        return "不支持的照片操作。可用：dismiss_visit_stop / reassign_photo / unassign_photo / attach_visit_stop。"

    if action_key == "dismiss_visit_stop":
        stops = find_visit_stops(session.context, place_name=place_name, visit_stop_id=visit_stop_id)
        if not stops:
            return f"计划外停留里找不到「{place_name or visit_stop_id}」。这不是行程计划节点，也不能根据位置瞎猜。"
        if len(stops) > 1:
            names = "、".join(row.get("place_name") or "" for row in stops[:5])
            return f"有多处计划外停留像「{place_name}」：{names}。请说完整名称。"
        stop = stops[0]
        count = int(stop.get("photo_count") or 0)
        delta = ItineraryDelta(
            action="dismiss_visit_stop",
            payload=ItineraryDeltaPayload(
                poi_name=stop.get("place_name"),
                visit_stop_id=_parse_uuid(str(stop.get("id") or "")),
                notes=f"{count}张",
            ),
            preview_before=f"计划外停留：{stop.get('place_name')}（{count}张）",
            preview_after="去掉停留，照片回到未归类；不改行程计划",
        )
        session.suggestions.append(delta)
        return json.dumps(delta.model_dump(mode="json"), ensure_ascii=False)

    if action_key == "reassign_photo" and not photo_id and not filename:
        stops = find_visit_stops(session.context, place_name=place_name, visit_stop_id=visit_stop_id)
        if len(stops) == 1:
            action_key = "attach_visit_stop"
            visit_stop_id = str(stops[0].get("id") or visit_stop_id)
            place_name = str(stops[0].get("place_name") or place_name)

    if action_key == "attach_visit_stop":
        stops = find_visit_stops(session.context, place_name=place_name, visit_stop_id=visit_stop_id)
        item = _find_plan_item(session.context, poi_name=poi_name, item_id=item_id)
        if not stops:
            return f"计划外停留里找不到「{place_name or visit_stop_id}」。"
        if item is None:
            return "请指定要挂到的计划节点名称。不会根据照片猜测地点。"
        if len(stops) > 1:
            return "有多处同名停留，请说完整名称。"
        stop = stops[0]
        delta = ItineraryDelta(
            action="attach_visit_stop",
            target=ItineraryDeltaTarget(item_id=_parse_uuid(str(item.get("id") or ""))),
            payload=ItineraryDeltaPayload(
                poi_name=item.get("poi_name"),
                visit_stop_id=_parse_uuid(str(stop.get("id") or "")),
                notes=stop.get("place_name"),
            ),
            preview_before=f"计划外停留：{stop.get('place_name')}",
            preview_after=f"照片改挂到计划节点「{item.get('poi_name')}」，去掉该停留",
        )
        session.suggestions.append(delta)
        return json.dumps(delta.model_dump(mode="json"), ensure_ascii=False)

    photos = find_photos(
        session.context,
        photo_id=photo_id,
        filename=filename,
        place_name=place_name if not (photo_id or filename) else "",
    )
    if not photos:
        return "找不到要改的照片。请说它们现在在哪（例如望江公园、未归类），或先点开那张照片再说「改挂到岳麓山」。"
    photo_ids = [_parse_uuid(str(row.get("id") or "")) for row in photos]
    photo_ids = [value for value in photo_ids if value is not None]
    if not photo_ids:
        return "找不到有效的照片。"
    labels = _photo_batch_label(photos)
    before_place = photos[0].get("place") or "未归类"

    if action_key == "unassign_photo":
        delta = ItineraryDelta(
            action="unassign_photo",
            payload=ItineraryDeltaPayload(photo_ids=photo_ids, notes=labels),
            preview_before=f"{labels} 现挂在「{before_place}」",
            preview_after="从地点拿掉，回到未归类；不改行程计划",
        )
        session.suggestions.append(delta)
        return json.dumps(delta.model_dump(mode="json"), ensure_ascii=False)

    item = _find_plan_item(session.context, poi_name=poi_name, item_id=item_id)
    if item is None:
        return "请指定要改挂到的计划节点（例如岳麓山）。不会根据 GPS 或画面猜测地点。"
    delta = ItineraryDelta(
        action="reassign_photo",
        target=ItineraryDeltaTarget(item_id=_parse_uuid(str(item.get("id") or ""))),
        payload=ItineraryDeltaPayload(
            poi_name=item.get("poi_name"),
            photo_ids=photo_ids,
            notes=labels,
        ),
        preview_before=f"{labels} 现挂在「{before_place}」",
        preview_after=f"改挂到计划节点「{item.get('poi_name')}」",
    )
    session.suggestions.append(delta)
    return json.dumps(delta.model_dump(mode="json"), ensure_ascii=False)


def _item_on_trip(db: Session, trip_id: UUID, item_id: UUID) -> ItineraryItem:
    item = (
        db.query(ItineraryItem)
        .join(ItineraryDay)
        .filter(ItineraryItem.id == item_id, ItineraryDay.trip_id == trip_id)
        .first()
    )
    if item is None:
        raise HTTPException(status_code=400, detail="计划节点不存在")
    return item


def _assignment_for(db: Session, photo: PhotoAsset) -> PhotoAssignment:
    assignment = _primary(photo)
    if assignment is not None:
        return assignment
    assignment = PhotoAssignment(
        photo_id=photo.id,
        assignment_type="manual",
        confidence=1.0,
        is_primary=True,
    )
    db.add(assignment)
    db.flush()
    return assignment


def apply_photo_delta(db: Session, trip_id: UUID, delta: ItineraryDelta) -> None:
    action = delta.action
    payload = delta.payload
    target = delta.target
    if action not in PHOTO_ACTIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported photo delta action: {action}")
    if payload is None:
        raise HTTPException(status_code=400, detail="photo delta requires payload")

    if action == "dismiss_visit_stop":
        if payload.visit_stop_id is None:
            raise HTTPException(status_code=400, detail="dismiss_visit_stop requires visit_stop_id")
        stop = db.get(VisitStop, payload.visit_stop_id)
        if stop is None or stop.trip_id != trip_id:
            raise HTTPException(status_code=404, detail="停留不存在")
        dismiss_visit_stop(db, stop)
        db.commit()
        return

    if action == "attach_visit_stop":
        if payload.visit_stop_id is None or target is None or target.item_id is None:
            raise HTTPException(status_code=400, detail="attach_visit_stop requires visit_stop_id and item_id")
        stop = db.get(VisitStop, payload.visit_stop_id)
        if stop is None or stop.trip_id != trip_id:
            raise HTTPException(status_code=404, detail="停留不存在")
        _item_on_trip(db, trip_id, target.item_id)
        attach_visit_stop_to_item(db, stop, target.item_id)
        db.commit()
        return

    photo_ids = list(payload.photo_ids or [])
    if payload.photo_id is not None:
        photo_ids.append(payload.photo_id)
    if not photo_ids:
        raise HTTPException(status_code=400, detail="需要 photo_ids")

    if action == "reassign_photo":
        if target is None or target.item_id is None:
            raise HTTPException(status_code=400, detail="reassign_photo requires target.item_id")
        _item_on_trip(db, trip_id, target.item_id)

    for photo_id in photo_ids:
        photo = db.get(PhotoAsset, photo_id)
        if photo is None or photo.trip_id != trip_id:
            continue
        assignment = _assignment_for(db, photo)
        if action == "unassign_photo":
            assignment.item_id = None
            assignment.visit_stop_id = None
            assignment.is_confirmed = False
            assignment.assignment_type = "manual"
            assignment.confidence = 0
        else:
            assignment.item_id = target.item_id  # type: ignore[union-attr]
            assignment.visit_stop_id = None
            assignment.assignment_type = "manual"
            assignment.confidence = 1.0
            assignment.is_confirmed = True
    db.commit()
