"""
API Controller - Direct SMTP Integration
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
import logging
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/send-email', methods=['POST'])
@login_required
def send_email():
    """Send email immediately via SMTP"""
    try:
        data = request.get_json()
        
        recipient = data.get('to')
        subject = data.get('subject')
        html_body = data.get('html_body') or data.get('html')
        text_body = data.get('text_body', '')
        
        if not recipient or not subject:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        
        # Get sender domain
        domains_result = db.session.execute(
            text("SELECT domain_name FROM domains WHERE organization_id = :org_id LIMIT 1"),
            {'org_id': current_user.organization_id}
        )
        domain_row = domains_result.fetchone()
        sender_domain = domain_row[0] if domain_row else 'sendbaba.com'
        sender = f'noreply@{sender_domain}'
        
        # Send via SMTP relay immediately
        from app.smtp.relay_server import send_email_sync
        
        result = send_email_sync({
            'from': sender,
            'to': recipient,
            'subject': subject,
            'html_body': html_body,
            'text_body': text_body
        })
        
        if result.get('success'):
            # Log to database
            try:
                email_id = str(uuid.uuid4())
                db.session.execute(
                    text("""
                        INSERT INTO emails (id, organization_id, sender, recipient, subject, html_body, status, sent_at, created_at)
                        VALUES (:id, :org_id, :sender, :recipient, :subject, :html, 'sent', NOW(), NOW())
                    """),
                    {
                        'id': email_id,
                        'org_id': current_user.organization_id,
                        'sender': sender,
                        'recipient': recipient,
                        'subject': subject,
                        'html': html_body
                    }
                )
                db.session.commit()
            except Exception as db_err:
                logger.warning(f"DB logging failed: {db_err}")
            
            return jsonify({
                'success': True,
                'message': f'Email sent to {recipient}',
                'details': result
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('message', 'Send failed')
            }), 500
            
    except Exception as e:
        logger.error(f"Send email error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================
# EMAIL INFRASTRUCTURE STATS
# ============================================

@api_bp.route('/infrastructure/stats', methods=['GET'])
@login_required
def get_infrastructure_stats():
    """Get email infrastructure stats"""
    try:
        from app.utils.email_infrastructure import get_infrastructure
        infra = get_infrastructure()
        stats = infra.get_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
