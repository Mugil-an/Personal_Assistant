# Personal Assistant - Setup and Deployment

This project has:

- Backend API: FastAPI (`web_app.py`) started via `run.py`
- Scheduler: APScheduler started inside backend process (`run.py`)
- Frontend: Streamlit (`ui/streamlit_app.py`)
- Database: PostgreSQL (`DATABASE_URL`)

## 1. Local Development

### Prerequisites

- Python 3.11+
- PostgreSQL
- Google OAuth credentials file (`credentials.json`)

### Install

```bash
pip install -r requirements.txt
```

### Configure `.env`

Required keys:

- `DATABASE_URL=postgresql://<user>:<password>@<host>:<port>/<db>`
- `GEMINI_API_KEY=<your_key>`
- `NOTIFY_EMAIL_FROM=<gmail_sender>`
- `NOTIFY_EMAIL_PASSWORD=<gmail_app_password>`

Recommended keys:

- `SCHEDULER_REFRESH_MINUTES=10`
- `ADMIN_API_KEY=<strong_secret_for_admin_endpoints>`
- `TIMEZONE=Asia/Kolkata` (or your timezone)
- `GMAIL_MAX_RESULTS=20`

### Run Backend

```bash
python run.py
```

Backend URLs:

- API: `http://localhost:8000`
- Docs: `http://localhost:8000/docs`

### Run Frontend

```bash
streamlit run ui/streamlit_app.py
```

Frontend URL:

- `http://localhost:8501`

## 2. Scheduler Behavior

The backend process starts APScheduler automatically.

Jobs:

- `sync_emails_<user_id>`: runs every `user.email_sync_hours`
- `notify_<user_id>`: runs daily at `user.notify_time` in `user.timezone`
- `schedule_notifications`: refreshes per-user jobs every `SCHEDULER_REFRESH_MINUTES`

Important:

- Run only one scheduler-enabled backend instance, otherwise scheduled jobs can execute multiple times

## 3. Docker (Local)

Build and start:

```bash
docker compose up --build -d
```

Services:

- API: `http://localhost:8000`
- UI: `http://localhost:8501`
- PostgreSQL: `localhost:5432`

Stop:

```bash
docker compose down
```

## 4. Deployment - Backend on Render, Frontend on Streamlit

### Backend (Render Web Service)

Use Docker deployment from `Dockerfile`.

Set environment variables in Render:

- `DATABASE_URL` (Render Postgres connection string)
- `GEMINI_API_KEY`
- `NOTIFY_EMAIL_FROM`
- `NOTIFY_EMAIL_PASSWORD`
- `ADMIN_API_KEY`
- `SCHEDULER_REFRESH_MINUTES`
- `TIMEZONE`
- `GOOGLE_CREDENTIALS_FILE=credentials.json`

Notes:

- Ensure `credentials.json` is available to the container
- Keep one running backend instance to avoid duplicate scheduler runs

### Frontend (Streamlit Cloud or Docker-hosted Streamlit)

Set:

- `API_BASE_URL=https://<your-render-backend-domain>`

Then run:

```bash
streamlit run ui/streamlit_app.py
```

## 5. Admin Scheduler Endpoint

Protected endpoint:

- `GET /api/admin/scheduler-jobs`
- Header required: `X-Admin-Key: <ADMIN_API_KEY>`

If `ADMIN_API_KEY` is not set, endpoint is disabled.

## 6. Troubleshooting

### `ModuleNotFoundError: psycopg2`

Install dependencies in the same interpreter environment used to run the app:

```bash
pip install -r requirements.txt
```

### OAuth callback errors (`Missing code verifier`)

Clear browser cookies for localhost and run OAuth flow again.

### Sync succeeds but UI shows failure

This usually indicates request timeout in UI while backend was still processing. Retry and check backend logs.

### Daily digest not sent

Verify:

- user has `notify_email` (fallback is login email)
- `NOTIFY_EMAIL_FROM` and `NOTIFY_EMAIL_PASSWORD` are valid
- Gmail app password is used (not normal password)
