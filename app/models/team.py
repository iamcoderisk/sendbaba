"""Team Models for SendBaba"""
from app import db
from datetime import datetime
import uuid


class Department(db.Model):
    __tablename__ = 'departments'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.String(36), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(20), default='#6366F1')
    email_quota = db.Column(db.Integer, default=1000)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    members = db.relationship('TeamMember', backref='department', lazy='dynamic', foreign_keys='TeamMember.department_id')
    
    def __repr__(self):
        return f'<Department {self.name}>'


class TeamMember(db.Model):
    __tablename__ = 'team_members'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.String(36), nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    user_id = db.Column(db.String(36), nullable=True, index=True)
    
    email = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    role = db.Column(db.String(50), default='member')
    
    invitation_token = db.Column(db.String(255))
    invitation_accepted = db.Column(db.Boolean, default=False)
    invited_at = db.Column(db.DateTime, default=datetime.utcnow)
    accepted_at = db.Column(db.DateTime)
    
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    password_hash = db.Column(db.String(255))
    
    can_send_email = db.Column(db.Boolean, default=True)
    can_manage_contacts = db.Column(db.Boolean, default=True)
    can_manage_campaigns = db.Column(db.Boolean, default=True)
    can_view_analytics = db.Column(db.Boolean, default=True)
    can_manage_team = db.Column(db.Boolean, default=False)
    can_manage_billing = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return self.email.split('@')[0] if self.email else 'Unknown'
    
    def __repr__(self):
        return f'<TeamMember {self.email}>'


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.String(36), nullable=False, index=True)
    user_id = db.Column(db.String(36))
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50))
    resource_id = db.Column(db.String(36))
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<AuditLog {self.action}>'
