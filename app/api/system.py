"""System routes: health check, app config, and user status."""

import logging

from fastapi import APIRouter, HTTPException, Query

from app.config import (
    CALENDAR_ID, DEFAULT_EVENT_DURATION_MIN,
    GMAIL_MAX_RESULTS, GMAIL_QUERY, TIMEZONE,
)
from app.models import Session, User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", summary="Health check")
def health():
    return {"status": "ok"}


@router.get("/api/config", summary="App configuration")
def api_config():
    return {
        "gmail_query":            GMAIL_QUERY,
        "gmail_max_results":      GMAIL_MAX_RESULTS,
        "calendar_id":            CALENDAR_ID,
        "timezone":               TIMEZONE,
        "default_event_duration": DEFAULT_EVENT_DURATION_MIN,
    }


@router.get("/status", summary="Check your current preferences")
def get_status(user_id: str = Query(...)):
    db = Session()
    try:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        return {
            "email":            user.email,
            "notify_time":      user.notify_time,
            "timezone":         user.timezone,
            "notify_email":     user.notify_email,
            "gmail_query":      user.gmail_query,
            "email_sync_hours": user.email_sync_hours or 24,
        }
    finally:
        db.close()
