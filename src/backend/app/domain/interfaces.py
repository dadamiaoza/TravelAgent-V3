"""Ports (interfaces) for trip application services.

The application/service layer depends only on these abstractions.
Infrastructure adapters (Amap, DB, etc.) implement them so future AI
delta / snapshot / rollback can swap implementations without touching
trip_editor business logic.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class RouteReplanner(Protocol):
    """Recompute travel times/routes for a day without changing order."""

    def reoptimize(
        self,
        *,
        city: str,
        route_type: str,
        items: list[dict],
    ) -> list[dict]:
        """Return updated item dicts in the same order as input."""
        ...


@runtime_checkable
class TimeScheduler(Protocol):
    """Recalculate start/end times for a day's items."""

    def recalculate(self, day) -> None:
        ...


@runtime_checkable
class Geocoder(Protocol):
    """Resolve a POI name to structured location data."""

    def geocode(self, name: str, city: str) -> dict | None:
        ...

@runtime_checkable
class TripGenerator(Protocol):
    """Generate itinerary drafts (no persistence side effects)."""

    def generate(self, **kwargs) -> dict:
        """Generate a full itinerary draft."""
        ...

    def generate_day(self, **kwargs) -> dict:
        """Generate a single day draft (day_index passed via kwargs)."""
        ...
