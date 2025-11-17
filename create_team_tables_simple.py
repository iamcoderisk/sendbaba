import sys
sys.path.insert(0, '/opt/sendbaba-staging')

from app import db
from flask import Flask
import os

# Create minimal app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://emailer:SecurePassword123@localhost:5432/emailer')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    # Import models
    from app.models.team import Department, TeamMember, AuditLog
    
    # Create tables
    db.create_all()
    print("✅ Team tables created successfully!")
