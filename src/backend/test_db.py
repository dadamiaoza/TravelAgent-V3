"""Test DB scaffolding: create trip, generate itinerary, read back."""
import sys
sys.path.insert(0, ".")

from app.db.session import SessionLocal
from app.models.trip import Trip
from app.schemas.trip import TripCreate
from app.services.itinerary import generate_itinerary

db = SessionLocal()

# 1. Create trip
print("[1] Creating trip...")
trip = Trip(
    destination="北京",
    start_date="2026-06-01",
    end_date="2026-06-03",
    people_count=2,
)
db.add(trip)
db.commit()
db.refresh(trip)
print(f"    ID={trip.id}, status={trip.status}")

# 2. Generate itinerary
print("[2] Generating itinerary...")
trip = generate_itinerary(db, trip)
print(f"    Status={trip.status}, Days={len(trip.days)}")
for day in trip.days:
    items_str = ", ".join(f"{i.poi_name}@{i.start_time}" for i in day.items)
    print(f"    Day{day.day_index} {day.date}: {len(day.items)} items → {items_str}")

# 3. Read back
print("[3] Reading back...")
trip2 = db.query(Trip).filter(Trip.id == trip.id).first()
print(f"    Found: {trip2.destination}, {len(trip2.days)} days")

db.close()
print("All tests passed!")
