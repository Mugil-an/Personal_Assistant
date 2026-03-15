import base64
import io
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import GMAIL_MAX_RESULTS, GMAIL_QUERY
from app.models import SeenEmail

try:
    import pypdf
    _PYPDF_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYPDF_AVAILABLE = False

logger = logging.getLogger(__name__)

# Max attachment size to download (10 MB)
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

# File used to persist message IDs that have already been processed (legacy single-user path)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SEEN_IDS_FILE = os.path.join(_BASE_DIR, "data", ".seen_email_ids.json")


def _load_seen_ids(path: str | None = None) -> set:
    """Load already-processed Gmail message IDs from disk."""
    target = path or _SEEN_IDS_FILE
    if os.path.exists(target):
        try:
            with open(target, "r", encoding="utf-8") as fh:
                return set(json.load(fh))
        except Exception:
            pass
    return set()


def _save_seen_ids(seen: set, path: str | None = None) -> None:
    """Persist the set of processed Gmail message IDs to disk."""
    target = path or _SEEN_IDS_FILE
    try:
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(list(seen), fh)
    except Exception as exc:
        logger.warning("Could not save seen email IDs to %s: %s", target, exc)


def _load_seen_ids_from_db(db: Any, account_id: str, candidate_ids: List[str]) -> set[str]:
    """Load seen IDs for one account from DB for a given candidate set."""
    if not candidate_ids:
        return set()
    rows = (
        db.query(SeenEmail.message_id)
        .filter(SeenEmail.account_id == account_id, SeenEmail.message_id.in_(candidate_ids))
        .all()
    )
    return {row[0] for row in rows}


def _save_seen_ids_to_db(db: Any, account_id: str, message_ids: set[str]) -> None:
    """Persist newly seen message IDs for one account."""
    if not message_ids:
        return

    existing_rows = (
        db.query(SeenEmail.message_id)
        .filter(SeenEmail.account_id == account_id, SeenEmail.message_id.in_(list(message_ids)))
        .all()
    )
    existing = {row[0] for row in existing_rows}
    to_insert = message_ids - existing
    if not to_insert:
        return

    db.add_all([SeenEmail(account_id=account_id, message_id=msg_id) for msg_id in to_insert])
    db.commit()


def _decode_body_from_payload(payload: Dict[str, Any]) -> str:
    """Extract and decode the plain-text body from a Gmail payload.

    Preference order: text/plain → text/html → first part.
    """
    body = ""
    parts = payload.get("parts")
    if not parts:
        data = payload.get("body", {}).get("data")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return body

    # Prefer text/plain, fall back to text/html, then first part
    text_part: Optional[Dict[str, Any]] = None
    for preferred_mime in ("text/plain", "text/html"):
        for part in parts:
            if part.get("mimeType", "") == preferred_mime:
                text_part = part
                break
        if text_part is not None:
            break

    if text_part is None:
        text_part = parts[0]

    data = text_part.get("body", {}).get("data")
    if data:
        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    return body


