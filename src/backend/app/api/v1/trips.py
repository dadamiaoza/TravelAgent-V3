"""Trip CRUD + itinerary generation API endpoints."""
import json
import re
import uuid
from datetime import timedelta
from typing import Dict
from uuid import UUID

from langchain_openai import ChatOpenAI

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db, SessionLocal
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
    ItineraryDelta,
    EntityImportRequest,
)
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
from app.services.generation_jobs import create_job, update_job, get_latest_job_for_trip

router = APIRouter(prefix="/trips", tags=["trips"])

def _run_generation_in_background(trip_id: str, job_id: str):
    import uuid as _uuid

    trip_uuid = _uuid.UUID(trip_id)
    job_uuid = _uuid.UUID(job_id)
    db = SessionLocal()
    try:
        update_job(db, job_uuid, status="running", progress=10, message="正在准备生成行程...")

        trip = db.query(Trip).filter(Trip.id == trip_uuid).first()
        if not trip:
            update_job(db, job_uuid, status="failed", progress=100, message="行程不存在")
            return

        update_job(db, job_uuid, status="running", progress=30, message="AI 正在生成行程...")
        regenerate_trip(db, trip)

        update_job(db, job_uuid, status="succeeded", progress=100, message="行程生成完成")
    except Exception as exc:
        db.rollback()
        try:
            update_job(db, job_uuid, status="failed", progress=100, message=f"生成失败：{exc}")
        except Exception:
            pass
    finally:
        db.close()




@router.post("/suggest", response_model=TripSuggestOut)
def suggest_trip(body: TripSuggestRequest):
    """把用户自然语言优化为结构化行程参数 + 优化提示词。"""
    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )
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
    response = model.invoke(prompt)
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
        raise HTTPException(status_code=500, detail="Failed to optimize trip prompt")

    import json as _json
    data = _json.loads(content[start:end + 1])
    return TripSuggestOut(
        destination=(data.get("destination") or "").strip() or None,
          city=(data.get("city") or "").strip() or None,
        start_date=data.get("start_date") or None,
        end_date=data.get("end_date") or None,
        people_count=int(data.get("people_count") or 1),
        optimized_prompt=data.get("optimized_prompt", body.text),
          must_visit=data.get("must_visit") or [],
    )
