import logging
import sys

from auth import authenticate
from calendar_manager import create_event
from daily_plan import get_today_schedule
from gmail_reader import fetch_emails
from notifier import send_whatsapp


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_assistant() -> None:
    """Run the full assistant workflow once.

    1. Authenticate to Google.
    2. Fetch meeting-related emails and create calendar events.
    3. Build today's schedule and send it via WhatsApp.
    """

    try:
        logger.info("Authenticating with Google APIs")
        gmail, calendar = authenticate()
    except Exception as exc:
        logger.error("Authentication failed: %s", exc)
        return

    # Step 2: Read & Parse Emails
    logger.info("Checking for meeting-related emails")
    new_emails = fetch_emails(gmail)
    for email in new_emails:
        subject = email.get("subject", "")
        body = email.get("body", "")
        try:
            create_event(calendar, subject, body)
        except Exception as exc:
            logger.error("Failed to create event for email '%s': %s", subject, exc)

    # Step 3: Get Today's Schedule & Notify
    logger.info("Fetching today's schedule from calendar")
    schedule = get_today_schedule(calendar)

    logger.info("Sending schedule to WhatsApp")
    send_whatsapp(schedule)
    logger.info("All tasks complete")


if __name__ == "__main__":
    try:
        run_assistant()
    except KeyboardInterrupt:
        logger.info("Interrupted by user; exiting.")
        sys.exit(1)