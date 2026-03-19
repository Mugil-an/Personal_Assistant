import logging
import json
import re
import threading
import time
from typing import Any, Dict, Optional

import google.generativeai as genai
from app.config import GEMINI_API_KEY, GEMINI_MODEL
from google.generativeai.types import GenerationConfig

logger = logging.getLogger(__name__)

_quota_guard_lock = threading.Lock()
_quota_block_until_monotonic = 0.0


def _strip_markdown_code_fence(text: str) -> str:
    """Strip optional markdown code fences from model output."""
    stripped = (text or "").strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _parse_gemini_json_payload(text: str) -> Optional[Dict[str, Any]]:
    """Best-effort parse of Gemini JSON payload.

    Gemini can occasionally return JSON wrapped in markdown fences or include
    minor formatting issues such as trailing commas.
    """
    cleaned = _strip_markdown_code_fence(text)
    if not cleaned:
        return None

    # Fast path: strict JSON.
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Some responses include prose around the JSON object.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start : end + 1]
    else:
        candidate = cleaned

    # Remove trailing commas before closing object/array tokens.
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as decode_error:
        logger.warning(
            "Failed to parse Gemini JSON payload after cleanup: %s. Payload preview: %r",
            decode_error,
            candidate[:500],
        )
        return None


def _extract_retry_delay_seconds(error_text: str) -> int:
    """Extract retry delay from Gemini error text when available."""
    match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", error_text, flags=re.IGNORECASE)
    if not match:
        return 0
    try:
        return int(float(match.group(1)))
    except (ValueError, TypeError):
        return 0


def _is_quota_exhausted_error(error_text: str) -> bool:
    text = (error_text or "").lower()
    return "resourceexhausted" in text or "quota exceeded" in text or "429" in text


if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY not found. Email parsing will be disabled.")


GEMINI_PROMPT = """
Analyze the following email content (and any extracted PDF attachment text below)
and extract key information in a structured JSON format.

**Email Subject:** {email_subject}
**Email Sender:** {email_sender}

**Email Body:**
---
{email_body}
---
{pdf_section}
**Instructions:**
1.  **Identify the primary intent.** If the email discusses a scheduled event, appointment, deadline, webinar, or any activity at a specific date/time, classify the intent as **"Event Scheduling"**. Other intents could be "Information Sharing", "Task Assignment", "Spam", etc.
2.  **Extract ALL specific dates and deadlines** mentioned, including those deep within PDF attachments (e.g., event dates, submission deadlines). Return them as full, unambiguous strings (e.g., "April 13 2026", "2026-04-13 14:00"). Do not return vague terms like "tomorrow" or "next week".
3.  **Extract key entities,** such as names of people, organizations, and locations.
4.  **Summarize the email** in one or two sentences.
5.  **Suggest a concrete next action** (e.g., "Add deadline to calendar," "Reply to sender").
6.  **Assign exactly one email category** from this list only: **"Event"**, **"Promotion"**, **"Personal"**, **"Important"**. Be strict: if it is a newsletter, update, or marketing, mark it as "Promotion" so it can be filtered out.
7.  **Prioritize the email** with one of these values only: **"High"**, **"Medium"**, **"Low"**. Use **"High"** for urgent, deadline-driven, executive, financial, or action-required messages.
8.  **Detect if this email has an imminent deadline.** Set `has_deadline` to `true` if:
    - The email mentions a specific deadline, due date, or submission date that is upcoming (within the next 7 days)
    - The email requires immediate action (apply, submit, register, pay, respond, etc.)
    - The email contains urgency language (ASAP, urgent, final notice, last chance, etc.)
    - Set to `false` otherwise.

**Output Format (JSON only):**
{{
  "intent": "...",
  "category": "Event|Promotion|Personal|Important",
  "priority": "High|Medium|Low",
  "summary": "...",
  "has_deadline": true|false,
  "entities": {{
    "people": ["..."],
    "organizations": ["..."],
    "dates": ["..."],
    "locations": ["..."]
  }},
  "suggested_action": "..."
}}
"""


