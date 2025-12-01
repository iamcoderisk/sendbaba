"""
Team Member Model for SendBaba
"""
from app import db
from datetime import datetime
import uuid


class TeamMember(db.Model):
    __tablename__ = 'team_members'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), index=True)
    user_id = db.Column(db.String(36), index=True)
    email = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), default='member')
    department_id = db.Column(db.String(36))
    invitation_token = db.Column(db.String(255))
    invitation_accepted = db.Column(db.Boolean, default=False)
    invited_at = db.Column(db.DateTime)
    accepted_at = db.Column(db.DateTime)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, email=None, organization_id=None, **kwargs):
        if 'id' not in kwargs:
            kwargs['id'] = str(uuid.uuid4())
        if email:
            kwargs['email'] = email.lower().strip()
        if organization_id:
            kwargs['organization_id'] = organization_id
        super().__init__(**kwargs)
    
    def __repr__(self):
        return f'<TeamMember {self.email}>'
