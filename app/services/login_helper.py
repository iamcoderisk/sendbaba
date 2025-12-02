"""
Login Helper - Captures login information and sends notifications
"""
from datetime import datetime
from flask import request
from user_agents import parse
import requests
import logging

logger = logging.getLogger(__name__)


def get_login_info(request_obj=None):
    """Extract login information from request"""
    if request_obj is None:
        request_obj = request
    
    # Get IP address
    ip_address = request_obj.headers.get('X-Forwarded-For', request_obj.remote_addr)
    if ',' in str(ip_address):
        ip_address = ip_address.split(',')[0].strip()
    
    # Parse user agent
    user_agent_string = request_obj.headers.get('User-Agent', '')
    user_agent = parse(user_agent_string)
    
    # Device info
    if user_agent.is_mobile:
        device = f"Mobile ({user_agent.device.family})"
    elif user_agent.is_tablet:
        device = f"Tablet ({user_agent.device.family})"
    elif user_agent.is_pc:
        device = f"Desktop ({user_agent.os.family} {user_agent.os.version_string})"
    else:
        device = user_agent.device.family or "Unknown Device"
    
    # Browser info
    browser = f"{user_agent.browser.family} {user_agent.browser.version_string}"
    
    # Get location from IP (using free API)
    location = get_location_from_ip(ip_address)
    
    # Current datetime
    now = datetime.utcnow()
    datetime_str = now.strftime("%B %d, %Y at %I:%M %p UTC")
    
    return {
        'ip_address': ip_address,
        'device': device,
        'browser': browser,
        'location': location,
        'datetime': datetime_str,
        'timestamp': now,
        'user_agent': user_agent_string[:500]
    }


def get_location_from_ip(ip_address):
    """Get location from IP address using free API"""
    try:
        # Skip for local/private IPs
        if ip_address in ['127.0.0.1', 'localhost', '::1'] or ip_address.startswith('192.168.') or ip_address.startswith('10.'):
            return "Local Network"
        
        # Use ip-api.com (free, no API key needed)
        response = requests.get(f'http://ip-api.com/json/{ip_address}', timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                city = data.get('city', '')
                region = data.get('regionName', '')
                country = data.get('country', '')
                
                parts = [p for p in [city, region, country] if p]
                return ', '.join(parts) if parts else "Unknown Location"
        
        return "Unknown Location"
    except Exception as e:
        logger.error(f"Failed to get location for IP {ip_address}: {e}")
        return "Unknown Location"


def log_login_activity(user, login_info):
    """Log login activity to database"""
    try:
        from app import db
        from app.models.team import AuditLog
        
        log = AuditLog(
            organization_id=str(user.organization_id) if hasattr(user, 'organization_id') else None,
            user_id=str(user.id),
            action='user_login',
            resource_type='user',
            resource_id=str(user.id),
            details=f"Login from {login_info['device']} - {login_info['browser']} - {login_info['location']}",
            ip_address=login_info['ip_address'],
            user_agent=login_info['user_agent']
        )
        
        db.session.add(log)
        db.session.commit()
        
        logger.info(f"Login logged for user {user.email}")
    except Exception as e:
        logger.error(f"Failed to log login: {e}")


def send_login_notification(user, login_info):
    """Send login notification email"""
    try:
        from app.services.email_service import email_service
        
        user_name = getattr(user, 'first_name', None) or user.email.split('@')[0]
        
        email_service.send_login_notification(
            user_email=user.email,
            user_name=user_name,
            login_info=login_info
        )
        
        logger.info(f"Login notification sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send login notification: {e}")
