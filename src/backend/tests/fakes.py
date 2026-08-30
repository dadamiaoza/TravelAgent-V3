"""Shared fakes for unit tests of the trip editor / application layer."""
from typing import Callable


class FakeRouteReplanner:
    def __init__(self, updated_items: list[dict] | None = None):
        self.updated_items = updated_items or []
        self.calls: list[dict] = []

    def reoptimize(self, *, city: str, route_type: str, items: list[dict]) -> list[dict]:
        self.calls.append({"city": city, "route_type": route_type, "items": items})
        return self.updated_items or items


class FakeTimeScheduler:
    def __init__(self, side_effect: Callable | None = None):
        self.side_effect = side_effect
        self.calls: list = []

    def recalculate(self, day) -> None:
        self.calls.append(day)
        if self.side_effect:
            self.side_effect(day)


class FakeGeocoder:
    def __init__(self, result: dict | None = None):
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def geocode(self, name: str, city: str) -> dict | None:
        self.calls.append((name, city))
        return self.result


class FakeTripGenerator:
    def __init__(self, draft: dict | None = None, day_draft: dict | None = None):
        self.draft = draft or {"days": []}
        self.day_draft = day_draft or {"day_index": 1, "route_type": "city", "items": []}
        self.generate_calls: list[dict] = []
        self.generate_day_calls: list[dict] = []

    def generate(self, **kwargs) -> dict:
        self.generate_calls.append(kwargs)
        return self.draft

    def generate_day(self, **kwargs) -> dict:
        self.generate_day_calls.append(kwargs)
        return self.day_draft