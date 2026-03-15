"""System routes: health check, app config, and user status."""

import hmac
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query

from app.config import (
    ADMIN_API_KEY,
    CALENDAR_ID, DEFAULT_EVENT_DURATION_MIN,
    GMAIL_MAX_RESULTS, GMAIL_QUERY, TIMEZONE,
)
from app.models import Session, User

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", summary="Health check")
def health():
    return {"status": "ok"}


@router.get("/api/config", summary="App configuration")
def api_config():
    return {
        "gmail_query":            GMAIL_QUERY,
        "gmail_max_results":      GMAIL_MAX_RESULTS,
        "calendar_id":            CALENDAR_ID,
        "timezone":               TIMEZONE,
        "default_event_duration": DEFAULT_EVENT_DURATION_MIN,
    }


@router.get("/status", summary="Check your current preferences")
def get_status(user_id: str = Query(...)):
    db = Session()
    try:
        user = db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        return {
            "email":            user.email,
            "notify_time":      user.notify_time,
            "timezone":         user.timezone,
            "notify_email":     user.notify_email,
            "gmail_query":      user.gmail_query,
            "email_sync_hours": user.email_sync_hours or 24,
        }
    finally:
        db.close()


@router.get("/api/admin/scheduler-jobs", summary="List scheduler jobs and next run times")
def scheduler_jobs(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")):
    """Return active APScheduler jobs for operational verification.

    Useful in deployment to confirm per-user sync and notification jobs are
    scheduled with expected next-run times.
    """
    if not ADMIN_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Admin endpoint is disabled. Set ADMIN_API_KEY in environment.",
        )

    if not x_admin_key or not hmac.compare_digest(x_admin_key, ADMIN_API_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        from app.scheduler import scheduler

        jobs = []
        for job in scheduler.get_jobs():
            job_id = job.id or ""
            if job_id.startswith("sync_emails_"):
                job_type = "sync"
                user_id = job_id[len("sync_emails_"):]
            elif job_id.startswith("notify_"):
                job_type = "notify"
                user_id = job_id[len("notify_"):]
            else:
                job_type = "system"
                user_id = None

            jobs.append(
                {
                    "id": job_id,
                    "name": job.name,
                    "type": job_type,
                    "user_id": user_id,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                }
            )

        jobs.sort(key=lambda x: x["id"])
        return {
            "server_time_utc": datetime.now(timezone.utc).isoformat(),
            "count": len(jobs),
            "jobs": jobs,
        }
    except Exception as exc:
        logger.error("Failed to list scheduler jobs: %s", exc)
        raise HTTPException(status_code=500, detail=f"Could not read scheduler jobs: {exc}")
