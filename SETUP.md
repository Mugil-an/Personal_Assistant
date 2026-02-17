# Personal Assistant - FastAPI + Streamlit Setup

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start FastAPI Backend (Terminal 1)
```bash
python app.py
```
Or with auto-reload:
```bash
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at:
- **API Base:** http://localhost:8000
- **Swagger Docs:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### 3. Start Streamlit Frontend (Terminal 2)
```bash
streamlit run streamlit_app.py
```

Streamlit will open in your browser at `http://localhost:8501`

---

## 📋 Features

### Dashboard Tab
- **Run Full Assistant** - Execute the complete workflow (fetch emails → create events → get schedule → send WhatsApp)
- **Get Today's Schedule** - View all calendar events for today
- Real-time status updates and event displays

### Email Management Tab
- **Custom Gmail Queries** - Search for specific email patterns
- **Adjustable Results** - Fetch 1-100 emails at a time
- **Email Preview** - View email subjects, senders, and full body content

### Create Event Tab
- **Quick Event Creation** - Add events to your calendar directly
- **Event Details** - Include subject and description
- **Instant Feedback** - Get confirmation when events are created

### Advanced Tab
- **Custom Workflows** - Run assistant with custom Gmail queries
- **Toggle Features** - Enable/disable WhatsApp notifications
- **API Documentation** - Quick access to Swagger UI
- **Configuration View** - See all current settings

---

## 🔧 API Endpoints

### GET /
Health check endpoint

### GET /api/config
Get current configuration settings

### POST /api/run-assistant
Run full workflow
```json
{
  "gmail_query": "subject:meeting",
  "max_results": 20,
  "send_whatsapp": true
}
```

### POST /api/fetch-emails
Fetch emails with custom query
```json
{
  "query": "subject:meeting",
  "max_results": 20
}
```

### GET /api/schedule
Get today's calendar events

### POST /api/create-event
Create a calendar event
```json
{
  "subject": "Team Meeting",
  "description": "Discuss Q1 goals"
}
```

---

## 📁 Project Structure

```
Personal_Assistant/
├── app.py                 # FastAPI backend
├── streamlit_app.py       # Streamlit frontend
├── main.py               # Original CLI entry point
├── auth.py               # Google authentication
├── calendar_manager.py    # Calendar operations
├── daily_plan.py         # Schedule management
├── gmail_reader.py       # Email fetching
├── notifier.py           # WhatsApp notifications
├── config.py             # Configuration settings
├── credentials.json      # Google service account key
├── requirements.txt      # Python dependencies
└── tokens/               # OAuth tokens storage
```

---

## 🔐 Configuration

All settings are in `config.py`. You can also set environment variables:

```bash
# Gmail settings
GMAIL_QUERY="subject:meeting OR subject:appointment"
GMAIL_MAX_RESULTS=20

# Calendar settings
GOOGLE_CALENDAR_ID="primary"
TIMEZONE="UTC"
DEFAULT_EVENT_DURATION_MIN=60

# WhatsApp (Twilio)
TWILIO_ACCOUNT_SID="your-sid"
TWILIO_AUTH_TOKEN="your-token"
WHATSAPP_FROM="whatsapp:+1234567890"
WHATSAPP_TO="whatsapp:+0987654321"
```

---

## 🎯 Workflow

1. **Streamlit Frontend** sends requests to **FastAPI Backend**
2. **FastAPI** authenticates with Google APIs
3. **Gmail Reader** fetches meeting-related emails
4. **Calendar Manager** creates events from email content
5. **Daily Plan** retrieves today's schedule
6. **Notifier** sends schedule via WhatsApp
7. Results are displayed in Streamlit dashboard

---

## 🐛 Troubleshooting

### "API is not running"
- Make sure FastAPI is running on port 8000
- Check if `python app.py` or `uvicorn app:app --reload` is active

### "Authentication failed"
- Verify `credentials.json` exists and is valid
- Check Google API credentials and permissions
- Ensure token.pickle is accessible

### "WhatsApp notifications fail"
- Verify Twilio credentials in `.env`
- Check `WHATSAPP_FROM` and `WHATSAPP_TO` are valid
- Ensure Twilio account has WhatsApp sandbox enabled

### Port 8000 already in use
```bash
uvicorn app:app --port 8001
```
Then update `API_BASE_URL` in `streamlit_app.py` to `http://localhost:8001`

---

## 📊 Performance Tips

- **Batch Email Fetching** - Filter with specific Gmail queries instead of fetching all emails
- **Caching** - Streamlit caches API responses automatically
- **Rate Limiting** - Google APIs have rate limits; adjust `GMAIL_MAX_RESULTS` accordingly

---

## 🔄 Workflow Examples

### Manual Run
Visit the Dashboard tab and click "Run Full Assistant"

### Scheduled Runs (Optional)
Add to your system scheduler or use APScheduler:
```python
from apscheduler.schedulers.background import BackgroundScheduler
from app import run_full_assistant

scheduler = BackgroundScheduler()
scheduler.add_job(run_full_assistant, 'cron', hour=9, minute=0)
scheduler.start()
```

---

## 📞 Support

For issues:
1. Check logs in terminal running FastAPI
2. Visit Swagger UI at `http://localhost:8000/docs`
3. Review Google API error messages
4. Verify `.env` configuration
