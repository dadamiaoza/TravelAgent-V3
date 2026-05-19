"""Route optimization tool — geocode POIs and fill lat/lng coordinates.

In Step 5, this tool keeps the original POI order and only fills coordinates.
Real route reordering (TSP nearest-neighbor with Amap route distances) is deferred to Step 7.
"""
import json

from app.agents.tools.geo import geocode_poi


def optimize_itinerary(itinerary_json: str) -> str:
    """Geocode all POIs in an itinerary and fill lat/lng coordinates.

    Does NOT reorder POIs (排序延后到 Step 7 用高德真实路径实现).
    POI order is preserved exactly as input.

    Args:
        itinerary_json: JSON string with structure:
            {"days": [{"day_index": 1, "theme": "...", "items": [
                {"seq": 1, "poi_name": "...", "duration_h": 0, "travel_minutes_from_prev": 0}
            ]}]}

    Returns:
        JSON string with same structure, each item augmented with "lat" and "lng" fields.
    """
    itinerary = json.loads(itinerary_json)

    for day in itinerary.get("days", []):
        for item in day.get("items", []):
            result = geocode_poi(item["poi_name"])
            item["lat"] = result["lat"]
            item["lng"] = result["lng"]

    return json.dumps(itinerary, ensure_ascii=False)
