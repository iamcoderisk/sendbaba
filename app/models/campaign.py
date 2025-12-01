"""
SendBaba Campaign Model
"""
from datetime import datetime
import uuid

try:
    from app import db
except ImportError:
    from flask_sqlalchemy import SQLAlchemy
    db = SQLAlchemy()


class Campaign(db.Model):
    __tablename__ = 'campaigns'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), index=True)
    created_by_user_id = db.Column(db.String(36), index=True)
    name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='draft')
    from_name = db.Column(db.String(255))
    from_email = db.Column(db.String(255))
    reply_to = db.Column(db.String(255))
    subject = db.Column(db.String(500))
    preview_text = db.Column(db.Text)
    html_body = db.Column(db.Text)
    text_body = db.Column(db.Text)
    total_recipients = db.Column(db.Integer, default=0)
    emails_sent = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    recipients_count = db.Column(db.Integer, default=0)
    opens = db.Column(db.Integer, default=0)
    clicks = db.Column(db.Integer, default=0)
    bounces = db.Column(db.Integer, default=0)
    unsubscribes = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sent_at = db.Column(db.DateTime)
    scheduled_at = db.Column(db.DateTime)
    
    def __init__(self, **kwargs):
        if 'id' not in kwargs:
            kwargs['id'] = str(uuid.uuid4())
        super().__init__(**kwargs)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'status': self.status,
            'from_name': self.from_name,
            'from_email': self.from_email,
            'subject': self.subject,
            'total_recipients': self.total_recipients,
            'emails_sent': self.emails_sent,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None
        }
