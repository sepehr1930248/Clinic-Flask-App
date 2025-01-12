from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from pymongo import MongoClient
from bson import ObjectId

manager_bp = Blueprint('manager', __name__)
client = MongoClient('mongodb://localhost:27017/')
db = client['clinical_management']

@manager_bp.route('/manager/dashboard')
@login_required
def dashboard():
    if not hasattr(current_user, 'role') or current_user.role != 'manager':
        abort(403, "Unauthorized access")
        
    unapproved_accountants = list(db.accountants.find({'status': {'$ne': 'approved'}}))
    return render_template('manager.html', accountants=unapproved_accountants)  # Note: changed to manager.html

