from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from datetime import datetime, timedelta
from bson import ObjectId
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

# Create Blueprint
doctor_bp = Blueprint('doctor', __name__)

# Database connection
client = MongoClient('mongodb://localhost:27017/')
db = client['clinical_management']



# doctor.py modifications
from flask_login import login_required, current_user

@doctor_bp.route('/doctor/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        update_data = {
            'name': request.form['name'],
            'specialization': request.form['specialization'],
            'email': request.form['email']
        }
        if request.form.get('new_password'):
            update_data['password'] = generate_password_hash(request.form['new_password'])
            
        db.doctors.update_one(
            {'_id': ObjectId(current_user.id)},
            {'$set': update_data}
        )
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('doctor.profile'))
    
    doctor = db.doctors.find_one({'_id': ObjectId(current_user.id)})
    return render_template('doctor/profile.html', doctor=doctor)

# Update existing routes to include doctor authentication
@doctor_bp.route('/doctor/treatments', methods=['GET', 'POST'])
@login_required
def manage_treatments():
    if request.method == 'POST':
        treatment_data = {
            'name': request.form['name'],
            'description': request.form['description'],
            'price': float(request.form['price']),
            'duration': int(request.form['duration']),
            'doctor_id': ObjectId(current_user.id),
            'created_at': datetime.now()
        }
        db.treatments.insert_one(treatment_data)
        flash('Treatment added successfully!', 'success')
        return redirect(url_for('doctor.manage_treatments'))
    
    treatments = list(db.treatments.find({'doctor_id': ObjectId(current_user.id)}))
    return render_template('doctor/treatments.html', treatments=treatments)

@doctor_bp.route('/doctor/treatment/<treatment_id>', methods=['PUT', 'DELETE'])
def handle_treatment(treatment_id):
    if request.method == 'PUT':
        updated_data = request.get_json()
        db.treatments.update_one(
            {'_id': ObjectId(treatment_id)},
            {'$set': {
                'name': updated_data['name'],
                'description': updated_data['description'],
                'price': float(updated_data['price']),
                'duration': int(updated_data['duration'])
            }}
        )
        return jsonify({'status': 'success'})
    
    elif request.method == 'DELETE':
        db.treatments.delete_one({'_id': ObjectId(treatment_id)})
        return jsonify({'status': 'success'})

# Flask route modifications
@doctor_bp.route('/doctor/prescription/<patient_id>', methods=['GET', 'POST'])
def manage_prescription(patient_id):
    if request.method == 'POST':
        prescription_data = {
            'patient_id': patient_id,
            'medicines': [
                {
                    'name': med['name'],
                    'dosage': med['dosage'],
                    'frequency': med['frequency'],
                    'duration': med['duration']
                }
                for med in request.get_json()['medicines']
            ],
            'notes': request.get_json().get('notes', ''),
            'prescribed_date': datetime.now(),
            'doctor_name': current_user.name,
            '_id': ObjectId()  # Explicitly add ObjectId
        }
        db.prescriptions.insert_one(prescription_data)

        return jsonify({'status': 'success'})
    
    # Convert ObjectId to string for each prescription
    prescriptions = list(db.prescriptions.find({'patient_id': patient_id}).sort('prescribed_date', -1))
    for prescription in prescriptions:
        prescription['_id'] = str(prescription['_id'])
        if isinstance(prescription['prescribed_date'], str):
            prescription['prescribed_date'] = datetime.strptime(
                prescription['prescribed_date'], 
                '%Y-%m-%dT%H:%M:%S'
            )
    
    patient = db.patients.find_one({'patient_id': patient_id})
    if patient:
        patient['_id'] = str(patient['_id'])
    
    return render_template(
        'doctor/prescription.html',
        prescriptions=prescriptions,
        patient=patient,
        datetime=datetime  # Pass datetime to template
    )

