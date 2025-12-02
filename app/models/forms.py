"""Forms Model - SendBaba"""
from app import db
from datetime import datetime
import uuid
import json


class Form(db.Model):
    __tablename__ = 'forms'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False, default='Untitled Form')
    form_type = db.Column(db.String(50), default='inline')
    status = db.Column(db.String(20), default='draft', index=True)
    fields = db.Column(db.Text, default='[]')
    design_settings = db.Column(db.Text, default='{}')
    trigger_type = db.Column(db.String(50), default='immediate')
    trigger_value = db.Column(db.String(50), nullable=True)
    success_action = db.Column(db.String(50), default='message')
    success_message = db.Column(db.Text, default='Thanks for subscribing!')
    success_redirect_url = db.Column(db.String(500), nullable=True)
    double_optin = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    submissions = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def fields_list(self):
        try:
            return json.loads(self.fields) if self.fields else []
        except:
            return []
    
    @property
    def design(self):
        try:
            d = json.loads(self.design_settings) if self.design_settings else {}
            return {
                'primary_color': d.get('primary_color', '#F97316'),
                'background_color': d.get('background_color', '#FFFFFF'),
                'text_color': d.get('text_color', '#1F2937'),
                'button_text': d.get('button_text', 'Subscribe')
            }
        except:
            return {'primary_color': '#F97316', 'background_color': '#FFFFFF', 'text_color': '#1F2937', 'button_text': 'Subscribe'}
    
    @property
    def conversion_rate(self):
        if not self.views or self.views == 0:
            return 0
        return round((self.submissions or 0) / self.views * 100, 1)
    
    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'form_type': self.form_type, 'status': self.status,
            'fields': self.fields_list, 'design': self.design, 'trigger_type': self.trigger_type,
            'trigger_value': self.trigger_value, 'success_action': self.success_action,
            'success_message': self.success_message, 'success_redirect_url': self.success_redirect_url,
            'double_optin': self.double_optin, 'views': self.views or 0, 'submissions': self.submissions or 0,
            'conversion_rate': self.conversion_rate,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_embed_code(self, base_url):
        if self.form_type == 'inline':
            return f'<div id="sb-form-{self.id}"></div>\n<script src="{base_url}/forms/embed/{self.id}.js" async></script>'
        return f'<script src="{base_url}/forms/embed/{self.id}.js" async></script>'


class FormSubmission(db.Model):
    __tablename__ = 'form_submissions'
    __table_args__ = {'extend_existing': True}
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    form_id = db.Column(db.String(36), nullable=False, index=True)
    data = db.Column(db.Text)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(500))
    confirmed = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def submission_data(self):
        try:
            return json.loads(self.data) if self.data else {}
        except:
            return {}
    
    def to_dict(self):
        return {
            'id': self.id, 'form_id': self.form_id, 'data': self.submission_data,
            'ip_address': self.ip_address, 'confirmed': self.confirmed,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
