"""
Organization Model for SendBaba
"""
from app import db
from datetime import datetime
import uuid


class Organization(db.Model):
    __tablename__ = 'organizations'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(255), nullable=False)
    plan = db.Column(db.String(50), default='free')
    status = db.Column(db.String(50), default='active')
    is_active = db.Column(db.Boolean, default=True)
    email_limit = db.Column(db.Integer, default=1000)
    feature_workflows = db.Column(db.Boolean, default=True)
    feature_segments = db.Column(db.Boolean, default=True)
    feature_team = db.Column(db.Boolean, default=True)
    feature_ai_reply = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, name=None, **kwargs):
        if 'id' not in kwargs:
            kwargs['id'] = str(uuid.uuid4())
        if name:
            kwargs['name'] = name
        super().__init__(**kwargs)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'plan': self.plan,
            'status': self.status,
            'is_active': self.is_active,
            'email_limit': self.email_limit,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
    
    def __repr__(self):
        return f'<Organization {self.name}>'
