"""APScheduler jobs for the multi-user Personal Assistant service.

Jobs (all per-user, managed by schedule_notifications):
  - sync_emails_<user_id>   : Runs every user.email_sync_hours hours. Fetches
                              emails in that same window, parses them with Gemini,
                              and creates calendar events.
  - notify_<user_id>        : Daily cron at user.notify_time. Sends the user
                              today's calendar schedule via email.
  - schedule_notifications  : Runs every 10 min. Re-reads DB and upserts both
                              per-user jobs above so preference changes apply quickly.
"""

import datetime
import logging
from email.utils import parseaddr
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.auth_web import get_user_services
from app.config import SCHEDULER_REFRESH_MINUTES
from app.services.calendar_manager import create_event
from app.services.daily_plan import get_today_schedule
from app.services.email_parser import enrich_email_analysis, parse_email_with_gemini
from app.services.gmail_reader import fetch_emails
from app.models import Session, User, LinkedAccount, SenderPriority, SenderFilter
from app.services.notifier import send_daily_schedule

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")


def _normalize_sender(sender: str) -> str:
    """Normalize sender values to a stable lowercase email key."""
    _, parsed_email = parseaddr(sender or "")
    candidate = (parsed_email or sender or "").strip().lower()
    return candidate


def _valid_timezone_name(value: str | None) -> str:
    """Return a valid IANA timezone name, falling back to UTC."""
    tz_name = value or "UTC"
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning("Invalid user timezone '%s'; falling back to UTC", value)
        return "UTC"
    return tz_name


def _prune_stale_user_jobs(active_user_ids: set[str]) -> None:
    """Remove stale per-user jobs for users no longer present in DB."""
    for job in scheduler.get_jobs():
        if not (job.id.startswith("sync_emails_") or job.id.startswith("notify_")):
            continue

        if job.id.startswith("sync_emails_"):
            user_id = job.id[len("sync_emails_"):]
        else:
            user_id = job.id[len("notify_"):]

        if user_id not in active_user_ids:
            scheduler.remove_job(job.id)
            logger.info("Removed stale scheduler job '%s'", job.id)


# ---------------------------------------------------------------------------
# Core per-account email processing
# ---------------------------------------------------------------------------