EMAIL_CATEGORIES = {"Event", "Promotion", "Personal", "Important"}
PRIORITY_ORDER = {"Low": 1, "Medium": 2, "High": 3}

PROMOTION_PATTERNS = [
    r"\bdiscount\b",
    r"\boffer\b",
    r"\bsale\b",
    r"\bpromo\b",
    r"\bcoupon\b",
    r"\bdeal\b",
    r"\bunsubscribe\b",
    r"\bfree trial\b",
    r"\bmarketing\b",
    r"\bnewsletter\b",
    r"\blimited time\b",
]

IMPORTANT_PATTERNS = [
    r"\burgent\b",
    r"\basap\b",
    r"\bimmediate\b",
    r"\baction required\b",
    r"\bdeadline\b",
    r"\bdue\b",
    r"\boverdue\b",
    r"\bpayment\b",
    r"\binvoice\b",
    r"\bsecurity alert\b",
    r"\bverify\b",
    r"\bimportant\b",
]

PERSONAL_PATTERNS = [
    r"\bfamily\b",
    r"\bfriend\b",
    r"\bcatch up\b",
    r"\bdinner\b",
    r"\bweekend\b",
    r"\bbirthday\b",
    r"\bcall me\b",
    r"\bhow are you\b",
]

EVENT_PATTERNS = [
    r"\bmeeting\b",
    r"\bappointment\b",
    r"\bwebinar\b",
    r"\bcalendar\b",
    r"\bschedule\b",
    r"\breschedule\b",
    r"\bjoin us\b",
    r"\bconference\b",
    r"\binterview\b",
    r"\bstarts at\b",
]


