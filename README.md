# Personal Assistant

Personal Assistant is a multi-user service that connects Gmail and Google Calendar to triage incoming email, extract time-sensitive information, and create calendar events automatically. The platform includes a FastAPI backend, a Streamlit UI, and an in-process scheduler for continuous sync and daily notifications.

## Highlights
- Multi-user OAuth flow with support for linked Gmail accounts
- Gemini-powered email understanding and classification
- Event creation with duplicate protection and timezone normalization
- Daily schedule notifications via Gmail SMTP
- Background scheduler for periodic syncs
- Streamlit dashboard for user sign-in and controls

## Architecture Overview
Core components:
- API server: FastAPI app in `web_app.py`, started via `run.py`
- Scheduler: APScheduler running inside the API process
- Services: Gmail reader, calendar manager, email parser, notifier
- UI: Streamlit app in `ui/streamlit_app.py`
- Database: PostgreSQL for users, linked accounts, and deduplication

Request flow (simplified):
1. User signs in via Google OAuth.
2. Tokens are stored in PostgreSQL.
3. Scheduler pulls email on a per-user schedule.
4. Gemini analyzes email content and returns structured intent.
5. Calendar events are created from qualified items.
6. Daily schedule summaries are emailed to users.

## Project Structure
- `app/` : FastAPI app code, services, and scheduler
- `ui/` : Streamlit UI
- `web_app.py` : FastAPI entry point (Uvicorn)
- `run.py` : Starts scheduler and API server together
- `Dockerfile` / `docker-compose.yml` : Container setup
- `SETUP.md` : Deployment and operational notes

## Requirements
- Python 3.11+ (local) or Docker
- PostgreSQL
- Google OAuth credentials (client JSON)
- Gemini API key

## Configuration
Use a `.env` file or environment variables. Required values vary by environment.

Required:
- `DATABASE_URL` : PostgreSQL URL (e.g., `postgresql://user:pass@host:5432/db`)
- `GEMINI_API_KEY` : Gemini API key
- `NOTIFY_EMAIL_FROM` : Gmail sender address
- `NOTIFY_EMAIL_PASSWORD` : Gmail App Password

Recommended:
- `ADMIN_API_KEY` : API key for admin endpoints
- `TIMEZONE` : IANA timezone (default: `UTC`)
- `GMAIL_MAX_RESULTS` : Max Gmail messages per sync (default: 20)
- `SCHEDULER_REFRESH_MINUTES` : Scheduler refresh interval (default: 10)

Optional:
- `GOOGLE_CREDENTIALS_FILE` : OAuth client file (default: `credentials.json`)
- `GOOGLE_TOKEN_FILE` : Token cache file name (default: `token.pickle`)
- `GEMINI_MODEL` : Gemini model name (default: `gemini-2.5-flash`)
- `GOOGLE_CALENDAR_ID` : Calendar ID (default: `primary`)
- `DEFAULT_EVENT_DURATION_MIN` : Default event duration minutes (default: 60)
- `NOTIFY_EMAIL_TO` : Fallback recipient for single-user mode
- `BASE_URL` : FastAPI base URL (default: `http://localhost:8000`)
- `STREAMLIT_URL` : Streamlit UI URL (default: `http://localhost:8501`)

## OAuth Setup
1. Create a Google Cloud OAuth client for a web application.
2. Download the client credentials JSON and place it at `credentials.json`.
3. Configure authorized redirect URIs:
   - `http://localhost:8000/oauth/callback`
   - `http://localhost:8000/link-account/callback`

## Running Locally
1. Create and activate a virtual environment.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Set environment variables or create a `.env` file.
4. Start the API server and scheduler:
   - `python run.py`
5. Start the Streamlit UI:
   - `streamlit run ui/streamlit_app.py`

API URLs:
- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`
- UI: `http://localhost:8501`

## Running with Docker
Build and run all services:
- `docker compose up --build -d`

Stop services:
- `docker compose down`

## Scheduler Behavior
The scheduler runs in the same process as the API server when using `run.py`.
Only run a single scheduler-enabled instance to avoid duplicate jobs.

Jobs:
- `sync_emails_<user_id>` : Runs every `user.email_sync_hours`
- `notify_<user_id>` : Runs daily at `user.notify_time` in the user timezone
- `schedule_notifications` : Refreshes per-user jobs every `SCHEDULER_REFRESH_MINUTES`

## API Endpoints (High Level)
- `GET /` : Health check
- `GET /api/config` : App configuration
- `GET /api/schedule` : Today's schedule
- `POST /api/run-assistant` : Run sync and event creation
- `POST /api/fetch-emails` : Fetch and parse emails
- `GET /status` : User preferences
- `GET /api/admin/scheduler-jobs` : Scheduler job list (admin key)

## Security Notes
- Use a Gmail App Password for SMTP notifications.
- Protect admin endpoints using `ADMIN_API_KEY`.
- Store OAuth credentials securely and do not commit them.

## Troubleshooting
- OAuth errors: verify redirect URIs and client JSON.
- No emails processed: check Gmail scopes and `GMAIL_MAX_RESULTS`.
- No events created: inspect Gemini output and email parsing logs.
- Duplicate events: ensure only one scheduler instance is active.

## Development Tips
- Use `SETUP.md` for deployment-specific details.
- Prefer running `run.py` so scheduler and API stay in sync.
- If you add new models, update the lightweight migration in `app/models.py`.
