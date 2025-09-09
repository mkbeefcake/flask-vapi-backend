from flask import Flask, render_template, request, redirect, url_for, jsonify
from twilio.rest import Client
from datetime import date, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build

from dotenv import load_dotenv
import dateparser
import os
import pyshorteners
import uuid

app = Flask(__name__)

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
GMAIL_ACCOUNT = os.getenv("GMAIL_ACCOUNT")

SERVICE_ACCOUNT_FILE = "vapi-dentist-book-222f512f966f.json"
SCOPES = ['https://www.googleapis.com/auth/calendar']


def shorten_url(long_url):
    s = pyshorteners.Shortener()
    return s.tinyurl.short(long_url)


def make_calendar_public(service, calendar_id):
    """Makes a calendar public to enable shareable links."""
    rule = {
        'scope': {
            'type': 'default',
        },
        'role': 'reader'
    }
    try:
        service.acl().insert(calendarId=calendar_id, body=rule).execute()
        print(f"Calendar {calendar_id} is now public.")
    except Exception as e:
        print(f"Failed to set calendar public (may already be public): {e}")


@app.route("/book_dentist", methods=['POST'])
def book_dentist():
    data = request.json
    if not data:
        return jsonify(status="failure", error="Invalid or missing parameters"), 500
    
    customer_number = data.get("customer_number")
    patient_name = data.get('patient_name')
    appointment_type = data.get("appointment_type")
    appointment_datetime = data.get("appointment_datetime")

    # validate customer number
    if not customer_number:
        return jsonify(status="failure", err="Invalid customer phone number"), 500

    # Parse appointment datetime and calculate end time (+30 mins by default)
    start_dt = dateparser.parse(appointment_datetime, settings={"TIMEZONE": "America/Toronto", "RETURN_AS_TIMEZONE_AWARE": True})
    if not start_dt:
        return jsonify(status="failure", error="Invalid datetime format"), 500

    end_dt = start_dt + timedelta(minutes=30)  # <-- changed from hours=1 to minutes=30
    start_dt = start_dt.replace(tzinfo=ZoneInfo("America/Toronto"))
    end_dt = end_dt.replace(tzinfo=ZoneInfo("America/Toronto"))

    # Format for Google Calendar (UTC)
    start_str = start_dt.strftime("%Y%m%dT%H%M%SZ")
    end_str = end_dt.strftime("%Y%m%dT%H%M%SZ")

    # Create Google Calendar link
    event_title = quote(f"{appointment_type} Dental Clinic")
    event_details = quote(f"Patient: {patient_name}\nPhone: {customer_number}\nType: {appointment_type} Dental Clinic")


    try:
        # Authenticate using service account
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service = build('calendar', 'v3', credentials=credentials)

        # Step 1: Create a public calendar (run this part once)
        new_calendar_body = {'summary': 'Shared Events', 'timeZone': 'America/Toronto'}
        created_calendar = service.calendars().insert(body=new_calendar_body).execute()
        calendar_id = created_calendar['id']
        make_calendar_public(service, calendar_id)

        # Create event
        event = {
            'summary': f'{appointment_type} Dental Clinic',
            'description': f"Patient: {patient_name}\nPhone: {customer_number}\nType: {appointment_type} Dental Clinic",
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'America/Toronto',
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'America/Toronto',
            },
            'conferenceData': {
                'createRequest': {
                    'requestId': str(uuid.uuid4()),
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            }
        }
        created_event = service.events().insert(calendarId=calendar_id, body=event).execute()
        calendar_link = created_event.get('htmlLink')    
        short_url = shorten_url(calendar_link)

        # Create Twilio SMS body
        sms_body = f"Hello {patient_name}, your {appointment_type} appointment is scheduled. Click here to add it to your Google Calendar: {short_url}"
        print(calendar_link)    
        print(sms_body)

        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=sms_body,
            from_=TWILIO_PHONE_NUMBER,
            to=customer_number
        )
        return jsonify({
            "status": "success",
            "sid": message.sid
        })

    except Exception as e:
        return jsonify({"status": "failure", "error": str(e)}), 500

@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=False)