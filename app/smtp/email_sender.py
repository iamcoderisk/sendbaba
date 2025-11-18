"""
Multi-tenant Email Sender
Uses verified domains for each organization
"""
import sys
sys.path.insert(0, '/opt/sendbaba-staging')

from app import create_app, db
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

app = create_app()


def get_verified_sender(organization_id: str) -> str:
    """Get verified domain for organization"""
    with app.app_context():
        try:
            # Get verified domain
            result = db.session.execute(text("""
                SELECT domain_name 
                FROM domains 
                WHERE organization_id = :org_id 
                AND dns_verified = true
                ORDER BY created_at DESC
                LIMIT 1
            """), {'org_id': organization_id})
            
            row = result.fetchone()
            
            if row:
                domain = row[0]
                sender = f"noreply@{domain}"
                logger.info(f"Using verified domain: {sender}")
                return sender
            else:
                # Fallback to default
                logger.warning(f"No verified domain for org {organization_id}, using default")
                return "test@myakama.com"
                
        except Exception as e:
            logger.error(f"Error getting verified sender: {e}")
            return "test@myakama.com"


def prepare_email_data(email_row) -> dict:
    """Prepare email data from database row"""
    email_id, org_id, sender, recipient, subject, html_body, text_body, campaign_id = email_row
    
    # Use verified domain if sender is default
    if not sender or sender == 'noreply@sendbaba.com':
        sender = get_verified_sender(org_id)
    
    return {
        'id': email_id,
        'from': sender,
        'to': recipient,
        'subject': subject,
        'html_body': html_body or '',
        'text_body': text_body or '',
        'body': html_body or text_body or 'Email from SendBaba',
        'campaign_id': campaign_id
    }