@doctor_bp.route('/doctor/appointments/<patient_id>', methods=['GET', 'POST'])
def manage_appointments(patient_id):
    if request.method == 'POST':
        appointment_data = {
            'patient_id': patient_id,
            'date': datetime.strptime(request.form['date'], '%Y-%m-%d'),
            'time': request.form['time'],
            'duration': int(request.form['duration']),
            'treatment_id': request.form.get('treatment_id'),
            'notes': request.form.get('notes', ''),
            'doctor_name': request.form['doctor_name'],
            'status': 'scheduled'
        }
        db.appointments.insert_one(appointment_data)
        
        # If there's a treatment, create a billing record
        if appointment_data.get('treatment_id'):
            treatment = db.treatments.find_one({'_id': ObjectId(appointment_data['treatment_id'])})
            if treatment:
                billing_data = {
                    'patient_id': patient_id,
                    'appointment_id': str(appointment_data['_id']),
                    'treatment_name': treatment['name'],
                    'amount': treatment['price'],
                    'status': 'pending',
                    'created_at': datetime.now()
                }
                db.billings.insert_one(billing_data)
        
        flash('Appointment scheduled successfully!', 'success')
        return redirect(url_for('doctor.manage_appointments', patient_id=patient_id))
    
    patient = db.patients.find_one({'patient_id': patient_id})
    appointments = list(db.appointments.find({'patient_id': patient_id}).sort('date', -1))
    treatments = list(db.treatments.find())
    return render_template('doctor/appointments.html', 
                         patient=patient, 
                         appointments=appointments,
                         treatments=treatments)

@doctor_bp.route('/doctor/billing/<patient_id>')
def view_billing(patient_id):
    billings = list(db.billings.find({'patient_id': patient_id}).sort('created_at', -1))
    patient = db.patients.find_one({'patient_id': patient_id})
    return render_template('doctor/billing.html', billings=billings, patient=patient)

@doctor_bp.route('/doctor/billing/add/<patient_id>', methods=['GET', 'POST'])
@login_required
def add_billing(patient_id):
    if request.method == 'POST':
        billing_data = {
            'patient_id': patient_id,
            'treatment_name': request.form['treatment_name'],
            'amount': float(request.form['amount']),
            'status': request.form['status'],
            'notes': request.form.get('notes', ''),
            'created_at': datetime.now(),
            'doctor_id': ObjectId(current_user.id),
            'due_date': datetime.strptime(request.form['due_date'], '%Y-%m-%d') if request.form.get('due_date') else None,
            'payment_method': request.form.get('payment_method', ''),
            'insurance_details': request.form.get('insurance_details', '')
        }
        
        db.billings.insert_one(billing_data)
        flash('Billing record added successfully!', 'success')
        return redirect(url_for('doctor.view_billing', patient_id=patient_id))
    
    patient = db.patients.find_one({'patient_id': patient_id})
    treatments = list(db.treatments.find({'doctor_id': ObjectId(current_user.id)}))
    return render_template('doctor/add_billing.html', patient=patient, treatments=treatments)

@doctor_bp.route('/doctor/billing/edit/<billing_id>', methods=['GET', 'POST'])
@login_required
def edit_billing(billing_id):
    billing = db.billings.find_one({'_id': ObjectId(billing_id)})
    
    if request.method == 'POST':
        update_data = {
            'treatment_name': request.form['treatment_name'],
            'amount': float(request.form['amount']),
            'status': request.form['status'],
            'notes': request.form.get('notes', ''),
            'due_date': datetime.strptime(request.form['due_date'], '%Y-%m-%d') if request.form.get('due_date') else None,
            'payment_method': request.form.get('payment_method', ''),
            'insurance_details': request.form.get('insurance_details', '')
        }
        
        db.billings.update_one(
            {'_id': ObjectId(billing_id)},
            {'$set': update_data}
        )
        flash('Billing record updated successfully!', 'success')
        return redirect(url_for('doctor.view_billing', patient_id=billing['patient_id']))
    
    patient = db.patients.find_one({'patient_id': billing['patient_id']})
    treatments = list(db.treatments.find({'doctor_id': ObjectId(current_user.id)}))
    return render_template('doctor/edit_billing.html', billing=billing, patient=patient, treatments=treatments)

@doctor_bp.route('/doctor/billing/delete/<billing_id>', methods=['POST'])
@login_required
def delete_billing(billing_id):
    billing = db.billings.find_one({'_id': ObjectId(billing_id)})
    if billing:
        db.billings.delete_one({'_id': ObjectId(billing_id)})
        flash('Billing record deleted successfully!', 'success')
        return redirect(url_for('doctor.view_billing', patient_id=billing['patient_id']))
    flash('Billing record not found!', 'error')
    return redirect(url_for('home'))
from bson.objectid import ObjectId
from bson.errors import InvalidId



# @doctor_bp.route('/doctor/patient/medical-info/<patient_id>', methods=['POST'])
# @login_required
# def update_medical_info(patient_id):
#     medical_info = {
#         'blood_type': request.form.get('blood_type'),
#         'allergies': request.form.get('allergies', '').split(','),
#         'chronic_conditions': request.form.get('chronic_conditions', '').split(','),
#         'current_medications': request.form.get('current_medications', '').split(',')
#     }
    
#     # Update the patient document
#     db.patients.update_one(
#         {'patient_id': patient_id},
#         {'$set': {'medical_info': medical_info}}
#     )
    
