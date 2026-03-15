import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

from dateutil import parser as dt_parser
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import CALENDAR_ID, TIMEZONE


logger = logging.getLogger(__name__)


def _normalize_text(value: str) -> str:
    """Lowercase text and keep only alphanumeric tokens for loose matching."""
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def _is_similar_summary(a: str, b: str) -> bool:
    """Return True when two summaries are likely about the same event."""
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


def _resolve_timezone() -> Any:
    """Return the configured timezone; fallback to UTC if invalid."""
    try:
        return ZoneInfo(TIMEZONE)
    except ZoneInfoNotFoundError:
        logger.warning("Invalid TIMEZONE '%s'; defaulting to UTC", TIMEZONE)
        return timezone.utc


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


def _is_transient_network_error(exc: Exception) -> bool:
    text = str(exc).lower()
    patterns = [
        r"timed out",
        r"timeout",
        r"connection aborted",
        r"connection reset",
        r"unexpected eof",
        r"temporary failure",
        r"ssl",
        r"winerror\s*10053",
        r"winerror\s*10060",
        r"unable to find the server",
    ]
    return any(re.search(p, text) for p in patterns)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _list_calendar_events(service: Any, start_of_day: str, end_of_day: str) -> Dict[str, Any]:
    """Read one day's events with retry/backoff for transient failures."""
    return (
        service.events()
        .list(
            calendarId=CALENDAR_ID,
            timeMin=start_of_day,
            timeMax=end_of_day,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )


def get_today_schedule(service: Any) -> str:
    """Return a human-friendly summary of today's calendar events."""

    tzinfo = _resolve_timezone()
    now_local = datetime.now(tzinfo)
    start_of_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day_local = start_of_day_local + timedelta(days=1)

    # Query Google Calendar in UTC boundaries for the user's full local day.
    start_of_day = start_of_day_local.astimezone(timezone.utc).isoformat()
    end_of_day = end_of_day_local.astimezone(timezone.utc).isoformat()

    try:
        events_result = _list_calendar_events(service, start_of_day, end_of_day)
    except Exception as exc:
        level = logger.warning if _is_transient_network_error(exc) else logger.error
        level("Failed to fetch today's schedule from calendar after retries: %s", exc)
        return "■ Could not fetch today's schedule due to an error."

    events: List[Dict[str, Any]] = events_result.get("items", [])

    if not events:
        return "🗓️ No meetings scheduled for today. Enjoy your day!"

    message = "📅 *Your Daily Schedule:*\n\n"
    seen_signatures: list[tuple[str, str]] = []
    for event in events:
        start_obj = event.get("start", {})
        start_dt = _parse_event_start(start_obj)
        summary = event.get("summary") or "(No title)"

        if start_obj.get("date") and not start_obj.get("dateTime"):
            duplicate = any(sig_time == "all-day" and _is_similar_summary(summary, sig_summary) for sig_time, sig_summary in seen_signatures)
            if duplicate:
                continue
            seen_signatures.append(("all-day", summary))
            message += f"- All day - {summary}\n"
            continue

        if not start_dt:
            duplicate = any(sig_time == "unknown" and _is_similar_summary(summary, sig_summary) for sig_time, sig_summary in seen_signatures)
            if duplicate:
                continue
            seen_signatures.append(("unknown", summary))
            message += f"- (time unknown) - {summary}\n"
            continue

        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=timezone.utc)
        time_str = start_dt.astimezone(tzinfo).strftime("%H:%M")

        duplicate = any(sig_time == time_str and _is_similar_summary(summary, sig_summary) for sig_time, sig_summary in seen_signatures)
        if duplicate:
            continue
        seen_signatures.append((time_str, summary))

        message += f"- {time_str} - {summary}\n"

    return message
