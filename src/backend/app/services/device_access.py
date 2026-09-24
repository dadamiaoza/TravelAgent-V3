"""Anonymous device cookie and server-side trip ownership.

The browser does not invent or filter a device key. This module issues an
HttpOnly cookie and every trip read/write checks ``trips.device_id``.
"""
from uuid import UUID, uuid4

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.models.trip import Trip

DEVICE_COOKIE = "ta_device"
_MAX_AGE_SECONDS = 60 * 60 * 24 * 365


def ensure_device_cookie(request: Request, response: Response) -> str:
    """Reuse a valid ``ta_device`` cookie, or issue a new server-side id."""
    raw = (request.cookies.get(DEVICE_COOKIE) or "").strip()
    try:
        device_id = str(UUID(raw))
    except ValueError:
        device_id = str(uuid4())
        response.set_cookie(
            DEVICE_COOKIE,
            device_id,
            max_age=_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
            path="/",
        )
    request.state.device_id = device_id
    return device_id


def load_owned_trip(db: Session, trip_id: UUID, device_id: str) -> Trip:
    """Return the trip only when it is bound to this device.

    Missing rows, other devices, and legacy rows with a null ``device_id``
    all 404. Callers cannot tell those cases apart.
    """
    trip = (
        db.query(Trip)
        .filter(Trip.id == trip_id, Trip.device_id == device_id)
        .first()
    )
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip
