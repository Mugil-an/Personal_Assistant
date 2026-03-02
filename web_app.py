"""FastAPI web application for multi-user Personal Assistant."""

import json
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from googleapiclient.discovery import build
from pydantic import BaseModel

from auth_web import create_auth_flow, get_user_services
from calendar_manager import create_event
from config import (
    CALENDAR_ID, DEFAULT_EVENT_DURATION_MIN,
    GMAIL_MAX_RESULTS, GMAIL_QUERY, TIMEZONE,
)
from daily_plan import get_today_schedule
from email_parser import parse_email_with_gemini
from gmail_reader import fetch_emails
from models import Session, User
from notifier import send_whatsapp

logger = logging.getLogger(__name__)

app = FastAPI(title="Personal Assistant", version="1.0.0")

# Change this to your deployed URL in production (e.g. https://yourdomain.com)
BASE_URL = "http://localhost:8000"
REDIRECT_URI = f"{BASE_URL}/oauth/callback"


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/signup", summary="Begin Google OAuth sign-up")
def signup():
    """Redirects the user to Google's OAuth2 consent screen."""
    flow = create_auth_flow(REDIRECT_URI)
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    return RedirectResponse(auth_url)


@app.get("/oauth/callback", summary="Google OAuth callback")
def oauth_callback(request: Request):
    """Google redirects here after the user grants permission.

    Stores the OAuth token and creates (or updates) the user record.
    """
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing 'code' parameter from Google.")

    flow = create_auth_flow(REDIRECT_URI)
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Fetch the user's Google profile info
    profile_svc = build("oauth2", "v2", credentials=creds)
    info = profile_svc.userinfo().get().execute()
    user_id    = info["id"]
    user_email = info["email"]

    db = Session()
    try:
        user = db.get(User, user_id)
        if not user:
            user = User(id=user_id, email=user_email)
            logger.info("New user signed up: %s", user_email)
        else:
            logger.info("Existing user re-authenticated: %s", user_email)

        user.token_json = json.loads(creds.to_json())
        db.add(user)
        db.commit()
    finally:
        db.close()

    return JSONResponse({
        "message": f"✅ Signed up successfully as {user_email}!",
        "user_id": user_id,
        "next_step": f"POST {BASE_URL}/preferences to set your notification time and email address.",
    })


# ---------------------------------------------------------------------------
# Preferences route
# ---------------------------------------------------------------------------

@app.post("/preferences", summary="Set notification time and email address")
def set_preferences(
    user_id:      str = Query(...,        description="Your Google user ID returned after sign-up"),
    notify_time:  str = Query("07:00",    description="Daily notification time in HH:MM 24h format"),
    timezone:     str = Query("UTC",      description="Your timezone, e.g. Asia/Kolkata"),
    notify_email: str = Query(...,        description="Email address to receive your daily schedule"),
):
    """Save the user's notification time and email address."""
    db = Session()
    try:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found. Please sign up first.")

        user.notify_time  = notify_time
        user.timezone     = timezone
        user.notify_email = notify_email
        db.commit()
    finally:
        db.close()

    return {
        "message": "✅ Preferences saved!",
        "notify_time":  notify_time,
        "timezone":     timezone,
        "notify_email": notify_email,
    }


# ---------------------------------------------------------------------------
# Health + config
# ---------------------------------------------------------------------------

@app.get("/", summary="Health check")
def health():
    return {"status": "ok"}


@app.get("/api/config", summary="App configuration")
def api_config():
    return {
        "gmail_query":            GMAIL_QUERY,
        "gmail_max_results":      GMAIL_MAX_RESULTS,
        "calendar_id":            CALENDAR_ID,
        "timezone":               TIMEZONE,
        "default_event_duration": DEFAULT_EVENT_DURATION_MIN,
    }


# ---------------------------------------------------------------------------
# Status route
# ---------------------------------------------------------------------------

@app.get("/status", summary="Check your current preferences")
def get_status(user_id: str = Query(...)):
    db = Session()
    try:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        return {
            "email":        user.email,
            "notify_time":  user.notify_time,
            "timezone":     user.timezone,
            "notify_email": user.notify_email,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class RunAssistantRequest(BaseModel):
    user_id:     str
    gmail_query: Optional[str] = None
    max_results: Optional[int] = None
    send_email:  bool          = False


class FetchEmailsRequest(BaseModel):
    user_id:     str
    query:       Optional[str] = None
    max_results: Optional[int] = None


class CreateEventRequest(BaseModel):
    user_id:     str
    subject:     str
    description: str


# ---------------------------------------------------------------------------
# Run full assistant pipeline
# ---------------------------------------------------------------------------

@app.post("/api/run-assistant")
def run_assistant(req: RunAssistantRequest):
    db = Session()
    try:
        user = db.get(User, req.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
    finally:
        db.close()

    try:
        gmail, calendar = get_user_services(user.token_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auth failed: {exc}")

    emails = fetch_emails(gmail, query=req.gmail_query, max_results=req.max_results)
    events_created = 0
    details = []

    for email in emails:
        subject = email.get("subject", "")
        body    = email.get("body", "")
        parsed  = parse_email_with_gemini(body)
        intent  = parsed.get("intent", "")  if parsed else ""
        summary = parsed.get("summary", "") if parsed else ""
        created = False

        if intent == "Event Scheduling":
            try:
                create_event(calendar, subject, body)
                events_created += 1
                created = True
            except Exception:
                pass

        details.append({
            "subject":       subject,
            "intent":        intent,
            "summary":       summary,
            "event_created": created,
        })

    if req.send_email and user.notify_email:
        schedule = get_today_schedule(calendar)
        send_whatsapp(schedule, to=user.notify_email)

    return {
        "message":          "Assistant workflow complete.",
        "emails_processed": len(emails),
        "events_created":   events_created,
        "details":          details,
    }


# ---------------------------------------------------------------------------
# Fetch + parse emails
# ---------------------------------------------------------------------------

@app.post("/api/fetch-emails")
def api_fetch_emails(req: FetchEmailsRequest):
    db = Session()
    try:
        user = db.get(User, req.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
    finally:
        db.close()

    try:
        gmail, _ = get_user_services(user.token_json)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auth failed: {exc}")

    emails = fetch_emails(gmail, query=req.query, max_results=req.max_results)
    result = []
    for email in emails:
        body   = email.get("body", "")
        parsed = parse_email_with_gemini(body)
        result.append({
            "subject":          email.get("subject", ""),
            "from_":            email.get("from_", ""),
            "date":             email.get("date", ""),
            "body_preview":     body[:300],
            "intent":           parsed.get("intent", "")           if parsed else "",
            "summary":          parsed.get("summary", "")          if parsed else "",
            "suggested_action": parsed.get("suggested_action", "") if parsed else "",
            "attachments":      len(email.get("attachments", [])),
        })
    return {"count": len(result), "emails": result}


# ---------------------------------------------------------------------------
# Today's schedule
# ---------------------------------------------------------------------------

@app.get("/api/schedule")
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


# ---------------------------------------------------------------------------
# Create calendar event
# ---------------------------------------------------------------------------

@app.post("/api/create-event")
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
