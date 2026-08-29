"""Amap geocoding adapter."""
from app.agents.tools.geo import geocode_poi


class AmapGeocoder:
    def geocode(self, name: str, city: str) -> dict | None:
        try:
            return geocode_poi(name, city=city or "", mock_fallback=True)
        except Exception:
            return None