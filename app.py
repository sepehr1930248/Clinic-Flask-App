from flask import Flask, abort, send_file, render_template, request, redirect, url_for, flash
from datetime import datetime,timedelta
from pymongo import MongoClient
from io import BytesIO
import pandas as pd
from bson import ObjectId
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from schedule import schedule_bp
from patient import patient_bp
from doctor import doctor_bp
from appointment import appointment_bp
from markupsafe import Markup, escape
from exportdata import export_bp
from accountant import accountant_bp



app = Flask(__name__)
app.secret_key = 'your_secret_key'  
app.register_blueprint(doctor_bp)
client = MongoClient('mongodb://localhost:27017/')
db = client['clinical_management']
patients_collection = db['patients']
appointments_collection = db['appointments']

from manager import manager_bp


@app.template_filter('nl2br')
def nl2br(value):
    if value is None:
        return ''
    return Markup('<br>'.join(escape(value).splitlines()))

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.email = user_data['email']
        self.name = user_data['name']
        self.role = user_data.get('role', 'doctor')  # default role is doctor
        self.specialization = user_data.get('specialization', '')



@login_manager.user_loader
def load_user(user_id):
    if user_id == 'manager':
        manager_data = {
            '_id': 'manager',
            'email': 'admin@admin.com',
            'name': 'Manager',
            'role': 'manager'
        }
        return User(manager_data)
    # Then check other users
    user_data = db.doctors.find_one({'_id': ObjectId(user_id)})
    if not user_data:
        user_data = db.accountants.find_one({'_id': ObjectId(user_id)})
    return User(user_data) if user_data else None

    

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Check if it's manager login
        if email == 'admin@admin.com' and password == 'admin':
            manager_data = {
                '_id': 'manager',
                'email': email,
                'name': 'Manager',
                'role': 'manager'
            }
            user_obj = User(manager_data)
            login_user(user_obj)
            return redirect(url_for('manager.dashboard'))
        
        # Check doctors
        user = db.doctors.find_one({'email': email})
        if not user:
            # If not a doctor, check accountants
            user = db.accountants.find_one({'email': email})
        
        if user and check_password_hash(user['password'], password):
            user_obj = User(user)
            login_user(user_obj)
            if getattr(user_obj, 'role', 'doctor') == 'accountant':
                return redirect(url_for('accountant.dashboard'))
            return redirect(url_for('home'))
            
        flash('Invalid email or password', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        role = request.form['role']
        
        # Check if email exists in either doctors or accountants collection
        if db.doctors.find_one({'email': email}) or db.accountants.find_one({'email': email}):
            flash('Email already registered', 'error')
            return redirect(url_for('register'))
        
        user_data = {
            'email': email,
            'password': generate_password_hash(request.form['password'], method='pbkdf2:sha256'),
            'name': request.form['name'],
            'role': role,
            'created_at': datetime.now()
        }
        
        if role == 'doctor':
            user_data['specialization'] = request.form['specialization']
            db.doctors.insert_one(user_data)
        else:
            db.accountants.insert_one(user_data)
            
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/approved_by_manager', methods=['GET', 'POST'])
def approved_by_manager():
    if not hasattr(current_user, 'role') or current_user.role != 'manager':
        abort(403, "Unauthorized access")

    if request.method == 'POST':
        accountant_id = request.form.get('accountant_id')
        action = request.form.get('action')

        try:
            if action == 'approve':
                db.accountants.update_one(
                    {'_id': ObjectId(accountant_id)},
                    {'$set': {'status': 'approved'}}
                )
                flash('Accountant approved successfully!', 'success')
            elif action == 'reject':
                db.accountants.delete_one({'_id': ObjectId(accountant_id)})
                flash('Accountant rejected and removed!', 'success')
            else:
                flash('Invalid action', 'error')
        except Exception as e:
            flash(f'Error processing request: {str(e)}', 'error')

        return redirect(url_for('approved_by_manager'))

    # Fetch all unapproved accountants
    unapproved_accountants = list(db.accountants.find({'status': {'$ne': 'approved'}}))
    return render_template('manager.html', accountants=unapproved_accountants)


@app.route('/')
@login_required
def home():
    if current_user.role == 'accountant':
        return redirect(url_for('accountant.dashboard'))
    
    patients = list(patients_collection.find({'doctor_id': ObjectId(current_user.id)}))
    billing_stats = db.billings.aggregate([
        {'$match': {'doctor_id': ObjectId(current_user.id)}},
        {'$group': {
            '_id': '$status',
            'total': {'$sum': '$amount'},
            'count': {'$sum': 1}
        }}
    ])
    billing_summary = {item['_id']: {
        'total': item['total'], 
        'count': item['count']
    } for item in billing_stats}    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    today_appointments = list(appointments_collection.find({
        'doctor_id': ObjectId(current_user.id),
        'date': {
            '$gte': today,
            '$lt': tomorrow
        }
    }).sort('time', 1))
    week_end = today + timedelta(days=7)    
    weekly_appointments = list(appointments_collection.find({
        'doctor_id': ObjectId(current_user.id),
        'date': {
            '$gte': today,
            '$lt': week_end
        }
    }).sort([('date', 1), ('time', 1)]))

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
                         patients=patients,
                         billing_summary=billing_summary,
                         today_appointments=today_appointments,
                         weekly_appointments=weekly_appointments,
                         now=datetime.now())

app.register_blueprint(accountant_bp)
app.register_blueprint(appointment_bp)
app.register_blueprint(patient_bp)
app.register_blueprint(schedule_bp)
app.register_blueprint(export_bp)
app.register_blueprint(manager_bp)



app.run(debug=True)