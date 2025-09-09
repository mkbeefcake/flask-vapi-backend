from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import date
import dateparser

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route("/book_dentist", methods=['POST'])
def book_dentist():
    data = request.json()
    if not data:
        return jsonify(status="Invalid or missing parameters", data=[])
    
    customer_number = data.get("customer_number")
    patient_name = data.get('patient_name')
    appointment_type = data.get("appointment_type")
    customer_type = data.get("customer_type")
    appointment_datetime = data.get("appointment_datetime")



    pass


if __name__ == '__main__':
    app.run(debug=False)