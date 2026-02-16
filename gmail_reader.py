import base64
import logging
from typing import Any, Dict, List

from config import GMAIL_MAX_RESULTS, GMAIL_QUERY


logger = logging.getLogger(__name__)


def _decode_body_from_payload(payload: Dict[str, Any]) -> str:
    """Extract and decode the plain-text body from a Gmail payload.

    Tries to find a "text/plain" part; falls back to the first available part
    if necessary.
    """

    body = ""
    parts = payload.get("parts")
    if not parts:
        data = payload.get("body", {}).get("data")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return body

    # Prefer text/plain if present
    text_part = None
    for part in parts:
        mime_type = part.get("mimeType", "")
        if mime_type == "text/plain":
            text_part = part
            break

    if text_part is None:
        text_part = parts[0]

    data = text_part.get("body", {}).get("data")
    if data:
        body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")

    return body


def fetch_emails(service, query: str | None = None, max_results: int | None = None) -> List[Dict[str, str]]:
    """Fetch recent emails matching the configured query from Gmail.

    Parameters
    ----------
    service: Gmail service client from googleapiclient.discovery.build
    query: Optional Gmail-style search query string. Defaults to GMAIL_QUERY.
    max_results: Optional maximum number of messages to fetch. Defaults to
        GMAIL_MAX_RESULTS from configuration.
    """

    if query is None:
        query = GMAIL_QUERY
    if max_results is None:
        max_results = GMAIL_MAX_RESULTS

    logger.info("Fetching emails with query='%s' (max %s)", query, max_results)

    email_data: List[Dict[str, str]] = []
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

                # Fetch the full details of each email using its ID
                txt = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg_id, format="full")
                    .execute()
                )

                payload = txt.get("payload", {})
                headers = payload.get("headers", [])

                # Extract the Subject
                subject = ""
                for header in headers:
                    if header.get("name") == "Subject":
                        subject = header.get("value", "")
                        break

                # Extract and decode the body
                body = _decode_body_from_payload(payload)

                email_data.append({"subject": subject, "body": body})

            page_token = results.get("nextPageToken")
            if not page_token:
                break

    except Exception as exc:  # Broad catch to prevent whole run from failing
        logger.error("Error while fetching emails: %s", exc)

    logger.info("Fetched %d email(s) matching query", len(email_data))
    return email_data