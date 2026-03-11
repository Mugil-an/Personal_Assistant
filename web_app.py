"""FastAPI web application for multi-user Personal Assistant."""

import json
import logging
import os
from typing import Optional

# Allow OAuth over plain HTTP in development (localhost). Remove in production.
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
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
from models import Session, User, LinkedAccount
from notifier import send_whatsapp

logger = logging.getLogger(__name__)

app = FastAPI(title="Personal Assistant", version="1.0.0")

# Change this to your deployed URL in production (e.g. https://yourdomain.com)
BASE_URL = "http://localhost:8000"
REDIRECT_URI = f"{BASE_URL}/oauth/callback"
STREAMLIT_URL = "http://localhost:8501"

# In-memory store of OAuth flows keyed by state.
# This preserves the PKCE code_verifier that lives inside the flow object.
# The callback must reuse the SAME flow instance that generated the auth URL.
_pending_flows: dict = {}


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.get("/signup", summary="Begin Google OAuth sign-up")
def signup():
    """Redirects the user to Google's OAuth2 consent screen."""
    flow = create_auth_flow(REDIRECT_URI)
    auth_url, state = flow.authorization_url(prompt="consent", access_type="offline")
    # Stash the flow so the callback can reuse it (and its PKCE code_verifier).
    _pending_flows[state] = flow
    return RedirectResponse(auth_url)


@app.get("/oauth/callback", summary="Google OAuth callback")
def oauth_callback(request: Request):
    """Google redirects here after the user grants permission.

    Stores the OAuth token and creates (or updates) the user record.
    """
    # Check for OAuth error response from Google
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")

    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Missing 'code' parameter from Google.")

    state = request.query_params.get("state")
    try:
        # Reuse the original flow that holds the PKCE code_verifier.
        flow = _pending_flows.pop(state, None)
        if flow is None:
            # Fallback: reconstruct flow (works only when PKCE is not used)
            flow = create_auth_flow(REDIRECT_URI, state=state)
        flow.fetch_token(authorization_response=str(request.url))
        creds = flow.credentials
    except Exception as exc:
        logger.exception("Token exchange failed")
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {exc}")

    try:
        # Fetch the user's Google profile info using the userinfo endpoint directly
        import requests as _requests
        userinfo_resp = _requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=10,
        )
        userinfo_resp.raise_for_status()
        info = userinfo_resp.json()
        user_id    = info.get("sub") or info.get("id")
        user_email = info.get("email")
        if not user_id or not user_email:
            raise ValueError(f"Incomplete profile info returned: {info}")
    except Exception as exc:
        logger.exception("Failed to fetch user profile")
        raise HTTPException(status_code=500, detail=f"Failed to fetch user profile: {exc}")

    token_dict = json.loads(creds.to_json())

    db = Session()
    try:
        user = db.get(User, user_id)
        if not user:
            user = User(id=user_id, email=user_email, token_json=token_dict)
            logger.info("New user signed up: %s", user_email)
        else:
            user.token_json = token_dict
            logger.info("Existing user re-authenticated: %s", user_email)

        db.add(user)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Database error during sign-up")
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")
    finally:
        db.close()

    return RedirectResponse(f"{STREAMLIT_URL}/?user_id={user_id}")


# ---------------------------------------------------------------------------
# Link additional Gmail account
# ---------------------------------------------------------------------------

# Pending flows for the link-account OAuth loop (keyed by state).
_link_pending_flows: dict = {}


@app.get("/link-account", summary="Begin linking a secondary Gmail account")
def link_account(owner_id: str = Query(..., description="Primary user ID")):
    """Start a second OAuth flow so the user can grant access to another Gmail account."""
    flow = create_auth_flow(f"{BASE_URL}/link-account/callback")
    auth_url, state = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        login_hint="",          # force account chooser
    )
    _link_pending_flows[state] = (flow, owner_id)
    return RedirectResponse(auth_url)


@app.get("/link-account/callback", summary="OAuth callback for linked account")
def link_account_callback(request: Request):
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")

    code  = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code:
        raise HTTPException(status_code=400, detail="Missing 'code' parameter.")

    entry = _link_pending_flows.pop(state, None)
    if entry is None:
        raise HTTPException(status_code=400, detail="Unknown OAuth state. Please try again.")
    flow, owner_id = entry

    try:
        flow.fetch_token(authorization_response=str(request.url))
        creds = flow.credentials
    except Exception as exc:
        logger.exception("Token exchange failed for linked account")
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {exc}")

    try:
        import requests as _requests
        userinfo_resp = _requests.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=10,
        )
        userinfo_resp.raise_for_status()
        info       = userinfo_resp.json()
        account_id = info.get("sub") or info.get("id")
        email      = info.get("email")
        if not account_id or not email:
            raise ValueError(f"Incomplete profile info: {info}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to fetch profile: {exc}")

    if account_id == owner_id:
        raise HTTPException(
            status_code=400,
            detail="This is already your primary account. Please choose a different account.",
        )

    token_dict = json.loads(creds.to_json())
    db = Session()
    try:
        existing = db.get(LinkedAccount, account_id)
        if existing:
            existing.token_json = token_dict
            existing.owner_id   = owner_id
            existing.email      = email
        else:
            db.add(LinkedAccount(
                id=account_id, owner_id=owner_id,
                email=email, token_json=token_dict,
            ))
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {exc}")
    finally:
        db.close()

    return RedirectResponse(f"{STREAMLIT_URL}/?user_id={owner_id}")


@app.get("/linked-accounts", summary="List linked Gmail accounts for a user")
def list_linked_accounts(user_id: str = Query(...)):
    db = Session()
    try:
        accounts = db.query(LinkedAccount).filter(LinkedAccount.owner_id == user_id).all()
        return [{"id": a.id, "email": a.email} for a in accounts]
    finally:
        db.close()


@app.delete("/linked-accounts/{account_id}", summary="Remove a linked Gmail account")
def delete_linked_account(account_id: str, user_id: str = Query(...)):
    db = Session()
    try:
        account = db.get(LinkedAccount, account_id)
        if not account or account.owner_id != user_id:
            raise HTTPException(status_code=404, detail="Linked account not found.")
        db.delete(account)
        db.commit()
        return {"message": f"Account {account.email} removed."}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        db.close()

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
    user_id:           str
    query:             Optional[str] = None
    max_results:       Optional[int] = None
    linked_account_id: Optional[str] = None  # fetch from a linked account instead


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
        # Validate the primary user exists
        user = db.get(User, req.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        if req.linked_account_id:
            linked = db.get(LinkedAccount, req.linked_account_id)
            if not linked or linked.owner_id != req.user_id:
                raise HTTPException(status_code=404, detail="Linked account not found.")
            token_json = linked.token_json
        else:
            token_json = user.token_json
    finally:
        db.close()

    try:
        gmail, _ = get_user_services(token_json)
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
