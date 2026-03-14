import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

import dateparser

from app.config import CALENDAR_ID, DEFAULT_EVENT_DURATION_MIN, TIMEZONE


logger = logging.getLogger(__name__)


def _normalize_text(value: str) -> str:
    """Lowercase text and keep only alphanumeric tokens for loose matching."""
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def _is_similar_summary(a: str, b: str) -> bool:
    """Return True when two summaries are likely the same event context."""
    na = _normalize_text(a)
    nb = _normalize_text(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True

    tokens_a = set(na.split())
    tokens_b = set(nb.split())
    if not tokens_a or not tokens_b:
        return False

    overlap = len(tokens_a & tokens_b) / min(len(tokens_a), len(tokens_b))
    return overlap >= 0.6


def _has_duplicate_event(service: Any, summary: str, start_dt: datetime) -> bool:
    """Check nearby events and skip creation if a similar one already exists."""
    window_start = (start_dt - timedelta(hours=2)).isoformat()
    window_end = (start_dt + timedelta(hours=2)).isoformat()

    try:
        existing = (
            service.events()
            .list(
                calendarId=CALENDAR_ID,
                timeMin=window_start,
                timeMax=window_end,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
            .get("items", [])
        )
    except Exception as exc:
        logger.warning("Could not check duplicate events for '%s': %s", summary, exc)
        return False

    for item in existing:
        existing_summary = item.get("summary") or ""
        if _is_similar_summary(summary, existing_summary):
            logger.info(
                "Skipping duplicate-like event. incoming='%s' existing='%s'",
                summary,
                existing_summary,
            )
            return True

    return False


def _calendar_tz() -> Any:
    """Return configured calendar timezone, defaulting to UTC."""
    try:
        return ZoneInfo(TIMEZONE)
    except ZoneInfoNotFoundError:
        logger.warning("Invalid TIMEZONE '%s'; defaulting to UTC", TIMEZONE)
        return ZoneInfo("UTC")


def _normalize_event_time(parsed: datetime | None) -> datetime | None:
    """Normalize parsed datetime to configured timezone. Returns None on parse failure."""
    if parsed is None:
        return None
    tzinfo = _calendar_tz()
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=tzinfo)
    return parsed.astimezone(tzinfo)


def create_event(service: Any, summary: str, description: str, location: str | None = None, date_hints: list | None = None) -> bool:
    """Create a calendar event inferred from an email's subject and body.

    Args:
        service: Google Calendar service client.
        summary: Event title.
        description: Event description.
        location: Event location.
        date_hints: List of date strings extracted by Gemini.
    
    Returns:
        True if the event was created, False otherwise.
    """
    settings = {
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": TIMEZONE,
        "RETURN_AS_TIMEZONE_AWARE": True,
    }
    dt = None

    # Try Gemini-supplied date hints first (most accurate)
    if date_hints:
        for hint in date_hints:
            try:
                parsed_dt = dateparser.parse(str(hint), settings=settings)
            except Exception as exc:
                logger.warning("Failed to parse Gemini date hint '%s': %s", hint, exc)
                parsed_dt = None
            dt = _normalize_event_time(parsed_dt)
            if dt:
                logger.debug("Used Gemini date hint '%s' for event '%s'", hint, summary)
                break

    # Fall back to scanning the full email body
    if not dt:
        try:
            # Bound input size to avoid parser recursion/performance blowups on long threads.
            parsed_dt = dateparser.parse((description or "")[:1000], settings=settings)
        except Exception as exc:
            logger.warning("Failed to parse date from email body for '%s': %s", summary, exc)
            parsed_dt = None
        dt = _normalize_event_time(parsed_dt)

    if not dt:
        logger.info("Could not find a date in email summary='%s'", summary)
        return False

    if _has_duplicate_event(service, summary or "(No title)", dt):
        return False

    # Apply default duration
    end_dt = dt + timedelta(minutes=DEFAULT_EVENT_DURATION_MIN)

    event = {
        "summary": summary or "(No title)",
        "description": (description or "")[:500],  # Keep only first 500 chars
        "start": {
            "dateTime": dt.isoformat(),
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": TIMEZONE,
        },
    }

    if location:
        event["location"] = location

    try:
        created = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        logger.info(
            "Event created: id=%s summary=%s start=%s",
            created.get("id"),
            created.get("summary"),
            created.get("start", {}).get("dateTime"),
        )
        return True
    except Exception as exc:
        logger.error("Failed to create calendar event for '%s': %s", summary, exc)
        return False