def _process_gmail_account(
    db,
    db_obj,
    account_id: str,
    account_email: str,
    gmail_token: dict,
    calendar_service,
    sync_hours: int = 24,
    sender_priorities: dict | None = None,
    excluded_senders: set[str] | None = None,
) -> int:
    """Fetch new emails from one Gmail account and create calendar events.

    Only emails received within the last ``sync_hours`` hours are fetched.
    Returns the number of calendar events created.
    """
    events_created = 0
    sender_priorities = sender_priorities or {}
    excluded_senders = excluded_senders or set()
    try:
        gmail, _ = get_user_services(gmail_token, db=db, db_obj=db_obj)
    except Exception as exc:
        logger.error("Auth failed for account %s: %s", account_email, exc)
        return 0

    after_epoch = int(
        (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=sync_hours)).timestamp()
    )
    try:
        emails = fetch_emails(
            gmail,
            after_epoch=after_epoch,
            db=db,
            seen_account_id=account_id,
        )
    except Exception as exc:
        logger.error("Failed to fetch emails for %s: %s", account_email, exc)
        return 0

    if not emails:
        logger.info("No new emails for %s", account_email)
        return 0

    for email in emails:
        subject = email.get("subject", "")
        sender  = _normalize_sender(email.get("from_", ""))
        if sender and sender in excluded_senders:
            continue
        body    = email.get("body", "")

        # Collect PDF attachment texts to feed into Gemini
        pdf_texts = [
            att["extracted_text"]
            for att in email.get("attachments", [])
            if att.get("extracted_text")
        ]

        full_description = body
        if pdf_texts:
            combined_pdf = "\n\n".join(text for text in pdf_texts if text)
            if combined_pdf:
                full_description = f"{body}\n\n[PDF Attachment Text]\n{combined_pdf[:2000]}"

        parsed = parse_email_with_gemini(
            body,
            attachment_texts=pdf_texts or None,
            email_subject=subject,
            email_sender=sender,
        )
        
        # Determine user ID for SenderPriority. If linked account, owner_id is the user.
        user_id = getattr(db_obj, "owner_id", getattr(db_obj, "id", account_id))
        
        # Check if this sender already exists in the priority table
        if sender and sender not in sender_priorities and sender not in excluded_senders:
            # Check DB to see if they were added recently
            existing = db.query(SenderPriority).filter(
                SenderPriority.user_id == user_id,
                SenderPriority.sender == sender
            ).first()
            if not existing:
                new_sp = SenderPriority(user_id=user_id, sender=sender, priority="medium")
                db.add(new_sp)
                db.commit()
                # Update our local dictionary so we don't query/insert again in this loop
                sender_priorities[sender] = "medium"
            else:
                sender_priorities[sender] = existing.priority

        sender_prio = sender_priorities.get(sender, "medium")
        analysis = enrich_email_analysis(body, parsed, subject=subject, sender=sender, sender_priority=sender_prio)

        intent = analysis.get("intent", "")
        category = analysis.get("category", "")
        priority = analysis.get("priority", "Medium")
        dates  = analysis.get("entities", {}).get("dates", [])
        has_deadline = analysis.get("has_deadline", False)
        locations = analysis.get("entities", {}).get("locations", [])
        location_str = ", ".join(locations) if isinstance(locations, list) and locations else None
        logger.info(
            "[%s] '%s' → category=%s priority=%s intent=%s dates=%s",
            account_email,
            subject,
            category,
            priority,
            intent,
            dates,
        )

        # Add to calendar strictly for events/deadlines, ignoring unimportant ones
        should_create_event = (
            category not in ["Promotion", "Personal"] and (
                category == "Event" or 
                (has_deadline and dates) or
                # Only add Important emails to calendar if dates were actually found
                (category == "Important" and priority in ["High", "Medium"] and dates)
            )
        )

        if should_create_event:
            try:
                date_hints = analysis.get("entities", {}).get("dates", [])
                create_event(
                    calendar_service, 
                    summary=subject, 
                    description=full_description, 
                    location=location_str,
                    date_hints=date_hints
                )
                events_created += 1
                logger.info("Created calendar event for %s", subject)
            except Exception as e:
                logger.error("Failed to create event for %s: %s", subject, e)

    return events_created


# ---------------------------------------------------------------------------
# Per-user processing helpers
# ---------------------------------------------------------------------------

def process_emails_for_user(user: User) -> None:
    """Fetch emails for a user's primary + all linked Gmail accounts and
    create calendar events in the user's primary Google Calendar.

    Looks back ``user.email_sync_hours`` hours so each run only processes
    the slice of mail since the previous sync.
    """
    logger.info("Processing emails for %s (window=%sh)", user.email, user.email_sync_hours or 24)

    sync_hours = int(user.email_sync_hours or 24)
    
    db = Session()
    try:
        # Get the latest user object in this session to avoid detached errors
        user_db = db.get(User, user.id)
        if not user_db:
            return

        # Pre-load sender priorities from DB into a dict
        sp_records = db.query(SenderPriority).filter(SenderPriority.user_id == user_db.id).all()
        sender_priorities = {sp.sender: sp.priority for sp in sp_records}
        excluded_senders = {
            row.sender
            for row in db.query(SenderFilter)
            .filter(SenderFilter.user_id == user_db.id, SenderFilter.excluded.is_(True))
            .all()
        }

        # Build the primary user's calendar service once
        try:
            _, calendar = get_user_services(user_db.token_json, db=db, db_obj=user_db)
        except Exception as exc:
            logger.error("Calendar auth failed for %s: %s", user_db.email, exc)
            return

        total = 0

        # --- Primary Gmail account ---
        total += _process_gmail_account(
            db,
            user_db,
            user_db.id,
            user_db.email,
            user_db.token_json,
            calendar,
            sync_hours,
            sender_priorities,
            excluded_senders,
        )

        # --- Linked Gmail accounts ---
        linked_accounts = db.query(LinkedAccount).filter(
            LinkedAccount.owner_id == user_db.id
        ).all()

        for acct in linked_accounts:
            total += _process_gmail_account(
                db,
                acct,
                acct.id,
                acct.email,
                acct.token_json,
                calendar,
                sync_hours,
                sender_priorities,
                excluded_senders,
            )

        logger.info("Finished processing for %s — %d event(s) created", user_db.email, total)
    finally:
        db.close()


