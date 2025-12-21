import dateparser
from datetime import datetime

def create_event(service, subject, body):
    # 1. Use dateparser to extract a date from the text
    # It turns "Tomorrow at 4pm" into a real Python datetime object
    settings = {'PREFER_DATES_FROM': 'future'}
    dt = dateparser.parse(body, settings=settings)

    if not dt:
        print(f"Could not find a date in: {subject}")
        return

    # 2. Format the event for Google Calendar
    event = {
        'summary': subject,
        'description': body[:500], # Keep only first 500 chars
        'start': {
            'dateTime': dt.isoformat(),
            'timeZone': 'UTC', # Change to your timezone, e.g., 'Asia/Kolkata'
        },
        'end': {
            'dateTime': dt.isoformat(), # You can add +1 hour logic here
            'timeZone': 'UTC',
        },
    }

    # 3. Push to Google Calendar
    service.events().insert(calendarId='primary', body=event).execute()
    print(f"Event created: {subject} on {dt}")