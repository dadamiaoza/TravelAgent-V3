"""Attraction opening hours tool — Step 2 of agent learning path."""


def get_opening_hours(name: str, date: str) -> str:
    """Query the opening hours and ticket information for a scenic spot.

    Args:
        name: Name of the scenic spot in Chinese, e.g. "故宫博物院"
        date: Date in YYYY-MM-DD format, e.g. "2026-06-01"

    Returns:
        Opening hours, ticket price, and reservation status.
    """
    # Mock data — replace with real API (e.g. Amap POI) later
    return f"{name}：{date} 开放时间 08:30-17:00（16:00 停止入园），门票 60 元，当日可预约"
