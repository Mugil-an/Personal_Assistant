"""FastAPI backend for Personal Assistant."""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

from auth import authenticate
from calendar_manager import create_event
from daily_plan import get_today_schedule
from gmail_reader import fetch_emails
from notifier import send_whatsapp
import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Personal Assistant API", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class RunAssistantRequest(BaseModel):
    gmail_query: str = config.GMAIL_QUERY
    max_results: int = config.GMAIL_MAX_RESULTS
    send_whatsapp: bool = True


class FetchEmailsRequest(BaseModel):
    query: str = config.GMAIL_QUERY
    max_results: int = config.GMAIL_MAX_RESULTS


class CreateEventRequest(BaseModel):
    subject: str
    description: str = ""


@app.get("/")
def read_root():
    """Health check endpoint."""
    return {"message": "Personal Assistant API is running", "version": "1.0.0"}


@app.get("/api/config")
def get_config_endpoint():
    """Get current configuration."""
    return {
        "gmail_query": config.GMAIL_QUERY,
        "gmail_max_results": config.GMAIL_MAX_RESULTS,
        "timezone": config.TIMEZONE,
        "default_event_duration": config.DEFAULT_EVENT_DURATION_MIN,
        "calendar_id": config.CALENDAR_ID,
    }


@app.post("/api/run-assistant")
def run_assistant(request: RunAssistantRequest):
    """Run the full assistant workflow with custom settings."""
    try:
        logger.info("Authenticating with Google APIs")
        gmail, calendar = authenticate()
        
        logger.info(f"Fetching emails with query: {request.gmail_query}")
        new_emails = fetch_emails(gmail, query=request.gmail_query, max_results=request.max_results)
        
        created_events = []
        for email in new_emails:
            subject = email.get("subject", "")
            body = email.get("body", "")
            try:
                event = create_event(calendar, subject, body)
                created_events.append(event)
            except Exception as exc:
                logger.error(f"Failed to create event: {exc}")
        
        logger.info("Fetching today's schedule")
        schedule = get_today_schedule(calendar)
        
        # Send WhatsApp notification if enabled
        if request.send_whatsapp:
            logger.info("Sending schedule to WhatsApp")
            send_whatsapp(schedule)
        
        return {
            "status": "success",
            "message": "Assistant workflow completed",
            "emails_processed": len(new_emails),
            "events_created": len(created_events),
            "schedule": schedule,
        }
        
    except Exception as exc:
        logger.error(f"Error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/fetch-emails")
def fetch_emails_endpoint(request: FetchEmailsRequest):
    """Fetch emails with custom query."""
    try:
        gmail, _ = authenticate()
        
        emails = fetch_emails(gmail, query=request.query, max_results=request.max_results)
        
        return {
            "status": "success",
            "count": len(emails),
            "emails": emails,
        }
        
    except Exception as exc:
        logger.error(f"Error fetching emails: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/schedule")
def get_schedule_endpoint():
    """Get today's schedule from calendar."""
    try:
        _, calendar = authenticate()
        schedule = get_today_schedule(calendar)
        
        return {
            "status": "success",
            "schedule": schedule,
        }
        
    except Exception as exc:
        logger.error(f"Error fetching schedule: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/create-event")
def create_event_endpoint(request: CreateEventRequest):
    """Create a calendar event."""
    try:
        if not request.subject:
            raise HTTPException(status_code=400, detail="Subject is required")
        
        _, calendar = authenticate()
        event = create_event(calendar, request.subject, request.description)
        
        return {
            "status": "success",
            "event": event,
        }
        
    except Exception as exc:
        logger.error(f"Error creating event: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
