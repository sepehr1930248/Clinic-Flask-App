from flask import Flask,Blueprint, abort, jsonify, render_template, request, redirect, url_for, flash
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


from doctor import doctor_bp


app = Flask(__name__)
app.secret_key = 'your_secret_key'  
app.register_blueprint(doctor_bp)
client = MongoClient('mongodb://localhost:27017/')
db = client['clinical_management']
patients_collection = db['patients']
appointments_collection = db['appointments']

patient_bp = Blueprint('patient', __name__)


@patient_bp.route('/patient/edit/<string:patient_id>', methods=['GET', 'POST'])
def edit_patient(patient_id):
    patient = patients_collection.find_one({'patient_id': patient_id})
    if request.method == 'POST':
        updated_data = {
            "name": request.form['name'],
            "phone": request.form['phone'],
            "birth_date": datetime.strptime(request.form['birth_date'], '%Y-%m-%d'),
            "doctor_name": request.form['doctor_name'],
            "expert_details": {
                "last_visit": datetime.strptime(request.form['last_visit'], '%Y-%m-%d') if request.form['last_visit'] else None,
                "therapy_method": request.form['therapy_method'],
                "medicine": request.form['medicine'],
                "notes": request.form['notes']
            }
        }
        patients_collection.update_one({'patient_id': patient_id}, {'$set': updated_data})
        flash('Patient updated successfully!', 'success')
        return redirect(url_for('home'))
    return render_template('edit_patient.html', patient=patient)


@patient_bp.route('/search')
@login_required
def search_patients():
    query = request.args.get('q', '').lower()
    filter_query = {
        'doctor_id': ObjectId(current_user.id),  # Add doctor_id filter
        '$or': [
            {'name': {'$regex': query, '$options': 'i'}},
            {'patient_id': {'$regex': query, '$options': 'i'}},
            {'doctor_name': {'$regex': query, '$options': 'i'}}
        ]
    }
    
    # Get filtered patients
    filtered_patients = list(patients_collection.find(filter_query))
    
    # Initialize default billing summary
    billing_summary = {
        'paid': {'total': 0, 'count': 0},
        'pending': {'total': 0, 'count': 0}
    }
    
    # Get billing stats
    billing_stats = db.billings.aggregate([
        {'$match': {'doctor_id': ObjectId(current_user.id)}},
        {'$group': {
            '_id': '$status',
            'total': {'$sum': '$amount'},
            'count': {'$sum': 1}
        }}
    ])
    
    # Update billing summary with actual data
    for item in billing_stats:
        if item['_id'] in ['paid', 'pending']:
            billing_summary[item['_id']] = {
                'total': item['total'],
                'count': item['count']
            }
    
    # Get today's appointments
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    today_appointments = list(appointments_collection.find({
        'doctor_id': ObjectId(current_user.id),
        'date': {
            '$gte': today,
            '$lt': tomorrow
        }
    }).sort('time', 1))
    
    # Get weekly appointments
    week_end = today + timedelta(days=7)
    weekly_appointments = list(appointments_collection.find({
        'doctor_id': ObjectId(current_user.id),
        'date': {
            '$gte': today,
            '$lt': week_end
        }
    }).sort([('date', 1), ('time', 1)]))
    
    # Format appointment times
    for appt in today_appointments:
        if isinstance(appt.get('time'), str):
            appt['formatted_time'] = appt['time']
        else:
            appt['formatted_time'] = appt['time'].strftime('%H:%M') if appt.get('time') else ''
            
    for appt in weekly_appointments:
        if isinstance(appt.get('time'), str):
            appt['formatted_time'] = appt['time']
        else:
            appt['formatted_time'] = appt['time'].strftime('%H:%M') if appt.get('time') else ''
        appt['formatted_date'] = appt['date'].strftime('%Y-%m-%d')
    
    return render_template('dashboard.html',
                         patients=filtered_patients,
                         billing_summary=billing_summary,
                         today_appointments=today_appointments,
                         weekly_appointments=weekly_appointments,
                         now=datetime.now())

