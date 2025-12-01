from app import db
from datetime import datetime
import uuid

class Domain(db.Model):
    __tablename__ = 'domains'
    
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id = db.Column(db.String(36), nullable=False, index=True)
    created_by_user_id = db.Column(db.String(36), index=True)
    
    # Domain info
    domain_name = db.Column(db.String(255), nullable=False, index=True)
    
    # Verification
    dns_verified = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    
    # DKIM keys
    dkim_selector = db.Column(db.String(100), default='mail')
    dkim_private_key = db.Column(db.Text)
    dkim_public_key = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    verified_at = db.Column(db.DateTime)
    
    # Note: organization relationship comes from backref in Organization model
    
    def __init__(self, **kwargs):
        if 'id' not in kwargs:
            kwargs['id'] = str(uuid.uuid4())
        super().__init__(**kwargs)
    
    def to_dict(self):
        return {
            'id': self.id,
            'domain_name': self.domain_name,
            'dns_verified': self.dns_verified,
            'is_active': self.is_active,
            'dkim_selector': self.dkim_selector,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None
        }
