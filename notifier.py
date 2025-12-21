import os
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
FROM = os.getenv("WHATSAPP_FROM")
TO = os.getenv("WHATSAPP_TO")

def send_whatsapp(message_body):
    # These credentials come from your Twilio Dashboard
    client = Client(ACCOUNT_SID, AUTH_TOKEN)

    message = client.messages.create(
        from_=FROM, # Twilio Sandbox Number
        body=message_body,
        to=TO # Your verified number
    )

    print(f"📲 Message sent! SID: {message.sid}")