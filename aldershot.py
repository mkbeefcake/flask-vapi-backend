from flask import Blueprint, request, jsonify
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
import os
from datetime import datetime, timezone
from dateutil import parser
from dateutil.tz import gettz
import pytz
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from dotenv import load_dotenv

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
GMAIL_ACCOUNT = os.getenv("GMAIL_ACCOUNT")
SPREAD_SHEET = os.getenv("SPREAD_SHEET")

SERVICE_ACCOUNT_FILE = "vapi-dentist-book-222f512f966f.json"
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    "https://www.googleapis.com/auth/spreadsheets",     # full access to sheets
    "https://www.googleapis.com/auth/drive"             # sometimes needed for open_by_key/open
]


# Create a Blueprint for the extra routes
asbp = Blueprint("aldershot", __name__)

def send_sms_notification(to_number: str, message_body: str, from_number: str = None) -> dict:
    """
    Send SMS notification using Twilio
    
    Parameters:
    - to_number (str): Recipient's phone number in E.164 format (e.g., '+1234567890')
    - message_body (str): The message content to send
    - from_number (str, optional): Sender's Twilio phone number. If None, uses default from env
    
    Returns:
    - dict: Contains status and details of the SMS sending attempt
        {
            'success': bool,
            'message': str,
            'sid': str,  # Only included if successful
            'error_code': str,  # Only included if failed
        }
    """
    try:
        # Get Twilio credentials from environment variables
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        default_from = os.getenv('TWILIO_PHONE_NUMBER')

        # Validate required credentials
        if not all([account_sid, auth_token]):
            return {
                'success': False,
                'message': 'Twilio credentials not properly configured',
                'error_code': 'MISSING_CREDENTIALS'
            }

        # Use provided from_number or fall back to default
        sender = from_number or default_from
        if not sender:
            return {
                'success': False,
                'message': 'No sender phone number provided or configured',
                'error_code': 'MISSING_SENDER'
            }

        # Initialize Twilio client
        client = Client(account_sid, auth_token)

        # Send message
        message = client.messages.create(
            body=message_body,
            from_=sender,
            to=to_number
        )

        return {
            'success': True,
            'message': 'SMS sent successfully',
            'sid': message.sid
        }

    except TwilioRestException as e:
        return {
            'success': False,
            'message': f'Twilio error: {str(e)}',
            'error_code': e.code
        }
    except Exception as e:
        return {
            'success': False,
            'message': f'Unexpected error: {str(e)}',
            'error_code': 'UNKNOWN_ERROR'
        }

def validate_appointment_time(appointment_date: str) -> tuple[bool, str, datetime]:
    """
    Validate the appointment time format and ensure it's in the future
    
    Parameters:
    - appointment_date: ISO 8601 format string in America/Toronto timezone
    
    Returns:
    - tuple: (is_valid: bool, error_message: str, parsed_datetime: datetime)
    """
    try:
        # Parse the appointment date
        toronto_tz = gettz('America/Toronto')
        appointment_dt = parser.parse(appointment_date)
        
        # If timezone not specified, assume Toronto time
        if appointment_dt.tzinfo is None:
            appointment_dt = appointment_dt.replace(tzinfo=toronto_tz)
        else:
            # Convert to Toronto time if in different timezone
            appointment_dt = appointment_dt.astimezone(toronto_tz)
            
        # Check if appointment is in the future
        now = datetime.now(toronto_tz)
        if appointment_dt <= now:
            return False, "Appointment time must be in the future", None
            
        return True, "", appointment_dt
        
    except ValueError:
        return False, "Invalid date format. Please use ISO 8601 format.", None

def format_appointment_time(iso_time_str: str) -> str:
    """Convert ISO time string to human-readable format in Toronto timezone"""
    toronto_tz = pytz.timezone('America/Toronto')
    dt = parser.parse(iso_time_str)
    toronto_time = dt.astimezone(toronto_tz)
    return toronto_time.strftime("%B %d, %Y at %I:%M %p %Z")

def get_calendar_service():
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    
    return build('calendar', 'v3', credentials=credentials)


@asbp.route("/cancel", methods=['POST'])
def cancel():
    try:
        data = request.get_json()
        patient_name = data.get('patient_name')
        patient_phone = data.get('patient_phone')

        print(f"@cancel: patient name: {patient_name}, number: {patient_phone}")
        
        if not patient_name or not patient_phone:
            return {
                "cancel_appointment_statusmessage": "error: patient name or phone number is not indicated",
            }, 400

        # Initialize the Calendar API service
        service = get_calendar_service()
        
        # Get the calendar ID (use 'primary' for primary calendar)
        calendar_id = GMAIL_ACCOUNT  # or your specific calendar ID
        
        # Get current time in ISO format
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            # Get all events from now
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=now,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            events = events_result.get('items', [])
            
            matching_event = None
            
            # Search through events to find matching patient
            for event in events:
                description = event.get('description', '').lower()
                if (patient_name.lower() in description and 
                    patient_phone in description):
                    matching_event = event
                    break
            
            if matching_event:
                # Cancel the event
                service.events().delete(
                    calendarId=calendar_id,
                    eventId=matching_event['id']
                ).execute()
                
            else:
                return {
                    "cancel_appointment_statusmessage": f"error: No active appointment found for {patient_name} with phone {patient_phone}"
                }, 404
                
        except Exception as calendar_error:
            return {
                "cancel_appointment_statusmessage": f"error: Error accessing calendar: {str(calendar_error)}"
            }, 500

        print(f"@cancel: delete calendar event")

        # Send cancellation confirmation SMS
        sms_result = send_sms_notification(
            to_number=patient_phone,
            message_body=(
                f"Hello {patient_name}, "
                "Your appointment has been cancelled successfully. "
                "Thank you for letting us know. "
                "For any questions, please contact our office."
            )
        )

        print(f"@cancel: SMS sent")
        return {"cancel_appointment_statusmessage": "success"}
    except Exception as e:
        return {"cancel_appointment_statusmessage": f"error : {str(e)}"}

