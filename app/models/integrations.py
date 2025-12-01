"""
SendBaba Integrations Module - Database Models
Handles third-party integrations (Shopify, WooCommerce, Stripe, etc.)
"""
from datetime import datetime
import uuid
import json

try:
    from app import db
except ImportError:
    from flask_sqlalchemy import SQLAlchemy
    db = SQLAlchemy()


class Integration(db.Model):
    """Third-party integration configuration"""
    __tablename__ = 'integrations'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), nullable=False)
    
    # Integration type
    integration_type = db.Column(db.String(50), nullable=False)  # shopify, woocommerce, stripe, zapier, etc
    name = db.Column(db.String(255))  # Custom name for this integration
    
    # Authentication
    api_key = db.Column(db.String(500))
    api_secret = db.Column(db.String(500))
    access_token = db.Column(db.Text)
    refresh_token = db.Column(db.Text)
    token_expires_at = db.Column(db.DateTime)
    
    # Connection details
    store_url = db.Column(db.String(500))  # For Shopify/WooCommerce
    store_id = db.Column(db.String(100))
    webhook_secret = db.Column(db.String(255))
    
    # Configuration (JSON)
    config = db.Column(db.Text, default='{}')
    
    # Sync settings
    sync_contacts = db.Column(db.Boolean, default=True)
    sync_orders = db.Column(db.Boolean, default=True)
    sync_products = db.Column(db.Boolean, default=False)
    auto_tag_customers = db.Column(db.Boolean, default=True)
    default_tags = db.Column(db.String(500))  # Comma-separated tags for imported contacts
    
    # Mapping configuration
    field_mapping = db.Column(db.Text, default='{}')  # Map external fields to contact fields
    
    # Status
    status = db.Column(db.String(20), default='pending')  # pending, active, error, disabled
    last_sync_at = db.Column(db.DateTime)
    last_error = db.Column(db.Text)
    
    # Stats
    contacts_synced = db.Column(db.Integer, default=0)
    orders_synced = db.Column(db.Integer, default=0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    sync_logs = db.relationship('IntegrationSyncLog', backref='integration', lazy='dynamic', cascade='all, delete-orphan')
    
    @property
    def configuration(self):
        try:
            return json.loads(self.config) if self.config else {}
        except:
            return {}
    
    @property
    def field_map(self):
        try:
            return json.loads(self.field_mapping) if self.field_mapping else {}
        except:
            return {}
    
    def to_dict(self, include_secrets=False):
        data = {
            'id': self.id,
            'integration_type': self.integration_type,
            'name': self.name,
            'store_url': self.store_url,
            'status': self.status,
            'sync_contacts': self.sync_contacts,
            'sync_orders': self.sync_orders,
            'auto_tag_customers': self.auto_tag_customers,
            'default_tags': self.default_tags,
            'contacts_synced': self.contacts_synced,
            'orders_synced': self.orders_synced,
            'last_sync_at': self.last_sync_at.isoformat() if self.last_sync_at else None,
            'last_error': self.last_error,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
        if include_secrets:
            data['api_key'] = self.api_key
            data['api_secret'] = self.api_secret
        return data


class IntegrationSyncLog(db.Model):
    """Integration sync activity log"""
    __tablename__ = 'integration_sync_logs'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_id = db.Column(db.String(36), db.ForeignKey('integrations.id'), nullable=False)
    
    # Sync details
    sync_type = db.Column(db.String(50), nullable=False)  # full, incremental, webhook
    entity_type = db.Column(db.String(50))  # contacts, orders, products
    
    # Results
    status = db.Column(db.String(20), default='running')  # running, completed, failed
    records_processed = db.Column(db.Integer, default=0)
    records_created = db.Column(db.Integer, default=0)
    records_updated = db.Column(db.Integer, default=0)
    records_failed = db.Column(db.Integer, default=0)
    
    # Error tracking
    error_message = db.Column(db.Text)
    error_details = db.Column(db.Text)  # JSON
    
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'integration_id': self.integration_id,
            'sync_type': self.sync_type,
            'entity_type': self.entity_type,
            'status': self.status,
            'records_processed': self.records_processed,
            'records_created': self.records_created,
            'records_updated': self.records_updated,
            'records_failed': self.records_failed,
            'error_message': self.error_message,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


class IntegrationWebhook(db.Model):
    """Incoming webhooks from integrations"""
    __tablename__ = 'integration_webhooks'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    integration_id = db.Column(db.String(36), db.ForeignKey('integrations.id'), nullable=False)
    
    # Webhook details
    event_type = db.Column(db.String(100), nullable=False)
    payload = db.Column(db.Text)
    headers = db.Column(db.Text)
    
    # Processing
    status = db.Column(db.String(20), default='pending')  # pending, processed, failed, ignored
    processed_at = db.Column(db.DateTime)
    error_message = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'integration_id': self.integration_id,
            'event_type': self.event_type,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


# Integration type definitions
INTEGRATION_TYPES = {
    'shopify': {
        'name': 'Shopify',
        'description': 'Sync customers and orders from your Shopify store',
        'icon': 'fab fa-shopify',
        'color': 'green',
        'features': ['Customer sync', 'Order sync', 'Abandoned cart', 'Product sync'],
        'auth_type': 'oauth',
        'required_fields': ['store_url'],
        'webhook_events': ['customers/create', 'customers/update', 'orders/create', 'orders/paid', 'checkouts/create']
    },
    'woocommerce': {
        'name': 'WooCommerce',
        'description': 'Sync customers and orders from your WooCommerce store',
        'icon': 'fab fa-wordpress',
        'color': 'purple',
        'features': ['Customer sync', 'Order sync', 'Abandoned cart'],
        'auth_type': 'api_key',
        'required_fields': ['store_url', 'api_key', 'api_secret'],
        'webhook_events': ['customer.created', 'customer.updated', 'order.created', 'order.completed']
    },
    'stripe': {
        'name': 'Stripe',
        'description': 'Sync customers and payment data from Stripe',
        'icon': 'fab fa-stripe',
        'color': 'blue',
        'features': ['Customer sync', 'Payment events', 'Subscription tracking'],
        'auth_type': 'api_key',
        'required_fields': ['api_key'],
        'webhook_events': ['customer.created', 'customer.updated', 'invoice.paid', 'subscription.created']
    },
    'zapier': {
        'name': 'Zapier',
        'description': 'Connect with 5000+ apps via Zapier',
        'icon': 'fas fa-bolt',
        'color': 'orange',
        'features': ['Trigger on events', 'Action: Add contact', 'Action: Send email'],
        'auth_type': 'webhook',
        'required_fields': []
    },
    'wordpress': {
        'name': 'WordPress',
        'description': 'Sync users and form submissions from WordPress',
        'icon': 'fab fa-wordpress',
        'color': 'blue',
        'features': ['User sync', 'Form integration', 'Comment notifications'],
        'auth_type': 'api_key',
        'required_fields': ['store_url', 'api_key']
    },
    'custom_webhook': {
        'name': 'Custom Webhook',
        'description': 'Receive data from any system via webhooks',
        'icon': 'fas fa-code',
        'color': 'gray',
        'features': ['Custom events', 'Flexible payload', 'Field mapping'],
        'auth_type': 'webhook',
        'required_fields': []
    }
}
