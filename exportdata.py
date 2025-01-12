from flask import Flask, Blueprint, send_file, render_template, request, redirect, url_for, flash
from datetime import datetime, timedelta
from pymongo import MongoClient
from io import BytesIO
import pandas as pd
from bson import ObjectId
from flask_login import login_required, current_user

export_bp = Blueprint('export', __name__)

doctor_bp = Blueprint('doctor', __name__)
client = MongoClient('mongodb://localhost:27017/')
db = client['clinical_management']
from flask_login import login_required, current_user

@export_bp.route('/export-data')
@login_required
def export_data():
    # Get filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    data_types = request.args.getlist('data_types')
    patient_status = request.args.get('patient_status')
    payment_status = request.args.get('payment_status')

    # Convert dates to datetime objects
    if start_date:
        start_date = datetime.strptime(start_date, '%Y-%m-%d')
    if end_date:
        end_date = datetime.strptime(end_date, '%Y-%m-%d')

    # Initialize query filters
    date_filter = {}
    if start_date and end_date:
        date_filter = {'$gte': start_date, '$lte': end_date}

    # Prepare data containers
    data_frames = {}

    # Process Patients Data
    if 'patients' in data_types:
        query = {'doctor_id': ObjectId(current_user.id)}
        if patient_status:
            now = datetime.now()
            if patient_status == 'active':
                query['expert_details.last_visit'] = {'$gte': now - timedelta(days=30)}
            elif patient_status == 'follow_up':
                query['expert_details.last_visit'] = {
                    '$lt': now - timedelta(days=30),
                    '$gte': now - timedelta(days=90)
                }
            elif patient_status == 'inactive':
                query['expert_details.last_visit'] = {'$lt': now - timedelta(days=90)}

        patients = list(db.patients.find(query))
        if patients:
            patients_data = [{
                'Patient ID': p['patient_id'],
                'Name': p['name'],
                'Phone': p.get('phone', ''),
                'Birth Date': p.get('birth_date', '').strftime('%Y-%m-%d') if p.get('birth_date') else '',
                'Last Visit': p['expert_details'].get('last_visit', '').strftime('%Y-%m-%d') if p['expert_details'].get('last_visit') else '',
                'Therapy Method': p['expert_details'].get('therapy_method', ''),
                'Medicine': p['expert_details'].get('medicine', ''),
                'Notes': p['expert_details'].get('notes', '')
            } for p in patients]
            data_frames['Patients'] = pd.DataFrame(patients_data)

    # Process Billing Data
    if 'billing' in data_types:
        query = {'doctor_id': ObjectId(current_user.id)}
        if date_filter:
            query['created_at'] = date_filter
        if payment_status:
            query['status'] = payment_status

        billing = list(db.billing.find(query))
        if billing:
            billing_data = [{
                'Patient ID': b['patient_id'],
                'Treatment Name': b.get('treatment_name', ''),
                'Amount': b.get('amount', ''),
                'Status': b.get('status', ''),
                'Notes': b.get('notes', ''),
                'Created At': b.get('created_at', '').strftime('%Y-%m-%d') if b.get('created_at') else '',
                'Payment Method': b.get('payment_method', ''),
                'Insurance Details': b.get('insurance_details', '')
            } for b in billing]
            data_frames['Billing'] = pd.DataFrame(billing_data)

    # Process Prescriptions Data
    if 'prescriptions' in data_types:
        query = {'doctor_id': ObjectId(current_user.id)}
        if date_filter:
            query['prescribed_date'] = date_filter

        prescriptions = list(db.prescription.find(query))
        if prescriptions:
            prescriptions_data = []
            for p in prescriptions:
                medicines = p.get('medicines', [])
                medicines_str = ', '.join([
                    f"{med['name']} ({med['dosage']}, {med['frequency']}x/day, {med['duration']} days)"
                    for med in medicines
                ])
                prescriptions_data.append({
                    'Patient ID': p['patient_id'],
                    'Medicines': medicines_str,
                    'Notes': p.get('notes', ''),
                    'Prescribed Date': p.get('prescribed_date', '').strftime('%Y-%m-%d') if p.get('prescribed_date') else '',
                    'Doctor Name': p.get('doctor_name', '')
                })
            data_frames['Prescriptions'] = pd.DataFrame(prescriptions_data)

    # Process Receipts Data
    if 'receipts' in data_types:
        query = {'doctor_id': ObjectId(current_user.id)}
        if date_filter:
            query['created_at'] = date_filter

        receipts = list(db.receipt.find(query))
        if receipts:
            receipts_data = []
            for r in receipts:
                items = r.get('items', [])
                amounts = r.get('amounts', [])
                items_str = ', '.join([f"{item} (${amount})" for item, amount in zip(items, amounts)])
                receipts_data.append({
                    'Patient ID': r['patient_id'],
                    'Items': items_str,
                    'Total Amount': r.get('total_amount', ''),
                    'Comment': r.get('comment', ''),
                    'Created At': r.get('created_at', '').strftime('%Y-%m-%d') if r.get('created_at') else '',
                    'Status': r.get('status', '')
                })
            data_frames['Receipts'] = pd.DataFrame(receipts_data)

    # If no data is selected or found, redirect with a message
    if not data_frames:
        flash('No data found for the selected criteria', 'warning')
        return redirect(url_for('export.export_page'))

    # Export to Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        for sheet_name, df in data_frames.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'clinical_data_{datetime.now().strftime("%Y%m%d")}.xlsx'
    )

@export_bp.route('/export')
@login_required
def export_page():
    return render_template('export.html')