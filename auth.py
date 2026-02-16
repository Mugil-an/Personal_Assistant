import logging
import os
import pickle
from typing import Tuple

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from config import GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE


logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
]


def authenticate() -> Tuple[object, object]:
    """Authenticate with Google and return Gmail and Calendar service clients.

    Uses a cached token file when available, otherwise runs the OAuth flow
    using the configured credentials file.
    """

    creds = None

    # Load existing credentials from disk if available
    if os.path.exists(GOOGLE_TOKEN_FILE):
        try:
            with open(GOOGLE_TOKEN_FILE, "rb") as token:
                creds = pickle.load(token)
            logger.info("Loaded cached Google credentials from %s", GOOGLE_TOKEN_FILE)
        except Exception as exc:  # corrupted token file, etc.
            logger.warning("Failed to load cached credentials: %s. Re-running auth flow.", exc)
            creds = None

    # If there are no valid credentials, either refresh or run the full flow
    if not creds or not getattr(creds, "valid", False):
        if creds and getattr(creds, "expired", False) and getattr(creds, "refresh_token", None):
            logger.info("Refreshing expired Google credentials")
            creds.refresh(Request())
        else:
            if not os.path.exists(GOOGLE_CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Google credentials file not found at {GOOGLE_CREDENTIALS_FILE}. "
                    "Set GOOGLE_CREDENTIALS_FILE or place credentials.json in the project directory."
                )

            logger.info("Running new OAuth flow using %s", GOOGLE_CREDENTIALS_FILE)
            flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Persist credentials for future runs
        try:
            with open(GOOGLE_TOKEN_FILE, "wb") as token:
                pickle.dump(creds, token)
            logger.info("Saved Google credentials to %s", GOOGLE_TOKEN_FILE)
        except Exception as exc:
            logger.warning("Failed to save credentials to %s: %s", GOOGLE_TOKEN_FILE, exc)

    gmail_service = build("gmail", "v1", credentials=creds)
    calendar_service = build("calendar", "v3", credentials=creds)

    return gmail_service, calendar_service