"""
SendBaba Campaign Model
Includes sender fields: from_name, from_email, reply_to, preview_text
"""
from datetime import datetime
import uuid

try:
    from app import db
except ImportError:
    from flask_sqlalchemy import SQLAlchemy
    db = SQLAlchemy()


class Campaign(db.Model):
    """Email Campaign with full sender customization"""
    __tablename__ = 'campaigns'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False, index=True)
    created_by_user_id = db.Column(db.String(36), db.ForeignKey('users.id'), index=True)
    
    # Campaign info
    name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='draft')
    
    # Sender Information
    from_name = db.Column(db.String(255))
    from_email = db.Column(db.String(255))
    reply_to = db.Column(db.String(255))
    
    # Email Content
    subject = db.Column(db.String(500))
    preview_text = db.Column(db.Text)
    html_body = db.Column(db.Text)
    text_body = db.Column(db.Text)
    
    # Stats
    total_recipients = db.Column(db.Integer, default=0)
    emails_sent = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sent_at = db.Column(db.DateTime)
    
    def __init__(self, **kwargs):
        if 'id' not in kwargs:
            kwargs['id'] = str(uuid.uuid4())
        super().__init__(**kwargs)
    
    @property
    def sender_display(self):
        if self.from_name and self.from_email:
            return f'{self.from_name} <{self.from_email}>'
        return self.from_email or 'SendBaba'
