"""
Team and Department Models
Multi-tenant support for SendBaba
"""
from app import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class Department(db.Model):
    """Department model"""
    __tablename__ = 'departments'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(7), default='#6366F1')
    email_quota = db.Column(db.Integer, default=1000)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Department {self.name}>'


class TeamMember(db.Model):
    """Team Member model"""
    __tablename__ = 'team_members'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'))
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'))  # Changed to String(36)
    
    # User details
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    password_hash = db.Column(db.String(255))
    
    # Role and permissions
    role = db.Column(db.String(20), default='member')  # owner, admin, member, viewer
    
    # Permissions
    can_send_email = db.Column(db.Boolean, default=True)
    can_manage_contacts = db.Column(db.Boolean, default=True)
    can_manage_campaigns = db.Column(db.Boolean, default=True)
    can_view_analytics = db.Column(db.Boolean, default=True)
    can_manage_team = db.Column(db.Boolean, default=False)
    can_manage_billing = db.Column(db.Boolean, default=False)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    invitation_token = db.Column(db.String(100))
    invitation_accepted = db.Column(db.Boolean, default=False)
    
    # Stats
    emails_sent = db.Column(db.Integer, default=0)
    last_login = db.Column(db.DateTime)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship
    department = db.relationship('Department', backref='members')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email
    
    def __repr__(self):
        return f'<TeamMember {self.email}>'


class AuditLog(db.Model):
    """Audit log for team activities"""
    __tablename__ = 'audit_logs'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.Integer, primary_key=True)
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('team_members.id'))
    
    action = db.Column(db.String(100), nullable=False)
    resource_type = db.Column(db.String(50))
    resource_id = db.Column(db.Integer)
    details = db.Column(db.JSON)
    ip_address = db.Column(db.String(45))
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<AuditLog {self.action}>'
