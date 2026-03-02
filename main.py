import logging
import sys

from auth import authenticate
from calendar_manager import create_event
from daily_plan import get_today_schedule
from gmail_reader import fetch_emails
from notifier import send_whatsapp
from email_parser import parse_email_with_gemini

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

    # --- Fetch and Process Emails ---
    logger.info("Fetching and processing emails...")
    emails = fetch_emails(gmail)

    if not emails:
        logger.info("No new emails to process.")
    else:
        logger.info(f"Found {len(emails)} emails to analyze.")
        for email in emails:
            subject = email.get("subject", "")
            body = email.get("body", "")

            logger.info(f"--- Analyzing Subject: {subject} ---")
            parsed_data = parse_email_with_gemini(body)

            if parsed_data:
                intent = parsed_data.get("intent", "")
                logger.info("Intent: %s", intent)
                logger.info("Summary: %s", parsed_data.get("summary"))
                logger.info("Suggested Action: %s", parsed_data.get("suggested_action"))

                # If the intent is Event Scheduling, create a calendar event
                if intent == "Event Scheduling":
                    logger.info("Event Scheduling intent detected. Attempting to create calendar event.")
                    try:
                        create_event(calendar, subject, body)
                    except Exception as exc:
                        logger.error("Failed to create event for email '%s': %s", subject, exc)
            else:
                logger.warning("Could not parse email: %s", subject)

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