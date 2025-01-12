from flask import Blueprint, render_template, request, flash, abort, redirect, url_for, flash
from datetime import datetime
from bson import ObjectId
from flask_login import login_required, current_user
from pymongo import MongoClient
import os
from werkzeug.utils import secure_filename
from flask import send_file

# Add these configurations at the top of your receipt routes file
RECEIPT_UPLOAD_FOLDER = 'uploads/receipts'
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB max-limit

receipt_bp = Blueprint('receipt', __name__)
client = MongoClient('mongodb://localhost:27017/')
db = client['clinical_management']


@receipt_bp.route('/doctor/receipt/<appointment_id>', methods=['GET', 'POST'])
@login_required
def manage_receipt(appointment_id):
    if request.method == 'POST':
        try:
            receipt_data = {
                'appointment_id': ObjectId(appointment_id),
                'doctor_id': ObjectId(current_user.id),
                'doctor_name': current_user.name,
                'items': request.form.getlist('items[]'),
                'amounts': [float(amount) for amount in request.form.getlist('amounts[]')],
                'comment': request.form.get('comment', ''),
                'total_amount': sum(float(amount) for amount in request.form.getlist('amounts[]')),
                'created_at': datetime.now(),
                'status': 'issued'
            }
            
            # Get appointment to add patient_id
            appointment = db.appointments.find_one({'_id': ObjectId(appointment_id)})
            if appointment:
                receipt_data['patient_id'] = appointment['patient_id']
            
            db.receipts.insert_one(receipt_data)
            flash('Receipt created successfully!', 'success')
            return redirect(url_for('doctor.receipt.view_receipt', receipt_id=str(receipt_data['_id'])))
        except Exception as e:
            flash(f'Error creating receipt: {str(e)}', 'error')
            return redirect(url_for('doctor.receipt.manage_receipt', appointment_id=appointment_id))
    
    # Get existing receipt data
    appointment = db.appointments.find_one({'_id': ObjectId(appointment_id)})
    patient = db.patients.find_one({'patient_id': appointment['patient_id']})
    previous_receipts = list(db.receipts.find({
        'patient_id': appointment['patient_id']
    }).sort('created_at', -1))
    
    # Get billing data for this appointment
    billings = list(db.billings.find({
        'patient_id': appointment['patient_id']
    }).sort('created_at', -1))
    
    # Pass the zip function to the template
    return render_template('doctor/receipt.html',
                         appointment=appointment,
                         patient=patient,
                         previous_receipts=previous_receipts,
                         billings=billings
                         ) 


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@receipt_bp.route('/doctor/receipt/view/<receipt_id>', methods=['GET'])
@login_required
def view_receipt(receipt_id):
    try:
        # Get receipt data
        receipt = db.receipts.find_one({'_id': ObjectId(receipt_id)})
        if not receipt:
            flash('Receipt not found', 'error')
            return abort(404)
        
        # Convert items and amounts to lists if they're not already
        receipt['items'] = list(receipt.get('items', []))
        receipt['amounts'] = list(receipt.get('amounts', []))
            
        # Get related appointment data
        appointment = db.appointments.find_one({'_id': receipt['appointment_id']})
        if not appointment:
            flash('Associated appointment not found', 'error')
            return abort(404)
            
        # Get patient data
        patient = db.patients.find_one({'patient_id': receipt['patient_id']})
        if not patient:
            flash('Associated patient not found', 'error')
            return abort(404)
            
        # Get receipt comments
        comments = list(db.receipt_comments.find({
            'receipt_id': ObjectId(receipt_id)
        }).sort('created_at', -1))

        # Get receipt files
        receipt_files = list(db.receipt_files.find({
            'receipt_id': ObjectId(receipt_id)
        }).sort('upload_date', -1))
            
        return render_template('doctor/view_receipt.html',
                             receipt=receipt,
                             appointment=appointment,
                             patient=patient,
                             comments=comments,
                             receipt_files=receipt_files)
    except Exception as e:
        flash(f'Error viewing receipt: {str(e)}', 'error')
        return redirect(url_for('doctor.dashboard'))

