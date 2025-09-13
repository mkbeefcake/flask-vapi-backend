from flask import Blueprint, request, jsonify
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from datetime import datetime, timezone, timedelta
from dateutil import parser
from dateutil.tz import gettz
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
from dotenv import load_dotenv
from typing import Optional, Tuple, List, Dict
from collections import defaultdict
from zoneinfo import ZoneInfo
import pytz
import gspread
import os

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
GMAIL_ACCOUNT = os.getenv("GMAIL_ACCOUNT")
SPREAD_SHEET = os.getenv("SPREAD_SHEET")
SERVICE_TIME = int(os.getenv("SERVICE_TIME", 60))
ALDERSHOT_DENTURE_CLINIC = os.getenv("ALDERSHOT_DENTURE_CLINIC")

SERVICE_ACCOUNT_FILE = "vapi-dentist-book-222f512f966f.json"
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    "https://www.googleapis.com/auth/spreadsheets",     # full access to sheets
    "https://www.googleapis.com/auth/drive"             # sometimes needed for open_by_key/open
]


# Create a Blueprint for the extra routes
asbp = Blueprint("aldershot", __name__)


class BusinessHours:
    OPEN_HOUR = int(os.getenv("OPEN_HOUR", 9))
    CLOSE_HOUR = int(os.getenv("CLOSE_HOUR", 17))
    LUNCH_START = int(os.getenv("LUNCH_START", 12))
    LUNCH_END = int(os.getenv("LUNCH_END", 13))
    SLOT_DURATION = int(os.getenv("SERVICE_TIME", 60))


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

def get_sheet_service():
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    
    return gspread.authorize(credentials=credentials)


def validate_appointment_params(
    patient_name: str,
    patient_phone: str,
    service_type: str,
    dentist: str,
    appointment_date: str,
    referral: Optional[str] = None,
    insurance_name: Optional[str] = None
) -> Tuple[bool, str, Optional[datetime]]:
    """
    Validate all appointment parameters
    
    Returns:
    - Tuple[is_valid: bool, error_message: str, parsed_datetime: Optional[datetime]]
    """
    # Validate required fields are not empty
    if not all([patient_name, patient_phone, service_type, dentist, appointment_date]):
        return False, "Missing required fields", None

    # Validate phone number format (basic validation)
    if not patient_phone.startswith('+') or not patient_phone[1:].isdigit():
        return False, "Phone number must be in E.164 format (e.g., +12345678900)", None

    # Validate appointment date
    try:
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

def create_appointment_description(
    patient_name: str,
    patient_phone: str,
    service_type: str,
    dentist: str,
    referral: Optional[str] = None,
    insurance_name: Optional[str] = None
) -> str:
    """Create a formatted description for the calendar event"""
    description = f"""
Booking Information:
------------------
Patient: {patient_name}
Phone: {patient_phone}
Service: {service_type}
Dentist: {dentist}

"""
    if referral:
        description += f"Referral: {referral}\n"
    if insurance_name:
        description += f"Insurance: {insurance_name}\n"
    
    return description.strip()

def is_business_day(date: datetime) -> bool:
    """Check if the given date is a business day (Monday-Friday)"""
    return date.weekday() < 5  # Monday = 0, Friday = 4

def get_next_three_business_days(start_date: datetime) -> List[datetime]:
    """Get the next three business days from the given start date"""
    business_days = []
    current_date = start_date
    
    while len(business_days) < 3:
        if is_business_day(current_date):
            business_days.append(current_date)
        current_date += timedelta(days=1)
    
    return business_days

def get_time_slots(date: datetime) -> List[datetime]:
    """Generate all possible time slots for a given day"""
    slots = []
    current_time = date.replace(
        hour=BusinessHours.OPEN_HOUR,
        minute=0,
        second=0,
        microsecond=0
    )
    
    while current_time.hour < BusinessHours.CLOSE_HOUR:
        # Skip lunch hour
        if current_time.hour != BusinessHours.LUNCH_START:
            slots.append(current_time)
        # If we're at lunch start, jump to lunch end
        if current_time.hour == BusinessHours.LUNCH_START:
            current_time = current_time.replace(hour=BusinessHours.LUNCH_END)
        else:
            current_time += timedelta(minutes=BusinessHours.SLOT_DURATION)
    
    return slots

