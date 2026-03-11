import logging
import json
from typing import Any, Dict, Optional

import google.generativeai as genai
from app.config import GEMINI_API_KEY, GEMINI_MODEL
from google.generativeai.types import GenerationConfig

logger = logging.getLogger(__name__)


if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY not found. Email parsing will be disabled.")


GEMINI_PROMPT = """
Analyze the following email content (and any extracted PDF attachment text below)
and extract key information in a structured JSON format.

**Email Body:**
---
{email_body}
---
{pdf_section}
**Instructions:**
1.  **Identify the primary intent.** If the email discusses a scheduled event, appointment, deadline, webinar, or any activity at a specific date/time, classify the intent as **"Event Scheduling"**. Other intents could be "Information Sharing", "Task Assignment", "Spam", etc.
2.  **Extract ALL specific dates and deadlines** mentioned. Return them as full, unambiguous strings (e.g., "April 13 2026", "2026-04-13 14:00"). Do not return vague terms like "tomorrow" or "next week".
3.  **Extract key entities,** such as names of people, organizations, and locations.
4.  **Summarize the email** in one or two sentences.
5.  **Suggest a concrete next action** (e.g., "Add deadline to calendar," "Reply to sender").

**Output Format (JSON only):**
{{
  "intent": "...",
  "summary": "...",
  "entities": {{
    "people": ["..."],
    "organizations": ["..."],
    "dates": ["..."],
    "locations": ["..."]
  }},
  "suggested_action": "..."
}}
"""


def parse_email_with_gemini(
        email_body: str,
        attachment_texts: list | None = None,
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

    if not GEMINI_API_KEY:
        logger.error("Cannot parse email: GEMINI_API_KEY is not configured")
        return None
    if not email_body and not attachment_texts:
        logger.warning("Email body and attachments are empty, skipping analysis")
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
        full_prompt = prompt.format(email_body=email_body or "", pdf_section=pdf_section)

        generation_config = GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json",
        )
        response = model.generate_content(
            full_prompt,
            generation_config=generation_config,
        )

        return json.loads(response.text)
    except Exception as e:
        logger.error("Error during Gemini API call: %s", e, exc_info=True)
        return None
