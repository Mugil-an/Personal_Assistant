from auth import authenticate
from gmail_reader import fetch_emails
from calendar_manager import create_event
from daily_plan import get_today_schedule
from notifier import send_whatsapp

def run_assistant():
    # Step 1: Login to Google
    print("🔐 Authenticating...")
    gmail, calendar = authenticate()

    # Step 2: Read & Parse Emails
    print("📩 Checking for meeting emails...")
    new_emails = fetch_emails(gmail)
    for email in new_emails:
        create_event(calendar, email['subject'], email['body'])

    # Step 3: Get Today's Schedule & Notify
    print("📅 Fetching today's schedule...")
    schedule = get_today_schedule(calendar)
    
    print("📱 Sending to WhatsApp...")
    send_whatsapp(schedule)
    print("🏁 All tasks complete!")

if __name__ == "__main__":
    run_assistant()