from flask import Flask, Blueprint, abort, jsonify, render_template, request, redirect, url_for, flash
from datetime import datetime
from pymongo import MongoClient
from calendar import monthcalendar
from io import BytesIO
import pandas as pd
from flask import send_file
from datetime import datetime, timedelta
from bson import ObjectId
import logging
from bson import ObjectId
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from doctor import doctor_bp
app = Flask(__name__)
app.secret_key = 'your_secret_key'  
app.register_blueprint(doctor_bp)
client = MongoClient('mongodb://localhost:27017/')
db = client['clinical_management']
patients_collection = db['patients']
appointments_collection = db['appointments']
doctors_collection = db['doctors']

schedule_bp = Blueprint('schedule', __name__)

@schedule_bp.route('/schedule', methods=['GET', 'POST'])
@login_required
def schedule():
    if request.method == 'POST':
        try:
            appointment_date = datetime.strptime(request.form['date'], '%Y-%m-%d')
            appointment_time = request.form['time']
            
            # Handle doctor selection based on user role
            if current_user.role == 'accountant':
                doctor_id = ObjectId(request.form['doctor_id'])
                doctor = doctors_collection.find_one({'_id': doctor_id})
                doctor_name = doctor['name'] if doctor else 'Unknown Doctor'
            else:
                doctor_id = ObjectId(current_user.id)
                doctor_name = current_user.name
            
            appointment_data = {
                'patient_id': request.form['patient_id'],
                'date': appointment_date,
                'time': appointment_time,
                'formatted_time': appointment_time,
                'duration': int(request.form['duration']),
                'doctor_id': doctor_id,
                'doctor_name': doctor_name,
                'notes': request.form.get('notes', '')
            }
            
            appointments_collection.insert_one(appointment_data)
            flash('Appointment scheduled successfully!', 'success')
            return redirect(url_for('schedule.schedule', date=request.form['date']))
            
        except Exception as e:
            flash(f'Error scheduling appointment: {str(e)}', 'error')
            return redirect(url_for('schedule.schedule'))

    today = datetime.now()
    cal = monthcalendar(today.year, today.month)
    selected_date = request.args.get('date', today.strftime('%Y-%m-%d'))
    selected_datetime = datetime.strptime(selected_date, '%Y-%m-%d')
    next_day = selected_datetime + timedelta(days=1)

    # Query based on user role
    if current_user.role == 'accountant':
        # For accountants, get all doctors and their appointments
        doctors = list(doctors_collection.find())
        selected_doctor = request.args.get('doctor_id', None)
        
        if selected_doctor:
            appointments = list(appointments_collection.find({
                'doctor_id': ObjectId(selected_doctor),
                'date': {
                    '$gte': selected_datetime,
                    '$lt': next_day
                }
            }).sort('time', 1))
            # Get patients for selected doctor
            patients = list(patients_collection.find({'doctor_id': ObjectId(selected_doctor)}))
        else:
            # Show all appointments if no doctor is selected
            appointments = list(appointments_collection.find({
                'date': {
                    '$gte': selected_datetime,
                    '$lt': next_day
                }
            }).sort('time', 1))
            # Get all patients
            patients = list(patients_collection.find({}))
    else:
        # For doctors, show only their appointments and patients
        doctors = []
        appointments = list(appointments_collection.find({
            'doctor_id': ObjectId(current_user.id),
            'date': {
                '$gte': selected_datetime,
                '$lt': next_day
            }
        }).sort('time', 1))
        patients = list(patients_collection.find({'doctor_id': ObjectId(current_user.id)}))

    time_slots = []
    for hour in range(8, 20):  # 8 AM to 8 PM
        time_slots.append(f"{hour:02d}:00")
        time_slots.append(f"{hour:02d}:30")

    return render_template('schedule.html', 
                         calendar=cal,
                         time_slots=time_slots,
                         appointments=appointments,
                         patients=patients,
                         doctors=doctors,
                         selected_doctor=selected_doctor if current_user.role == 'accountant' else None,
                         selected_date=selected_date,
                         today=today,
                         user_role=current_user.role)

@schedule_bp.route('/api/patients/<doctor_id>')
@login_required
def get_patients(doctor_id):
    """API endpoint to get patients for a specific doctor"""
    if not ObjectId.is_valid(doctor_id):
        return jsonify({'error': 'Invalid doctor ID'}), 400

    patients = list(patients_collection.find({'doctor_id': ObjectId(doctor_id)}))
    # Convert ObjectId to string for JSON serialization
    for patient in patients:
        patient['_id'] = str(patient['_id'])
    
    return jsonify({'patients': patients})

@schedule_bp.route('/api/check-availability', methods=['POST'])
@login_required
def check_availability():
    """API endpoint to check doctor's availability for a specific time slot"""
    data = request.get_json()
    date = datetime.strptime(data['date'], '%Y-%m-%d')
    time = data['time']
    doctor_id = data.get('doctor_id', str(current_user.id))

    # Check for existing appointments
    existing = appointments_collection.find_one({
        'doctor_id': ObjectId(doctor_id),
        'date': date,
        'time': time
    })

    return jsonify({'available': not existing})