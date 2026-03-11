"""APScheduler jobs for the multi-user Personal Assistant service.

Jobs:
  - hourly_email_job        : Runs every hour. Fetches NEW emails for all users
                              (primary + linked Gmail accounts), parses body and
                              PDF attachments with Gemini, creates calendar events
                              on the exact date Gemini extracted.
  - schedule_notifications  : Runs every 10 min. Re-reads DB and ensures each
                              user has a daily cron job at their chosen time.
"""

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from auth_web import get_user_services
from calendar_manager import create_event
from daily_plan import get_today_schedule
from email_parser import parse_email_with_gemini
from gmail_reader import fetch_emails
from models import Session, User, LinkedAccount
from notifier import send_whatsapp

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")

# Directory where per-account seen-IDs files are stored
_SEEN_IDS_DIR = os.path.join(os.path.dirname(__file__), ".seen_ids")


def _seen_ids_file(account_id: str) -> str:
    """Return a unique seen-IDs file path for an account."""
    os.makedirs(_SEEN_IDS_DIR, exist_ok=True)
    safe = "".join(c for c in account_id if c.isalnum() or c in "-_")
    return os.path.join(_SEEN_IDS_DIR, f"{safe}.json")


# ---------------------------------------------------------------------------
# Core per-account email processing
# ---------------------------------------------------------------------------

def _process_gmail_account(
    account_id: str,
    account_email: str,
    gmail_token: dict,
    calendar_service,
) -> int:
    """Fetch new emails from one Gmail account and create calendar events.

    Returns the number of calendar events created.
    """
    events_created = 0
    try:
        gmail, _ = get_user_services(gmail_token)
    except Exception as exc:
        logger.error("Auth failed for account %s: %s", account_email, exc)
        return 0

    try:
        emails = fetch_emails(gmail, seen_ids_file=_seen_ids_file(account_id))
    except Exception as exc:
        logger.error("Failed to fetch emails for %s: %s", account_email, exc)
        return 0

    if not emails:
        logger.info("No new emails for %s", account_email)
        return 0

    for email in emails:
        subject = email.get("subject", "")
        body    = email.get("body", "")

        # Collect PDF attachment texts to feed into Gemini
        pdf_texts = [
            att["extracted_text"]
            for att in email.get("attachments", [])
            if att.get("extracted_text")
        ]

        parsed = parse_email_with_gemini(body, attachment_texts=pdf_texts or None)
        if not parsed:
            continue

        intent = parsed.get("intent", "")
        dates  = parsed.get("entities", {}).get("dates", [])
        logger.info("[%s] '%s' → intent=%s dates=%s", account_email, subject, intent, dates)

        if intent == "Event Scheduling":
            try:
                create_event(calendar_service, subject, body, date_hints=dates or None)
                events_created += 1
            except Exception as exc:
                logger.error("Failed to create event for '%s' (%s): %s", subject, account_email, exc)

    return events_created


# ---------------------------------------------------------------------------
# Per-user processing helpers
# ---------------------------------------------------------------------------

def process_emails_for_user(user: User) -> None:
    """Fetch emails for a user's primary + all linked Gmail accounts and
    create calendar events in the user's primary Google Calendar."""
    logger.info("Processing emails for %s", user.email)

    # Build the primary user's calendar service once
    try:
        _, calendar = get_user_services(user.token_json)
    except Exception as exc:
        logger.error("Calendar auth failed for %s: %s", user.email, exc)
        return

    total = 0

    # --- Primary Gmail account ---
    total += _process_gmail_account(user.id, user.email, user.token_json, calendar)

    # --- Linked Gmail accounts ---
    db = Session()
    try:
        linked_accounts = db.query(LinkedAccount).filter(
            LinkedAccount.owner_id == user.id
        ).all()
    finally:
        db.close()

    for acct in linked_accounts:
        total += _process_gmail_account(acct.id, acct.email, acct.token_json, calendar)

    logger.info("Finished processing for %s — %d event(s) created", user.email, total)


def notify_user(user: User) -> None:
    """Fetch today's schedule and send it to a user via email."""
    logger.info("Sending daily schedule to %s", user.email)
    if not user.notify_email:
        logger.warning("No notification email set for %s — skipping notification.", user.email)
        return

    try:
        _, calendar = get_user_services(user.token_json)
        schedule = get_today_schedule(calendar)
        send_whatsapp(schedule, to=user.notify_email)
    except Exception as exc:
        logger.error("Error notifying %s: %s", user.email, exc)


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------

def hourly_email_job() -> None:
    """Runs every hour — process emails for ALL registered users."""
    logger.info("=== Hourly email job started ===")
    db = Session()
    try:
        users = db.query(User).all()
        logger.info("Processing emails for %d user(s)", len(users))
        for user in users:
            process_emails_for_user(user)
    finally:
        db.close()
    logger.info("=== Hourly email job complete ===")


def schedule_notifications() -> None:
    """Re-reads the DB and upserts a daily cron job per user at their chosen time.

    Runs every 10 minutes so new users or preference changes take effect quickly.
    """
    db = Session()
    try:
        users = db.query(User).all()
        for user in users:
            if not user.notify_time:
                continue
            try:
                hour, minute = user.notify_time.split(":")
                scheduler.add_job(
                    notify_user,
                    CronTrigger(
                        hour=int(hour),
                        minute=int(minute),
                        timezone=user.timezone or "UTC",
                    ),
                    args=[user],
                    id=f"notify_{user.id}",
                    replace_existing=True,
                )
                logger.debug(
                    "Scheduled daily notification for %s at %s (%s)",
                    user.email, user.notify_time, user.timezone,
                )
            except Exception as exc:
                logger.error(
                    "Failed to schedule notification for %s: %s", user.email, exc
                )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scheduler startup
# ---------------------------------------------------------------------------

def start_scheduler() -> None:
    """Register all jobs and start the background scheduler."""
    # Hourly email processing for all users
    scheduler.add_job(
        hourly_email_job,
        IntervalTrigger(hours=1),
        id="hourly_email_job",
        replace_existing=True,
    )

    # Refresh per-user notification schedules every 10 minutes
    scheduler.add_job(
        schedule_notifications,
        IntervalTrigger(minutes=10),
        id="schedule_notifications",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started. Jobs: %s", [j.id for j in scheduler.get_jobs()])

    # Immediately register any existing users' notification jobs
    schedule_notifications()
