import base64
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import (
    NOTIFY_EMAIL_FROM,
    NOTIFY_EMAIL_PASSWORD,
    NOTIFY_EMAIL_TO,
)

logger = logging.getLogger(__name__)


def send_daily_schedule(
    message_body: str,
    to: str | None = None,
    gmail_service: object | None = None,
    from_email: str | None = None,
) -> None:
    """Send the daily schedule via Gmail API when available, otherwise SMTP.

    Parameters
    ----------
    message_body:
        The text content of the notification.
    to:
        Optional recipient email address. Falls back to NOTIFY_EMAIL_TO
        from config (single-user default).
    gmail_service:
        Optional Gmail API service client. When provided, uses the Gmail API.
    from_email:
        Optional sender email address. Defaults to NOTIFY_EMAIL_FROM.
    """
    recipient = to or NOTIFY_EMAIL_TO
    sender = from_email or NOTIFY_EMAIL_FROM

    if not recipient:
        logger.error("No recipient email address. Set NOTIFY_EMAIL_TO in .env or pass 'to' argument.")
        return

    if not sender:
        logger.error("No sender email address configured.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "\U0001f4c5 Your Daily Schedule"
    msg["From"] = sender
    msg["To"] = recipient
    msg.attach(MIMEText(message_body, "plain"))

    if gmail_service is not None:
        try:
            raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            gmail_service.users().messages().send(userId="me", body={"raw": raw_message}).execute()
            logger.info("Schedule email sent to %s via Gmail API", recipient)
            return
        except Exception as exc:
            logger.error("Failed to send email notification via Gmail API: %s", exc)

    if not NOTIFY_EMAIL_FROM or not NOTIFY_EMAIL_PASSWORD:
        logger.error(
            "Email notification is not configured for SMTP. "
            "Set NOTIFY_EMAIL_FROM and NOTIFY_EMAIL_PASSWORD in your .env file."
        )
        return

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(NOTIFY_EMAIL_FROM, NOTIFY_EMAIL_PASSWORD)
            smtp.send_message(msg, from_addr=NOTIFY_EMAIL_FROM)
        logger.info("Schedule email sent to %s via SMTP", recipient)
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Gmail authentication failed for %s. "
            "Make sure you are using an App Password, not your regular Gmail password. "
            "Generate one at https://myaccount.google.com/apppasswords",
            NOTIFY_EMAIL_FROM,
        )
    except Exception as exc:
        logger.error("Failed to send email notification via SMTP: %s", exc)
