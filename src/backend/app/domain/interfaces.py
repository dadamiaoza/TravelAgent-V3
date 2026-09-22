"""Ports (interfaces) for trip application services.

The application/service layer depends only on these abstractions.
Infrastructure adapters (Amap, DB, etc.) implement them so future AI
delta / snapshot / rollback can swap implementations without touching
trip_editor business logic.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class RouteReplanner(Protocol):
    """Recompute travel times. Explicit reoptimize may reorder within the day."""

    def reoptimize(
        self,
        *,
        city: str,
        route_type: str,
        items: list[dict],
    ) -> list[dict]:
        """Return updated item dicts. Order may follow nearest-neighbor."""
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