@receipt_bp.route('/doctor/receipt/upload/<receipt_id>', methods=['POST'])
@login_required
def upload_receipt_file(receipt_id):
    try:
        if 'file' not in request.files:
            flash('No file selected', 'error')
            return redirect(url_for('doctor.receipt.view_receipt', receipt_id=receipt_id))

        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('doctor.receipt.view_receipt', receipt_id=receipt_id))

        if file and allowed_file(file.filename):
            # Create receipt upload directory if it doesn't exist
            if not os.path.exists(RECEIPT_UPLOAD_FOLDER):
                os.makedirs(RECEIPT_UPLOAD_FOLDER)
            
            # Generate unique filename
            filename = secure_filename(f"{receipt_id}_{file.filename}")
            file_path = os.path.join(RECEIPT_UPLOAD_FOLDER, filename)
            
            # Save file to disk
            file.save(file_path)
            
            # Get receipt details
            receipt = db.receipts.find_one({'_id': ObjectId(receipt_id)})
            
            # Save file information to database
            file_doc = {
                'filename': filename,
                'file_path': file_path,
                'document_type': request.form['document_type'],
                'description': request.form.get('description', ''),
                'upload_date': datetime.now(),
                'receipt_id': ObjectId(receipt_id),
                'patient_id': receipt['patient_id'],
                'doctor_id': ObjectId(current_user.id),
                'doctor_name': current_user.name
            }
            
            db.receipt_files.insert_one(file_doc)
            flash('File uploaded successfully!', 'success')
        else:
            flash('Invalid file type', 'error')
            
        return redirect(url_for('doctor.receipt.view_receipt', receipt_id=receipt_id))
    
    except Exception as e:
        flash(f'Error uploading file: {str(e)}', 'error')
        return redirect(url_for('doctor.receipt.view_receipt', receipt_id=receipt_id))

@receipt_bp.route('/doctor/receipt/file/<file_id>')
@login_required
def download_receipt_file(file_id):
    try:
        file_doc = db.receipt_files.find_one({'_id': ObjectId(file_id)})
        if not file_doc:
            abort(404)
            
        return send_file(file_doc['file_path'],
                        download_name=file_doc['filename'],
                        as_attachment=True)
    except Exception as e:
        flash(f'Error downloading file: {str(e)}', 'error')
        return redirect(url_for('doctor.dashboard'))

@receipt_bp.route('/doctor/receipt/file/delete/<file_id>', methods=['POST'])
@login_required
def delete_receipt_file(file_id):
    try:
        file_doc = db.receipt_files.find_one({'_id': ObjectId(file_id)})
        if not file_doc:
            abort(404)
            
        # Delete file from disk
        if os.path.exists(file_doc['file_path']):
            os.remove(file_doc['file_path'])
            
        # Remove database entry
        db.receipt_files.delete_one({'_id': ObjectId(file_id)})
        
        flash('File deleted successfully!', 'success')
        return redirect(url_for('doctor.receipt.view_receipt', 
                              receipt_id=file_doc['receipt_id']))
    
    except Exception as e:
        flash(f'Error deleting file: {str(e)}', 'error')
        return redirect(url_for('doctor.dashboard'))
    

@receipt_bp.route('/doctor/receipt/comment/<receipt_id>', methods=['POST'])
@login_required
def add_comment(receipt_id):
    try:
        comment_data = {
            'receipt_id': ObjectId(receipt_id),
            'doctor_id': ObjectId(current_user.id),
            'doctor_name': current_user.name,
            'comment': request.form['comment'],
            'created_at': datetime.now()
        }
        
        db.receipt_comments.insert_one(comment_data)
        flash('Comment added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding comment: {str(e)}', 'error')
    
    return redirect(url_for('doctor.receipt.view_receipt', receipt_id=receipt_id))

@receipt_bp.route('/receipt/<patient_id>', methods=['GET'])
@login_required
def patient_receipts(patient_id):
    try:
        # Get patient information
        patient = db.patients.find_one({'patient_id': patient_id})
        if not patient:
            flash('Patient not found', 'error')
            return abort(404)
            
        # Get all receipts for the patient
        receipts = list(db.receipts.find({
            'patient_id': patient_id
        }).sort('created_at', -1))
        
        # Calculate total amount for all receipts
        total_amount = sum(receipt.get('total_amount', 0) for receipt in receipts)
        
        # Get all billings for the patient
        billings = list(db.billings.find({
            'patient_id': patient_id
        }).sort('created_at', -1))
        
        # Get all appointments for reference
        appointments = {str(appt['_id']): appt for appt in db.appointments.find({
            'patient_id': patient_id
        })}
        
        return render_template('patient_receipts.html',
                             patient=patient,
                             receipts=receipts,
                             billings=billings,
                             appointments=appointments,
                             total_amount=total_amount)
                             
    except Exception as e:
        flash(f'Error retrieving receipts: {str(e)}', 'error')
        return redirect(url_for('doctor.dashboard'))


@receipt_bp.route('/doctor/receipt/delete/<receipt_id>', methods=['POST'])
@login_required
def delete_receipt(receipt_id):
    try:
        receipt = db.receipts.find_one({'_id': ObjectId(receipt_id)})
        if receipt:
            # Delete receipt and its comments
            db.receipts.delete_one({'_id': ObjectId(receipt_id)})
            db.receipt_comments.delete_many({'receipt_id': ObjectId(receipt_id)})
            flash('Receipt deleted successfully!', 'success')
            return redirect(url_for('doctor.dashboard'))
    except Exception as e:
        flash(f'Error deleting receipt: {str(e)}', 'error')
    
    return redirect(url_for('doctor.receipt.view_receipt', receipt_id=receipt_id))