def format_time_slots(available_slots: Dict[str, List[datetime]]) -> str:
    """
    Convert available slots into format like "Thursday 9:00 am ~ 17:00 pm, Friday 11:00 am ~ 4:00 pm"
    """
    if not available_slots:
        return "No available slots found in the next 3 business days."
    
    # Group by day of week
    day_groups = defaultdict(list)
    for date, slots in available_slots.items():
        if slots:  # Only process days with available slots
            # Get first slot of the day to extract day name
            first_slot = slots[0]
            day_name = first_slot.strftime("%A")
            
            # Get min and max times for the day
            min_time = min(slots)
            max_time = max(slots) + timedelta(minutes=BusinessHours.SLOT_DURATION)  # Add duration to get end time
            
            # Format start and end times
            start_hour = min_time.hour
            end_hour = max_time.hour
            
            # Format start time
            if start_hour < 12:
                start_formatted = f"{start_hour}:00 am"
            elif start_hour == 12:
                start_formatted = "12:00 pm"
            else:
                start_formatted = f"{start_hour - 12}:00 pm"
                
            # Format end time
            # For end times, decide whether to use 12-hour or 24-hour format
            if end_hour < 12:
                end_formatted = f"{end_hour}:00 am"
            elif end_hour == 12:
                end_formatted = "12:00 pm"
            elif end_hour <= 17:  # Up to 5 PM, use 12-hour format
                end_formatted = f"{end_hour - 12}:00 pm"
            else:  # After 5 PM, use 24-hour format
                end_formatted = f"{end_hour}:00 pm"
            
            # Remove leading zeros
            start_formatted = start_formatted.replace(" 0", " ")
            end_formatted = end_formatted.replace(" 0", " ")
            
            day_groups[day_name] = {
                'start': start_formatted,
                'end': end_formatted
            }
    
    if not day_groups:
        return "No available slots"
    
    # Convert to final format
    formatted_days = []
    for day, times in day_groups.items():
        formatted_days.append(f"{day} {times['start']} ~ {times['end']}")
    
    return ", ".join(formatted_days)


