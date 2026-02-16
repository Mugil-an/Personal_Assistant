import logging

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from config import (
    TWILIO_ACCOUNT_SID,
    TWILIO_AUTH_TOKEN,
    WHATSAPP_FROM,
    WHATSAPP_TO,
    validate_twilio_config,
)


logger = logging.getLogger(__name__)


def _get_twilio_client() -> Client:
    """Return an initialized Twilio client after validating config."""

    validate_twilio_config()
    assert TWILIO_ACCOUNT_SID is not None
    assert TWILIO_AUTH_TOKEN is not None
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def send_whatsapp(message_body: str) -> None:
    """Send a WhatsApp message using Twilio.

    Raises an exception only for configuration problems; Twilio API errors
    are logged but do not crash the whole process.
    """

    try:
        client = _get_twilio_client()
    except RuntimeError as exc:
        logger.error("Twilio configuration error: %s", exc)
        return

    try:
        message = client.messages.create(
            from_=WHATSAPP_FROM,
            body=message_body,
            to=WHATSAPP_TO,
        )
        logger.info("WhatsApp message sent. SID=%s", message.sid)
    except TwilioRestException as exc:
        logger.error("Failed to send WhatsApp message via Twilio: %s", exc)