"""Itinerary persistence helpers.

This module converts a generated itinerary draft into ORM rows.
It is kept separate from generation so the generator strategy can stay pure
and application orchestration can own transaction boundaries.
"""
from datetime import date, time, timedelta

from sqlalchemy.orm import Session

from app.models.trip import Trip, ItineraryDay, ItineraryItem
from app.services.visit_fields import copy_visit_fields


def persist_itinerary(
    db: Session,
    trip: Trip,
    itinerary: dict,
    start_date: date,
    *,
    commit: bool = True,
):
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

            visit = copy_visit_fields(item_data)
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
                suggested_duration_h=visit.get("suggested_duration_h"),
                best_time=visit.get("best_time"),
                cost_note=visit.get("cost_note"),
                opening_hours=visit.get("opening_hours"),
                visit_tips=visit.get("visit_tips"),
                fact_warning=visit.get("fact_warning"),
            )
            db.add(item)
            accumulated_minutes = start_minutes + duration_m

    trip.status = "generated"
    if commit:
        db.commit()
        db.refresh(trip)
