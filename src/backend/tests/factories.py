"""Factories for building minimal ORM instances in tests."""
from datetime import date, time
from uuid import uuid4

from app.models.trip import Trip, ItineraryDay, ItineraryItem


def make_trip(
    *,
    destination: str = "杭州",
    city: str | None = None,
    start_date: date = date(2026, 6, 1),
    end_date: date = date(2026, 6, 3),
    people_count: int = 2,
    user_prompt: str | None = None,
    must_visit: list[str] | None = None,
) -> Trip:
    return Trip(
        destination=destination,
        city=city,
        start_date=start_date,
        end_date=end_date,
        people_count=people_count,
        user_prompt=user_prompt,
        must_visit=must_visit,
    )


def make_day(
    *,
    trip_id: object | None = None,
    day_index: int = 1,
    date_value: date = date(2026, 6, 1),
    route_type: str = "city",
) -> ItineraryDay:
    return ItineraryDay(
        trip_id=trip_id,
        day_index=day_index,
        date=date_value,
        route_type=route_type,
    )


def make_item(
    *,
    day_id: object | None = None,
    seq: int = 1,
    poi_name: str = "测试景点",
    start_time: time | None = time(9, 0),
    end_time: time | None = time(10, 0),
    lat: float | None = 30.0,
    lng: float | None = 120.0,
    travel_minutes: int = 0,
) -> ItineraryItem:
    return ItineraryItem(
        day_id=day_id,
        seq=seq,
        poi_name=poi_name,
        start_time=start_time,
        end_time=end_time,
        lat=lat,
        lng=lng,
        travel_minutes=travel_minutes,
    )