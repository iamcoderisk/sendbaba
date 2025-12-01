"""
SendBaba Forms Module - Database Models
Handles signup forms, popups, slide-ins, and sticky bars
"""
from datetime import datetime
import uuid
import json

try:
    from app import db
except ImportError:
    from flask_sqlalchemy import SQLAlchemy
    db = SQLAlchemy()


class Form(db.Model):
    """Signup form model"""
    __tablename__ = 'forms'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), nullable=False)
    
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    form_type = db.Column(db.String(50), default='inline')  # inline, popup, slide_in, sticky_bar
    
    # Design settings (JSON)
    design_settings = db.Column(db.Text, default='{}')
    
    # Form fields (JSON array)
    fields = db.Column(db.Text, default='[]')
    
    # Behavior settings
    trigger_type = db.Column(db.String(50), default='immediate')
    trigger_value = db.Column(db.String(100))
    show_on_pages = db.Column(db.Text, default='*')
    
    # Success actions
    success_action = db.Column(db.String(50), default='message')
    success_message = db.Column(db.Text, default='Thanks for subscribing!')
    success_redirect_url = db.Column(db.String(500))
    
    # Double opt-in
    double_optin = db.Column(db.Boolean, default=False)
    confirmation_email_subject = db.Column(db.String(255))
    confirmation_email_body = db.Column(db.Text)
    
    # Integration
    add_to_list_id = db.Column(db.String(36))
    add_tags = db.Column(db.String(500))
    
    # Status
    status = db.Column(db.String(20), default='draft')
    
    # Stats
    views = db.Column(db.Integer, default=0)
    submissions = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    submissions_rel = db.relationship('FormSubmission', backref='form', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def conversion_rate(self):
        if self.views == 0:
            return 0
        return round((self.submissions / self.views) * 100, 2)
    
    @property
    def fields_list(self):
        try:
            return json.loads(self.fields) if self.fields else []
        except:
            return []
    
    @property
    def design(self):
        try:
            return json.loads(self.design_settings) if self.design_settings else {}
        except:
            return {}
    
    def get_embed_code(self, base_url='https://sendbaba.com'):
        if self.form_type == 'inline':
            return f'<div id="sb-form-{self.id}"></div>\n<script src="{base_url}/forms/embed/{self.id}.js" async></script>'
        return f'<script src="{base_url}/forms/embed/{self.id}.js" async></script>'
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'form_type': self.form_type,
            'status': self.status,
            'views': self.views,
            'submissions': self.submissions,
            'conversion_rate': self.conversion_rate,
            'fields': self.fields_list,
            'design': self.design,
            'trigger_type': self.trigger_type,
            'trigger_value': self.trigger_value,
            'success_action': self.success_action,
            'success_message': self.success_message,
            'double_optin': self.double_optin,
            'add_to_list_id': self.add_to_list_id,
            'add_tags': self.add_tags,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class FormSubmission(db.Model):
    """Form submission tracking"""
    __tablename__ = 'form_submissions'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    form_id = db.Column(db.String(36), db.ForeignKey('forms.id'), nullable=False)
    
    data = db.Column(db.Text, nullable=False)
    
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    referrer = db.Column(db.String(500))
    page_url = db.Column(db.String(500))
    
    contact_id = db.Column(db.String(36))
    
    confirmed = db.Column(db.Boolean, default=False)
    confirmation_token = db.Column(db.String(100))
    confirmed_at = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def submission_data(self):
        try:
            return json.loads(self.data) if self.data else {}
        except:
            return {}
    
    def to_dict(self):
        return {
            'id': self.id,
            'form_id': self.form_id,
            'data': self.submission_data,
            'ip_address': self.ip_address,
            'confirmed': self.confirmed,
            'contact_id': self.contact_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