def _text_matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _normalize_category(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().title()
    return normalized if normalized in EMAIL_CATEGORIES else ""


def _normalize_priority(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    normalized = value.strip().title()
    return normalized if normalized in PRIORITY_ORDER else ""


def _infer_category(subject: str, sender: str, email_body: str, intent: str) -> str:
    combined = "\n".join(part for part in [subject, sender, email_body] if part).lower()
    sender_lower = (sender or "").lower()

    if intent == "Event Scheduling" or _text_matches(combined, EVENT_PATTERNS):
        return "Event"
    if _text_matches(combined, IMPORTANT_PATTERNS):
        return "Important"
    if _text_matches(combined, PROMOTION_PATTERNS) or any(
        token in sender_lower for token in ("noreply", "newsletter", "marketing", "offers")
    ):
        return "Promotion"
    if _text_matches(combined, PERSONAL_PATTERNS):
        return "Personal"
    return "Important" if intent == "Task Assignment" else "Personal"


def _infer_priority(category: str, subject: str, email_body: str, intent: str) -> tuple[str, int]:
    combined = "\n".join(part for part in [subject, email_body] if part).lower()

    base_score = {
        "Important": 90,
        "Event": 75,
        "Personal": 55,
        "Promotion": 20,
    }.get(category, 50)

    if _text_matches(combined, IMPORTANT_PATTERNS):
        base_score += 15
    if _text_matches(combined, EVENT_PATTERNS) or intent == "Event Scheduling":
        base_score += 10
    if re.search(r"\btoday\b|\btonight\b|\bthis afternoon\b|\bby eod\b", combined, flags=re.IGNORECASE):
        base_score += 10
    if _text_matches(combined, PROMOTION_PATTERNS):
        base_score -= 15

    score = max(0, min(100, base_score))
    if score >= 80:
        return "High", score
    if score >= 45:
        return "Medium", score
    return "Low", score


def enrich_email_analysis(
    email_body: str,
    parsed: Optional[Dict[str, Any]],
    subject: str = "",
    sender: str = "",
    sender_priority: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a stable email analysis payload with category and priority.
    
    Parameters
    ----------
    sender_priority : str, optional
        User's priority level for this sender ("high", "medium", "low").
        If "high", the email's priority will be boosted to High.
    """

    analysis = dict(parsed or {})
    intent = analysis.get("intent", "")

    category = _normalize_category(analysis.get("category")) or _infer_category(
        subject=subject,
        sender=sender,
        email_body=email_body,
        intent=intent,
    )
    priority, priority_score = _infer_priority(
        category=category,
        subject=subject,
        email_body=email_body,
        intent=intent,
    )
    parsed_priority = _normalize_priority(analysis.get("priority"))
    if parsed_priority:
        priority = parsed_priority
        priority_score = {"Low": 30, "Medium": 60, "High": 90}[priority]

    # Boost priority if sender is marked as high-priority
    if sender_priority and sender_priority.lower() == "high":
        priority = "High"
        priority_score = 95
        # Optionally boost "Promotion" to "Important" if from high-priority sender
        if category == "Promotion":
            category = "Important"

    analysis["category"] = category
    analysis["priority"] = priority
    analysis["priority_score"] = priority_score
    analysis["sender_priority"] = sender_priority or "medium"
    analysis.setdefault("summary", "")
    analysis.setdefault("suggested_action", "")
    analysis.setdefault("has_deadline", False)
    analysis.setdefault(
        "entities",
        {"people": [], "organizations": [], "dates": [], "locations": []},
    )

    return analysis


def parse_email_with_gemini(
        email_body: str,
        attachment_texts: list | None = None,
    email_subject: str = "",
    email_sender: str = "",
        prompt: str = GEMINI_PROMPT,
        model_name: str = GEMINI_MODEL,
) -> Optional[Dict[str, Any]]:
    """Parse email body (and optional PDF attachment texts) with Gemini.

    Parameters
    ----------
    email_body:
        Plain-text body of the email.
    attachment_texts:
        List of text strings extracted from PDF attachments. Each will be
        appended to the prompt so Gemini can read deadline/date info from PDFs.
    """

    global _quota_block_until_monotonic

    if not GEMINI_API_KEY:
        logger.error("Cannot parse email: GEMINI_API_KEY is not configured")
        return None
    if not email_body and not attachment_texts:
        logger.warning("Email body and attachments are empty, skipping analysis")
        return None

    # Avoid hammering Gemini after quota/rate-limit failures.
    now_monotonic = time.monotonic()
    if now_monotonic < _quota_block_until_monotonic:
        remaining = int(_quota_block_until_monotonic - now_monotonic)
        logger.warning(
            "Skipping Gemini call due to active quota cooldown (%ss remaining)",
            max(0, remaining),
        )
        return None

    # Build the optional PDF section injected into the prompt
    pdf_section = ""
    if attachment_texts:
        combined = "\n\n---\n\n".join(t for t in attachment_texts if t)
        if combined.strip():
            pdf_section = f"\n**Extracted PDF Attachment Content:**\n---\n{combined[:4000]}\n---\n"

    logger.info("Analyzing email with Gemini model: %s", model_name)
    try:
        model = genai.GenerativeModel(model_name)
        full_prompt = prompt.format(
            email_subject=email_subject or "",
            email_sender=email_sender or "",
            email_body=email_body or "",
            pdf_section=pdf_section,
        )

        generation_config = GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json",
        )
        response = model.generate_content(
            full_prompt,
            generation_config=generation_config,
        )
        parsed = _parse_gemini_json_payload(getattr(response, "text", ""))
        if parsed is None:
            logger.warning("Gemini response was not valid JSON after cleanup; skipping email analysis.")
            return None
        return parsed
    except Exception as e:
        error_text = str(e)
        if _is_quota_exhausted_error(error_text):
            retry_delay = _extract_retry_delay_seconds(error_text)

            # If quota appears daily-limited, avoid retry storms for this run.
            daily_metric_hit = "perday" in error_text.lower() or "free_tier_requests" in error_text.lower()
            cooldown_seconds = max(retry_delay, 3600 if daily_metric_hit else 30)

            with _quota_guard_lock:
                _quota_block_until_monotonic = max(
                    _quota_block_until_monotonic,
                    time.monotonic() + cooldown_seconds,
                )

            logger.warning(
                "Gemini quota/rate limit hit. Entering cooldown for %ss. Error: %s",
                cooldown_seconds,
                error_text,
            )
            return None

        logger.error("Error during Gemini API call: %s", e, exc_info=True)
        return None
