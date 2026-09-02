"""Postgres-backed cache store for Amap geocoding/direction results."""
from sqlalchemy.orm import Session

from app.models.trip import AmapCache


def get_cache(db: Session, cache_type: str, cache_key: str) -> dict | None:
    row = (
        db.query(AmapCache)
        .filter(AmapCache.cache_type == cache_type, AmapCache.cache_key == cache_key)
        .first()
    )
    return row.payload if row else None


def set_cache(db: Session, cache_type: str, cache_key: str, payload: dict) -> None:
    row = (
        db.query(AmapCache)
        .filter(AmapCache.cache_type == cache_type, AmapCache.cache_key == cache_key)
        .first()
    )
    if row:
        row.payload = payload
        row.updated_at = None  # let server_default/onupdate handle
    else:
        db.add(AmapCache(cache_type=cache_type, cache_key=cache_key, payload=payload))
    db.commit()