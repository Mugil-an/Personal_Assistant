import base64

def fetch_emails(service):
    # 1. Define what we are looking for
    # This is exactly like typing in the Gmail search bar
    query = "subject:meeting OR subject:appointment OR subject:scheduled"
    
    # 2. Get the list of message IDs that match the query
    results = service.users().messages().list(userId='me', q=query).execute()
    messages = results.get('messages', [])

    email_data = []

    for msg in messages:
        # 3. Fetch the full details of each email using its ID
        txt = service.users().messages().get(userId='me', id=msg['id']).execute()
        
        payload = txt['payload']
        headers = payload['headers']

        # 4. Extract the Subject
        subject = ""
        for d in headers:
            if d['name'] == 'Subject':
                subject = d['value']

        # 5. Extract the Body (The actual text inside the email)
        # Gmail emails are encoded in Base64 (computer gibberish), so we decode them
        parts = payload.get('parts')
        body = ""
        if parts:
            data = parts[0]['body'].get('data')
            if data:
                body = base64.urlsafe_b64decode(data).decode('utf-8')

        email_data.append({'subject': subject, 'body': body})

    return email_data