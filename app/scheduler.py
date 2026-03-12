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
import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.auth_web import get_user_services
from app.services.calendar_manager import create_event
from app.services.daily_plan import get_today_schedule
from app.services.email_parser import parse_email_with_gemini
from app.services.gmail_reader import fetch_emails
from app.models import Session, User, LinkedAccount
from app.services.notifier import send_whatsapp

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")

# Directory where per-account seen-IDs files are stored
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SEEN_IDS_DIR = os.path.join(_BASE_DIR, "data", ".seen_ids")


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
    sync_hours: int = 24,
) -> int:
    """Fetch new emails from one Gmail account and create calendar events.

    Only emails received within the last ``sync_hours`` hours are fetched.
    Returns the number of calendar events created.
    """
    events_created = 0
    try:
        gmail, _ = get_user_services(gmail_token)
    except Exception as exc:
        logger.error("Auth failed for account %s: %s", account_email, exc)
        return 0

    after_epoch = int(
        (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=sync_hours)).timestamp()
    )
    try:
        emails = fetch_emails(
            gmail,
            seen_ids_file=_seen_ids_file(account_id),
            after_epoch=after_epoch,
        )
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
    create calendar events in the user's primary Google Calendar.

    Looks back ``user.email_sync_hours`` hours so each run only processes
    the slice of mail since the previous sync.
    """
    logger.info("Processing emails for %s (window=%sh)", user.email, user.email_sync_hours or 24)

    sync_hours = int(user.email_sync_hours or 24)

    # Build the primary user's calendar service once
    try:
        _, calendar = get_user_services(user.token_json)
    except Exception as exc:
        logger.error("Calendar auth failed for %s: %s", user.email, exc)
        return

    total = 0

    # --- Primary Gmail account ---
    total += _process_gmail_account(user.id, user.email, user.token_json, calendar, sync_hours)

    # --- Linked Gmail accounts ---
    db = Session()
    try:
        linked_accounts = db.query(LinkedAccount).filter(
            LinkedAccount.owner_id == user.id
        ).all()
    finally:
        db.close()

    for acct in linked_accounts:
        total += _process_gmail_account(acct.id, acct.email, acct.token_json, calendar, sync_hours)

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
                logger.error("Failed to schedule notification for %s: %s", user.email, exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Scheduler startup
# ---------------------------------------------------------------------------

def start_scheduler() -> None:
    """Register all jobs and start the background scheduler."""
    # Refresh per-user jobs every 10 minutes so preference changes apply quickly
    scheduler.add_job(
        schedule_notifications,
        IntervalTrigger(minutes=10),
        id="schedule_notifications",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started.")

    # Immediately upsert per-user sync + notification jobs for existing users
    schedule_notifications()
    logger.info("Active jobs: %s", [j.id for j in scheduler.get_jobs()])
