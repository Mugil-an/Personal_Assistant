"""Per-user Google OAuth helpers for the web/multi-user mode."""

import logging
from typing import Tuple

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from config import GOOGLE_CREDENTIALS_FILE

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]


def create_auth_flow(redirect_uri: str) -> Flow:
    """Create a Google OAuth2 Flow for the web callback."""
    return Flow.from_client_secrets_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )


def get_user_services(token_json: dict) -> Tuple[object, object]:
    """Rebuild Gmail and Calendar service clients from a stored token dict.

    Parameters
    ----------
    token_json:
        The dict previously saved as User.token_json in the database.

    Returns
    -------
    (gmail_service, calendar_service)
    """
    creds = Credentials.from_authorized_user_info(token_json, SCOPES)

    # Refresh token silently if expired
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        logger.info("Refreshed OAuth token for stored credentials.")

    gmail    = build("gmail",    "v1", credentials=creds)
    calendar = build("calendar", "v3", credentials=creds)
    return gmail, calendar
