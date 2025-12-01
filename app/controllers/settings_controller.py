"""
SendBaba Settings Controller - Complete with all API endpoints
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from sqlalchemy import text
import secrets
import logging

logger = logging.getLogger(__name__)

settings_bp = Blueprint('settings', __name__, url_prefix='/dashboard/settings')


@settings_bp.route('/')
@settings_bp.route('')
@login_required
def index():
    """Settings page with API key and all options"""
    try:
        # Get organization
        org_result = db.session.execute(
            text("SELECT id, name, api_key FROM organizations WHERE id = :org_id"),
            {'org_id': current_user.organization_id}
        )
        org = org_result.fetchone()
        
        org_data = {
            'id': org[0],
            'name': org[1],
            'api_key': org[2]
        } if org else None
        
        # Get user details
        user_result = db.session.execute(
            text("SELECT id, email, first_name, last_name, role FROM users WHERE id = :user_id"),
            {'user_id': current_user.id}
        )
        user_row = user_result.fetchone()
        
        user_data = {
            'id': user_row[0],
            'email': user_row[1],
            'first_name': user_row[2] or '',
            'last_name': user_row[3] or '',
            'role': user_row[4] or 'member'
        } if user_row else None
        
        # Features are now injected by context processor
        
        return render_template('dashboard/settings.html', 
                             organization=org_data, 
                             user_data=user_data)
    except Exception as e:
        logger.error(f"Settings error: {e}", exc_info=True)
        return render_template('dashboard/settings.html', 
                             organization=None, 
                             user_data=None)


@settings_bp.route('/api/generate-key', methods=['POST'])
@login_required
def generate_api_key():
    """Generate new API key via AJAX"""
    try:
        new_api_key = 'sk_live_' + secrets.token_urlsafe(32)
        
        db.session.execute(
            text("UPDATE organizations SET api_key = :api_key WHERE id = :org_id"),
            {'api_key': new_api_key, 'org_id': current_user.organization_id}
        )
        db.session.commit()
        
        return jsonify({'success': True, 'api_key': new_api_key})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Generate API key error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/update-profile', methods=['POST'])
@login_required
def update_profile():
    """Update user profile"""
    try:
        data = request.get_json()
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        
        db.session.execute(
            text("UPDATE users SET first_name = :first_name, last_name = :last_name WHERE id = :user_id"),
            {'first_name': first_name, 'last_name': last_name, 'user_id': current_user.id}
        )
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Profile updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Update profile error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/update-organization', methods=['POST'])
@login_required
def update_organization():
    """Update organization name"""
    try:
        data = request.get_json()
        org_name = data.get('name', '').strip()
        
        if not org_name:
            return jsonify({'success': False, 'error': 'Organization name is required'}), 400
        
        db.session.execute(
            text("UPDATE organizations SET name = :name WHERE id = :org_id"),
            {'name': org_name, 'org_id': current_user.organization_id}
        )
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Organization updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Update organization error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/update-password', methods=['POST'])
@login_required
def update_password():
    """Update user password"""
    try:
        from werkzeug.security import generate_password_hash, check_password_hash
        
        data = request.get_json()
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        confirm_password = data.get('confirm_password', '')
        
        if not current_password or not new_password:
            return jsonify({'success': False, 'error': 'All password fields are required'}), 400
        
        if new_password != confirm_password:
            return jsonify({'success': False, 'error': 'New passwords do not match'}), 400
        
        if len(new_password) < 8:
            return jsonify({'success': False, 'error': 'Password must be at least 8 characters'}), 400
        
        # Verify current password
        result = db.session.execute(
            text("SELECT password_hash FROM users WHERE id = :user_id"),
            {'user_id': current_user.id}
        )
        user = result.fetchone()
        
        if not user or not check_password_hash(user[0], current_password):
            return jsonify({'success': False, 'error': 'Current password is incorrect'}), 400
        
        # Update password
        new_hash = generate_password_hash(new_password)
        db.session.execute(
            text("UPDATE users SET password_hash = :password_hash WHERE id = :user_id"),
            {'password_hash': new_hash, 'user_id': current_user.id}
        )
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Password updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Update password error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@settings_bp.route('/api/update-features', methods=['POST'])
@login_required
def update_features():
    """Update feature toggles"""
    try:
        data = request.get_json()
        feature = data.get('feature')
        enabled = data.get('enabled', True)
        
        valid_features = ['workflows', 'segments', 'team', 'ai_reply']
        if feature not in valid_features:
            return jsonify({'success': False, 'error': 'Invalid feature'}), 400
        
        column = f"feature_{feature}"
        
        db.session.execute(
            text(f"UPDATE organizations SET {column} = :enabled WHERE id = :org_id"),
            {'enabled': enabled, 'org_id': current_user.organization_id}
        )
        db.session.commit()
        
        return jsonify({'success': True, 'message': f'Feature updated successfully'})
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Update features error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500
