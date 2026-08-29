"""Pure unit tests for itinerary schedule recalculation."""
from datetime import time
from types import SimpleNamespace

from app.services.itinerary import recalculate_day_schedule


def _item(seq, travel=0, start=time(9, 0), end=time(10, 0)):
    return SimpleNamespace(
        seq=seq,
        travel_minutes=travel,
        start_time=start,
        end_time=end,
    )


def test_recalculate_day_schedule_sets_all_times():
    day = SimpleNamespace(items=[
        _item(1, travel=0),
        _item(2, travel=30),
        _item(3, travel=15),
    ])

    recalculate_day_schedule(day)

    assert day.items[0].start_time == time(9, 0)
    assert day.items[0].end_time == time(10, 0)
    assert day.items[1].start_time == time(10, 30)
    assert day.items[1].end_time == time(11, 30)
    assert day.items[2].start_time == time(11, 45)
    assert day.items[2].end_time == time(12, 45)


def test_recalculate_day_schedule_uses_default_duration_when_null():
    day = SimpleNamespace(items=[
        _item(1, start=None, end=None),
    ])

    recalculate_day_schedule(day)

    assert day.items[0].start_time == time(9, 0)
    assert day.items[0].end_time == time(10, 30)  # default 1.5h
