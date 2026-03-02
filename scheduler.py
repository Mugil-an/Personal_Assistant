"""APScheduler jobs for the multi-user Personal Assistant service.

Jobs:
  - hourly_email_job   : Runs every hour. Fetches emails for all users,
                         parses with Gemini, creates calendar events.
  - schedule_notifications : Runs every 10 min. Re-reads DB and ensures each
                             user has a daily cron job at their chosen time.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from auth_web import get_user_services
from calendar_manager import create_event
from daily_plan import get_today_schedule
from email_parser import parse_email_with_gemini
from gmail_reader import fetch_emails
from models import Session, User
from notifier import send_whatsapp

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler(timezone="UTC")


# ---------------------------------------------------------------------------
# Per-user processing helpers
# ---------------------------------------------------------------------------

def process_emails_for_user(user: User) -> None:
    """Fetch emails, parse with Gemini, and create calendar events for one user."""
    logger.info("Processing emails for %s", user.email)
    try:
        gmail, calendar = get_user_services(user.token_json)
        emails = fetch_emails(gmail)

        if not emails:
            logger.info("No new emails for %s", user.email)
            return

        for email in emails:
            subject = email.get("subject", "")
            body    = email.get("body", "")

            parsed = parse_email_with_gemini(body)
            if not parsed:
                continue

            intent = parsed.get("intent", "")
            logger.info("[%s] Email '%s' → intent: %s", user.email, subject, intent)

            if intent == "Event Scheduling":
                try:
                    create_event(calendar, subject, body)
                except Exception as exc:
                    logger.error(
                        "Failed to create event for '%s' (%s): %s",
                        subject, user.email, exc,
                    )

    except Exception as exc:
        logger.error("Error processing emails for %s: %s", user.email, exc)


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
