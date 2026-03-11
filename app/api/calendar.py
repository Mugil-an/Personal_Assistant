"""Calendar-related API routes: today's schedule and event creation."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.auth_web import get_user_services
from app.models import Session, User
from app.services.calendar_manager import create_event
from app.services.daily_plan import get_today_schedule

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateEventRequest(BaseModel):
    user_id:     str
    subject:     str
    description: str


@router.get("/api/schedule")
def api_schedule(user_id: str = Query(...)):
    db = Session()
    try:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
    finally:
        db.close()

    try:
        _, calendar = get_user_services(user.token_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auth failed: {exc}")

    return {"schedule": get_today_schedule(calendar)}


@router.post("/api/create-event")
def api_create_event(req: CreateEventRequest):
    db = Session()
    try:
        user = db.get(User, req.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
    finally:
        db.close()

    try:
        _, calendar = get_user_services(user.token_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auth failed: {exc}")

    try:
        create_event(calendar, req.subject, req.description)
        return {"message": f"Event '{req.subject}' created successfully."}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create event: {exc}")
