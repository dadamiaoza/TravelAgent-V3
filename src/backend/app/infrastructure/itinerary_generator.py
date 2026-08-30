"""LangGraph/LangChain itinerary generator adapter.

Implements the TripGenerator port by delegating to the pure
generate_itinerary_draft strategy. The application orchestrator never talks
to the agent directly.
"""
from app.services.itinerary import generate_itinerary_draft


class LangGraphTripGenerator:
    def generate(self, **kwargs) -> dict:
        return generate_itinerary_draft(**kwargs)

    def generate_day(self, **kwargs) -> dict:
        day_index = kwargs.pop("day_index")
        draft = self.generate(**kwargs)
        for day in draft.get("days", []):
            if day.get("day_index") == day_index:
                return day
        raise ValueError(f"generated draft does not contain day {day_index}")