#     flash('Medical information updated successfully!', 'success')
#     return redirect(url_for('doctor.visit_prescription', appointment_id=request.form.get('appointment_id')))




@doctor_bp.route('/doctor/visit/<appointment_id>', methods=['GET'])
@login_required
def visit_prescription(appointment_id):
    try:
        # Get appointment
        appointment = db.appointments.find_one({'_id': ObjectId(appointment_id)})
        if not appointment:
            flash('Appointment not found!', 'error')
            return redirect(url_for('doctor.dashboard'))
        
        # Get patient
        patient = db.patients.find_one({'patient_id': appointment['patient_id']})
        if not patient:
            flash('Patient not found!', 'error')
            return redirect(url_for('doctor.dashboard'))
        
        # Get visit history
        visit_history = list(db.visits.find({
            'patient_id': appointment['patient_id']
        }).sort('date', -1).limit(10))
        
        # Get prescriptions for this appointment
        prescriptions = list(db.prescriptions.find({
            'patient_id': appointment['patient_id']  # Query by patient_id instead
        }).sort('prescribed_date', -1))
        
        # Get billing history
        billings = list(db.billings.find({
            'patient_id': appointment['patient_id']
        }).sort('created_at', -1))
        
        return render_template('doctor/visit_prescription.html',
                             appointment=appointment,
                             patient=patient,
                             visit_history=visit_history,
                             prescriptions=prescriptions,
                             billings=billings)
    except InvalidId:
        flash('Invalid appointment ID!', 'error')
        return redirect(url_for('doctor.dashboard'))


    
@doctor_bp.route('/doctor/dashboard')
@login_required
def dashboard():
    # Get today's date range
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    # Fetch today's appointments
    today_appointments = list(db.appointments.find({
        'date': {'$gte': today, '$lt': tomorrow},
        'doctor_id': ObjectId(current_user.id)
    }).sort('time', 1))
    
    # Format the appointments
    for appointment in today_appointments:
        try:
            # Parse 'time' to datetime if it's a string
            if isinstance(appointment['time'], str):
                appointment['time'] = datetime.strptime(appointment['time'], '%H:%M:%S')
            appointment['formatted_time'] = appointment['time'].strftime('%I:%M %p')
        except (KeyError, ValueError):
            appointment['formatted_time'] = 'Invalid time'
        
        # Add status if not present
        if 'status' not in appointment:
            appointment['status'] = 'scheduled'
    
    # Fetch weekly appointments
    week_end = today + timedelta(days=7)
    weekly_appointments = list(db.appointments.find({
        'date': {'$gte': tomorrow, '$lt': week_end},
        'doctor_id': ObjectId(current_user.id)
    }).sort('date', 1))
    
    # Format weekly appointments
    for appointment in weekly_appointments:
        try:
            if isinstance(appointment['date'], str):
                appointment['date'] = datetime.strptime(appointment['date'], '%Y-%m-%d')
            appointment['formatted_date'] = appointment['date'].strftime('%B %d, %Y')
            
            if isinstance(appointment['time'], str):
                appointment['time'] = datetime.strptime(appointment['time'], '%H:%M:%S')
            appointment['formatted_time'] = appointment['time'].strftime('%I:%M %p')
        except (KeyError, ValueError):
            appointment['formatted_date'] = 'Invalid date'
            appointment['formatted_time'] = 'Invalid time'
    
    # Get billing summary
    billing_summary = {
        'paid': {
            'total': sum(b['amount'] for b in db.billings.find({
                'doctor_id': ObjectId(current_user.id),
                'status': 'paid'
            })),
            'count': db.billings.count_documents({
                'doctor_id': ObjectId(current_user.id),
                'status': 'paid'
            })
        },
        'pending': {
            'total': sum(b['amount'] for b in db.billings.find({
                'doctor_id': ObjectId(current_user.id),
                'status': 'pending'
            })),
            'count': db.billings.count_documents({
                'doctor_id': ObjectId(current_user.id),
                'status': 'pending'
            })
        }
    }
    
    # Get all patients for the current doctor
    patients = list(db.patients.find({'doctor_id': ObjectId(current_user.id)}))
    
    return render_template('doctor/dashboard.html',
                         today_appointments=today_appointments,
                         weekly_appointments=weekly_appointments,
                         billing_summary=billing_summary,
                         patients=patients,
                         now=datetime.now())