@router.post("", response_model=TripOut, status_code=201)
def create_trip(
    body: TripCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Create a trip immediately, then generate itinerary in background."""
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
        status="generating",
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    job = create_job(db, trip.id)
    background_tasks.add_task(_run_generation_in_background, str(trip.id), str(job.id))

    return trip


@router.get("/{trip_id}/progress")
def get_generation_progress(trip_id: UUID, db: Session = Depends(get_db)):
    """查询异步生成进度（从 generation_jobs 读取）。"""
    job = get_latest_job_for_trip(db, trip_id)
    if not job:
        return {"status": "unknown", "progress": 0, "message": "暂无进度信息"}
    return {
        "status": job.status or "unknown",
        "progress": job.progress or 0,
        "message": job.message or "",
    }


@router.get("/{trip_id}", response_model=TripOut)
def get_trip(trip_id: UUID, db: Session = Depends(get_db)):
    """Get a trip with all days and items."""
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@router.patch("/{trip_id}/items/{item_id}", response_model=ItineraryItemOut)
def update_itinerary_item(
    trip_id: UUID,
    item_id: UUID,
    body: ItineraryItemUpdate,
    db: Session = Depends(get_db),
):
    """更新单个行程节点（改名称会自动重新地理编码）。"""
    return update_item(db, trip_id, item_id, body)


@router.post("/{trip_id}/items", response_model=TripOut, status_code=201)
def create_itinerary_item(
    trip_id: UUID,
    body: ItineraryItemCreate,
    db: Session = Depends(get_db),
):
    """新增单个行程节点。"""
    return create_item(db, trip_id, body)


@router.delete("/{trip_id}/items/{item_id}", response_model=TripOut)
def delete_itinerary_item(
    trip_id: UUID,
    item_id: UUID,
    db: Session = Depends(get_db),
):
    """删除单个行程节点，返回最新完整行程。"""
    return delete_item(db, trip_id, item_id)


@router.post("/{trip_id}/days", response_model=TripOut, status_code=201)
def create_day_endpoint(
    trip_id: UUID,
    body: ItineraryDayCreate,
    db: Session = Depends(get_db),
):
    """新增一天。"""
    return create_day(db, trip_id, body)


@router.delete("/{trip_id}/days/{day_id}", response_model=TripOut)
def delete_day_endpoint(
    trip_id: UUID,
    day_id: UUID,
    db: Session = Depends(get_db),
):
    """删除一天，并重排剩余 Day 编号和日期。"""
    return delete_day(db, trip_id, day_id)


@router.post("/{trip_id}/sync", response_model=TripOut)
def sync_trip_endpoint(
    trip_id: UUID,
    body: TripSyncRequest,
    db: Session = Depends(get_db),
):
    """轻量最终一致性同步：批量保存排序和名称修改。"""
    return sync_trip(db, trip_id, body)


@router.post("/{trip_id}/days/{day_id}/reoptimize", response_model=TripOut)
def reoptimize_day(
    trip_id: UUID,
    day_id: UUID,
    db: Session = Depends(get_db),
):
    """重算当天交通时间/路线，并重新生成游玩时间段。"""
    return reoptimize_day(db, trip_id, day_id)


@router.post("/{trip_id}/days/{day_id}/reorder", response_model=ItineraryDayOut)
def reorder_day_items(
    trip_id: UUID,
    day_id: UUID,
    body: ItineraryDayReorder,
    db: Session = Depends(get_db),
):
    """同一天内按 item_ids 顺序重新编号并重算时间段。"""
    return reorder_day(db, trip_id, day_id, body)


@router.post("/{trip_id}/entities/import", response_model=TripOut)
def import_entities_to_trip(
    trip_id: UUID,
    body: EntityImportRequest,
    db: Session = Depends(get_db),
):
    """把用户勾选的攻略候选 POI 写入指定行程，补全对应 Day/Item。"""
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

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
    db: Session = Depends(get_db),
):
    """编辑行程标题（destination）。"""
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    if body.destination is not None:
        trip.destination = body.destination.strip()
    db.commit()
    db.refresh(trip)
    return trip
def _build_trip_context(trip) -> Dict:
    """Compact itinerary context for the chat prompt (no heavy route polylines)."""
    return {
        "destination": trip.destination,
        "city": trip.city or "",
        "days": [
            {
                "day_index": day.day_index,
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


def _run_trip_chat(trip, body: TripChatRequest, thread_id: str) -> TripChatOut:
    """Run the trip chat LLM call and return structured output."""
    context = _build_trip_context(trip)
    if body.context:
        context["current_day_index"] = body.context.day_index
        if body.context.item_id:
            context["current_item_id"] = str(body.context.item_id)

    prompt = (
        "你是旅行行程协作助手。根据当前行程 JSON 和用户消息，给出中文回复和可执行的结构化建议。\n"
        "只输出 JSON，格式：\n"
        '{"reply": "...", "suggestions": [{"action": "add|update|delete|move|reorder", '
        '"target": {"day_index": 1, "item_id": "uuid", "seq": 2}, '
        '"payload": {"poi_name": "...", "start_time": "09:00:00", "end_time": "10:00:00"}}]}\n'
        "如果没有建议，suggestions 返回空数组。不要修改行程，只给建议。\n\n"
        f"当前行程：\n{json.dumps(context, ensure_ascii=False)}\n\n"
        f"用户消息：{body.message}\n"
    )

    try:
        model = ChatOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
        response = model.invoke(prompt)
        content = response.content.strip()
        content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)
        fence = re.search(r"```json\s*(.*?)```", content, flags=re.DOTALL)
        if fence:
            content = fence.group(1)
        start = content.find("{")
        end = content.rfind("}")
        data = json.loads(content[start:end + 1]) if start != -1 and end > start else {}
        reply = data.get("reply") or "抱歉，我暂时没有理解你的需求。"
        raw_suggestions = data.get("suggestions") or []
        suggestions = []
        for raw in raw_suggestions:
            try:
                suggestions.append(ItineraryDelta(**raw))
            except Exception:
                continue
        return TripChatOut(reply=reply, thread_id=thread_id, suggestions=suggestions)
    except Exception:
        return TripChatOut(
            reply="AI 对话服务暂时不可用，请稍后再试。",
            thread_id=thread_id,
            suggestions=[],
        )


@router.post("/{trip_id}/chat", response_model=TripChatOut)
def trip_chat(
    trip_id: UUID,
    body: TripChatRequest,
    db: Session = Depends(get_db),
):
    """带行程上下文的 AI 对话，返回文本和结构化建议（同步版本）。"""
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    thread_id = body.thread_id or f"trip-{trip_id}"
    return _run_trip_chat(trip, body, thread_id)


@router.post("/{trip_id}/chat/stream")
def trip_chat_stream(
    trip_id: UUID,
    body: TripChatRequest,
    db: Session = Depends(get_db),
):
    """SSE 流式返回 AI 对话：先发思考状态，再逐段输出回复，最后附建议。"""
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    thread_id = body.thread_id or f"trip-{trip_id}"

    async def event_generator():
        import asyncio

        yield 'event: status\ndata: {"status":"thinking"}\n\n'
        # 模拟/真实计算放在这里，避免阻塞第一个事件
        result = await asyncio.to_thread(_run_trip_chat, trip, body, thread_id)

        reply = result.reply or ""
        # 按2-4个字符切块，形成流式输出效果
        step = 3
        for i in range(0, len(reply), step):
            chunk = reply[i:i + step]
            import json as _json
            yield f'event: delta\ndata: {_json.dumps({"text": chunk}, ensure_ascii=False)}\n\n'
            await asyncio.sleep(0.03)

        final_payload = {
            "reply": reply,
            "thread_id": result.thread_id,
            "suggestions": [s.model_dump(mode="json") for s in result.suggestions],
        }
        yield f'event: done\ndata: {json.dumps(final_payload, ensure_ascii=False)}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{trip_id}/deltas/apply", response_model=TripOut)
def apply_trip_delta(
    trip_id: UUID,
    body: DeltaApplyRequest,
    db: Session = Depends(get_db),
):
    """应用一条 AI 建议 Delta，返回最新完整行程。"""
    return apply_delta(db, trip_id, body.delta)


@router.get("", response_model=list[TripBrief])
def list_trips(db: Session = Depends(get_db)):
    """List all trips (brief)."""
    return db.query(Trip).order_by(Trip.created_at.desc()).all()
