from flask import Blueprint, abort, render_template, request, jsonify, redirect, url_for, flash
from datetime import datetime, timedelta
from bson import ObjectId
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from bson.objectid import ObjectId
from bson.errors import InvalidId
from receipt import receipt_bp
import os
from werkzeug.utils import secure_filename
from flask import send_file

doctor_bp = Blueprint('doctor', __name__)
client = MongoClient('mongodb://localhost:27017/')
db = client['clinical_management']
from flask_login import login_required, current_user


doctor_bp.register_blueprint(receipt_bp)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max-limit

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@doctor_bp.route('/doctor/upload/<appointment_id>', methods=['POST'])
@login_required
def upload_files(appointment_id):
    try:
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(url_for('doctor.visit_prescription', appointment_id=appointment_id))

        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('doctor.visit_prescription', appointment_id=appointment_id))

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            
            # Create upload directory if it doesn't exist
            if not os.path.exists(UPLOAD_FOLDER):
                os.makedirs(UPLOAD_FOLDER)
            
            # Save file to disk
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(file_path)
            
            # Get appointment details
            appointment = db.appointments.find_one({'_id': ObjectId(appointment_id)})
            
            # Save file information to database
            file_doc = {
                'filename': filename,
                'file_path': file_path,
                'document_type': request.form['document_type'],
                'description': request.form.get('description', ''),
                'upload_date': datetime.now(),
                'appointment_id': ObjectId(appointment_id),
                'patient_id': appointment['patient_id'],
                'doctor_id': ObjectId(current_user.id),
                'doctor_name': current_user.name
            }
            
            db.uploaded_files.insert_one(file_doc)
            flash('File uploaded successfully!', 'success')
        else:
            flash('Invalid file type', 'error')
            
        return redirect(url_for('doctor.visit_prescription', appointment_id=appointment_id))
    
    except Exception as e:
        flash(f'Error uploading file: {str(e)}', 'error')
        return redirect(url_for('doctor.visit_prescription', appointment_id=appointment_id))

@doctor_bp.route('/doctor/file/<file_id>')
@login_required
def view_file(file_id):
    try:
        file_doc = db.uploaded_files.find_one({'_id': ObjectId(file_id)})
        if not file_doc:
            abort(404)
            
        return send_file(file_doc['file_path'])
    except Exception as e:
        flash(f'Error viewing file: {str(e)}', 'error')
        return redirect(url_for('doctor.dashboard'))

@doctor_bp.route('/doctor/file/delete/<file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    try:
        file_doc = db.uploaded_files.find_one({'_id': ObjectId(file_id)})
        if not file_doc:
            abort(404)
            
        # Delete file from disk
        if os.path.exists(file_doc['file_path']):
            os.remove(file_doc['file_path'])
            
        # Remove database entry
        db.uploaded_files.delete_one({'_id': ObjectId(file_id)})
        
        flash('File deleted successfully!', 'success')
        return redirect(url_for('doctor.visit_prescription', 
                              appointment_id=file_doc['appointment_id']))
    
    except Exception as e:
        flash(f'Error deleting file: {str(e)}', 'error')
        return redirect(url_for('doctor.dashboard'))



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

        previous_receipts = list(db.receipts.find({
                    'patient_id': appointment['patient_id']
                }).sort('created_at', -1))        
        

        uploaded_files = list(db.uploaded_files.find({
            'appointment_id': ObjectId(appointment_id)
        }).sort('upload_date', -1))

        return render_template('doctor/visit_prescription.html',
                             appointment=appointment,
                             patient=patient,
                             visit_history=visit_history,
                             prescriptions=prescriptions,
                             billings=billings,
                             previous_receipts=previous_receipts,
                             uploaded_files=uploaded_files)
    except InvalidId:
        flash('Invalid appointment ID!', 'error')
        return redirect(url_for('doctor.dashboard'))

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
