import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import pytz
from flask import Flask
import json

from aldershot import asbp, BusinessHours, format_time_slots

class TestAldershotEndpoints(unittest.TestCase):
    def setUp(self):
        """Set up test client and app context"""
        self.app = Flask(__name__)
        self.app.register_blueprint(asbp)
        self.client = self.app.test_client()
        self.toronto_tz = pytz.timezone('America/Toronto')

    def test_format_time_slots(self):
        """Test the time slot formatting function"""
        # Create test data with known times
        now = datetime.now(self.toronto_tz)
        thursday = now + timedelta(days=(3 - now.weekday()))  # Next Thursday
        friday = thursday + timedelta(days=1)

        test_slots = {
            thursday: [
                thursday.replace(hour=9, minute=0),
                thursday.replace(hour=16, minute=30)
            ],
            friday: [
                friday.replace(hour=11, minute=0),
                friday.replace(hour=15, minute=30)
            ]
        }

        expected_output = "Thursday 9:00 am ~ 17:00 pm, Friday 11:00 am ~ 4:00 pm"
        result = format_time_slots(test_slots)
        self.assertEqual(result, expected_output)

    @patch('aldershot.get_calendar_service')
    def test_get_available_success(self, mock_calendar_service):
        """Test successful retrieval of available slots"""
        # Mock calendar service response
        mock_events_result = {
            'items': [
                {
                    'description': 'dentist: Robert',
                    'start': {'dateTime': '2025-09-22T10:00:00-05:00'},
                    'end': {'dateTime': '2025-09-22T11:00:00-05:00'}
                }
            ]
        }
        
        mock_service = MagicMock()
        mock_service.events().list().execute.return_value = mock_events_result
        mock_calendar_service.return_value = mock_service

        # Make request
        response = self.client.get('/get_available?dentist=Robert')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('available_dates', data)
        self.assertEqual(data['dentist'], 'Robert')

    def test_get_available_missing_dentist(self):
        """Test get_available without dentist parameter"""
        response = self.client.get('/get_available')
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
        self.assertIn('Missing required parameter', data['message'])

    def test_get_available_invalid_dentist(self):
        """Test get_available with invalid dentist name"""
        response = self.client.get('/get_available?dentist=InvalidName')
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
        self.assertIn('Invalid dentist name', data['message'])

    @patch('aldershot.get_calendar_service')
    def test_book_appointment_success(self, mock_calendar_service):
        """Test successful appointment booking"""
        # Mock calendar service response
        mock_service = MagicMock()
        mock_service.events().insert().execute.return_value = {'id': 'test_event_id'}
        mock_calendar_service.return_value = mock_service

        # Test data
        appointment_data = {
            'patient_name': 'John Doe',
            'patient_phone': '+17125172528',
            'service_type': 'Complete Dentures',
            'dentist': 'Robert',
            'appointment_date': '2025-09-22T14:30:00-05:00',
            'referral': 'Dr. Smith',
            'insurance_name': 'TestInsurance'
        }

        response = self.client.post(
            '/book',
            data=json.dumps(appointment_data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('appointment_details', data)

    def test_book_appointment_missing_required_fields(self):
        """Test booking with missing required fields"""
        # Test data with missing fields
        appointment_data = {
            'patient_name': 'John Doe',
            # missing patient_phone
            'service_type': 'Complete Dentures',
            'dentist': 'Robert'
            # missing appointment_date
        }

        response = self.client.post(
            '/book',
            data=json.dumps(appointment_data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
        self.assertIn('Missing required fields', data['message'])

    @patch('aldershot.get_calendar_service')
    def test_reschedule_appointment_success(self, mock_calendar_service):
        """Test successful appointment rescheduling"""
        # Mock calendar service responses
        mock_events_result = {
            'items': [
                {
                    'id': 'test_event_id',
                    'description': 'Patient Name: John Doe\nPhone: +17125172528',
                    'start': {'dateTime': '2025-09-22T10:00:00-05:00'},
                    'end': {'dateTime': '2025-09-22T11:00:00-05:00'}
                }
            ]
        }
        
        mock_service = MagicMock()
        mock_service.events().list().execute.return_value = mock_events_result
        mock_service.events().update().execute.return_value = {'id': 'test_event_id'}
        mock_calendar_service.return_value = mock_service

        reschedule_data = {
            'patient_name': 'John Doe',
            'patient_phone': '+17125172528',
            'appointment_date': '2025-09-23T14:30:00-05:00'
        }

        response = self.client.post(
            '/reschedule',
            data=json.dumps(reschedule_data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')

    @patch('aldershot.get_calendar_service')
    def test_find_existing_appointment_success(self, mock_calendar_service):
        """Test successful finding of existing appointment"""
        # Mock calendar service response
        mock_events_result = {
            'items': [
                {
                    'id': 'test_event_id',
                    'description': 'Patient Name: John Doe\nPhone: +17125172528',
                    'start': {'dateTime': '2025-09-22T10:00:00-05:00'},
                    'end': {'dateTime': '2025-09-22T11:00:00-05:00'}
                }
            ]
        }
        
        mock_service = MagicMock()
        mock_service.events().list().execute.return_value = mock_events_result
        mock_calendar_service.return_value = mock_service

        response = self.client.get(
            '/find_existing?patient_name=John%20Doe&patient_phone=%2B17125172528'
        )
        
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertTrue(data['exists'])

    def test_calendar_service_error(self):
        """Test handling of calendar service errors"""
        with patch('aldershot.get_calendar_service') as mock_calendar_service:
            mock_calendar_service.side_effect = Exception('Calendar API Error')
            
            response = self.client.get('/get_available?dentist=Robert')
            self.assertEqual(response.status_code, 500)
            
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'error')
            self.assertIn('Error accessing calendar', data['message'])

    def test_business_hours_validation(self):
        """Test business hours constraints"""
        appointment_data = {
            'patient_name': 'John Doe',
            'patient_phone': '+17125172528',
            'service_type': 'Complete Dentures',
            'dentist': 'Robert',
            'appointment_date': '2025-09-22T18:00:00-05:00'  # After business hours
        }

        response = self.client.post(
            '/book',
            data=json.dumps(appointment_data),
            content_type='application/json'
        )
        
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'error')
        self.assertIn('outside business hours', data['message'].lower())

if __name__ == '__main__':
    unittest.main()