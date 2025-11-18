"""
Models package
Import order matters for SQLAlchemy relationships
"""
# Import base models first
from app.models.organization import Organization
from app.models.user import User

# Then dependent models
from app.models.domain import Domain
from app.models.contact import Contact, ContactList, BulkImport
from app.models.email import (
    Email, 
    EmailTracking, 
    EmailClick, 
    EmailOpen, 
    EmailBounce, 
    EmailUnsubscribe,
    DNSRecord
)
from app.models.campaign import Campaign
from app.models.segment import Segment
from app.models.suppression import SuppressionList

__all__ = [
    'Organization',
    'User',
    'Domain',
    'Contact',
    'ContactList',
    'BulkImport',
    'Email',
    'EmailTracking',
    'EmailClick',
    'EmailOpen',
    'EmailBounce',
    'EmailUnsubscribe',
    'DNSRecord',
    'Campaign',
    'Segment',
    'SuppressionList'
]
