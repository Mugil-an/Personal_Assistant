"""Email-related API routes: run assistant pipeline and fetch/parse emails."""

import datetime as _dt
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.auth_web import get_user_services
from app.models import Session, User, LinkedAccount, SenderPriority
from app.services.calendar_manager import create_event
from app.services.daily_plan import get_today_schedule
from app.services.email_parser import enrich_email_analysis, parse_email_with_gemini
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
        gmail, calendar = get_user_services(user.token_json, db=db, db_obj=user)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auth failed: {exc}")

    sync_hours  = int(user.email_sync_hours or 24)
    after_epoch = int((_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=sync_hours)).timestamp())
    
    # Collect emails from primary account and all linked accounts
    all_emails = []
    accounts_to_sync = [(user.id, user.token_json, user)]
    
    # Add linked accounts
    db = Session()
    try:
        linked_accounts = db.query(LinkedAccount).filter(LinkedAccount.owner_id == user.id).all()
        for linked in linked_accounts:
            accounts_to_sync.append((linked.id, linked.token_json, linked))
    finally:
        db.close()
    
    # Process each account with per-account seen-IDs tracking
    def _seen_ids_file(account_id: str) -> str:
        """Return a unique seen-IDs file path for an account."""
        import os
        safe = "".join(c for c in account_id if c.isalnum() or c in "-_")
        seen_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", ".seen_ids")
        os.makedirs(seen_dir, exist_ok=True)
        return os.path.join(seen_dir, f"{safe}.json")
    
    for account_id, token_json, db_obj in accounts_to_sync:
        try:
            acct_gmail, acct_calendar = get_user_services(token_json, db=None, db_obj=None)
            account_seen_ids_file = _seen_ids_file(account_id)
            emails = fetch_emails(acct_gmail, query=None, max_results=req.max_results, after_epoch=after_epoch, seen_ids_file=account_seen_ids_file)
            for email in emails:
                email['account_id'] = account_id
            all_emails.extend(emails)
        except Exception as acc_exc:
            logger.warning(f"Failed to sync account {account_id}: {acc_exc}")
            continue

    events_created = 0
    details = []

    for email in all_emails:
        subject = email.get("subject", "")
        sender  = email.get("from_", "")
        body    = email.get("body", "")
        parsed  = parse_email_with_gemini(body, email_subject=subject, email_sender=sender)
        
        db_user_id = user.id

        # Load priority from the explicit SenderPriority table
        db = Session()
        try:
            sp_record = db.query(SenderPriority).filter(
                SenderPriority.user_id == db_user_id,
                SenderPriority.sender == sender
            ).first()
            
            if sp_record:
                sender_prio = sp_record.priority
            else:
                sender_prio = "medium"
                if sender:
                    new_sp = SenderPriority(user_id=db_user_id, sender=sender, priority="medium")
                    db.add(new_sp)
                    db.commit()
        finally:
            db.close()
        
        analysis = enrich_email_analysis(body, parsed, subject=subject, sender=sender, sender_priority=sender_prio)
        intent  = analysis.get("intent", "")
        category = analysis.get("category", "")
        priority = analysis.get("priority", "Medium")
        summary = analysis.get("summary", "")
        has_deadline = analysis.get("has_deadline", False)
        
        # Extract date_hints from entities dictionary
        entities = analysis.get("entities", {})
        date_hints = entities.get("dates", []) if isinstance(entities, dict) else []
        
        created = False

        # Event creation logic (using LLM intelligence, not hardcoded patterns):
        # 1. Event category emails always create events
        # 2. Important + High priority always create events
        # 3. Emails marked by LLM as having deadline + with date hints create events
        # 4. Exclude Promotion and Personal categories from event creation
        should_create_event = (
            category not in ["Promotion", "Personal"] and (
                category == "Event" or 
                (category == "Important" and priority in ["High", "Medium"]) or
                (has_deadline and date_hints)
            )
        )
        
        if should_create_event:
            try:
                created = create_event(
                    calendar,
                    summary=summary,
                    location=analysis.get("location"),
                    description=body,
                    date_hints=date_hints,
                )
                if created:
                    events_created += 1
            except Exception as e:
                logger.error(f"Failed to create calendar event: {e}")

        details.append({
            "subject":       subject,
            "from_":         sender,
            "intent":        intent,
            "category":      category,
            "priority":      priority,
            "priority_score": analysis.get("priority_score", 0),
            "summary":       summary,
            "event_created": created,
        })

    if req.send_email and user.notify_email:
        schedule = get_today_schedule(calendar)
        send_whatsapp(schedule, to=user.notify_email)

    return {
        "message":          "Assistant workflow complete.",
        "emails_processed": len(all_emails),
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

        db_obj = None
        if req.linked_account_id:
            linked = db.get(LinkedAccount, req.linked_account_id)
            if not linked or linked.owner_id != req.user_id:
                raise HTTPException(status_code=404, detail="Linked account not found.")
            token_json = linked.token_json
            db_obj = linked
        else:
            token_json = user.token_json
            db_obj = user
    finally:
        db.close()

    try:
        # NOTE: Using a new session purely for the token refresh if needed.
        # This keeps the main try-except block clean.
        db = Session()
        try:
            # We must fetch the db_obj cleanly under this session if refreshing
            clean_db_obj = db.get(type(db_obj), db_obj.id)
            gmail, _ = get_user_services(token_json, db=db, db_obj=clean_db_obj)
        finally:
            db.close()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auth failed: {exc}")

    emails = fetch_emails(gmail, query=req.query, max_results=req.max_results)
    result = []
    for email in emails:
        subject = email.get("subject", "")
        sender = email.get("from_", "")
        body   = email.get("body", "")
        parsed = parse_email_with_gemini(body, email_subject=subject, email_sender=sender)
        
        db_user_id = req.user_id
        
        sp_record = db.query(SenderPriority).filter(
            SenderPriority.user_id == db_user_id,
            SenderPriority.sender == sender
        ).first()
        
        if sp_record:
            sender_prio = sp_record.priority
        else:
            sender_prio = "medium"
            if sender:
                new_sp = SenderPriority(user_id=db_user_id, sender=sender, priority="medium")
                db.add(new_sp)
                db.commit()
        
        analysis = enrich_email_analysis(body, parsed, subject=subject, sender=sender, sender_priority=sender_prio)
        result.append({
            "subject":          subject,
            "from_":            sender,
            "date":             email.get("date", ""),
            "body_preview":     body[:300],
            "intent":           analysis.get("intent", ""),
            "category":         analysis.get("category", ""),
            "priority":         analysis.get("priority", "Medium"),
            "priority_score":   analysis.get("priority_score", 0),
            "summary":          analysis.get("summary", ""),
            "suggested_action": analysis.get("suggested_action", ""),
            "attachments":      len(email.get("attachments", [])),
        })
    result.sort(key=lambda item: item.get("priority_score", 0), reverse=True)
    return {"count": len(result), "emails": result}


@router.get("/api/senders")
def get_senders(user_id: str = Query(...)):
    """Fetch all known senders and their configured priority from the database."""
    db = Session()
    try:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
            
        senders_records = db.query(SenderPriority).filter(SenderPriority.user_id == user_id).all()
        
        # Format the response to match what the frontend expects
        response_data = {
            "senders": [
                {
                    "email": record.sender,
                    "priority": record.priority,
                }
                for record in senders_records
            ]
        }
        
        # Sort alphabetically by email
        response_data["senders"].sort(key=lambda x: x["email"])
        return response_data
    finally:
        db.close()


class UpdateSenderPriorityRequest(BaseModel):
    user_id: str
    sender: str
    priority: str  # "high", "medium", "low"


@router.post("/api/sender-priorities")
def update_sender_priority(req: UpdateSenderPriorityRequest):
    """Update priority for a specific sender in the database."""
    if req.priority.lower() not in ["high", "medium", "low"]:
        raise HTTPException(status_code=400, detail="Priority must be 'high', 'medium', or 'low'")
    
    db = Session()
    try:
        user = db.get(User, req.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        
        # Check if record exists
        sp_record = db.query(SenderPriority).filter(
            SenderPriority.user_id == req.user_id,
            SenderPriority.sender == req.sender
        ).first()
        
        if sp_record:
            sp_record.priority = req.priority.lower()
        else:
            new_record = SenderPriority(
                user_id=req.user_id,
                sender=req.sender,
                priority=req.priority.lower()
            )
            db.add(new_record)
            
        db.commit()
        
        return {
            "message": f"Priority for {req.sender} updated to {req.priority}",
        }
    finally:
        db.close()


@router.get("/api/sender-priorities")
def get_sender_priorities(user_id: str = Query(...)):
    """Get all sender priorities for a user."""
    db = Session()
    try:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        
        records = db.query(SenderPriority).filter(SenderPriority.user_id == user_id).all()
        priorities_dict = {r.sender: r.priority for r in records}
        
        return {"sender_priorities": priorities_dict}
    finally:
        db.close()
