"""Demo auth HTTP API. One click, no email."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.demo_auth import (
    DEMO_USER_ID,
    claim_device_trips,
    clear_session,
    demo_user,
    issue_session,
)
from app.services.device_access import ensure_device_cookie

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    dependencies=[Depends(ensure_device_cookie)],
)


class DemoUserOut(BaseModel):
    id: str
    display_name: str


class DemoSessionOut(BaseModel):
    demo_auth: bool
    user: DemoUserOut | None


def _session_out(user_id: str | None) -> DemoSessionOut:
    user = DemoUserOut(**demo_user()) if user_id == DEMO_USER_ID else None
    return DemoSessionOut(demo_auth=settings.demo_auth, user=user)


@router.get("/me", response_model=DemoSessionOut)
def me(request: Request):
    return _session_out(getattr(request.state, "user_id", None))


@router.post("/demo/login", response_model=DemoSessionOut)
def demo_login(request: Request, response: Response, db: Session = Depends(get_db)):
    """Sign in as the stable demo user and claim this device's trips."""
    if not settings.demo_auth:
        raise HTTPException(status_code=404, detail="Not found")
    issue_session(response)
    request.state.user_id = DEMO_USER_ID
    claim_device_trips(db, request.state.device_id, DEMO_USER_ID)
    return _session_out(DEMO_USER_ID)


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    """Clear the demo session. The device cookie is left in place."""
    clear_session(response)
