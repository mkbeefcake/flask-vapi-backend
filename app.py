from flask import Flask, render_template, request, redirect, url_for, jsonify
from twilio.rest import Client
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo
from google.oauth2 import service_account
from googleapiclient.discovery import build

from dotenv import load_dotenv
import dateparser
import os
import pyshorteners
import uuid
import urllib
import gspread
from aldershot import asbp

app = Flask(__name__)
app.register_blueprint(asbp, url_prefix="/aldershot")



# def shorten_url(long_url):
#     s = pyshorteners.Shortener()
#     return s.tinyurl.short(long_url)


# def make_calendar_public(service, calendar_id):
#     """Makes a calendar public to enable shareable links."""
#     rule = {
#         'scope': {
#             'type': 'default',
#         },
#         'role': 'reader'
#     }
#     try:
#         service.acl().insert(calendarId=calendar_id, body=rule).execute()
#         print(f"Calendar {calendar_id} is now public.")
#     except Exception as e:
#         print(f"Failed to set calendar public (may already be public): {e}")


# def make_event_public_and_get_link(service, calendar_id, event_id):
#     """Updates an event's visibility to public and returns its link."""
#     try:
#         # Patch the event to change its visibility
#         event_body = {'visibility': 'public'}
#         public_event = service.events().patch(
#             calendarId=calendar_id, 
#             eventId=event_id, 
#             body=event_body
#         ).execute()
        
#         return public_event.get('htmlLink')

#     except Exception as e:
#         print(f"Failed to update event visibility: {e}")
#         return None
    

# @app.route("/book_dentist", methods=['POST'])
# def book_dentist():
#     data = request.json
#     if not data:
#         return jsonify(status="failure", error="Invalid or missing parameters"), 500
    
#     is_rescheduling = False
    
#     customer_number = data.get("customer_number", "")
#     patient_name = data.get('patient_name')
#     appointment_datetime = data.get("appointment_datetime", "")
#     appointment_type = data.get("appointment_type", "Urgent")
#     previous_dentist_name = data.get("previous_dentist_name", "")
#     dentist_name = data.get("dentist_name", "")
#     intention = data.get("intention", "")
#     new_appointment_datetime = data.get("new_appointment_datetime", "")

#     print(f"Customer_number Intention: {intention}, Name: {patient_name}, DateTime: {appointment_datetime}, New Date: {new_appointment_datetime}, Type: {appointment_type}, prevDen: {previous_dentist_name}, Den: {dentist_name}\n")

#     if dentist_name == "":
#         dentist_name = previous_dentist_name

#     # Booking Date Time
#     # Parse appointment datetime and calculate end time (+30 mins by default)
#     start_str = ""
#     end_str = ""

#     start_dt = dateparser.parse(appointment_datetime, settings={"TIMEZONE": "America/Toronto", "RETURN_AS_TIMEZONE_AWARE": True})
#     end_dt = dateparser.parse(appointment_datetime, settings={"TIMEZONE": "America/Toronto", "RETURN_AS_TIMEZONE_AWARE": True})
#     if start_dt:
#         end_dt = start_dt + timedelta(minutes=30)  # <-- changed from hours=1 to minutes=30
#         start_dt = start_dt.replace(tzinfo=ZoneInfo("America/Toronto"))
#         end_dt = end_dt.replace(tzinfo=ZoneInfo("America/Toronto"))

#         start_dt_utc = start_dt.astimezone(timezone.utc)
#         end_dt_utc = end_dt.astimezone(timezone.utc)

#         # Format for Google Calendar (UTC)
#         start_str = start_dt_utc.strftime("%Y%m%dT%H%M%SZ")
#         end_str = end_dt_utc.strftime("%Y%m%dT%H%M%SZ")

#     # Rescheduling Date Time
#     # Parse new appointment datetime and calculate end time (+30 mins by default)
#     new_start_str = ""
#     new_end_str = ""
#     new_start_dt = dateparser.parse(new_appointment_datetime, settings={"TIMEZONE": "America/Toronto", "RETURN_AS_TIMEZONE_AWARE": True})
#     new_end_dt = dateparser.parse(new_appointment_datetime, settings={"TIMEZONE": "America/Toronto", "RETURN_AS_TIMEZONE_AWARE": True})
#     if new_start_dt:        
#         new_end_dt = new_start_dt + timedelta(minutes=30)  # <-- changed from hours=1 to minutes=30
#         new_start_dt = new_start_dt.replace(tzinfo=ZoneInfo("America/Toronto"))
#         new_end_dt = new_end_dt.replace(tzinfo=ZoneInfo("America/Toronto"))

