import os
from dotenv import load_dotenv

# Load environment variables from a .env file if present (for local/dev usage)
load_dotenv()

# --- Google API configuration ---

GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_TOKEN_FILE: str = os.getenv("GOOGLE_TOKEN_FILE", "token.pickle")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Gmail search query: fetch all emails (filter by importance happens in the app)
# Users can set a custom query in preferences if desired
GMAIL_QUERY: str = os.getenv(
    "GMAIL_QUERY",
    "meeting OR scheduled OR deadline OR urgent OR invite",  # Default Gmail search query
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

# Interval in minutes for reloading per-user scheduler jobs.
try:
    SCHEDULER_REFRESH_MINUTES: int = int(os.getenv("SCHEDULER_REFRESH_MINUTES", "10"))
except ValueError:
    SCHEDULER_REFRESH_MINUTES = 10

if SCHEDULER_REFRESH_MINUTES < 1:
    SCHEDULER_REFRESH_MINUTES = 10

# --- Email notification configuration (Gmail SMTP) ---

# The Gmail address you want to send notifications FROM
NOTIFY_EMAIL_FROM: str | None = os.getenv("NOTIFY_EMAIL_FROM")

# Gmail App Password (NOT your regular password).
# Generate one at: https://myaccount.google.com/apppasswords
NOTIFY_EMAIL_PASSWORD: str | None = os.getenv("NOTIFY_EMAIL_PASSWORD")

# Default recipient email (used for single-user / main.py mode)
NOTIFY_EMAIL_TO: str | None = os.getenv("NOTIFY_EMAIL_TO")

# Admin API key used to protect operational endpoints (e.g. scheduler status)
ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "")
