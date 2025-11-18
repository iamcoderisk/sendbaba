from app import db
from datetime import datetime
import uuid

class Campaign(db.Model):
    __tablename__ = 'campaigns'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False, index=True)
    created_by_user_id = db.Column(db.String(36), db.ForeignKey('users.id'), index=True)
    
    name = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(500))
    status = db.Column(db.String(20), default='draft')  # draft, scheduled, sending, sent, failed
    
    # Content
    html_body = db.Column(db.Text)
    text_body = db.Column(db.Text)
    
    # Stats
    total_recipients = db.Column(db.Integer, default=0)
    emails_sent = db.Column(db.Integer, default=0)
    sent_count = db.Column(db.Integer, default=0)
    recipients_count = db.Column(db.Integer, default=0)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    sent_at = db.Column(db.DateTime)
    
    def __init__(self, **kwargs):
        if 'id' not in kwargs:
            kwargs['id'] = str(uuid.uuid4())
        super().__init__(**kwargs)
