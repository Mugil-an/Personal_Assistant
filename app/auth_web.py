"""Per-user Google OAuth helpers for the web/multi-user mode."""

import logging
from typing import Tuple

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from app.config import GOOGLE_CREDENTIALS_FILE

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]


def create_auth_flow(redirect_uri: str, state: str = None) -> Flow:
    """Create a Google OAuth2 Flow for the web callback.

    Pass ``state`` (extracted from the OAuth callback URL) when recreating
    the flow in the callback handler so that the library's CSRF state
    verification succeeds.
    """
    return Flow.from_client_secrets_file(
        GOOGLE_CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
        state=state,
    )


def get_user_services(token_json: dict, db=None, db_obj=None) -> Tuple[object, object]:
    """Rebuild Gmail and Calendar service clients from a stored token dict.

    Parameters
    ----------
    token_json:
        The dict previously saved as User.token_json or LinkedAccount.token_json in the database.
    db:
        Optional SQLAlchemy session to use for saving the refreshed token.
    db_obj:
        Optional User or LinkedAccount object to update if the token is refreshed.

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
        
        # Save the new token back to the database if references are provided
        if db is not None and db_obj is not None:
            import json
            db_obj.token_json = json.loads(creds.to_json())
            db.commit()
            logger.info("Saved refreshed token back to database.")

    gmail    = build("gmail",    "v1", credentials=creds, cache_discovery=False)
    calendar = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return gmail, calendar
