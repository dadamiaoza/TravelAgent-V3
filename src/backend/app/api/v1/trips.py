"""Trip CRUD + itinerary generation API endpoints."""
import json
import queue
import re
import threading
import uuid
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.llm import chat_model
from app.db.session import get_db
from app.models.source import SourceEntity
from app.models.trip import Trip, ItineraryDay, ItineraryItem, GenerationJob
from app.schemas.trip import (
    TripCreate,
    TripUpdate,
    TripSuggestRequest,
    TripSuggestOut,
    TripOut,
    TripBrief,
    ItineraryItemOut,
    ItineraryDayOut,
    ItineraryItemUpdate,
    ItineraryItemCreate,
    ItineraryDayCreate,
    ItineraryDayReorder,
    TripSyncRequest,
    TripChatRequest,
    TripChatOut,
    DeltaApplyRequest,
    EntityImportRequest,
)
from app.services.destination_timezone import effective_timezone
from app.services.trip_cover import covers_for_trips
from app.services.trip_editor import (
    create_trip_with_itinerary,
    create_item,
    update_item,
    delete_item,
    reorder_day,
    reoptimize_day,
    create_day,
    delete_day,
    sync_trip,
    apply_delta,
    regenerate_trip,
)
from app.services.trip_chat import chat_thread_id, run_trip_chat
from app.services.generation_jobs import (
    create_job,
    get_job_by_idempotency_key,
    get_latest_job_for_trip,
    update_job,
)
from app.services.device_access import ensure_device_cookie, load_owned_trip, trip_visible_to

router = APIRouter(
    prefix="/trips",
    tags=["trips"],
    dependencies=[Depends(ensure_device_cookie)],
)

@router.post("/suggest", response_model=TripSuggestOut)
def suggest_trip(body: TripSuggestRequest):
    """把用户自然语言优化为结构化行程参数 + 优化提示词。"""
    model = chat_model()
    prompt = (
        "你是旅行规划提示词优化助手。请把用户的自然语言需求解析为结构化行程参数，"
        "并生成一段更精确的优化提示词。\n"
        "只输出 JSON，不要其他文字，格式：\n"
        '{"destination":"目的地","city":"干净的城市名","start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD",'
        '"people_count":1,"optimized_prompt":"简洁的优化提示词","must_visit":["用户明确指定必去地点"]}\n'
        "如果用户没有提供明确日期，start_date/end_date 可以填空字符串。\n\n"
          "optimized_prompt 保持简洁，不要写太长。\n"
        f"用户输入：{body.text}\n"
    )
    try:
        response = model.invoke(prompt)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="提示词优化暂时连不上模型服务，请稍后重试",
        ) from exc
    content = response.content.strip()
    # 去掉模型思考块，避免其中的花括号干扰 JSON 提取
    content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)
    # 如果模型用 ```json 包裹，优先取代码块内容
    fence = re.search(r"```json\s*(.*?)```", content, flags=re.DOTALL)
    if fence:
        content = fence.group(1)
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end <= start:
        raise HTTPException(status_code=502, detail="模型返回格式异常，请稍后重试")

    try:
        data = json.loads(content[start:end + 1])
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="模型返回格式异常，请稍后重试") from exc
    return TripSuggestOut(
        destination=(data.get("destination") or "").strip() or None,
          city=(data.get("city") or "").strip() or None,
        start_date=data.get("start_date") or None,
        end_date=data.get("end_date") or None,
        people_count=int(data.get("people_count") or 1),
        optimized_prompt=data.get("optimized_prompt", body.text),
          must_visit=data.get("must_visit") or [],
    )


def _normalized_idempotency_key(raw_key: str | None) -> str | None:
    key = (raw_key or "").strip()
    return key or None


def _trip_out_with_job(trip: Trip, job_id: UUID) -> TripOut:
    return TripOut.model_validate(trip).model_copy(update={"job_id": job_id})


def _require_dates_together(start_date, end_date) -> None:
    if (start_date is None) != (end_date is None):
        raise HTTPException(
            status_code=422,
            detail="start_date 与 end_date 需同时提供或同时留空",
        )
    if start_date is not None and end_date is not None and end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date 不能早于 start_date")


def _owned_or_404(db: Session, trip_id: UUID, request: Request) -> Trip:
    return load_owned_trip(
        db,
        trip_id,
        request.state.device_id,
        getattr(request.state, "user_id", None),
    )


