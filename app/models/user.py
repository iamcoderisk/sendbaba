"""
User Model for SendBaba
"""
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime
import uuid


class User(db.Model, UserMixin):
    __tablename__ = 'users'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    organization_id = db.Column(db.String(36), index=True)
    role = db.Column(db.String(50), default='member')
    is_verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, email=None, password=None, first_name=None, last_name=None, **kwargs):
        if 'id' not in kwargs:
            kwargs['id'] = str(uuid.uuid4())
        if email:
            kwargs['email'] = email.lower().strip()
        if password:
            kwargs['password_hash'] = generate_password_hash(password)
        if first_name:
            kwargs['first_name'] = first_name
        if last_name:
            kwargs['last_name'] = last_name
        super().__init__(**kwargs)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_id(self):
        return str(self.id)
    
    @property
    def full_name(self):
        parts = [self.first_name, self.last_name]
        return ' '.join(p for p in parts if p) or self.email.split('@')[0]
    
    def __repr__(self):
        return f'<User {self.email}>'
