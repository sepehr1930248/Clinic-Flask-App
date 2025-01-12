from flask import Flask, Blueprint,abort, jsonify, render_template, request, redirect, url_for, flash
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

from schedule import schedule_bp
from patient import patient_bp
from doctor import doctor_bp



app = Flask(__name__)
app.secret_key = 'your_secret_key'  
app.register_blueprint(doctor_bp)
client = MongoClient('mongodb://localhost:27017/')
db = client['clinical_management']
patients_collection = db['patients']
appointments_collection = db['appointments']

appointment_bp = Blueprint('appointment', __name__)



@appointment_bp.route('/api/appointment/<appointment_id>')
def get_appointment(appointment_id):
    try:
        appointment = db.appointments.find_one({'_id': ObjectId(appointment_id)})
        if appointment:
            appointment['_id'] = str(appointment['_id'])
            appointment['date'] = appointment['date'].strftime('%Y-%m-%d')
            return jsonify({'status': 'success', 'appointment': appointment})
        return jsonify({'status': 'error', 'message': 'Appointment not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@appointment_bp.route('/appointment/edit/<appointment_id>', methods=['POST'])
def edit_appointment(appointment_id):
    try:
        patient = patients_collection.find_one({'patient_id': request.form['patient_id']})
        doctor_name = patient.get('doctor_name', '') if patient else ''
        update_data = {
            'patient_id': request.form['patient_id'],
            'date': datetime.strptime(request.form['date'], '%Y-%m-%d'),
            'time': request.form['time'],
            'duration': int(request.form['duration']),
            'doctor_name': doctor_name,
            'notes': request.form.get('notes', '')
        }
        result = db.appointments.update_one(
            {'_id': ObjectId(appointment_id)},
            {'$set': update_data}
        )
        if result.modified_count:
            flash('Appointment updated successfully!', 'success')
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error', 'message': 'Appointment not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@appointment_bp.route('/appointment/delete/<appointment_id>', methods=['POST'])
def delete_appointment(appointment_id):
    try:
        result = db.appointments.delete_one({'_id': ObjectId(appointment_id)})
        if result.deleted_count:
            flash('Appointment deleted successfully!', 'success')
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error', 'message': 'Appointment not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400


@appointment_bp.route('/appointment/add', methods=['POST'])
@login_required
def add_appointment():
    try:
        patient_id = request.form.get('patient_id')
        if not patients_collection.find_one({'patient_id': patient_id}):
            return jsonify({'status': 'error', 'message': 'Patient not found'}), 400
        appointment_data = {
            'patient_id': patient_id,
            'date': datetime.strptime(request.form['date'], '%Y-%m-%d'),
            'time': request.form['time'],
            'duration': int(request.form['duration']),
            'doctor_id': ObjectId(current_user.id),  
            'doctor_name': current_user.name,
            'notes': request.form.get('notes', '')
        }
        result = db.appointments.insert_one(appointment_data)
        return jsonify({'status': 'success', 'id': str(result.inserted_id)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400