def notify_user(user: User) -> None:
    """Fetch today's schedule and send it to a user via email."""
    logger.info("Sending daily schedule to %s", user.email)
    if not user.notify_email:
        logger.warning("No notification email set for %s — skipping notification.", user.email)
        return

    db = Session()
    try:
        user_db = db.get(User, user.id)
        if not user_db:
            return
        gmail, calendar = get_user_services(user_db.token_json, db=db, db_obj=user_db)
        schedule = get_today_schedule(calendar)
        send_daily_schedule(
            schedule,
            to=user_db.notify_email,
            gmail_service=gmail,
            from_email=user_db.email,
        )
    except Exception as exc:
        logger.error("Error notifying %s: %s", user.email, exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------

def schedule_notifications() -> None:
    """Re-reads the DB and upserts two jobs per user:

    1. ``sync_emails_<id>``  — email fetch + calendar update, repeating every
       ``user.email_sync_hours`` hours.
    2. ``notify_<id>``       — daily schedule notification at ``user.notify_time``.

    Runs every 10 minutes so preference changes take effect quickly.
    """
    db = Session()
    try:
        users = db.query(User).all()
        active_user_ids = {str(user.id) for user in users}
        _prune_stale_user_jobs(active_user_ids)

        for user in users:
            # ── Per-user email sync job ───────────────────────────────────────
            sync_hours = int(user.email_sync_hours or 24)
            try:
                scheduler.add_job(
                    process_emails_for_user,
                    IntervalTrigger(hours=sync_hours),
                    args=[user],
                    id=f"sync_emails_{user.id}",
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                    misfire_grace_time=3600,
                )
                logger.debug(
                    "Scheduled email sync for %s every %sh",
                    user.email, sync_hours,
                )
            except Exception as exc:
                logger.error("Failed to schedule email sync for %s: %s", user.email, exc)

            # ── Per-user daily notification job ──────────────────────────────
            if not user.notify_time:
                continue
            try:
                hour, minute = user.notify_time.split(":")
                scheduler.add_job(
                    notify_user,
                    CronTrigger(
                        hour=int(hour),
                        minute=int(minute),
                        timezone=_valid_timezone_name(user.timezone),
                    ),
                    args=[user],
                    id=f"notify_{user.id}",
                    replace_existing=True,
                    coalesce=True,
                    max_instances=1,
                    misfire_grace_time=21600,
                )
                logger.debug(
                    "Scheduled daily notification for %s at %s (%s)",
                    user.email, user.notify_time, user.timezone,
                )
            except Exception as exc:
                logger.error("Failed to schedule notification for %s: %s", user.email, exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scheduler startup
# ---------------------------------------------------------------------------

def start_scheduler() -> None:
    """Register all jobs and start the background scheduler."""
    # Refresh per-user jobs periodically so preference changes apply quickly.
    scheduler.add_job(
        schedule_notifications,
        IntervalTrigger(minutes=SCHEDULER_REFRESH_MINUTES),
        id="schedule_notifications",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=1800,
    )

    scheduler.start()
    logger.info("Scheduler started (refresh every %s minute(s)).", SCHEDULER_REFRESH_MINUTES)

    # Immediately upsert per-user sync + notification jobs for existing users
    schedule_notifications()
    logger.info("Active jobs: %s", [j.id for j in scheduler.get_jobs()])