#         new_start_dt_utc = new_start_dt.astimezone(timezone.utc)
#         new_end_dt_utc = new_end_dt.astimezone(timezone.utc)

#         # Format for Google Calendar (UTC)
#         new_start_str = new_start_dt_utc.strftime("%Y%m%dT%H%M%SZ")
#         new_end_str = new_end_dt_utc.strftime("%Y%m%dT%H%M%SZ")
        
#         is_rescheduling = True


#     # Create Google Calendar link
#     event_title = quote(f"{appointment_type} Dental Clinic")
#     event_details = quote(f"Patient: {patient_name}\nPhone: {customer_number}\nType: {appointment_type} Dental Clinic\nContact:{GMAIL_ACCOUNT}")

#     try:

#         # 1. Create Service account
#         # Authenticate using service account
#         credentials = service_account.Credentials.from_service_account_file(
#             SERVICE_ACCOUNT_FILE, scopes=SCOPES
#         )
#         service = build('calendar', 'v3', credentials=credentials)

#         # 2. Update the Google Spreedsheet in Clinic's gmail account
#         # 
#         now_toronto = datetime.now(ZoneInfo("America/Toronto"))
#         current_datetime = now_toronto.strftime("%Y-%m-%d %H:%M:%S %Z")

#         try:
#             spread_client = gspread.authorize(credentials=credentials)
#             spreadsheet = spread_client.open(SPREAD_SHEET)
#             sheet = spreadsheet.sheet1 
#             sheet.append_row([intention, patient_name, customer_number, appointment_datetime, start_str, 
#                               new_appointment_datetime, new_start_str, appointment_type, dentist_name, current_datetime])
    
#             pass
#         except Exception as e:
#             print(f"Failed to open spreadsheet: {str(e)}")
#             pass

#         # 3. Create calendar event in Clinic's gmail account
#         # Create event
#         try:
#             event = {
#                 'summary': f'Rescheduled: {appointment_type} Dental Clinic' if is_rescheduling else f'{appointment_type} Dental Clinic' ,
#                 'description': f"Patient: {patient_name}\nPhone: {customer_number}\nType: {appointment_type} Dental Clinic\nDentist:{dentist_name}\nContact:{GMAIL_ACCOUNT}",
#                 'start': {
#                     'dateTime': (new_start_dt.isoformat() if new_start_dt else "") if is_rescheduling else (start_dt.isoformat() if start_dt else ""),
#                     'timeZone': 'America/Toronto',
#                 },
#                 'end': {
#                     'dateTime': (new_end_dt.isoformat() if new_end_dt else "" ) if is_rescheduling else (new_end_dt.isoformat() if new_end_dt else ""),
#                     'timeZone': 'America/Toronto',
#                 },
#                 'conferenceData': {
#                     'createRequest': {
#                         'requestId': str(uuid.uuid4()),
#                         'conferenceSolutionKey': {'type': 'hangoutsMeet'}
#                     }
#                 }
#             }
#             created_event = service.events().insert(calendarId=GMAIL_ACCOUNT, body=event).execute()
#         except Exception as e:
#             print(f"Failed to create google calendar: {str(e)}")
#             pass

#         # 4. Create Calendar Render URL for patient
#         # Create RENDER LINK STRING
#         params = {
#             'action': 'TEMPLATE',
#             'text': f"Rescheduled: {appointment_type} Dental Clinic" if is_rescheduling else f"{appointment_type} Dental Clinic",
#             'details': f"Patient: {patient_name}\nPhone: {customer_number}\nType: {appointment_type} Dental Clinic\nDentist:{dentist_name}\nContact:{GMAIL_ACCOUNT}",
#             'dates': f"{new_start_str}/{new_end_str}" if is_rescheduling else f"{start_str}/{end_str}",
#             'ctz': 'America/Toronto',
#         }

#         # Use urllib.parse to safely encode the parameters
#         query_string = urllib.parse.urlencode(params)
#         base_url = 'https://www.google.com/calendar/render?'       
#         calendar_link = base_url + query_string 
#         short_url = shorten_url(calendar_link)

#         # Create Twilio SMS body
#         sms_body = f"Hello {patient_name}, your {appointment_type} appointment is scheduled. Click here to add it to your Google Calendar: {short_url}"
#         print(calendar_link)
#         print(sms_body)

#         client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
#         message = client.messages.create(
#             body=sms_body,
#             from_=TWILIO_PHONE_NUMBER,
#             to=customer_number
#         )
#         return jsonify({
#             "status": "success",
#             "sid": message.sid
#         })

#     except Exception as e:
#         print(f"Error happened: {str(e)}")
#         return jsonify({"status": "failure", "error": str(e)}), 500

@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=False)