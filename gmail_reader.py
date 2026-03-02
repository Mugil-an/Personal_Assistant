import base64
import io
import json
import logging
import os
from typing import Any, Dict, List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from config import GMAIL_MAX_RESULTS, GMAIL_QUERY

try:
    import pypdf
    _PYPDF_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYPDF_AVAILABLE = False

logger = logging.getLogger(__name__)

# Max attachment size to download (10 MB)
_MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

# File used to persist message IDs that have already been processed
_SEEN_IDS_FILE = os.path.join(os.path.dirname(__file__), ".seen_email_ids.json")


def _load_seen_ids() -> set:
    """Load already-processed Gmail message IDs from disk."""
    if os.path.exists(_SEEN_IDS_FILE):
        try:
            with open(_SEEN_IDS_FILE, "r", encoding="utf-8") as fh:
                return set(json.load(fh))
        except Exception:
            pass
    return set()


def _save_seen_ids(seen: set) -> None:
    """Persist the set of processed Gmail message IDs to disk."""
    try:
        with open(_SEEN_IDS_FILE, "w", encoding="utf-8") as fh:
            json.dump(list(seen), fh)
    except Exception as exc:
        logger.warning("Could not save seen email IDs: %s", exc)


logger = logging.getLogger(__name__)


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


def fetch_emails(service, query: str | None = None, max_results: int | None = None) -> List[Dict[str, Any]]:
    """Fetch recent emails matching the configured query from Gmail.

    Parameters
    ----------
    service: Gmail service client from googleapiclient.discovery.build
    query: Optional Gmail-style search query string. Defaults to GMAIL_QUERY.
    max_results: Optional maximum number of messages to fetch. Defaults to
        GMAIL_MAX_RESULTS from configuration.

    Returns a list of dicts with keys:
        subject, from_, to, date, body, attachments.
    Already-seen message IDs are skipped and persisted to disk.
    """

    if query is None:
        query = GMAIL_QUERY
    if max_results is None:
        max_results = GMAIL_MAX_RESULTS

    logger.info("Fetching emails with query='%s' (max %s)", query, max_results)

    seen_ids = _load_seen_ids()
    email_data: List[Dict[str, Any]] = []
    page_token = None

    try:
        while True:
            remaining = max_results - len(email_data)
            if remaining <= 0:
                break

            list_req = (
                service.users()
                .messages()
                .list(userId="me", q=query, pageToken=page_token, maxResults=min(remaining, 100))
            )
            results = list_req.execute()
            messages = results.get("messages", [])

            for msg in messages:
                if len(email_data) >= max_results:
                    break

                msg_id = msg.get("id")
                if not msg_id:
                    continue

                # Skip already-processed emails
                if msg_id in seen_ids:
                    logger.debug("Skipping already-seen message %s", msg_id)
                    continue

                try:
                    txt = _get_message(service, msg_id)
                except Exception as exc:
                    logger.error("Failed to fetch message %s after retries: %s", msg_id, exc)
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

            page_token = results.get("nextPageToken")
            if not page_token:
                break

    except Exception as exc:
        logger.error("Error while fetching emails: %s", exc)

    _save_seen_ids(seen_ids)
    logger.info("Fetched %d new email(s) matching query", len(email_data))
    return email_data