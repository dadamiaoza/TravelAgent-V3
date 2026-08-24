"""Trip CRUD + itinerary generation API endpoints."""
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.source import SourceEntity
from app.models.trip import Trip, ItineraryDay, ItineraryItem
from app.schemas.trip import (
    TripCreate,
    TripOut,
    TripBrief,
    ItineraryItemOut,
    ItineraryDayOut,
    ItineraryItemUpdate,
    ItineraryDayReorder,
    EntityImportRequest,
)
from app.services.itinerary import generate_itinerary

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("", response_model=TripOut, status_code=201)
def create_trip(body: TripCreate, db: Session = Depends(get_db)):
    """Create a new trip and auto-generate a template itinerary."""
    trip = Trip(
        destination=body.destination,
        start_date=body.start_date,
        end_date=body.end_date,
        people_count=body.people_count,
        budget_min=body.budget_min,
        budget_max=body.budget_max,
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
    """更新单个行程节点的用户可编辑字段（名称/时间/备注）。"""
    item = (
        db.query(ItineraryItem)
        .join(ItineraryDay, ItineraryItem.day_id == ItineraryDay.id)
        .filter(
            ItineraryItem.id == item_id,
            ItineraryDay.trip_id == trip_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Itinerary item not found")

    # 只更新请求中实际传入的字段
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)
    return item


@router.post("/{trip_id}/days/{day_id}/reorder", response_model=ItineraryDayOut)
def reorder_day_items(
    trip_id: UUID,
    day_id: UUID,
    body: ItineraryDayReorder,
    db: Session = Depends(get_db),
):
    """同一天内按 item_ids 顺序重新编号，不重新请求高德路线。"""
    day = (
        db.query(ItineraryDay)
        .filter(
            ItineraryDay.id == day_id,
            ItineraryDay.trip_id == trip_id,
        )
        .first()
    )
    if not day:
        raise HTTPException(status_code=404, detail="Itinerary day not found")

    existing_ids = {item.id for item in day.items}
    if set(body.item_ids) != existing_ids:
        raise HTTPException(
            status_code=400,
            detail="item_ids must contain exactly all items in this day",
        )

    by_id = {item.id: item for item in day.items}
    for seq, item_id in enumerate(body.item_ids, start=1):
        by_id[item_id].seq = seq

    db.commit()
    db.refresh(day)
    return day


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


@router.get("", response_model=list[TripBrief])
def list_trips(db: Session = Depends(get_db)):
    """List all trips (brief)."""
    return db.query(Trip).order_by(Trip.created_at.desc()).all()
