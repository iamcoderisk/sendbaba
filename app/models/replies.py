"""
SendBaba Replies Module - Database Models
Handles email reply tracking and AI analysis
"""
from datetime import datetime
import uuid
import json

try:
    from app import db
except ImportError:
    from flask_sqlalchemy import SQLAlchemy
    db = SQLAlchemy()


class EmailReply(db.Model):
    """Incoming email reply tracking"""
    __tablename__ = 'email_replies'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), nullable=False)
    
    # Original email reference
    original_email_id = db.Column(db.String(36))
    campaign_id = db.Column(db.String(36))
    contact_id = db.Column(db.String(36), db.ForeignKey('contacts.id'))
    
    # Reply details
    from_email = db.Column(db.String(255), nullable=False)
    from_name = db.Column(db.String(255))
    to_email = db.Column(db.String(255))
    subject = db.Column(db.String(500))
    body_text = db.Column(db.Text)
    body_html = db.Column(db.Text)
    
    # Email headers
    message_id = db.Column(db.String(255))
    in_reply_to = db.Column(db.String(255))
    references = db.Column(db.Text)
    
    # Attachments
    has_attachments = db.Column(db.Boolean, default=False)
    attachment_count = db.Column(db.Integer, default=0)
    attachments = db.Column(db.Text)  # JSON array of attachment metadata
    
    # AI Analysis
    sentiment = db.Column(db.String(20))  # positive, negative, neutral
    sentiment_score = db.Column(db.Float)  # -1 to 1
    intent = db.Column(db.String(50))  # inquiry, complaint, feedback, purchase_intent, unsubscribe, other
    urgency = db.Column(db.String(20))  # low, medium, high, critical
    topics = db.Column(db.Text)  # JSON array of detected topics
    key_phrases = db.Column(db.Text)  # JSON array
    suggested_response = db.Column(db.Text)
    ai_summary = db.Column(db.Text)
    
    # Classification
    category = db.Column(db.String(50))  # support, sales, billing, feedback, spam, other
    is_auto_reply = db.Column(db.Boolean, default=False)
    is_out_of_office = db.Column(db.Boolean, default=False)
    is_bounce = db.Column(db.Boolean, default=False)
    
    # Status
    status = db.Column(db.String(20), default='unread')  # unread, read, replied, archived, spam
    starred = db.Column(db.Boolean, default=False)
    
    # Assignment
    assigned_to = db.Column(db.String(36))  # Team member ID
    assigned_at = db.Column(db.DateTime)
    
    # Response tracking
    replied_at = db.Column(db.DateTime)
    reply_time_seconds = db.Column(db.Integer)  # Time to first reply
    
    received_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def topics_list(self):
        try:
            return json.loads(self.topics) if self.topics else []
        except:
            return []
    
    @property
    def key_phrases_list(self):
        try:
            return json.loads(self.key_phrases) if self.key_phrases else []
        except:
            return []
    
    @property
    def attachments_list(self):
        try:
            return json.loads(self.attachments) if self.attachments else []
        except:
            return []
    
    def to_dict(self):
        return {
            'id': self.id,
            'from_email': self.from_email,
            'from_name': self.from_name,
            'subject': self.subject,
            'body_text': self.body_text,
            'body_html': self.body_html,
            'sentiment': self.sentiment,
            'sentiment_score': self.sentiment_score,
            'intent': self.intent,
            'urgency': self.urgency,
            'topics': self.topics_list,
            'key_phrases': self.key_phrases_list,
            'suggested_response': self.suggested_response,
            'ai_summary': self.ai_summary,
            'category': self.category,
            'status': self.status,
            'starred': self.starred,
            'is_auto_reply': self.is_auto_reply,
            'is_out_of_office': self.is_out_of_office,
            'has_attachments': self.has_attachments,
            'attachment_count': self.attachment_count,
            'campaign_id': self.campaign_id,
            'contact_id': self.contact_id,
            'assigned_to': self.assigned_to,
            'received_at': self.received_at.isoformat() if self.received_at else None,
            'replied_at': self.replied_at.isoformat() if self.replied_at else None
        }


