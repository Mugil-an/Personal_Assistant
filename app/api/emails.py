"""Email-related API routes: run assistant pipeline and fetch/parse emails."""
from typing import Optional
import logging
import datetime as _dt
from email.utils import parseaddr
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.auth_web import get_user_services
from app.models import User, LinkedAccount, SenderPriority, get_db, Session
from app.services.calendar_manager import create_event
from app.services.daily_plan import get_today_schedule
from app.services.email_parser import enrich_email_analysis, parse_email_with_gemini
from app.services.gmail_reader import fetch_emails
from app.services.notifier import send_daily_schedule

logger = logging.getLogger(__name__)
router = APIRouter()


def _normalize_sender(sender: str) -> str:
    """Normalize sender values to a stable lowercase email key."""
    _, parsed_email = parseaddr(sender or "")
    candidate = (parsed_email or sender or "").strip().lower()
    return candidate
    

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
        linked_accounts = db.query(LinkedAccount).filter(LinkedAccount.owner_id == user.id).all()
        for linked in linked_accounts:
            accounts_to_sync.append((linked.id, linked.token_json, linked))
        
        for account_id, token_json, db_obj in accounts_to_sync:
            try:
                acct_gmail, acct_calendar = get_user_services(token_json, db=None, db_obj=None)
                emails = fetch_emails(
                    acct_gmail,
                    query=None,
                    max_results=req.max_results,
                    after_epoch=after_epoch,
                    db=db,
                    seen_account_id=account_id,
                )
                for email in emails:
                    email['account_id'] = account_id
                all_emails.extend(emails)
            except Exception as acc_exc:
                logger.warning(f"Failed to sync account {account_id}: {acc_exc}")
                continue

        events_created = 0
        details = []

        # Preload sender priorities once to avoid N+1 queries.
        sp_records = db.query(SenderPriority).filter(SenderPriority.user_id == user.id).all()
        sender_priorities = {sp.sender: sp.priority for sp in sp_records}

        for email in all_emails:
            subject = email.get("subject", "")
            sender  = _normalize_sender(email.get("from_", ""))
            body    = email.get("body", "")
            pdf_texts = [
                att.get("extracted_text")
                for att in email.get("attachments", [])
                if att.get("extracted_text")
            ]
            parsed = parse_email_with_gemini(
                body,
                attachment_texts=pdf_texts or None,
                email_subject=subject,
                email_sender=sender,
            )
            
            db_user_id = user.id

            sender_prio = sender_priorities.get(sender)
            if not sender_prio:
                sender_prio = "medium"
                if sender:
                    new_sp = SenderPriority(user_id=db_user_id, sender=sender, priority="medium")
                    db.add(new_sp)
                    db.commit()
                    sender_priorities[sender] = "medium"
            
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
        
        # Optionally send a summary email
        if req.send_email and details:
            today_schedule = get_today_schedule(calendar)
            lines = [
                "Daily Digest",
                f"Found {len(details)} important emails.",
                "",
                "Today's Schedule",
                today_schedule,
                "",
                "Email Analysis",
            ]
            for item in details:
                lines.extend(
                    [
                        f"From: {item['from_']}",
                        f"Subject: {item['subject']}",
                        f"Summary: {item['summary']}",
                        f"Priority: {item['priority']} (Score: {item['priority_score']})",
                        f"Event Created: {'Yes' if item['event_created'] else 'No'}",
                        "-" * 40,
                    ]
                )
            send_daily_schedule("\n".join(lines), to=user.notify_email)

        return {
            "message": f"Assistant run complete. Found {len(all_emails)} emails, created {events_created} events.",
            "emails_processed": len(all_emails),
            "events_created": events_created,
            "details": details,
        }
    finally:
        db.close()


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

        try:
            clean_db_obj = db.get(type(db_obj), db_obj.id)
            gmail, _ = get_user_services(token_json, db=db, db_obj=clean_db_obj)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Auth failed: {exc}")

        seen_account_id = req.linked_account_id or req.user_id
        emails = fetch_emails(
            gmail,
            query=req.query,
            max_results=req.max_results,
            db=db,
            seen_account_id=seen_account_id,
        )
        result = []
        for email in emails:
            subject = email.get("subject", "")
            sender = _normalize_sender(email.get("from_", ""))
            body = email.get("body", "")
            pdf_texts = [
                att.get("extracted_text")
                for att in email.get("attachments", [])
                if att.get("extracted_text")
            ]
            parsed = parse_email_with_gemini(
                body,
                attachment_texts=pdf_texts or None,
                email_subject=subject,
                email_sender=sender,
            )

            sp_record = db.query(SenderPriority).filter(
                SenderPriority.user_id == req.user_id,
                SenderPriority.sender == sender,
            ).first()

            if sp_record:
                sender_prio = sp_record.priority
            else:
                sender_prio = "medium"
                if sender:
                    new_sp = SenderPriority(user_id=req.user_id, sender=sender, priority="medium")
                    db.add(new_sp)
                    db.commit()

            analysis = enrich_email_analysis(
                body,
                parsed,
                subject=subject,
                sender=sender,
                sender_priority=sender_prio,
            )
            result.append(
                {
                    "subject": subject,
                    "from_": sender,
                    "date": email.get("date", ""),
                    "body_preview": body[:300],
                    "intent": analysis.get("intent", ""),
                    "category": analysis.get("category", ""),
                    "priority": analysis.get("priority", "Medium"),
                    "priority_score": analysis.get("priority_score", 0),
                    "summary": analysis.get("summary", ""),
                    "suggested_action": analysis.get("suggested_action", ""),
                    "attachments": len(email.get("attachments", [])),
                }
            )

        result.sort(key=lambda item: item.get("priority_score", 0), reverse=True)
        return {"count": len(result), "emails": result}
    finally:
        db.close()


@router.get("/api/senders")
def get_senders(user_id: str = Query(...)):
    """Fetch all known senders and their configured priority from the database."""
    db = Session()
    try:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
            
        senders_records = db.query(SenderPriority).filter(SenderPriority.user_id == user_id).all()

        # Deduplicate sender rows defensively to avoid repeated entries in UI.
        unique_senders = {}
        for record in senders_records:
            sender_key = _normalize_sender(record.sender)
            if not sender_key:
                continue
            if sender_key not in unique_senders:
                unique_senders[sender_key] = {
                    "email": sender_key,
                    "priority": record.priority,
                }

        response_data = {
            "senders": list(unique_senders.values())
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
    
    normalized_sender = _normalize_sender(req.sender)
    if not normalized_sender:
        raise HTTPException(status_code=400, detail="Sender is required")

    db = Session()
    try:
        user = db.get(User, req.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        
        # Check if record exists
        sp_record = db.query(SenderPriority).filter(
            SenderPriority.user_id == req.user_id,
            SenderPriority.sender == normalized_sender
        ).first()
        
        if sp_record:
            sp_record.priority = req.priority.lower()
        else:
            new_record = SenderPriority(
                user_id=req.user_id,
                sender=normalized_sender,
                priority=req.priority.lower()
            )
            db.add(new_record)
            
        db.commit()
        
        return {
            "message": f"Priority for {normalized_sender} updated to {req.priority}",
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
