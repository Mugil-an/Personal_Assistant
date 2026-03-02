import logging
import json
from typing import Any,Dict,Optional

import google.generativeai as genai
from config import GEMINI_API_KEY,GEMINI_MODEL
from google.generativeai.types import GenerationConfig

logger = logging.getLogger(__name__)


if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY not found. Email parsing will be disabled.")


GEMINI_PROMPT = """
Analyze the following email content and extract key information in a structured JSON format.

**Email Content:**
---
{email_body}
---

**Instructions:**
1.  **Identify the primary intent.** If the email discusses a scheduled event, appointment, webinar, or any activity at a specific time, classify the intent as **"Event Scheduling"**. Other intents could be "Information Sharing", "Task Assignment", "Spam", etc.
2.  **Extract key entities,** such as names of people, organizations, specific dates (including "tomorrow"), and locations.
3.  **Summarize the email** in one or two sentences.
4.  **Suggest a concrete next action** (e.g., "Add to calendar," "Reply to sender").

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
        email_body : str,
        prompt:str = GEMINI_PROMPT,
        model_name : str = GEMINI_MODEL,
) -> Optional[Dict[str,Any]] | None:
    

    if not GEMINI_API_KEY:
        logger.error("Cannot parse email: GEMINI_API_KEY is not configured")
        return None
    if not email_body:
        logger.warning("Email body is empty,skipping analysis")
        return None
    logger.info("Analyzing email with Gemini model : %s",model_name)
    try:
        model = genai.GenerativeModel(model_name)
        full_prompt = prompt.format(email_body = email_body)

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
        logger.error("Error during Gemini API call: %s",e,exc_info=True)
        return None
