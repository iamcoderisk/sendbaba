from app import db
from datetime import datetime
import uuid

class Organization(db.Model):
    __tablename__ = 'organizations'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    name = db.Column(db.String(255), nullable=False)
    
    # Settings
    is_active = db.Column(db.Boolean, default=True)
    
    # Limits
    email_limit = db.Column(db.Integer, default=1000)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships with backref
    users = db.relationship('User', backref='organization', lazy='dynamic')
    domains = db.relationship('Domain', backref='organization', lazy='dynamic')
    
    def __init__(self, **kwargs):
        if 'id' not in kwargs:
            kwargs['id'] = str(uuid.uuid4())
        super().__init__(**kwargs)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'is_active': self.is_active,
            'email_limit': self.email_limit,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