def extract_event_details(event: dict) -> dict:
    """
    Extract detailed information from a Google Calendar event
    
    Parameters:
    - event: The Google Calendar event object
    
    Returns:
    - Dictionary containing parsed event details
    """
    try:
        # Parse the description field to extract patient information
        description = event.get('description', '')
        description_lines = description.split('\n')
        
        # Initialize details dictionary with default values
        details = {
            'event_id': event.get('id'),
            'summary': event.get('summary', ''),
            'patient_name': '',
            'patient_phone': '',
            'service_type': '',
            'dentist': '',
            'referral': '',
            'insurance_name': '',
            'location': event.get('location', ''),
            'start_time': '',
            'end_time': '',
            'created_at': event.get('created', ''),
            'last_updated': event.get('updated', ''),
            'status': event.get('status', ''),
            'creator': event.get('creator', {}).get('email', ''),
            'organizer': event.get('organizer', {}).get('email', ''),
        }

        # Parse description lines to extract information
        for line in description_lines:
            line = line.strip()
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if 'Patient' in key:
                    details['patient_name'] = value
                elif 'Phone' in key:
                    details['patient_phone'] = value
                elif 'Service' in key:
                    details['service_type'] = value
                elif 'Dentist' in key:
                    details['dentist'] = value
                elif 'Referral' in key:
                    details['referral'] = value
                elif 'Insurance' in key:
                    details['insurance_name'] = value

        # Parse and format time information
        if 'start' in event:
            start_dt = parser.parse(event['start'].get('dateTime', event['start'].get('date')))
            details['start_time'] = start_dt.astimezone(pytz.timezone('America/Toronto')).strftime('%Y-%m-%d %I:%M %p %Z')

        if 'end' in event:
            end_dt = parser.parse(event['end'].get('dateTime', event['end'].get('date')))
            details['end_time'] = end_dt.astimezone(pytz.timezone('America/Toronto')).strftime('%Y-%m-%d %I:%M %p %Z')

        # Calculate appointment duration
        if 'start' in event and 'end' in event:
            start_dt = parser.parse(event['start'].get('dateTime', event['start'].get('date')))
            end_dt = parser.parse(event['end'].get('dateTime', event['end'].get('date')))
            duration = end_dt - start_dt
            details['duration_minutes'] = int(duration.total_seconds() / 60)

        # Get conference details if any
        if 'conferenceData' in event:
            conf_data = event['conferenceData']
            details['conference_link'] = conf_data.get('entryPoints', [{}])[0].get('uri', '')
            details['conference_type'] = conf_data.get('conferenceSolution', {}).get('name', '')

        # Get attachment information if any
        if 'attachments' in event:
            details['attachments'] = [
                {
                    'title': attachment.get('title', ''),
                    'file_url': attachment.get('fileUrl', '')
                }
                for attachment in event['attachments']
            ]

        # Get reminder settings
        if 'reminders' in event:
            details['reminders'] = event['reminders'].get('overrides', [])

        # Get recurrence information if any
        if 'recurrence' in event:
            details['recurrence_rule'] = event['recurrence']

        # Get color information
        if 'colorId' in event:
            details['color_id'] = event['colorId']

        return details

    except Exception as e:
        # Log parsing error but return what we have
        print(f"Error parsing event details: {str(e)}")
        return details

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
        
        # 1. Create Google Calendar Event
        # 
        existing_event_detail = {}
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
                existing_event_detail = extract_event_details(matching_event)
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

        # 2. Update the Google Spreedsheet in Clinic's gmail account
        # 
        now_toronto = datetime.now(ZoneInfo("America/Toronto"))
        current_datetime = now_toronto.strftime("%Y-%m-%d %H:%M:%S %Z")

        try:
            spread_client = get_sheet_service()
            spreadsheet = spread_client.open(SPREAD_SHEET)
            sheet = spreadsheet.sheet1 
            sheet.append_row(["@Cancel", 
                              existing_event_detail['service_type'] if 'service_type' in existing_event_detail else "", 
                              patient_name, 
                              patient_phone, 
                              "", 
                              "", 
                              "", 
                              "",
                              existing_event_detail['start_time'] if 'start_time' in existing_event_detail else "", 
                              current_datetime])
    
            pass
        except Exception as e:
            print(f"Failed to open spreadsheet: {str(e)}")
            pass


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

        print(f"@cancel: SMS sent, {str(sms_result)}")
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
        
        existing_event_detail = {}
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

            existing_event_detail = extract_event_details(existing_event)

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

        # 2. Update the Google Spreedsheet in Clinic's gmail account
        # 
        now_toronto = datetime.now(ZoneInfo("America/Toronto"))
        current_datetime = now_toronto.strftime("%Y-%m-%d %H:%M:%S %Z")

        try:
            spread_client = get_sheet_service()
            spreadsheet = spread_client.open(SPREAD_SHEET)
            sheet = spreadsheet.sheet1 
            sheet.append_row(["@Reschedule", 
                              existing_event_detail['service_type'] if 'service_type' in existing_event_detail else "", 
                              patient_name, 
                              patient_phone, 
                              "", 
                              "", 
                              "", 
                              new_appointment_dt.isoformat(), 
                              existing_event_detail['start_time'] if 'start_time' in existing_event_detail else "", 
                              current_datetime])
    
            pass
        except Exception as e:
            print(f"Failed to open spreadsheet: {str(e)}")
            pass

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
        calendar_id = GMAIL_ACCOUNT  # or your specific calendar ID
        
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
    try:
        # Get request data
        data = request.get_json()
        
        # Extract required and optional parameters
        patient_name = data.get('patient_name')
        patient_phone = data.get('patient_phone')
        service_type = data.get('service_type')
        dentist = data.get('dentist')
        appointment_date = data.get('appointment_date')
        referral = data.get('referral')
        insurance_name = data.get('insurance_name')

        # Validate parameters
        is_valid, error_message, appointment_dt = validate_appointment_params(
            patient_name=patient_name,
            patient_phone=patient_phone,
            service_type=service_type,
            dentist=dentist,
            appointment_date=appointment_date,
            referral=referral,
            insurance_name=insurance_name
        )

        if not is_valid:
            return {"booking_status": f"error: {error_message}"}, 400

        # Initialize the Calendar API service
        service = get_calendar_service()
        calendar_id = GMAIL_ACCOUNT  # or your specific calendar ID

        # Calculate event end time (default to 1 hour unless specified by service type)
        duration_minutes = SERVICE_TIME
        end_time = appointment_dt + timedelta(minutes=duration_minutes)

        # Create event description
        description = create_appointment_description(
            patient_name=patient_name,
            patient_phone=patient_phone,
            service_type=service_type,
            dentist=dentist,
            referral=referral,
            insurance_name=insurance_name
        )

        # Create calendar event
        event = {
            'summary': f"{service_type} - {patient_name}",
            'location': ALDERSHOT_DENTURE_CLINIC,
            'description': description,
            'start': {
                'dateTime': appointment_dt.isoformat(),
                'timeZone': 'America/Toronto',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'America/Toronto',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},  # 24 hours
                    {'method': 'popup', 'minutes': 60},       # 1 hour
                ],
            },
        }

        try:
            event = service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()

            # 2. Update the Google Spreedsheet in Clinic's gmail account
            # 
            now_toronto = datetime.now(ZoneInfo("America/Toronto"))
            current_datetime = now_toronto.strftime("%Y-%m-%d %H:%M:%S %Z")

            try:
                spread_client = get_sheet_service()
                spreadsheet = spread_client.open(SPREAD_SHEET)
                sheet = spreadsheet.sheet1 
                sheet.append_row(["@Book", 
                                  service_type, 
                                  patient_name, 
                                  patient_phone,
                                  referral, 
                                  dentist, 
                                  insurance_name, 
                                  appointment_dt.isoformat(), 
                                  "", 
                                  current_datetime])
        
                pass
            except Exception as e:
                print(f"Failed to open spreadsheet: {str(e)}")
                pass


            # Send confirmation SMS
            sms_result = send_sms_notification(
                to_number=patient_phone,
                message_body=(
                    f"Hello {patient_name}, "
                    f"Your {service_type} appointment has been scheduled for "
                    f"{appointment_dt.strftime('%B %d, %Y at %I:%M %p')} "
                    f"with Dr. {dentist}. "
                    "Please arrive 10 minutes early. "
                    "If you need to reschedule, please contact our office."
                )
            )

            return {"booking_status": "success"}

        except Exception as calendar_error:
            return {"booking_status": f"error : {str(calendar_error)}"}, 500

    except Exception as e:
        return {"booking_status": f"error : {str(e)}"}, 500

