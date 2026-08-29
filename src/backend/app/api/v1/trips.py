"""Trip CRUD + itinerary generation API endpoints."""
from datetime import timedelta
from uuid import UUID

from langchain_openai import ChatOpenAI

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.source import SourceEntity
from app.models.trip import Trip, ItineraryDay, ItineraryItem
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
    ItineraryDayReorder,
    EntityImportRequest,
)
from app.services.itinerary import generate_itinerary
from app.services.trip_editor import (
    create_item,
    update_item,
    delete_item,
    reorder_day,
    reoptimize_day,
)

router = APIRouter(prefix="/trips", tags=["trips"])




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
def create_trip(body: TripCreate, db: Session = Depends(get_db)):
    """Create a new trip and auto-generate a template itinerary."""
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
    )
    db.add(trip)
    db.commit()
    db.refresh(trip)

    # Auto-generate template itinerary on creation
    trip = generate_itinerary(db, trip)
    return trip


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


@router.delete("/{trip_id}/items/{item_id}")
def delete_itinerary_item(
    trip_id: UUID,
    item_id: UUID,
    db: Session = Depends(get_db),
):
    """删除单个行程节点。"""
    return delete_item(db, trip_id, item_id)


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
@router.get("", response_model=list[TripBrief])
def list_trips(db: Session = Depends(get_db)):
    """List all trips (brief)."""
    return db.query(Trip).order_by(Trip.created_at.desc()).all()
