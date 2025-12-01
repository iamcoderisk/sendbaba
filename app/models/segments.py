"""
SendBaba Segments Module - Database Models
Handles contact segmentation with query builder
"""
from datetime import datetime
import uuid
import json

try:
    from app import db
except ImportError:
    from flask_sqlalchemy import SQLAlchemy
    db = SQLAlchemy()


class Segment(db.Model):
    """Contact segment with dynamic query rules"""
    __tablename__ = 'segments'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), nullable=False)
    
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    
    # Segment type
    segment_type = db.Column(db.String(20), default='dynamic')  # dynamic, static
    
    # Query rules (JSON) - for dynamic segments
    rules = db.Column(db.Text, default='{}')
    rules_match = db.Column(db.String(10), default='all')  # all, any
    
    # Static member list (for static segments)
    static_members = db.Column(db.Text)  # JSON array of contact IDs
    
    # Caching
    cached_count = db.Column(db.Integer, default=0)
    last_calculated_at = db.Column(db.DateTime)
    
    # Display settings
    color = db.Column(db.String(20), default='purple')
    icon = db.Column(db.String(50), default='fa-users')
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.String(36))
    
    @property
    def rules_list(self):
        try:
            return json.loads(self.rules) if self.rules else {}
        except:
            return {}
    
    @property
    def static_member_ids(self):
        try:
            return json.loads(self.static_members) if self.static_members else []
        except:
            return []
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'segment_type': self.segment_type,
            'rules': self.rules_list,
            'rules_match': self.rules_match,
            'cached_count': self.cached_count,
            'color': self.color,
            'icon': self.icon,
            'is_active': self.is_active,
            'last_calculated_at': self.last_calculated_at.isoformat() if self.last_calculated_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class SegmentCondition(db.Model):
    """Individual segment condition/rule"""
    __tablename__ = 'segment_conditions'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    segment_id = db.Column(db.String(36), db.ForeignKey('segments.id'), nullable=False)
    
    # Condition definition
    field = db.Column(db.String(100), nullable=False)  # email, first_name, tag, custom_field, etc
    operator = db.Column(db.String(50), nullable=False)  # equals, contains, starts_with, greater_than, etc
    value = db.Column(db.Text)
    
    # For nested conditions
    group_id = db.Column(db.String(36))
    group_operator = db.Column(db.String(10))  # and, or
    
    sort_order = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'segment_id': self.segment_id,
            'field': self.field,
            'operator': self.operator,
            'value': self.value,
            'group_id': self.group_id,
            'group_operator': self.group_operator
        }


# Available fields and operators for segment builder
SEGMENT_FIELDS = [
    {'field': 'email', 'label': 'Email', 'type': 'string'},
    {'field': 'first_name', 'label': 'First Name', 'type': 'string'},
    {'field': 'last_name', 'label': 'Last Name', 'type': 'string'},
    {'field': 'phone', 'label': 'Phone', 'type': 'string'},
    {'field': 'tags', 'label': 'Tags', 'type': 'tags'},
    {'field': 'status', 'label': 'Status', 'type': 'select', 'options': ['active', 'unsubscribed', 'bounced', 'complained']},
    {'field': 'source', 'label': 'Source', 'type': 'string'},
    {'field': 'created_at', 'label': 'Date Added', 'type': 'date'},
    {'field': 'last_email_at', 'label': 'Last Email Sent', 'type': 'date'},
    {'field': 'last_opened_at', 'label': 'Last Opened', 'type': 'date'},
    {'field': 'last_clicked_at', 'label': 'Last Clicked', 'type': 'date'},
    {'field': 'email_count', 'label': 'Emails Received', 'type': 'number'},
    {'field': 'open_count', 'label': 'Total Opens', 'type': 'number'},
    {'field': 'click_count', 'label': 'Total Clicks', 'type': 'number'},
    {'field': 'open_rate', 'label': 'Open Rate', 'type': 'percentage'},
    {'field': 'click_rate', 'label': 'Click Rate', 'type': 'percentage'},
]

SEGMENT_OPERATORS = {
    'string': [
        {'value': 'equals', 'label': 'equals'},
        {'value': 'not_equals', 'label': 'does not equal'},
        {'value': 'contains', 'label': 'contains'},
        {'value': 'not_contains', 'label': 'does not contain'},
        {'value': 'starts_with', 'label': 'starts with'},
        {'value': 'ends_with', 'label': 'ends with'},
        {'value': 'is_empty', 'label': 'is empty'},
        {'value': 'is_not_empty', 'label': 'is not empty'},
    ],
    'number': [
        {'value': 'equals', 'label': 'equals'},
        {'value': 'not_equals', 'label': 'does not equal'},
        {'value': 'greater_than', 'label': 'is greater than'},
        {'value': 'less_than', 'label': 'is less than'},
        {'value': 'greater_or_equal', 'label': 'is greater than or equal'},
        {'value': 'less_or_equal', 'label': 'is less than or equal'},
        {'value': 'between', 'label': 'is between'},
    ],
    'date': [
        {'value': 'on', 'label': 'is on'},
        {'value': 'before', 'label': 'is before'},
        {'value': 'after', 'label': 'is after'},
        {'value': 'between', 'label': 'is between'},
        {'value': 'in_last', 'label': 'in the last'},
        {'value': 'not_in_last', 'label': 'not in the last'},
        {'value': 'is_empty', 'label': 'is empty'},
        {'value': 'is_not_empty', 'label': 'is not empty'},
    ],
    'tags': [
        {'value': 'has_tag', 'label': 'has tag'},
        {'value': 'not_has_tag', 'label': 'does not have tag'},
        {'value': 'has_any_tag', 'label': 'has any of tags'},
        {'value': 'has_all_tags', 'label': 'has all of tags'},
    ],
    'select': [
        {'value': 'equals', 'label': 'equals'},
        {'value': 'not_equals', 'label': 'does not equal'},
        {'value': 'in', 'label': 'is any of'},
        {'value': 'not_in', 'label': 'is not any of'},
    ],
    'percentage': [
        {'value': 'equals', 'label': 'equals'},
        {'value': 'greater_than', 'label': 'is greater than'},
        {'value': 'less_than', 'label': 'is less than'},
        {'value': 'between', 'label': 'is between'},
    ],
}