@patient_bp.route('/add_patient', methods=['GET', 'POST'])
@login_required
def add_patient():
    # Fetch the list of doctors if the current user is an accountant
    doctors = []
    if current_user.role == 'accountant':
        # Include both name and _id fields
        doctors = list(db.doctors.find({}, {'name': 1, '_id': 1}))
   
    if request.method == 'POST':
        last_patient = patients_collection.find_one(
            {}, sort=[('patient_id', -1)]
        )
        if last_patient:
            last_num = int(last_patient['patient_id'][3:])
            new_id = f"PAT{last_num + 1:03d}"
        else:
            new_id = "PAT001"
       
        birth_date = datetime.strptime(request.form['birth_date'], '%Y-%m-%d')
        last_visit = datetime.strptime(request.form['last_visit'], '%Y-%m-%d') if request.form.get('last_visit') else datetime.now()
       
        # Handle doctor information based on user role
        if current_user.role == 'accountant':
            doctor_id = ObjectId(request.form['doctor_id'])
            # Fetch doctor name from database using the ID
            doctor = db.doctors.find_one({'_id': doctor_id})
            doctor_name = doctor['name'] if doctor else 'Unknown Doctor'
        else:
            doctor_id = ObjectId(current_user.id)
            doctor_name = current_user.name
       
        patient_data = {
            "patient_id": new_id,
            "name": request.form['name'],
            "phone": request.form['phone'],
            "birth_date": birth_date,
            "doctor_id": doctor_id,
            "doctor_name": doctor_name,
            "expert_details": {
                "last_visit": last_visit,
                "therapy_method": request.form['therapy_method'],
                "medicine": request.form['medicine'],
                "notes": request.form['notes']
            },
            "created_at": datetime.now()
        }
        patients_collection.insert_one(patient_data)
        flash('Patient added successfully!', 'success')
        return redirect(url_for('home'))
   
    return render_template('add_patient.html', doctors=doctors)


@patient_bp.route('/api/patients', methods=['GET'])
def get_patients():
    query = request.args.get('q', '').lower()
    filter_query = {
        '$or': [
            {'name': {'$regex': query, '$options': 'i'}},
            {'patient_id': {'$regex': query, '$options': 'i'}}
        ]
    } if query else {}
    patients = list(patients_collection.find(filter_query, {'_id': 0, 'patient_id': 1, 'name': 1}))
    return jsonify(patients)


@patient_bp.route('/patient/<string:patient_id>')
def view_patient(patient_id):
    try:
        patient = patients_collection.find_one({'patient_id': patient_id})
        if not patient:
            abort(404)
        patient.setdefault('visit_history', [])
        patient.setdefault('expert_details', {})
        patient.setdefault('birth_date', None)
        if patient['birth_date']:
            patient['birth_date'] = datetime.strptime(patient['birth_date'], '%Y-%m-%d') \
                if isinstance(patient['birth_date'], str) else patient['birth_date']
        for visit in patient['visit_history']:
            visit.setdefault('treatment', '')
            visit.setdefault('notes', '')
            if visit.get('date'):
                visit['date'] = parse_date(visit['date'])
        expert_details = patient['expert_details']
        expert_details.setdefault('notes', '')
        expert_details.setdefault('medicine', '')
        expert_details.setdefault('therapy_method', '')
        if expert_details.get('last_visit'):
            expert_details['last_visit'] = parse_date(expert_details['last_visit'])
        appointments = list(db.appointments.find({
            'patient_id': patient_id,
            'date': {'$gte': datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)}
        }).sort('date', 1))
        for appt in appointments:
            appt['_id'] = str(appt['_id'])
            if isinstance(appt['date'], str):
                appt['date'] = datetime.strptime(appt['date'], '%Y-%m-%d')
        return render_template('patient_details.html', 
                            patient=patient,
                            appointments=appointments)
    except Exception as e:
        app.logger.error(f"Error processing patient {patient_id}: {str(e)}")
        abort(500)

def parse_date(date_value):
    if isinstance(date_value, str):
        return datetime.strptime(date_value, '%Y-%m-%d')
    return date_value if isinstance(date_value, datetime) else None

@patient_bp.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@patient_bp.errorhandler(500)
def internal_error(error):
    return render_template('errors/500.html'), 500