@asbp.route("/reschedule", methods=['POST'])
def reschedule():
    try:
        # Get and validate required parameters
        data = request.get_json()
        patient_name = data.get('patient_name')
        patient_phone = data.get('patient_phone')
        appointment_date = data.get('appointment_date')
        
        print(f"@reschedule: patient name: {patient_name}, number: {patient_phone}, appointment date: {appointment_date}")

        if not all([patient_name, patient_phone, appointment_date]):
            return {
                "rescheduling_appointment_status": "error: patient name or phone number or appointment_date is not indicated",
            }, 400

        # Validate appointment time
        is_valid, error_message, new_appointment_dt = validate_appointment_time(appointment_date)
        if not is_valid:
            return {
                "rescheduling_appointment_status": "error: appintment date is not ISO format",
            }, 400

        # Initialize the Calendar API service
        service = get_calendar_service()
        calendar_id = GMAIL_ACCOUNT  # or your specific calendar ID
        
        # Get current time in ISO format
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            # Find existing appointment
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=now,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            existing_event = None
            for event in events_result.get('items', []):
                description = event.get('description', '').lower()
                if (patient_name.lower() in description and 
                    patient_phone in description):
                    existing_event = event
                    break
            
            if not existing_event:
                return {
                    "rescheduling_appointment_status": f"error: No active appointment found for {patient_name} with phone {patient_phone}"
                }, 404

            print(f"@reschedule: found previous record")

            # Calculate new event end time (assume same duration as original appointment)
            original_start = parser.parse(existing_event['start']['dateTime'])
            original_end = parser.parse(existing_event['end']['dateTime'])
            duration = original_end - original_start
            new_end_dt = new_appointment_dt + duration
            
            # Create new event object with updated times
            updated_event = existing_event.copy()
            updated_event['start']['dateTime'] = new_appointment_dt.isoformat()
            updated_event['end']['dateTime'] = new_end_dt.isoformat()
            
            # Update the event
            updated_event = service.events().update(
                calendarId=calendar_id,
                eventId=existing_event['id'],
                body=updated_event
            ).execute()
            
        except Exception as calendar_error:
            return {
                "rescheduling_appointment_status": f"error: couldn't reschedule calendar - {str(calendar_error)}",
            }, 400

        print(f"@reschedule: update existing calendar event")

        # Send SMS notification
        sms_result = send_sms_notification(
            to_number=patient_phone,
            message_body=(
                f"Hello {patient_name}, "
                f"Your appointment has been rescheduled to {new_appointment_dt.strftime('%B %d, %Y at %I:%M %p')} "
                "Toronto time. "
                "If you need to make any changes, please contact our office."
            )
        )

        print(f"@reschedule: SMS sent")

    except Exception as e:
        return {"rescheduling_appointment_status": f"error: {str(e)}"}

    return {"rescheduling_appointment_status": "success"}

@asbp.route("/find_existing", methods=['GET'])
def find_existing():
    try:
        # Get and validate required parameters
        patient_name = request.args.get('patient_name')
        patient_phone = request.args.get('patient_phone')
        
        print(f"@reschedule: patient name: {patient_name}, number: {patient_phone}")
        if not patient_name or not patient_phone:
            return {"existing_appointment_status": f"error: patient_name or patient_phone is not indicated"}

        # Initialize the Calendar API service
        service = get_calendar_service()
        calendar_id = 'primary'  # or your specific calendar ID
        
        # Get current time in ISO format
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            # Search for upcoming events
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=now,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            matching_appointments = []
            
            # Search through events to find matching patient
            for event in events_result.get('items', []):
                description = event.get('description', '').lower()
                if (patient_name.lower() in description and 
                    patient_phone in description):
                    
                    # Format appointment details
                    appointment_details = {
                        "summary": event.get('summary'),
                        "start_time": format_appointment_time(event['start']['dateTime']),
                        "end_time": format_appointment_time(event['end']['dateTime']),
                        "location": event.get('location', 'No location specified'),
                        "event_id": event['id'],
                        "raw_start": event['start']['dateTime'],  # Keep ISO format for sorting
                    }
                    matching_appointments.append(appointment_details)
            
            if matching_appointments:
                # Sort appointments by start time
                matching_appointments.sort(key=lambda x: x['raw_start'])
                print(f"@reschedule: found matched appointments")              
                
            else:
                return {"existing_appointment_status": "False"}
                
        except Exception as calendar_error:
            return {"existing_appointment_status": f"error: error accessing calendar {str(calendar_error)}"}, 500
            
    except Exception as e:
        return {"existing_appointment_status": f"error: {str(e)}"}

    return {"existing_appointment_status": "True"}

@asbp.route("/book", methods=['POST'])
def book():
    return {"booking_status": "success"}

@asbp.route("/get_available", methods=['GET'])
def get_available():
    return {"available_dates": "Thursday, Friday 11:00 am ~ 4:00pm"}
