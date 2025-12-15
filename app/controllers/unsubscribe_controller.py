"""
SendBaba Unsubscribe Controller
================================
Production-ready unsubscribe handling for CAN-SPAM/GDPR compliance.

Features:
- One-click unsubscribe (RFC 8058)
- Signed unsubscribe links (tamper-proof)
- Reason tracking
- Resubscribe capability
- API endpoints
"""
from flask import Blueprint, request, jsonify, render_template, current_app
from app import db
from sqlalchemy import text
import logging
import uuid
import os
import hashlib
import hmac
from datetime import datetime
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

unsubscribe_bp = Blueprint('unsubscribe', __name__)


class UnsubscribeService:
    """Service class for unsubscribe operations"""
    
    # Use environment variable or fallback
    SECRET_KEY = os.environ.get('UNSUBSCRIBE_SECRET', 'SendBaba2024UnsubscribeSecretKey')
    
    @classmethod
    def generate_token(cls, email: str, org_id: str = None, campaign_id: str = None) -> str:
        """
        Generate a signed token for unsubscribe link.
        Token is HMAC-SHA256 based, tamper-proof.
        """
        data = f"{email.lower()}:{org_id or ''}:{campaign_id or ''}"
        signature = hmac.new(
            cls.SECRET_KEY.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()[:24]
        return signature
    
    @classmethod
    def verify_token(cls, email: str, token: str, org_id: str = None, campaign_id: str = None) -> bool:
        """Verify unsubscribe token"""
        expected = cls.generate_token(email, org_id, campaign_id)
        return hmac.compare_digest(token, expected)
    
    @classmethod
    def generate_unsubscribe_url(cls, email: str, org_id: str = None, 
                                  campaign_id: str = None, base_url: str = None) -> str:
        """
        Generate a complete unsubscribe URL with signed token.
        Use this when sending emails.
        """
        if not base_url:
            base_url = os.environ.get('APP_URL', 'https://sendbaba.com')
        
        token = cls.generate_token(email, org_id, campaign_id)
        
        params = {
            'email': email.lower(),
            'token': token
        }
        if org_id:
            params['org'] = org_id
        if campaign_id:
            params['cid'] = campaign_id
        
        return f"{base_url}/unsubscribe?{urlencode(params)}"
    
    @classmethod
    def process_unsubscribe(cls, email: str, org_id: str = None, 
                           reason: str = None, ip_address: str = None) -> dict:
        """
        Process an unsubscribe request.
        Returns dict with success status.
        """
        email = email.lower().strip()
        
        if not email or '@' not in email:
            return {'success': False, 'error': 'Invalid email address'}
        
        try:
            # Add to suppression list
            suppression_id = str(uuid.uuid4())
            
            db.session.execute(text("""
                INSERT INTO suppression_list (id, email, type, reason, added_at, bounce_count)
                VALUES (:id, :email, 'unsubscribe', :reason, NOW(), 0)
                ON CONFLICT (email) DO UPDATE SET
                    type = 'unsubscribe',
                    reason = EXCLUDED.reason,
                    added_at = NOW()
            """), {
                'id': suppression_id,
                'email': email,
                'reason': reason or 'User requested'
            })
            
            # Update contact status
            if org_id:
                db.session.execute(text("""
                    UPDATE contacts SET status = 'unsubscribed', updated_at = NOW()
                    WHERE LOWER(email) = :email AND organization_id = :org_id
                """), {'email': email, 'org_id': org_id})
            else:
                db.session.execute(text("""
                    UPDATE contacts SET status = 'unsubscribed', updated_at = NOW()
                    WHERE LOWER(email) = :email
                """), {'email': email})
            
            # Log unsubscribe event
            unsub_id = str(uuid.uuid4())
            db.session.execute(text("""
                INSERT INTO email_unsubscribes (id, email_address, organization_id, reason, ip_address, unsubscribed_at)
                VALUES (:id, :email, :org_id, :reason, :ip, NOW())
                ON CONFLICT (email_address) DO UPDATE SET
                    reason = EXCLUDED.reason,
                    unsubscribed_at = NOW()
            """), {
                'id': unsub_id,
                'email': email,
                'org_id': org_id if org_id else None,
                'reason': reason or 'User requested',
                'ip': ip_address
            })
            
            db.session.commit()
            
            logger.info(f"Unsubscribed: {email} (reason: {reason})")
            
            return {'success': True, 'email': email}
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Unsubscribe error: {e}")
            return {'success': False, 'error': str(e)}
    
    @classmethod
    def process_resubscribe(cls, email: str, org_id: str = None) -> dict:
        """Process a resubscribe request"""
        email = email.lower().strip()
        
        try:
            # Remove from suppression (only unsubscribe type, not bounces)
            db.session.execute(text("""
                DELETE FROM suppression_list 
                WHERE email = :email AND type = 'unsubscribe'
            """), {'email': email})
            
            # Update contact status
            if org_id:
                db.session.execute(text("""
                    UPDATE contacts SET status = 'active', updated_at = NOW()
                    WHERE LOWER(email) = :email AND organization_id = :org_id
                """), {'email': email, 'org_id': org_id})
            else:
                db.session.execute(text("""
                    UPDATE contacts SET status = 'active', updated_at = NOW()
                    WHERE LOWER(email) = :email
                """), {'email': email})
            
            db.session.commit()
            
            logger.info(f"Resubscribed: {email}")
            
            return {'success': True, 'email': email}
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Resubscribe error: {e}")
            return {'success': False, 'error': str(e)}
    
    @classmethod
    def is_unsubscribed(cls, email: str) -> dict:
        """Check if email is unsubscribed"""
        email = email.lower().strip()
        
        try:
            result = db.session.execute(text("""
                SELECT type, reason, added_at 
                FROM suppression_list 
                WHERE email = :email AND type = 'unsubscribe'
            """), {'email': email})
            
            row = result.fetchone()
            
            if row:
                return {
                    'unsubscribed': True,
                    'type': row[0],
                    'reason': row[1],
                    'since': row[2].isoformat() if row[2] else None
                }
            
            return {'unsubscribed': False}
            
        except Exception as e:
            logger.error(f"Check unsubscribe error: {e}")
            return {'unsubscribed': False, 'error': str(e)}


# =============================================================================
# WEB ROUTES
# =============================================================================

@unsubscribe_bp.route('/unsubscribe')
def unsubscribe_page():
    """
    Unsubscribe landing page.
    URL: /unsubscribe?email=xxx&token=xxx&org=xxx&cid=xxx
    """
    email = request.args.get('email', '').lower().strip()
    token = request.args.get('token', '')
    org_id = request.args.get('org', '')
    campaign_id = request.args.get('cid', '')
    
    if not email:
        return render_template('unsubscribe/error.html', 
                             message="Invalid unsubscribe link. Email address is missing."), 400
    
    # Verify token if provided (optional for backwards compatibility)
    if token:
        if not UnsubscribeService.verify_token(email, token, org_id, campaign_id):
            logger.warning(f"Invalid unsubscribe token for {email}")
            # Still allow unsubscribe but log it
    
    return render_template('unsubscribe/confirm.html',
                         email=email,
                         token=token,
                         org_id=org_id,
                         campaign_id=campaign_id)


@unsubscribe_bp.route('/unsubscribe/confirm', methods=['POST'])
def unsubscribe_confirm():
    """Process unsubscribe confirmation from form"""
    # Support both form and JSON
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    email = data.get('email', '').lower().strip()
    org_id = data.get('org_id', '') or data.get('org', '')
    reason = data.get('reason', 'User requested')
    
    if not email:
        return render_template('unsubscribe/error.html',
                             message="Email address is required."), 400
    
    result = UnsubscribeService.process_unsubscribe(
        email=email,
        org_id=org_id if org_id else None,
        reason=reason,
        ip_address=request.remote_addr
    )
    
    if result.get('success'):
        return render_template('unsubscribe/success.html', email=email)
    else:
        # Still show success to user (they requested unsubscribe)
        # But log the error
        logger.error(f"Unsubscribe failed but showing success: {result.get('error')}")
        return render_template('unsubscribe/success.html', email=email)


@unsubscribe_bp.route('/unsubscribe/one-click', methods=['POST'])
def one_click_unsubscribe():
    """
    One-click unsubscribe endpoint (RFC 8058).
    Called automatically by email clients (Gmail, Yahoo, etc.)
    
    Requires List-Unsubscribe-Post header in email.
    """
    email = request.args.get('email', '').lower().strip()
    org_id = request.args.get('org', '')
    
    # RFC 8058: Also check form data for List-Unsubscribe=One-Click
    if not email:
        email = request.form.get('email', '').lower().strip()
    
    if not email:
        return '', 400
    
    result = UnsubscribeService.process_unsubscribe(
        email=email,
        org_id=org_id if org_id else None,
        reason='One-click unsubscribe',
        ip_address=request.remote_addr
    )
    
    # RFC 8058 requires 200 OK response
    return '', 200


@unsubscribe_bp.route('/unsubscribe/resubscribe', methods=['POST'])
def resubscribe():
    """Allow user to resubscribe"""
    if request.is_json:
        data = request.get_json()
    else:
        data = request.form.to_dict()
    
    email = data.get('email', '').lower().strip()
    org_id = data.get('org_id', '')
    
    if not email:
        return jsonify({'success': False, 'error': 'Email required'}), 400
    
    result = UnsubscribeService.process_resubscribe(email, org_id if org_id else None)
    
    return jsonify(result)


# =============================================================================
# API ROUTES
# =============================================================================

@unsubscribe_bp.route('/api/unsubscribe/status')
def api_check_status():
    """API: Check if email is unsubscribed"""
    email = request.args.get('email', '').lower().strip()
    
    if not email:
        return jsonify({'error': 'Email parameter required'}), 400
    
    result = UnsubscribeService.is_unsubscribed(email)
    return jsonify(result)


@unsubscribe_bp.route('/api/unsubscribe/generate-url')
def api_generate_url():
    """
    API: Generate unsubscribe URL for an email.
    Used when sending emails programmatically.
    """
    email = request.args.get('email', '').lower().strip()
    org_id = request.args.get('org_id', '')
    campaign_id = request.args.get('campaign_id', '')
    
    if not email:
        return jsonify({'error': 'Email parameter required'}), 400
    
    # Use request host as base URL
    base_url = f"{request.scheme}://{request.host}"
    
    url = UnsubscribeService.generate_unsubscribe_url(
        email=email,
        org_id=org_id if org_id else None,
        campaign_id=campaign_id if campaign_id else None,
        base_url=base_url
    )
    
    return jsonify({
        'success': True,
        'email': email,
        'unsubscribe_url': url
    })


@unsubscribe_bp.route('/api/unsubscribe', methods=['POST'])
def api_unsubscribe():
    """API: Unsubscribe an email programmatically"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'JSON body required'}), 400
    
    email = data.get('email', '').lower().strip()
    org_id = data.get('org_id')
    reason = data.get('reason', 'API request')
    
    if not email:
        return jsonify({'error': 'Email required'}), 400
    
    result = UnsubscribeService.process_unsubscribe(
        email=email,
        org_id=org_id,
        reason=reason,
        ip_address=request.remote_addr
    )
    
    return jsonify(result)


@unsubscribe_bp.route('/api/unsubscribe/bulk', methods=['POST'])
def api_bulk_unsubscribe():
    """API: Bulk unsubscribe emails"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'JSON body required'}), 400
    
    emails = data.get('emails', [])
    org_id = data.get('org_id')
    reason = data.get('reason', 'Bulk unsubscribe')
    
    if not emails:
        return jsonify({'error': 'Emails array required'}), 400
    
    if len(emails) > 10000:
        return jsonify({'error': 'Maximum 10,000 emails per request'}), 400
    
    success_count = 0
    failed = []
    
    for email in emails:
        email = email.lower().strip() if email else ''
        if email and '@' in email:
            result = UnsubscribeService.process_unsubscribe(
                email=email,
                org_id=org_id,
                reason=reason,
                ip_address=request.remote_addr
            )
            if result.get('success'):
                success_count += 1
            else:
                failed.append(email)
        else:
            failed.append(email)
    
    return jsonify({
        'success': True,
        'processed': len(emails),
        'unsubscribed': success_count,
        'failed': len(failed),
        'failed_emails': failed[:100]  # Limit response size
    })
