"""Trip editor service — centralizes itinerary mutation logic.

API endpoints stay thin; all add/update/delete/reorder/reoptimize business
logic lives here so future features (AI delta, chat, snapshots) reuse one
service layer instead of adding more ad-hoc API code.
"""
import json
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.trip import Trip, ItineraryDay, ItineraryItem
from app.schemas.trip import (
    ItineraryItemCreate,
    ItineraryItemUpdate,
    ItineraryDayReorder,
)
from app.agents.tools.geo import geocode_poi
from app.agents.tools.route_optimizer import optimize_itinerary
from app.services.itinerary import recalculate_day_schedule


def _get_trip(db: Session, trip_id: UUID) -> Trip:
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


def _get_day(db: Session, trip_id: UUID, day_id: UUID) -> ItineraryDay:
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
    return day


def _get_item(db: Session, trip_id: UUID, item_id: UUID) -> ItineraryItem:
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
    return item


def _geocode_name(name: str, city: str) -> dict | None:
    try:
        return geocode_poi(name, city=city or "", mock_fallback=True)
    except Exception:
        return None


def create_item(db: Session, trip_id: UUID, body: ItineraryItemCreate) -> Trip:
    trip = _get_trip(db, trip_id)
    day = _get_day(db, trip_id, body.day_id)

    next_seq = max((item.seq for item in day.items), default=0) + 1
    item = ItineraryItem(
        day_id=day.id,
        seq=next_seq,
        poi_name=body.poi_name,
        start_time=body.start_time,
        end_time=body.end_time,
        notes=body.notes,
        lat=body.lat,
        lng=body.lng,
    )

    if item.lat is None or item.lng is None:
        city = trip.city or trip.destination or ""
        geo = _geocode_name(body.poi_name, city)
        if geo:
            item.lat = geo.get("lat")
            item.lng = geo.get("lng")
            item.amap_poi_id = geo.get("amap_poi_id")
            item.poi_address = geo.get("poi_address")
            item.poi_type = geo.get("poi_type")

    db.add(item)
    db.flush()
    recalculate_day_schedule(day)
    db.commit()
    db.refresh(trip)
    return trip


def update_item(
    db: Session, trip_id: UUID, item_id: UUID, body: ItineraryItemUpdate
) -> ItineraryItem:
    item = _get_item(db, trip_id, item_id)
    poi_name_changed = body.poi_name is not None and body.poi_name != item.poi_name

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    if poi_name_changed:
        trip = _get_trip(db, trip_id)
        city = trip.city or trip.destination or ""
        geo = _geocode_name(body.poi_name or "", city)
        if geo:
            item.lat = geo.get("lat", item.lat)
            item.lng = geo.get("lng", item.lng)
            item.amap_poi_id = geo.get("amap_poi_id", item.amap_poi_id)
            item.poi_address = geo.get("poi_address", item.poi_address)
            item.poi_type = geo.get("poi_type", item.poi_type)

    db.commit()
    db.refresh(item)
    return item


def delete_item(db: Session, trip_id: UUID, item_id: UUID) -> dict:
    item = _get_item(db, trip_id, item_id)
    day_id = item.day_id
    db.delete(item)
    db.flush()
    day = _get_day(db, trip_id, day_id)
    recalculate_day_schedule(day)
    db.commit()
    return {"ok": True}


def reorder_day(
    db: Session, trip_id: UUID, day_id: UUID, body: ItineraryDayReorder
) -> ItineraryDay:
    day = _get_day(db, trip_id, day_id)
    existing_ids = {item.id for item in day.items}
    if set(body.item_ids) != existing_ids:
        raise HTTPException(
            status_code=400,
            detail="item_ids must contain exactly all items in this day",
        )

    by_id = {item.id: item for item in day.items}
    for seq, item_id in enumerate(body.item_ids, start=1):
        by_id[item_id].seq = seq

    recalculate_day_schedule(day)
    db.commit()
    db.refresh(day)
    return day


def reoptimize_day(db: Session, trip_id: UUID, day_id: UUID) -> Trip:
    trip = _get_trip(db, trip_id)
    day = _get_day(db, trip_id, day_id)

    city = trip.city or trip.destination or ""
    day_json = {
        "day_index": day.day_index,
        "route_type": day.route_type or "city",
        "items": [
            {
                "seq": item.seq,
                "poi_name": item.poi_name,
                "duration_h": 1.5,
                "travel_minutes_from_prev": item.travel_minutes or 0,
            }
            for item in sorted(day.items, key=lambda it: it.seq)
        ],
    }

    try:
        result = json.loads(
            optimize_itinerary(
                json.dumps({"city": city, "days": [day_json]}, ensure_ascii=False),
                reorder=False,
            )
        )
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Reoptimize failed")

    updated_items = (result.get("days") or [{}])[0].get("items") or []
    for item, updated in zip(sorted(day.items, key=lambda it: it.seq), updated_items):
        item.lat = updated.get("lat", item.lat)
        item.lng = updated.get("lng", item.lng)
        item.transport_mode = updated.get("transport_mode", item.transport_mode)
        item.travel_minutes = updated.get("travel_minutes_from_prev", item.travel_minutes)
        item.route_polyline = updated.get("route_polyline", item.route_polyline)
        item.route_verified = updated.get("route_verified", item.route_verified)
        item.travel_advice = updated.get("travel_advice", item.travel_advice)
        item.amap_poi_id = updated.get("amap_poi_id", item.amap_poi_id)
        item.poi_address = updated.get("poi_address", item.poi_address)
        item.poi_type = updated.get("poi_type", item.poi_type)

    recalculate_day_schedule(day)

    db.commit()
    db.refresh(trip)
    return trip