"""One-click demo session. No email, no SMTP, no verification code.

The session is an HttpOnly JWT cookie for a single stable demo user.
Login claims the current device's trips onto that user. Logout deletes
only the session cookie; ``ta_device`` stays so anonymous create still works.
Trip reads stay device-scoped, so another browser cannot see these trips.
"""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Request, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.trip import Trip

SESSION_COOKIE = "ta_session"
DEMO_USER_ID = "demo-user"
DEMO_DISPLAY_NAME = "演示用户"
_MAX_AGE_SECONDS = 60 * 60 * 24 * 7
_ALGORITHM = "HS256"


def demo_user() -> dict[str, str]:
    return {"id": DEMO_USER_ID, "display_name": DEMO_DISPLAY_NAME}


def read_session_user(request: Request) -> str | None:
    """Return the demo user id when the session cookie is valid."""
    if not settings.demo_auth:
        return None
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        payload = jwt.decode(raw, settings.demo_session_secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("sub") != DEMO_USER_ID:
        return None
    return DEMO_USER_ID


def issue_session(response: Response) -> dict[str, str]:
    expires = datetime.now(timezone.utc) + timedelta(seconds=_MAX_AGE_SECONDS)
    token = jwt.encode(
        {"sub": DEMO_USER_ID, "name": DEMO_DISPLAY_NAME, "exp": expires},
        settings.demo_session_secret,
        algorithm=_ALGORITHM,
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return demo_user()


def clear_session(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="lax")


def claim_device_trips(db: Session, device_id: str, user_id: str) -> int:
    """Stamp this device's trips with the demo user. Idempotent.

    Rows already owned by someone else, and rows on other devices, are left
    alone. ``device_id`` stays so a second browser remains isolated.
    """
    rows = (
        db.query(Trip)
        .filter(
            Trip.device_id == device_id,
            or_(Trip.user_id.is_(None), Trip.user_id == user_id),
        )
        .all()
    )
    changed = 0
    for row in rows:
        if row.user_id != user_id:
            row.user_id = user_id
            changed += 1
    if changed:
        db.commit()
    return changed
