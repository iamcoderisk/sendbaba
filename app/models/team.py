"""
Team Models for SendBaba - Department, TeamMember, AuditLog
"""
from app import db
from datetime import datetime
import uuid


class Department(db.Model):
    """Department model for organizing team members"""
    __tablename__ = 'departments'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.String(36), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(20), default='#6366F1')
    email_quota = db.Column(db.Integer, default=1000)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    members = db.relationship('TeamMember', backref='department', lazy='dynamic')
    
    def __repr__(self):
        return f'<Department {self.name}>'


class TeamMember(db.Model):
    """Team Member model"""
    __tablename__ = 'team_members'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.String(36), nullable=False, index=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), index=True)
    user_id = db.Column(db.String(36), index=True)
    
    email = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    role = db.Column(db.String(50), default='member')
    
    can_send_email = db.Column(db.Boolean, default=True)
    can_manage_contacts = db.Column(db.Boolean, default=True)
    can_manage_campaigns = db.Column(db.Boolean, default=True)
    can_view_analytics = db.Column(db.Boolean, default=True)
    can_manage_team = db.Column(db.Boolean, default=False)
    can_manage_billing = db.Column(db.Boolean, default=False)
    
    invitation_token = db.Column(db.String(255))
    invitation_accepted = db.Column(db.Boolean, default=False)
    password_hash = db.Column(db.String(255))
    
    is_active = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    
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
        return self.email.split('@')[0]
    
    def __repr__(self):
        return f'<TeamMember {self.email}>'


class AuditLog(db.Model):
    """Audit log for tracking team actions"""
    __tablename__ = 'audit_logs'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.String(36), nullable=False, index=True)
    user_id = db.Column(db.String(36), index=True)
    team_member_id = db.Column(db.Integer, db.ForeignKey('team_members.id'), index=True)
    
    action = db.Column(db.String(100), nullable=False)
    entity_type = db.Column(db.String(50))
    entity_id = db.Column(db.String(36))
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    team_member = db.relationship('TeamMember', backref='audit_logs')
    
    def __repr__(self):
        return f'<AuditLog {self.action}>'
