"""Itinerary persistence helpers.

This module converts a generated itinerary draft into ORM rows.
It is kept separate from generation so the generator strategy can stay pure
and application orchestration can own transaction boundaries.
"""
from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.models.trip import Trip, ItineraryDay, ItineraryItem


def persist_itinerary(db: Session, trip: Trip, itinerary: dict, start_date: date):
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
            route_type=day_data.get("route_type") or "city",
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
                amap_poi_id=item_data.get("amap_poi_id"),
                poi_address=item_data.get("poi_address"),
                poi_type=item_data.get("poi_type"),
                route_verified=item_data.get("route_verified"),
                travel_advice=item_data.get("travel_advice"),
            )
            db.add(item)
            accumulated_minutes = start_minutes + duration_m

    trip.status = "generated"
    db.commit()
    db.refresh(trip)

def _build_item_from_data(day, item_data: dict, start_minutes: int):
    duration_m = int(item_data.get("duration_h", 1.5) * 60)
    travel_m = item_data.get("travel_minutes_from_prev", 0)
    start_minutes = start_minutes + travel_m
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
        amap_poi_id=item_data.get("amap_poi_id"),
        poi_address=item_data.get("poi_address"),
        poi_type=item_data.get("poi_type"),
        route_verified=item_data.get("route_verified"),
        travel_advice=item_data.get("travel_advice"),
    )
    db.add(item)
    return start_minutes + duration_m


def replace_day(
    db: Session,
    trip: Trip,
    day_index: int,
    day_data: dict,
    start_date: date,
):
    """Atomically replace one day (delete old + insert new) within the current transaction."""
    existing = (
        db.query(ItineraryDay)
        .filter(ItineraryDay.trip_id == trip.id, ItineraryDay.day_index == day_index)
        .first()
    )
    if existing:
        db.delete(existing)
        db.flush()

    day = ItineraryDay(
        trip_id=trip.id,
        day_index=day_index,
        date=start_date + timedelta(days=day_index - 1),
        route_type=day_data.get("route_type") or "city",
    )
    db.add(day)
    db.flush()

    accumulated = 9 * 60
    for item_data in day_data.get("items", []):
        accumulated = _build_item_from_data(db, day, item_data, accumulated)

    return day