def _walk_attachment_parts(
    service: Any,
    message_id: str,
    parts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Recursively walk message parts and download attachments.

    Returns a list of dicts with keys:
        filename, mime_type, content (raw bytes), extracted_text (str or None).
    Skips attachments larger than _MAX_ATTACHMENT_BYTES.
    """
    attachments: List[Dict[str, Any]] = []

    for part in parts:
        subparts = part.get("parts")
        if subparts:
            attachments.extend(_walk_attachment_parts(service, message_id, subparts))
            continue

        filename = part.get("filename")
        body = part.get("body", {})
        mime_type = part.get("mimeType", "")
        attachment_id = body.get("attachmentId")

        if not (filename and attachment_id):
            continue

        # Skip files that are too large
        size = body.get("size", 0)
        if size > _MAX_ATTACHMENT_BYTES:
            logger.warning(
                "Skipping large attachment '%s' (%s bytes) for message %s",
                filename, size, message_id,
            )
            continue

        try:
            att = (
                service.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=message_id, id=attachment_id)
                .execute()
            )
            data = att.get("data")
            if not data:
                continue

            content: bytes = base64.urlsafe_b64decode(data)

            # Extract text from PDFs for Gemini
            extracted_text: Optional[str] = None
            if _PYPDF_AVAILABLE and mime_type == "application/pdf":
                try:
                    reader = pypdf.PdfReader(io.BytesIO(content))
                    extracted_text = "\n".join(
                        page.extract_text() or "" for page in reader.pages
                    )
                except Exception as pdf_exc:
                    logger.warning("Could not extract text from PDF '%s': %s", filename, pdf_exc)

            attachments.append(
                {
                    "filename": filename,
                    "mime_type": mime_type,
                    "content": content,
                    "extracted_text": extracted_text,
                }
            )
        except Exception as exc:
            logger.error(
                "Failed to download attachment '%s' for message %s: %s",
                filename, message_id, exc,
            )

    return attachments


def _extract_attachments(service: Any, message_id: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Public wrapper around _walk_attachment_parts."""
    parts = payload.get("parts") or []
    return _walk_attachment_parts(service, message_id, parts)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _get_message(service: Any, msg_id: str) -> Dict[str, Any]:
    """Fetch a single Gmail message with retry logic for transient errors."""
    return (
        service.users()
        .messages()
        .get(userId="me", id=msg_id, format="full")
        .execute()
    )


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
def _list_messages_page(service: Any, query: str, page_token: str | None, remaining: int) -> Dict[str, Any]:
    """Fetch one Gmail message-list page with retry for transient network faults."""
    list_req = (
        service.users()
        .messages()
        .list(userId="me", q=query, pageToken=page_token, maxResults=min(remaining, 100))
    )
    return list_req.execute()


def fetch_emails(
    service,
    query: str | None = None,
    max_results: int | None = None,
    seen_ids_file: str | None = None,
    after_epoch: int | None = None,
    db: Any | None = None,
    seen_account_id: str | None = None,
) -> List[Dict[str, Any]]:
    """Fetch recent emails matching the configured query from Gmail.

    Parameters
    ----------
    service: Gmail service client from googleapiclient.discovery.build
    query: Optional Gmail-style search query string. Defaults to GMAIL_QUERY.
    max_results: Optional maximum number of messages to fetch. Defaults to
        GMAIL_MAX_RESULTS from configuration.
    seen_ids_file: Optional path for per-account seen-IDs tracking. Defaults
        to the shared legacy file.
    after_epoch: Optional Unix timestamp (seconds). When provided, only emails
        received at or after this time are fetched (appended as ``after:<ts>``
        to the Gmail query).
    db: Optional SQLAlchemy session for DB-backed seen-ID tracking.
    seen_account_id: Account ID used with ``db`` for per-account deduplication.

    Returns a list of dicts with keys:
        subject, from_, to, date, body, attachments.
    Already-seen message IDs are skipped and persisted to disk.
    """

    if query is None:
        query = GMAIL_QUERY
    if max_results is None:
        max_results = GMAIL_MAX_RESULTS

    if after_epoch is not None:
        time_filter = f"after:{after_epoch}"
        query = f"{time_filter} {query}" if query else time_filter

    logger.info("Fetching emails with query='%s' (max %s)", query, max_results)

    use_db_seen_tracking = db is not None and bool(seen_account_id)
    seen_ids = set() if use_db_seen_tracking else _load_seen_ids(seen_ids_file)
    new_seen_ids_db: set[str] = set()
    email_data: List[Dict[str, Any]] = []
    page_token = None

    try:
        while True:
            remaining = max_results - len(email_data)
            if remaining <= 0:
                break

            try:
                results = _list_messages_page(service, query, page_token, remaining)
            except Exception as exc:
                level = logger.warning if _is_transient_network_error(exc) else logger.error
                level("Failed to list Gmail messages after retries: %s", exc)
                break
            messages = results.get("messages", [])

            seen_ids_this_page: set[str] = set()
            if use_db_seen_tracking:
                candidate_ids = [m.get("id") for m in messages if m.get("id")]
                seen_ids_this_page = _load_seen_ids_from_db(db, seen_account_id, candidate_ids)

            for msg in messages:
                if len(email_data) >= max_results:
                    break

                msg_id = msg.get("id")
                if not msg_id:
                    continue

                # Skip already-processed emails
                if msg_id in seen_ids or msg_id in seen_ids_this_page:
                    logger.debug("Skipping already-seen message %s", msg_id)
                    continue

                try:
                    txt = _get_message(service, msg_id)
                except Exception as exc:
                    level = logger.warning if _is_transient_network_error(exc) else logger.error
                    level("Failed to fetch message %s after retries: %s", msg_id, exc)
                    continue

                payload = txt.get("payload", {})
                headers = payload.get("headers", [])

                # Extract key headers: Subject, From, To, Date
                header_map: Dict[str, str] = {}
                for header in headers:
                    name = header.get("name", "").lower()
                    if name in ("subject", "from", "to", "date"):
                        header_map[name] = header.get("value", "")

                # Extract and decode the body
                body = _decode_body_from_payload(payload)

                # Extract attachments such as PDFs, images, etc.
                attachments = _extract_attachments(service, msg_id, payload)

                email_data.append(
                    {
                        "subject": header_map.get("subject", ""),
                        "from_": header_map.get("from", ""),
                        "to": header_map.get("to", ""),
                        "date": header_map.get("date", ""),
                        "body": body,
                        "attachments": attachments,
                    }
                )
                seen_ids.add(msg_id)
                if use_db_seen_tracking:
                    new_seen_ids_db.add(msg_id)

            page_token = results.get("nextPageToken")
            if not page_token:
                break

    except Exception as exc:
        logger.error("Error while fetching emails: %s", exc)

        if use_db_seen_tracking:
            _save_seen_ids_to_db(db, seen_account_id, new_seen_ids_db)
        else:
            _save_seen_ids(seen_ids, seen_ids_file)
    logger.info("Fetched %d new email(s) matching query", len(email_data))
    return email_data
