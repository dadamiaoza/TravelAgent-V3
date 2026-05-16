"""Itinerary generation service — template-based for MVP (S1).

Will be replaced by LangChain itinerary_gen agent in Step 3.
"""
from datetime import date, time, timedelta
from sqlalchemy.orm import Session
from app.models.trip import Trip, ItineraryDay, ItineraryItem


def generate_itinerary(db: Session, trip: Trip) -> Trip:
    """Generate a simple day-by-day itinerary with mock POIs."""
    day_count = (trip.end_date - trip.start_date).days + 1
    mock_pois = ["当地热门景点", "推荐餐厅", "文化地标", "购物中心", "公园漫步", "博物馆"]

    for day_idx in range(day_count):
        day_date = trip.start_date + timedelta(days=day_idx)
        day = ItineraryDay(
            trip_id=trip.id,
            day_index=day_idx + 1,
            date=day_date,
        )
        db.add(day)
        db.flush()

        # Assign 3-5 POIs per day
        for seq, poi in enumerate(mock_pois[: (3 + day_idx % 3)], start=1):
            item = ItineraryItem(
                day_id=day.id,
                seq=seq,
                poi_name=f"Day{day_idx+1} {poi}",
                start_time=time(9 + seq * 2, 0),
                end_time=time(10 + seq * 2, 0),
            )
            db.add(item)

    trip.status = "generated"
    db.commit()
    db.refresh(trip)
    return trip