@router.post("", response_model=TripOut, status_code=201)
def create_trip(
    body: TripCreate,
    request: Request,
    db: Session = Depends(get_db),
    idempotency_key: Annotated[str | None, Header()] = None,
):
    """Create a trip immediately, then generate itinerary in background."""
    device_id = request.state.device_id
    _require_dates_together(body.start_date, body.end_date)
    key = _normalized_idempotency_key(idempotency_key)
    if key:
        existing = get_job_by_idempotency_key(db, key)
        if existing is not None:
            trip = db.get(Trip, existing.trip_id)
            if not trip_visible_to(trip, device_id, getattr(request.state, "user_id", None)):
                raise HTTPException(status_code=404, detail="Trip not found")
            return _trip_out_with_job(trip, existing.id)

    undated = body.start_date is None
    trip = Trip(
        destination=body.destination,
        city=body.city,
        start_date=body.start_date,
        end_date=body.end_date,
        people_count=body.people_count,
        budget_min=body.budget_min,
        budget_max=body.budget_max,
        user_prompt=body.user_prompt,
        must_visit=body.must_visit,
        status="draft" if undated else "generating",
        device_id=device_id,
        user_id=getattr(request.state, "user_id", None),
        timezone=effective_timezone(None, body.city, body.destination),
    )
    if undated:
        db.add(trip)
        db.commit()
        db.refresh(trip)
        return trip
    db.add(trip)
    db.flush()
    try:
        job_payload = None
        if body.selected_entities:
            job_payload = {
                "selected_entities": [entity.model_dump() for entity in body.selected_entities]
            }
        job = create_job(
            db,
            trip.id,
            commit=False,
            idempotency_key=key,
            payload=job_payload,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        if key:
            existing = get_job_by_idempotency_key(db, key)
            if existing is not None:
                trip = db.get(Trip, existing.trip_id)
                if trip_visible_to(trip, device_id, getattr(request.state, "user_id", None)):
                    return _trip_out_with_job(trip, existing.id)
        raise
    db.refresh(trip)
    db.refresh(job)

    return _trip_out_with_job(trip, job.id)


def _progress_payload(job: GenerationJob | None) -> dict:
    if job is None:
        return {
            "status": "unknown",
            "progress": 0,
            "message": "暂无进度信息",
            "stages": [],
            "job_id": None,
        }
    return {
        "status": job.status or "unknown",
        "progress": job.progress or 0,
        "message": job.message or "",
        "stages": list(job.stages or []),
        "job_id": str(job.id),
    }


@router.get("/{trip_id}/progress")
def get_generation_progress(trip_id: UUID, request: Request, db: Session = Depends(get_db)):
    """查询异步生成进度（从 generation_jobs 读取）。"""
    _owned_or_404(db, trip_id, request)
    return _progress_payload(get_latest_job_for_trip(db, trip_id))


@router.get("/{trip_id}/progress/stream")
def get_generation_progress_stream(trip_id: UUID, request: Request, db: Session = Depends(get_db)):
    """SSE 实时推送生成进度。Job GET remains the durable source of truth."""
    _owned_or_404(db, trip_id, request)

    async def event_generator():
        import asyncio

        max_seconds = 180
        elapsed = 0
        while elapsed < max_seconds:
            job = get_latest_job_for_trip(db, trip_id)
            payload = _progress_payload(job)
            yield f"event: progress\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            if job is not None and job.status in ("succeeded", "failed"):
                yield f"event: done\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                return
            await asyncio.sleep(1)
            elapsed += 1

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{trip_id}", response_model=TripOut)
def get_trip(trip_id: UUID, request: Request, db: Session = Depends(get_db)):
    """Get a trip with all days and items."""
    return _owned_or_404(db, trip_id, request)


@router.post("/{trip_id}/retry", response_model=TripOut)
def retry_trip_generation(
    trip_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """Start a new generation job for a failed trip this caller may see.

    Device scope comes first. A demo session also reaches rows claimed by
    that user; logged-out callers cannot retry a claimed row.
    """
    device_id = request.state.device_id
    user_id = getattr(request.state, "user_id", None)
    trip = (
        db.query(Trip)
        .filter(Trip.id == trip_id, Trip.device_id == device_id)
        .with_for_update()
        .first()
    )
    if not trip_visible_to(trip, device_id, user_id):
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.status != "generation_failed":
        raise HTTPException(status_code=409, detail="只有生成失败的行程可以重新生成")
    if trip.start_date is None or trip.end_date is None:
        raise HTTPException(status_code=422, detail="请先补上出发和返程日期，再重新生成")

    previous = get_latest_job_for_trip(db, trip.id)
    payload = dict(previous.payload) if previous is not None and previous.payload else None
    trip.status = "generating"
    try:
        job = create_job(db, trip.id, commit=False, payload=payload)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="这趟行程已经在生成中")
    db.refresh(trip)
    db.refresh(job)
    return _trip_out_with_job(trip, job.id)


@router.patch("/{trip_id}/items/{item_id}", response_model=ItineraryItemOut)
def update_itinerary_item(
    trip_id: UUID,
    item_id: UUID,
    body: ItineraryItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """更新单个行程节点（改名称会自动重新地理编码）。"""
    _owned_or_404(db, trip_id, request)
    return update_item(db, trip_id, item_id, body)


@router.post("/{trip_id}/items", response_model=TripOut, status_code=201)
def create_itinerary_item(
    trip_id: UUID,
    body: ItineraryItemCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """新增单个行程节点。"""
    _owned_or_404(db, trip_id, request)
    return create_item(db, trip_id, body)


@router.delete("/{trip_id}/items/{item_id}", response_model=TripOut)
def delete_itinerary_item(
    trip_id: UUID,
    item_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """删除单个行程节点，返回最新完整行程。"""
    _owned_or_404(db, trip_id, request)
    return delete_item(db, trip_id, item_id)


@router.post("/{trip_id}/days", response_model=TripOut, status_code=201)
def create_day_endpoint(
    trip_id: UUID,
    body: ItineraryDayCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """新增一天。"""
    _owned_or_404(db, trip_id, request)
    return create_day(db, trip_id, body)


@router.delete("/{trip_id}/days/{day_id}", response_model=TripOut)
def delete_day_endpoint(
    trip_id: UUID,
    day_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """删除一天，并重排剩余 Day 编号和日期。"""
    _owned_or_404(db, trip_id, request)
    return delete_day(db, trip_id, day_id)


@router.post("/{trip_id}/sync", response_model=TripOut)
def sync_trip_endpoint(
    trip_id: UUID,
    body: TripSyncRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """轻量最终一致性同步：批量保存排序和名称修改。"""
    _owned_or_404(db, trip_id, request)
    return sync_trip(db, trip_id, body)


@router.post("/{trip_id}/days/{day_id}/reoptimize", response_model=TripOut)
def reoptimize_day(
    trip_id: UUID,
    day_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    """重算当天交通时间/路线，并重新生成游玩时间段。"""
    _owned_or_404(db, trip_id, request)
    return reoptimize_day(db, trip_id, day_id)


@router.post("/{trip_id}/days/{day_id}/reorder", response_model=ItineraryDayOut)
def reorder_day_items(
    trip_id: UUID,
    day_id: UUID,
    body: ItineraryDayReorder,
    request: Request,
    db: Session = Depends(get_db),
):
    """同一天内按 item_ids 顺序重新编号并重算时间段。"""
    _owned_or_404(db, trip_id, request)
    return reorder_day(db, trip_id, day_id, body)


@router.post("/{trip_id}/entities/import", response_model=TripOut)
def import_entities_to_trip(
    trip_id: UUID,
    body: EntityImportRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """把用户勾选的攻略候选 POI 写入指定行程，补全对应 Day/Item。"""
    trip = _owned_or_404(db, trip_id, request)
    if trip.start_date is None:
        raise HTTPException(status_code=400, detail="行程尚未设置日期")

    entities = (
        db.query(SourceEntity)
        .filter(SourceEntity.id.in_(body.entity_ids))
        .all()
    )
    if not entities:
        raise HTTPException(status_code=400, detail="No matching source entities")

    # 按 day_index 分组，保持 app 内出现顺序
    entities.sort(key=lambda e: (e.day_index, e.seq))
    days_by_index = {day.day_index: day for day in trip.days}
    imported_count = 0

    for entity in entities:
        day_index = max(1, entity.day_index)
        if day_index not in days_by_index:
            day = ItineraryDay(
                trip_id=trip.id,
                day_index=day_index,
                date=trip.start_date + timedelta(days=day_index - 1),
            )
            db.add(day)
            db.flush()
            days_by_index[day_index] = day

        day = days_by_index[day_index]
        next_seq = max((item.seq for item in day.items), default=0) + 1
        db.add(ItineraryItem(
            day_id=day.id,
            seq=next_seq,
            poi_name=entity.poi_name,
            lat=entity.lat,
            lng=entity.lng,
            suggested_duration_h=entity.suggested_duration_h,
            best_time=entity.best_time,
            cost_note=entity.cost_estimate,
            visit_tips=entity.visit_tips,
        ))
        imported_count += 1

    if imported_count == 0:
        raise HTTPException(status_code=400, detail="No entities were imported")

    db.commit()
    db.refresh(trip)
    return trip




@router.patch("/{trip_id}", response_model=TripOut)
def update_trip(
    trip_id: UUID,
    body: TripUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """编辑行程标题（destination）。"""
    trip = _owned_or_404(db, trip_id, request)
    if body.destination is not None:
        trip.destination = body.destination.strip()
    db.commit()
    db.refresh(trip)
    return trip


def _run_trip_chat(
    trip,
    body: TripChatRequest,
    thread_id: str,
    db: Session,
    progress=None,
) -> TripChatOut:
    """Run the trip assistant graph and return reply + suggestions."""
    return run_trip_chat(trip=trip, body=body, thread_id=thread_id, db=db, progress=progress)


@router.post("/{trip_id}/chat", response_model=TripChatOut)
def trip_chat(
    trip_id: UUID,
    body: TripChatRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """带行程上下文的 AI 对话，返回文本和结构化建议（同步版本）。"""
    trip = _owned_or_404(db, trip_id, request)

    thread_id = body.thread_id or chat_thread_id(trip_id)
    return _run_trip_chat(trip, body, thread_id, db)


@router.post("/{trip_id}/chat/stream")
def trip_chat_stream(
    trip_id: UUID,
    body: TripChatRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """SSE：思考/工具进度事件，再整段回复，最后附建议。"""
    trip = _owned_or_404(db, trip_id, request)
    # Load collections on the request thread before the worker starts.
    for day in trip.days:
        _ = list(day.items)

    thread_id = body.thread_id or chat_thread_id(trip_id)

    async def event_generator():
        import asyncio

        events: queue.Queue = queue.Queue()
        holder: dict = {}

        def progress(tool: str, message: str) -> None:
            events.put(("status", {"status": "tool", "tool": tool, "message": message}))

        def worker() -> None:
            try:
                holder["result"] = _run_trip_chat(trip, body, thread_id, db, progress)
            except Exception as exc:
                holder["error"] = exc
            finally:
                events.put(("finished", None))

        yield 'event: status\ndata: {"status":"thinking","message":"AI 正在思考…"}\n\n'
        threading.Thread(target=worker, daemon=True).start()
        while True:
            kind, payload = await asyncio.to_thread(events.get)
            if kind == "status":
                yield f"event: status\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            else:
                break

        error = holder.get("error")
        if error:
            fail = {
                "reply": "AI 对话服务暂时不可用，请稍后再试。",
                "thread_id": thread_id,
                "suggestions": [],
                "applied": [],
            }
            yield f"event: done\ndata: {json.dumps(fail, ensure_ascii=False)}\n\n"
            return

        result = holder["result"]
        reply = result.reply or ""
        if reply:
            yield f"event: delta\ndata: {json.dumps({'text': reply}, ensure_ascii=False)}\n\n"

        if result.applied:
            yield (
                "event: applied\ndata: "
                + json.dumps(
                    {"deltas": [s.model_dump(mode="json") for s in result.applied]},
                    ensure_ascii=False,
                )
                + "\n\n"
            )

        final_payload = {
            "reply": reply,
            "thread_id": result.thread_id,
            "suggestions": [s.model_dump(mode="json") for s in result.suggestions],
            "applied": [s.model_dump(mode="json") for s in result.applied],
        }
        yield f"event: done\ndata: {json.dumps(final_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{trip_id}/deltas/apply", response_model=TripOut)
def apply_trip_delta(
    trip_id: UUID,
    body: DeltaApplyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """应用一条 AI 建议 Delta，返回最新完整行程。"""
    _owned_or_404(db, trip_id, request)
    return apply_delta(db, trip_id, body.delta)


def _place_counts(db: Session, trip_ids: list[UUID]) -> dict[UUID, int]:
    if not trip_ids:
        return {}
    rows = (
        db.query(ItineraryDay.trip_id, func.count(ItineraryItem.id))
        .join(ItineraryItem, ItineraryItem.day_id == ItineraryDay.id)
        .filter(ItineraryDay.trip_id.in_(trip_ids))
        .group_by(ItineraryDay.trip_id)
        .all()
    )
    return {trip_id: int(count) for trip_id, count in rows}


def _trip_brief(trip: Trip, place_count: int, cover_url: str | None) -> TripBrief:
    return TripBrief(
        id=trip.id,
        destination=trip.destination,
        city=trip.city,
        timezone=effective_timezone(trip.timezone, trip.city, trip.destination),
        start_date=trip.start_date,
        end_date=trip.end_date,
        people_count=trip.people_count,
        place_count=place_count,
        status=trip.status,
        created_at=trip.created_at,
        cover_url=cover_url,
    )


@router.get("", response_model=list[TripBrief])
def list_trips(request: Request, db: Session = Depends(get_db)):
    """List this device's trips. A demo session also includes claimed rows."""
    device_id = request.state.device_id
    user_id = getattr(request.state, "user_id", None)
    query = db.query(Trip).filter(Trip.device_id == device_id)
    if user_id:
        query = query.filter(or_(Trip.user_id == user_id, Trip.user_id.is_(None)))
    else:
        query = query.filter(Trip.user_id.is_(None))
    trips = query.order_by(Trip.created_at.desc()).all()
    counts = _place_counts(db, [trip.id for trip in trips])
    covers = covers_for_trips(db, trips)
    return [_trip_brief(trip, counts.get(trip.id, 0), covers.get(trip.id)) for trip in trips]
