"""
Bounce Management Controller
Dashboard endpoints for managing bounces and suppression
"""
from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

bounce_bp = Blueprint('bounce', __name__, url_prefix='/dashboard/bounces')


@bounce_bp.route('/')
@login_required
def index():
    """Bounce management dashboard"""
    return render_template('dashboard/bounces/index.html')


@bounce_bp.route('/api/stats')
@login_required
def get_stats():
    """Get bounce statistics"""
    try:
        from app.services.bounce_service import get_bounce_service
        
        service = get_bounce_service()
        days = request.args.get('days', 7, type=int)
        
        stats = service.get_bounce_stats(str(current_user.organization_id), days)
        
        # Get suppression count
        result = db.session.execute(text("""
            SELECT COUNT(*) FROM suppression_list
        """))
        suppression_count = result.scalar() or 0
        
        # Get recent bounces
        result = db.session.execute(text("""
            SELECT e.to_email, e.recipient, eb.bounce_type, eb.reason, eb.bounced_at
            FROM email_bounces eb
            JOIN emails e ON eb.email_id = e.id
            WHERE e.organization_id = :org_id
            ORDER BY eb.bounced_at DESC
            LIMIT 20
        """), {'org_id': current_user.organization_id})
        
        recent = []
        for row in result:
            recent.append({
                'email': row[0] or row[1],
                'type': row[2],
                'reason': row[3],
                'bounced_at': row[4].isoformat() if row[4] else None
            })
        
        return jsonify({
            'success': True,
            'stats': stats,
            'suppression_count': suppression_count,
            'recent_bounces': recent
        })
        
    except Exception as e:
        logger.error(f"Get bounce stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bounce_bp.route('/api/suppression')
@login_required
def get_suppression_list():
    """Get suppression list with pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        search = request.args.get('search', '')
        
        offset = (page - 1) * per_page
        
        # Get suppressed emails
        if search:
            result = db.session.execute(text("""
                SELECT email, type, reason, added_at, bounce_count
                FROM suppression_list
                WHERE email LIKE :search
                ORDER BY added_at DESC
                LIMIT :limit OFFSET :offset
            """), {'search': f'%{search}%', 'limit': per_page, 'offset': offset})
        else:
            result = db.session.execute(text("""
                SELECT email, type, reason, added_at, bounce_count
                FROM suppression_list
                ORDER BY added_at DESC
                LIMIT :limit OFFSET :offset
            """), {'limit': per_page, 'offset': offset})
        
        items = []
        for row in result:
            items.append({
                'email': row[0],
                'type': row[1],
                'reason': row[2],
                'added_at': row[3].isoformat() if row[3] else None,
                'bounce_count': row[4]
            })
        
        # Get total count
        count_result = db.session.execute(text("SELECT COUNT(*) FROM suppression_list"))
        total = count_result.scalar() or 0
        
        return jsonify({
            'success': True,
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        })
        
    except Exception as e:
        logger.error(f"Get suppression list error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bounce_bp.route('/api/suppression/remove', methods=['POST'])
@login_required
def remove_suppression():
    """Remove email from suppression list"""
    try:
        from app.services.bounce_service import get_bounce_service
        
        data = request.get_json()
        email = data.get('email', '').lower().strip()
        
        if not email:
            return jsonify({'success': False, 'error': 'Email required'}), 400
        
        service = get_bounce_service()
        result = service.remove_from_suppression(email, str(current_user.organization_id))
        
        return jsonify({'success': result})
        
    except Exception as e:
        logger.error(f"Remove suppression error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bounce_bp.route('/api/suppression/add', methods=['POST'])
@login_required
def add_suppression():
    """Manually add email to suppression list"""
    try:
        from app.services.bounce_service import get_bounce_service
        
        data = request.get_json()
        email = data.get('email', '').lower().strip()
        reason = data.get('reason', 'Manual addition')
        
        if not email or '@' not in email:
            return jsonify({'success': False, 'error': 'Valid email required'}), 400
        
        service = get_bounce_service()
        result = service.add_to_suppression(
            email, 
            str(current_user.organization_id),
            'manual',
            reason
        )
        
        return jsonify({'success': result})
        
    except Exception as e:
        logger.error(f"Add suppression error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bounce_bp.route('/api/suppression/import', methods=['POST'])
@login_required
def import_suppression():
    """Bulk import suppression list"""
    try:
        from app.services.bounce_service import get_bounce_service
        
        data = request.get_json()
        emails = data.get('emails', [])
        reason = data.get('reason', 'Bulk import')
        
        if not emails:
            return jsonify({'success': False, 'error': 'Emails required'}), 400
        
        service = get_bounce_service()
        added = 0
        
        for email in emails[:10000]:  # Limit to 10k
            email = email.lower().strip()
            if email and '@' in email:
                if service.add_to_suppression(email, str(current_user.organization_id), 'import', reason):
                    added += 1
        
        return jsonify({'success': True, 'added': added})
        
    except Exception as e:
        logger.error(f"Import suppression error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@bounce_bp.route('/api/check', methods=['POST'])
@login_required
def check_emails():
    """Check if emails are suppressed"""
    try:
        from app.services.bounce_service import get_bounce_service
        
        data = request.get_json()
        emails = data.get('emails', [])
        
        if not emails:
            return jsonify({'success': False, 'error': 'Emails required'}), 400
        
        service = get_bounce_service()
        org_id = str(current_user.organization_id)
        
        results = []
        for email in emails[:1000]:
            is_suppressed, info = service.is_suppressed(email.lower().strip(), org_id)
            results.append({
                'email': email,
                'suppressed': is_suppressed,
                'info': info
            })
        
        suppressed_count = sum(1 for r in results if r['suppressed'])
        
        return jsonify({
            'success': True,
            'results': results,
            'total': len(results),
            'suppressed_count': suppressed_count
        })
        
    except Exception as e:
        logger.error(f"Check emails error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