@doctor_bp.route('/doctor/visit/notes/<appointment_id>', methods=['POST'])
@login_required
def save_visit_notes(appointment_id):
    try:
        data = request.get_json()
        visit_note = {
            'appointment_id': ObjectId(appointment_id),
            'doctor_id': ObjectId(current_user.id),
            'doctor_name': current_user.name,
            'notes': data['notes'],
            'date': datetime.now()
        }
        
        # Get appointment to get patient_id
        appointment = db.appointments.find_one({'_id': ObjectId(appointment_id)})
        if appointment:
            visit_note['patient_id'] = appointment['patient_id']
        
        result = db.visits.insert_one(visit_note)
        return jsonify({'status': 'success', 'id': str(result.inserted_id)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    


# Start an appointment
@doctor_bp.route('/doctor/appointment/start/<appointment_id>', methods=['POST'])
@login_required
def start_appointment(appointment_id):
    try:
        db.appointments.update_one(
            {'_id': ObjectId(appointment_id)},
            {'$set': {
                'status': 'in_progress',
                'start_time': datetime.now()
            }}
        )
        appointment = db.appointments.find_one({'_id': ObjectId(appointment_id)})
        visit_data = {
            'appointment_id': ObjectId(appointment_id),
            'patient_id': ObjectId(appointment['patient_id']),
            'doctor_id': ObjectId(current_user.id),
            'doctor_name': current_user.name,
            'start_time': datetime.now(),
            'status': 'in_progress',
            'notes': []
        }
        db.visits.insert_one(visit_data)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# End an appointment
@doctor_bp.route('/doctor/appointment/end/<appointment_id>', methods=['POST'])
@login_required
def end_appointment(appointment_id):
    try:
        db.appointments.update_one(
            {'_id': ObjectId(appointment_id)},
            {'$set': {
                'status': 'completed',
                'end_time': datetime.now()
            }}
        )
        appointment = db.appointments.find_one({'_id': ObjectId(appointment_id)})
        visit_summary = {
            'appointment_id': ObjectId(appointment_id),
            'patient_id': ObjectId(appointment['patient_id']),
            'doctor_id': ObjectId(current_user.id),
            'start_time': appointment.get('start_time'),
            'end_time': datetime.now(),
            'services': list(db.services.find({'appointment_id': ObjectId(appointment_id)})),
            'prescriptions': list(db.prescriptions.find({'appointment_id': ObjectId(appointment_id)})),
            'notes': list(db.visits.find({'appointment_id': ObjectId(appointment_id)})),
            'total_amount': sum(service['amount'] for service in 
                              db.services.find({'appointment_id': ObjectId(appointment_id)}))
        }
        db.visit_summaries.insert_one(visit_summary)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Add service to an appointment
# @doctor_bp.route('/doctor/service/add/<appointment_id>', methods=['POST'])
# @login_required
# def add_service(appointment_id):
#     try:
#         service_data = {
#             'appointment_id': ObjectId(appointment_id),
#             'name': request.form['service_name'],
#             'amount': float(request.form['amount']),
#             'notes': request.form.get('notes', ''),
#             'date': datetime.now()
#         }
#         db.services.insert_one(service_data)
#         return redirect(url_for('doctor.visit_prescription', appointment_id=appointment_id))
#     except Exception as e:
#         return jsonify({'status': 'error', 'message': str(e)}), 500


@doctor_bp.route('/doctor/prescription/<appointment_id>', methods=['POST'])
@login_required
def add_prescription(appointment_id):
    try:
        data = request.get_json()
        
        # Get appointment to get patient_id
        appointment = db.appointments.find_one({'_id': ObjectId(appointment_id)})
        if not appointment:
            return jsonify({'status': 'error', 'message': 'Appointment not found'}), 404
            
        prescription = {
            'appointment_id': ObjectId(appointment_id),
            'patient_id': appointment['patient_id'],
            'doctor_id': ObjectId(current_user.id),
            'doctor_name': current_user.name,
            'medicines': data['medicines'],
            'notes': data.get('notes', ''),
            'prescribed_date': datetime.now()
        }
        
        result = db.prescriptions.insert_one(prescription)
        return jsonify({'status': 'success', 'id': str(result.inserted_id)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# Retrieve visit history for a patient
@doctor_bp.route('/doctor/visit/history/<patient_id>', methods=['GET'])
@login_required
def get_visit_history(patient_id):
    try:
        visits = db.visits.find({'patient_id': ObjectId(patient_id)})
        visit_list = []
        for visit in visits:
            visit['_id'] = str(visit['_id'])
            visit['appointment_id'] = str(visit['appointment_id'])
            visit['doctor_id'] = str(visit['doctor_id'])
            visit_list.append(visit)
        return jsonify(visit_list)
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
