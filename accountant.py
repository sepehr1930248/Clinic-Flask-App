from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime

accountant_bp = Blueprint('accountant', __name__)
client = MongoClient('mongodb://localhost:27017/')
db = client['clinical_management']

class Accountant(UserMixin):
    def __init__(self, accountant_data):
        self.id = str(accountant_data['_id'])
        self.email = accountant_data['email']
        self.name = accountant_data['name']
        self.role = 'accountant'

@accountant_bp.route('/api/patients/<doctor_id>')
@login_required
def get_patients_by_doctor(doctor_id):
    if not hasattr(current_user, 'role') or current_user.role != 'accountant':
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 403
    
    try:
        doctor_obj_id = ObjectId(doctor_id)
        patients = list(db.patients.find({'doctor_id': doctor_obj_id}, 
                                       {'name': 1, 'patient_id': 1, '_id': 0}))
        return jsonify({'status': 'success', 'patients': patients})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@accountant_bp.route('/accountant/dashboard')
@login_required
def dashboard():
    # Check if the user is an accountant
    if not hasattr(current_user, 'role') or current_user.role != 'accountant':
        flash('Unauthorized access', 'error')
        return redirect(url_for('login'))

    # Fetch the accountant's status from the database
    accountant = db.accountants.find_one({'_id': ObjectId(current_user.id)})
    if not accountant or accountant.get('status') != 'approved':
        flash('Your access is pending approval from the manager.', 'warning')
        return redirect(url_for('accountant.pending_approval'))

    # Fetch doctors and appointments for the dashboard
    doctors = list(db.doctors.find({}, {'name': 1, '_id': 1}))
    appointments = list(db.appointments.aggregate([
        {
            '$match': {
                'date': {'$gte': datetime.now()}
            }
        },
        {
            '$lookup': {
                'from': 'patients',
                'localField': 'patient_id',
                'foreignField': 'patient_id',
                'as': 'patient_info'
            }
        },
        {
            '$addFields': {
                'patient_name': {'$arrayElemAt': ['$patient_info.name', 0]}
            }
        },
        {
            '$sort': {'date': 1}
        }
    ]))

    return render_template('accountantDashboard.html', 
                         doctors=doctors,
                         appointments=appointments)

@accountant_bp.route('/accountant/pending_approval')
@login_required
def pending_approval():
    # Check if the user is an accountant
    if not hasattr(current_user, 'role') or current_user.role != 'accountant':
        flash('Unauthorized access', 'error')
        return redirect(url_for('login'))

    return render_template('pending_approval.html')

@accountant_bp.route('/accountant/schedule', methods=['POST'])
@login_required
def schedule_appointment():
    if not hasattr(current_user, 'role') or current_user.role != 'accountant':
        return {'status': 'error', 'message': 'Unauthorized'}, 403
        
    try:
        appointment_data = {
            'patient_id': request.form['patient_id'],
            'doctor_id': ObjectId(request.form['doctor_id']),
            'date': datetime.strptime(request.form['date'], '%Y-%m-%d'),
            'time': request.form['time'],
            'duration': int(request.form['duration']),
            'notes': request.form.get('notes', '')
        }
        
        # Get doctor name
        doctor = db.doctors.find_one({'_id': appointment_data['doctor_id']})
        if doctor:
            appointment_data['doctor_name'] = doctor['name']
            
        # Get patient name
        patient = db.patients.find_one({'patient_id': appointment_data['patient_id']})
        if patient:
            appointment_data['patient_name'] = patient['name']
        
        db.appointments.insert_one(appointment_data)
        flash('Appointment scheduled successfully!', 'success')
        return redirect(url_for('accountant.dashboard'))
    except Exception as e:
        flash(f'Error scheduling appointment: {str(e)}', 'error')
        return redirect(url_for('accountant.dashboard'))