@asbp.route("/get_available", methods=['GET'])
def get_available():
    try:
        # Get and validate dentist parameter
        dentist = request.args.get('dentist')
        if not dentist:
            dentist = ""

        # Initialize calendar service
        service = get_calendar_service()
        calendar_id = GMAIL_ACCOUNT  # or specific calendar ID
        
        # Get Toronto timezone
        toronto_tz = pytz.timezone('America/Toronto')
        now = datetime.now(toronto_tz)
        
        # Get next three business days
        business_days = get_next_three_business_days(now)
        
        # Calculate time range for calendar query
        time_min = now.isoformat()
        time_max = (business_days[-1].replace(
            hour=BusinessHours.CLOSE_HOUR,
            minute=0,
            second=0,
            microsecond=0
        ) + timedelta(minutes=BusinessHours.SLOT_DURATION)).isoformat()
        
        try:
            # Get existing events for the dentist
            events_result = service.events().list(
                calendarId=calendar_id,
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            # Filter events for the specified dentist
            busy_slots = []
            for event in events_result.get('items', []):
                description = event.get('description', '').lower()
                if f"dentist: {dentist.lower()}" in description:
                    start = parser.parse(event['start']['dateTime'])
                    end = parser.parse(event['end']['dateTime'])
                    busy_slots.append((start, end))
            
            # Calculate available slots for each business day
            available_slots = defaultdict(list)
            
            for day in business_days:
                # Get all possible time slots for the day
                day_slots = get_time_slots(day)
                
                # Remove slots that are in the past
                if day.date() == now.date():
                    day_slots = [slot for slot in day_slots if slot > now]
                
                # Check each slot against busy periods
                for slot in day_slots:
                    slot_end = slot + timedelta(minutes=BusinessHours.SLOT_DURATION)
                    is_available = True
                    
                    for busy_start, busy_end in busy_slots:
                        if (slot < busy_end and slot_end > busy_start):
                            is_available = False
                            break
                    
                    if is_available:
                        date_key = slot.strftime("%A, %B %d, %Y")
                        available_slots[date_key].append(slot)
            
            # Format the response
            formatted_slots = format_time_slots(available_slots)
            
            # Create detailed response
            response = {
                "available_dates": "success",
                "details": {
                    date: [slot.strftime("%I:%M %p") for slot in slots]
                    for date, slots in available_slots.items()
                }
            }
            
            return jsonify(response)
            
        except Exception as calendar_error:
            return jsonify({
                "status": "error",
                "message": f"Error accessing calendar: {str(calendar_error)}"
            }), 500
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"Server error: {str(e)}"
        }), 500

    return {"available_dates": "Thursday, Friday 11:00 am ~ 4:00pm"}
