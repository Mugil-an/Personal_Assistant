from datetime import datetime, timedelta

def get_today_schedule(service):
    # 1. Define the start and end of "Today"
    now = datetime.utcnow().isoformat() + 'Z' # 'Z' indicates UTC time
    end_of_day = (datetime.utcnow() + timedelta(days=1)).replace(hour=0, minute=0, second=0).isoformat() + 'Z'

    # 2. Fetch events
    events_result = service.events().list(
        calendarId='primary', timeMin=now, timeMax=end_of_day,
        singleEvents=True, orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])

    if not events:
        return "☕ No meetings scheduled for today. Enjoy your day!"

    # 3. Build the WhatsApp message string
    message = "🚀 *Your Daily Schedule:*\n\n"
    for event in events:
        start = event['start'].get('dateTime', event['start'].get('date'))
        # Simple formatting of the time
        time_str = start[11:16] 
        message += f"⏰ {time_str} - {event['summary']}\n"
    
    return message