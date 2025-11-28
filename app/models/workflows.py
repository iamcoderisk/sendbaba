"""
SendBaba Workflows Module - Database Models
Handles email automation workflows
"""
from datetime import datetime
import uuid
import json

try:
    from app import db
except ImportError:
    from flask_sqlalchemy import SQLAlchemy
    db = SQLAlchemy()


class Workflow(db.Model):
    """Email automation workflow"""
    __tablename__ = 'workflows'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False)
    
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    
    # Trigger configuration
    trigger_type = db.Column(db.String(50), nullable=False)  # contact_added, tag_added, form_submitted, date_based, api_trigger
    trigger_config = db.Column(db.Text, default='{}')  # JSON config for trigger
    
    # Workflow steps (JSON array)
    steps = db.Column(db.Text, default='[]')
    
    # Settings
    entry_limit = db.Column(db.Integer, default=0)  # 0 = unlimited
    entry_limit_period = db.Column(db.String(20))  # per_day, per_week, per_month
    allow_reentry = db.Column(db.Boolean, default=False)
    reentry_delay_days = db.Column(db.Integer, default=0)
    
    # Goal settings
    goal_type = db.Column(db.String(50))  # email_opened, link_clicked, tag_added, etc
    goal_config = db.Column(db.Text, default='{}')
    remove_on_goal = db.Column(db.Boolean, default=True)
    
    # Status
    status = db.Column(db.String(20), default='draft')  # draft, active, paused, archived
    
    # Stats
    total_enrolled = db.Column(db.Integer, default=0)
    active_contacts = db.Column(db.Integer, default=0)
    completed = db.Column(db.Integer, default=0)
    goal_reached = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    activated_at = db.Column(db.DateTime)
    
    # Relationships
    enrollments = db.relationship('WorkflowEnrollment', backref='workflow', lazy='dynamic', cascade='all, delete-orphan')
    logs = db.relationship('WorkflowLog', backref='workflow', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def steps_list(self):
        try:
            return json.loads(self.steps) if self.steps else []
        except:
            return []
    
    @property
    def trigger_configuration(self):
        try:
            return json.loads(self.trigger_config) if self.trigger_config else {}
        except:
            return {}
    
    @property
    def conversion_rate(self):
        if self.total_enrolled == 0:
            return 0
        return round((self.goal_reached / self.total_enrolled) * 100, 2)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'trigger_type': self.trigger_type,
            'trigger_config': self.trigger_configuration,
            'steps': self.steps_list,
            'status': self.status,
            'total_enrolled': self.total_enrolled,
            'active_contacts': self.active_contacts,
            'completed': self.completed,
            'goal_reached': self.goal_reached,
            'conversion_rate': self.conversion_rate,
            'allow_reentry': self.allow_reentry,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'activated_at': self.activated_at.isoformat() if self.activated_at else None
        }


class WorkflowEnrollment(db.Model):
    """Tracks contacts enrolled in workflows"""
    __tablename__ = 'workflow_enrollments'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = db.Column(db.String(36), db.ForeignKey('workflows.id'), nullable=False)
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'), nullable=False)
    
    # Current position in workflow
    current_step = db.Column(db.Integer, default=0)
    
    # Status
    status = db.Column(db.String(20), default='active')  # active, paused, completed, exited, goal_reached
    
    # Timing
    next_action_at = db.Column(db.DateTime)
    
    # Entry tracking
    entry_count = db.Column(db.Integer, default=1)
    
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    exited_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'workflow_id': self.workflow_id,
            'contact_id': self.contact_id,
            'current_step': self.current_step,
            'status': self.status,
            'next_action_at': self.next_action_at.isoformat() if self.next_action_at else None,
            'enrolled_at': self.enrolled_at.isoformat() if self.enrolled_at else None
        }


class WorkflowLog(db.Model):
    """Workflow execution logs"""
    __tablename__ = 'workflow_logs'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workflow_id = db.Column(db.String(36), db.ForeignKey('workflows.id'), nullable=False)
    enrollment_id = db.Column(db.String(36), db.ForeignKey('workflow_enrollments.id'))
    contact_id = db.Column(db.String(36))
    
    # Action details
    action_type = db.Column(db.String(50), nullable=False)  # enrolled, email_sent, wait_started, condition_checked, completed, etc
    step_index = db.Column(db.Integer)
    
    # Result
    success = db.Column(db.Boolean, default=True)
    message = db.Column(db.Text)
    details = db.Column(db.Text)  # JSON for additional data
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'workflow_id': self.workflow_id,
            'contact_id': self.contact_id,
            'action_type': self.action_type,
            'step_index': self.step_index,
            'success': self.success,
            'message': self.message,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class WorkflowTemplate(db.Model):
    """Pre-built workflow templates"""
    __tablename__ = 'workflow_templates'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(db.String(50))  # welcome, nurture, abandoned_cart, birthday, reengagement
    
    # Template data
    trigger_type = db.Column(db.String(50), nullable=False)
    trigger_config = db.Column(db.Text, default='{}')
    steps = db.Column(db.Text, default='[]')
    
    # Display
    icon = db.Column(db.String(50), default='fa-cogs')
    color = db.Column(db.String(20), default='purple')
    
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        try:
            steps_data = json.loads(self.steps) if self.steps else []
        except:
            steps_data = []
        
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'trigger_type': self.trigger_type,
            'steps': steps_data,
            'icon': self.icon,
            'color': self.color
        }