class ReplyTemplate(db.Model):
    """Canned response templates"""
    __tablename__ = 'reply_templates'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), nullable=False)
    
    name = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(500))
    body = db.Column(db.Text, nullable=False)
    
    # Categorization
    category = db.Column(db.String(50))  # support, sales, billing, etc
    tags = db.Column(db.String(500))  # Comma-separated
    
    # Auto-suggest settings
    auto_suggest = db.Column(db.Boolean, default=False)
    trigger_keywords = db.Column(db.Text)  # JSON array
    trigger_intents = db.Column(db.Text)  # JSON array
    
    # Usage stats
    usage_count = db.Column(db.Integer, default=0)
    
    # Settings
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    
    created_by = db.Column(db.String(36))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'subject': self.subject,
            'body': self.body,
            'category': self.category,
            'tags': self.tags,
            'auto_suggest': self.auto_suggest,
            'usage_count': self.usage_count,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ReplyAnalytics(db.Model):
    """Aggregated reply analytics"""
    __tablename__ = 'reply_analytics'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), nullable=False)
    
    # Time period
    date = db.Column(db.Date, nullable=False)
    
    # Counts
    total_replies = db.Column(db.Integer, default=0)
    positive_replies = db.Column(db.Integer, default=0)
    negative_replies = db.Column(db.Integer, default=0)
    neutral_replies = db.Column(db.Integer, default=0)
    
    # By intent
    inquiry_count = db.Column(db.Integer, default=0)
    complaint_count = db.Column(db.Integer, default=0)
    feedback_count = db.Column(db.Integer, default=0)
    purchase_intent_count = db.Column(db.Integer, default=0)
    unsubscribe_count = db.Column(db.Integer, default=0)
    
    # Response metrics
    avg_response_time = db.Column(db.Float)  # seconds
    replied_count = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat() if self.date else None,
            'total_replies': self.total_replies,
            'positive_replies': self.positive_replies,
            'negative_replies': self.negative_replies,
            'neutral_replies': self.neutral_replies,
            'inquiry_count': self.inquiry_count,
            'complaint_count': self.complaint_count,
            'feedback_count': self.feedback_count,
            'purchase_intent_count': self.purchase_intent_count,
            'avg_response_time': self.avg_response_time,
            'replied_count': self.replied_count
        }


# AI Analysis categories and options
SENTIMENT_TYPES = ['positive', 'negative', 'neutral']

INTENT_TYPES = [
    {'value': 'inquiry', 'label': 'Inquiry', 'icon': 'fa-question-circle', 'color': 'blue'},
    {'value': 'complaint', 'label': 'Complaint', 'icon': 'fa-exclamation-circle', 'color': 'red'},
    {'value': 'feedback', 'label': 'Feedback', 'icon': 'fa-comment', 'color': 'purple'},
    {'value': 'purchase_intent', 'label': 'Purchase Intent', 'icon': 'fa-shopping-cart', 'color': 'green'},
    {'value': 'support', 'label': 'Support Request', 'icon': 'fa-life-ring', 'color': 'orange'},
    {'value': 'unsubscribe', 'label': 'Unsubscribe Request', 'icon': 'fa-user-minus', 'color': 'gray'},
    {'value': 'thank_you', 'label': 'Thank You', 'icon': 'fa-heart', 'color': 'pink'},
    {'value': 'other', 'label': 'Other', 'icon': 'fa-envelope', 'color': 'gray'}
]

URGENCY_LEVELS = [
    {'value': 'low', 'label': 'Low', 'color': 'green'},
    {'value': 'medium', 'label': 'Medium', 'color': 'yellow'},
    {'value': 'high', 'label': 'High', 'color': 'orange'},
    {'value': 'critical', 'label': 'Critical', 'color': 'red'}
]

REPLY_CATEGORIES = [
    {'value': 'support', 'label': 'Support'},
    {'value': 'sales', 'label': 'Sales'},
    {'value': 'billing', 'label': 'Billing'},
    {'value': 'feedback', 'label': 'Feedback'},
    {'value': 'spam', 'label': 'Spam'},
    {'value': 'other', 'label': 'Other'}
]
