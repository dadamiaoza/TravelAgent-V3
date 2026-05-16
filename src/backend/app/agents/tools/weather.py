"""Weather query tool — Step 1 of agent learning path."""


def get_weather(city: str, date: str) -> str:
    """Query weather for a city on a specific date.

    Args:
        city: City name in Chinese or English, e.g. "北京" or "Beijing"
        date: Date in YYYY-MM-DD format, e.g. "2026-06-01"

    Returns:
        Weather summary string including temperature, conditions, and wind.
    """
    # Mock data — replace with real API (e.g. QWeather) later
    return f"{city} {date}：晴转多云，15°C ~ 25°C，东北风 2-3 级，适合出行"
