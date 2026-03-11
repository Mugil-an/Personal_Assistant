"""Email-related API routes: run assistant pipeline and fetch/parse emails."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.auth_web import get_user_services
from app.models import Session, User, LinkedAccount
from app.services.calendar_manager import create_event
from app.services.daily_plan import get_today_schedule
from app.services.email_parser import parse_email_with_gemini
from app.services.gmail_reader import fetch_emails
from app.services.notifier import send_whatsapp

logger = logging.getLogger(__name__)
router = APIRouter()


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


@router.post("/api/run-assistant")
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


@router.post("/api/fetch-emails")
def api_fetch_emails(req: FetchEmailsRequest):
    db = Session()
    try:
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
