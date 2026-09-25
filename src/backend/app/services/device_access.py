"""Anonymous device cookie and server-side trip ownership.

The browser does not invent or filter a device key. This module issues an
HttpOnly cookie and every trip read/write checks ``trips.device_id``.

A demo session (see ``demo_auth``) may also stamp ``user_id``. Logged-out
callers only see unclaimed rows. Logged-in callers see this device's
unclaimed rows plus rows claimed by that demo user. Other devices never match.
"""
from uuid import UUID, uuid4

from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.models.trip import Trip
from app.services.demo_auth import read_session_user

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
    request.state.user_id = read_session_user(request)
    return device_id


def trip_visible_to(trip: Trip | None, device_id: str, user_id: str | None) -> bool:
    """Device scope first. Session only widens to trips claimed by that user."""
    if trip is None or trip.device_id != device_id:
        return False
    if user_id:
        return trip.user_id in (None, user_id)
    return trip.user_id is None


def load_owned_trip(
    db: Session,
    trip_id: UUID,
    device_id: str,
    user_id: str | None = None,
) -> Trip:
    """Return the trip only when this caller may see it.

    Missing rows, other devices, legacy rows with a null ``device_id``,
    and claimed rows read without a session all 404.
    """
    trip = (
        db.query(Trip)
        .filter(Trip.id == trip_id, Trip.device_id == device_id)
        .first()
    )
    if not trip_visible_to(trip, device_id, user_id):
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip
