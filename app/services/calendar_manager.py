import logging
from datetime import datetime, timedelta
from typing import Any

import dateparser

from app.config import CALENDAR_ID, DEFAULT_EVENT_DURATION_MIN, TIMEZONE


logger = logging.getLogger(__name__)


def _normalize_event_time(parsed: datetime | None) -> datetime | None:
    """Ensure parsed time is a timezone-naive datetime that can be passed to Google.
    If parsing fails, returns None.
    """
    if parsed is None:
        return None
    return parsed


def create_event(service: Any, subject: str, body: str, date_hints: list | None = None) -> None:
    """Create a calendar event inferred from an email's subject and body.

    Parameters
    ----------
    service:
        Google Calendar service client.
    subject:
        Email subject used as the event title.
    body:
        Email body, used as fallback for date parsing.
    date_hints:
        List of date strings extracted by Gemini (e.g. ["April 13 2026",
        "2026-04-13 14:00"]). Tried first before falling back to body scan.
    """

    settings = {"PREFER_DATES_FROM": "future"}
    dt = None

    # Try Gemini-supplied date hints first (most accurate)
    if date_hints:
        for hint in date_hints:
            parsed_dt = dateparser.parse(str(hint), settings=settings)
            dt = _normalize_event_time(parsed_dt)
            if dt:
                logger.debug("Used Gemini date hint '%s' for event '%s'", hint, subject)
                break

    # Fall back to scanning the full email body
    if not dt:
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
