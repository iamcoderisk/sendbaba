"""API Key Model"""
from app import db
from datetime import datetime
import uuid
import secrets

class APIKey(db.Model):
    __tablename__ = 'api_keys'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    
    name = db.Column(db.String(100), nullable=False)
    key_prefix = db.Column(db.String(10), nullable=False)  # First few chars for identification
    key_hash = db.Column(db.String(255), nullable=False)   # Hashed full key
    
    permissions = db.Column(db.JSON, default=list)  # ['send', 'contacts', 'campaigns', etc.]
    rate_limit = db.Column(db.Integer, default=1000)  # requests per minute
    
    is_active = db.Column(db.Boolean, default=True, index=True)
    last_used_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships with explicit foreign keys
    organization = db.relationship('Organization', backref=db.backref('api_keys', lazy='dynamic'), foreign_keys=[organization_id])
    user = db.relationship('User', backref=db.backref('api_keys', lazy='dynamic'), foreign_keys=[user_id])
    
    @staticmethod
    def generate_key():
        """Generate a new API key"""
        return f"sb_live_{secrets.token_urlsafe(32)}"
    
    @staticmethod
    def hash_key(key):
        """Hash an API key for storage"""
        import hashlib
        return hashlib.sha256(key.encode()).hexdigest()
    
    def __repr__(self):
        return f'<APIKey {self.name} ({self.key_prefix}...)>'


class SMTPCredential(db.Model):
    """SMTP Credentials for API users"""
    __tablename__ = 'smtp_credentials'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), db.ForeignKey('organizations.id'), nullable=False, index=True)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=True)
    
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(255), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Limits
    daily_limit = db.Column(db.Integer, default=1000)
    hourly_limit = db.Column(db.Integer, default=100)
    emails_sent_today = db.Column(db.Integer, default=0)
    
    is_active = db.Column(db.Boolean, default=True, index=True)
    last_used_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    organization = db.relationship('Organization', backref=db.backref('smtp_credentials', lazy='dynamic'), foreign_keys=[organization_id])
    user = db.relationship('User', backref=db.backref('smtp_credentials', lazy='dynamic'), foreign_keys=[user_id])
    
    @staticmethod
    def generate_password():
        """Generate a secure SMTP password"""
        return secrets.token_urlsafe(24)
    
    @staticmethod
    def hash_password(password):
        """Hash password for storage"""
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()
    
    def __repr__(self):
        return f'<SMTPCredential {self.username}>'
