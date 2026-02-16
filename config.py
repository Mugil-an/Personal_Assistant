import os
from dotenv import load_dotenv

# Load environment variables from a .env file if present (for local/dev usage)
load_dotenv()

# --- Google API configuration ---

GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_TOKEN_FILE: str = os.getenv("GOOGLE_TOKEN_FILE", "token.pickle")

# Gmail search query for meeting-related emails
GMAIL_QUERY: str = os.getenv(
    "GMAIL_QUERY",
    "subject:meeting OR subject:appointment OR subject:scheduled",
)

# Maximum number of Gmail messages to fetch in a single run
try:
    GMAIL_MAX_RESULTS: int = int(os.getenv("GMAIL_MAX_RESULTS", "20"))
except ValueError:
    GMAIL_MAX_RESULTS = 20

# Google Calendar configuration
CALENDAR_ID: str = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# Timezone used for calendar events and schedule formatting
TIMEZONE: str = os.getenv("TIMEZONE", "UTC")

# Default event duration in minutes when creating calendar events
try:
    DEFAULT_EVENT_DURATION_MIN: int = int(os.getenv("DEFAULT_EVENT_DURATION_MIN", "60"))
except ValueError:
    DEFAULT_EVENT_DURATION_MIN = 60

# --- Twilio / WhatsApp configuration ---

TWILIO_ACCOUNT_SID: str | None = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN: str | None = os.getenv("TWILIO_AUTH_TOKEN")
WHATSAPP_FROM: str | None = os.getenv("WHATSAPP_FROM")
WHATSAPP_TO: str | None = os.getenv("WHATSAPP_TO")


def validate_twilio_config() -> None:
    """Raise a clear error if mandatory Twilio settings are missing.

    This is meant to be called at startup before attempting to send messages.
    """

    missing = []
    if not TWILIO_ACCOUNT_SID:
        missing.append("TWILIO_ACCOUNT_SID")
    if not TWILIO_AUTH_TOKEN:
        missing.append("TWILIO_AUTH_TOKEN")
    if not WHATSAPP_FROM:
        missing.append("WHATSAPP_FROM")
    if not WHATSAPP_TO:
        missing.append("WHATSAPP_TO")

    if missing:
        raise RuntimeError(
            f"Missing required Twilio configuration values: {', '.join(missing)}. "
            "Check your environment variables or .env file."
        )
