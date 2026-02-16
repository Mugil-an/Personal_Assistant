import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from dateutil import parser as dt_parser

from config import CALENDAR_ID, TIMEZONE


logger = logging.getLogger(__name__)


def _parse_event_start(start: Dict[str, Any]) -> datetime | None:
    """Convert Google Calendar start object to a datetime.

    Handles both dateTime and date (all-day) events.
    """

    date_time_str = start.get("dateTime") or start.get("date")
    if not date_time_str:
        return None

    try:
        return dt_parser.isoparse(date_time_str)
    except Exception as exc:
        logger.warning("Failed to parse event start '%s': %s", date_time_str, exc)
        return None


def get_today_schedule(service: Any) -> str:
    """Return a human-friendly summary of today's calendar events."""

    # Define the start and end of "Today" in UTC
    now_utc = datetime.now(timezone.utc)
    end_of_day_utc = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    now = now_utc.isoformat()
    end_of_day = end_of_day_utc.isoformat()

    try:
        events_result = (
            service.events()
            .list(
                calendarId=CALENDAR_ID,
                timeMin=now,
                timeMax=end_of_day,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except Exception as exc:
        logger.error("Failed to fetch today's schedule from calendar: %s", exc)
        return "⚠️ Could not fetch today's schedule due to an error."

    events: List[Dict[str, Any]] = events_result.get("items", [])

    if not events:
        return "☕ No meetings scheduled for today. Enjoy your day!"

    message = "🚀 *Your Daily Schedule:*\n\n"
    for event in events:
        start_dt = _parse_event_start(event.get("start", {}))
        summary = event.get("summary") or "(No title)"

        if not start_dt:
            message += f"⏰ (time unknown) - {summary}\n"
            continue

        # Show only local time HH:MM – for simplicity we display whatever datetime gives us
        time_str = start_dt.strftime("%H:%M")
        message += f"⏰ {time_str} - {summary}\n"

    return message