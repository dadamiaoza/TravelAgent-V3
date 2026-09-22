"""Amap-based route replanner adapter.

Implements the RouteReplanner port by delegating to the route optimizer.
Explicit reoptimize asks for nearest-neighbor order (respect_fill_order=False).
Generation keeps fill order unless sanity checks fail.
"""
import json

from app.agents.tools.route_optimizer import optimize_itinerary


class AmapRouteReplanner:
    def reoptimize(
        self,
        *,
        city: str,
        route_type: str,
        items: list[dict],
    ) -> list[dict]:
        day_json = {
            "day_index": 1,
            "route_type": route_type,
            "items": items,
        }
        result = json.loads(
            optimize_itinerary(
                json.dumps({"city": city, "days": [day_json]}, ensure_ascii=False),
                respect_fill_order=False,
            )
        )
        return (result.get("days") or [{}])[0].get("items") or []