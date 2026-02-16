import logging
from datetime import datetime, timedelta
from typing import Any

import dateparser

from config import CALENDAR_ID, DEFAULT_EVENT_DURATION_MIN, TIMEZONE


logger = logging.getLogger(__name__)


def _normalize_event_time(parsed: datetime | None) -> datetime | None:
    """Ensure parsed time is a timezone-naive datetime that can be passed to Google.

    If parsing fails, returns None.
    """

    if parsed is None:
        return None
    # dateparser already returns a datetime; additional normalization could be added here
    return parsed


def create_event(service: Any, subject: str, body: str) -> None:
    """Create a calendar event inferred from an email's subject and body.

    Uses natural-language parsing on the email body to determine the start time
    and applies a default duration from configuration.
    """

    settings = {"PREFER_DATES_FROM": "future"}
    parsed_dt = dateparser.parse(body, settings=settings)
    dt = _normalize_event_time(parsed_dt)

    if not dt:
        logger.info("Could not find a date in email subject='%s'", subject)
        return

    # Apply default duration
    end_dt = dt + timedelta(minutes=DEFAULT_EVENT_DURATION_MIN)

    event = {
        "summary": subject or "(No subject)",
        "description": body[:500],  # Keep only first 500 chars
        "start": {
            "dateTime": dt.isoformat(),
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": TIMEZONE,
        },
    }

    try:
        created = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        logger.info(
            "Event created: id=%s summary=%s start=%s",
            created.get("id"),
            created.get("summary"),
            created.get("start", {}).get("dateTime"),
        )
    except Exception as exc:
        logger.error("Failed to create calendar event for '%s': %s", subject, exc)