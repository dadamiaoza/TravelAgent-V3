"""Itinerary time scheduler adapter.

Implements the TimeScheduler port by delegating to the pure scheduling
helper in the itinerary service.
"""
from app.services.itinerary import recalculate_day_schedule


class ItineraryTimeScheduler:
    def recalculate(self, day) -> None:
        recalculate_day_schedule(day)