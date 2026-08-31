"""LangGraph/LangChain itinerary generator adapter.

Implements the TripGenerator port by delegating to the pure
generate_itinerary_draft strategy. The application orchestrator never talks
to the agent directly.
"""
from app.services.itinerary import generate_itinerary_draft


class LangGraphTripGenerator:
    def generate(self, **kwargs) -> dict:
        return generate_itinerary_draft(**kwargs)