import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import (
    NOTIFY_EMAIL_FROM,
    NOTIFY_EMAIL_PASSWORD,
    NOTIFY_EMAIL_TO,
)

logger = logging.getLogger(__name__)


def send_whatsapp(message_body: str, to: str | None = None) -> None:
    """Send the daily schedule as an email via Gmail SMTP.

    Parameters
    ----------
    message_body:
        The text content of the notification.
    to:
        Optional recipient email address. Falls back to NOTIFY_EMAIL_TO
        from config (single-user default).
    """
    recipient = to or NOTIFY_EMAIL_TO

    if not NOTIFY_EMAIL_FROM or not NOTIFY_EMAIL_PASSWORD:
        logger.error(
            "Email notification is not configured. "
            "Set NOTIFY_EMAIL_FROM and NOTIFY_EMAIL_PASSWORD in your .env file."
        )
        return

    if not recipient:
        logger.error("No recipient email address. Set NOTIFY_EMAIL_TO in .env or pass 'to' argument.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "\U0001f4c5 Your Daily Schedule"
    msg["From"]    = NOTIFY_EMAIL_FROM
    msg["To"]      = recipient
    msg.attach(MIMEText(message_body, "plain"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(NOTIFY_EMAIL_FROM, NOTIFY_EMAIL_PASSWORD)
            smtp.send_message(msg)
        logger.info("Schedule email sent to %s", recipient)
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Gmail authentication failed for %s. "
            "Make sure you are using an App Password, not your regular Gmail password. "
            "Generate one at https://myaccount.google.com/apppasswords",
            NOTIFY_EMAIL_FROM,
        )
    except Exception as exc:
        logger.error("Failed to send email notification: %s", exc)