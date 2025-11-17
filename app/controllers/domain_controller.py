from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from app.models.domain import Domain
from app.utils.permissions import can_see_all_org_data, can_edit_resource
import logging

logger = logging.getLogger(__name__)

domain_bp = Blueprint('domain', __name__, url_prefix='/dashboard/domains')


@domain_bp.route('/')
@login_required
def list_domains():
    """List domains based on role"""
    try:
        query = Domain.query.filter_by(organization_id=current_user.organization_id)
        
        # Non-admins only see their own domains
        if not can_see_all_org_data():
            query = query.filter_by(created_by_user_id=current_user.id)
        
        domains = query.order_by(Domain.created_at.desc()).all()
        
        return render_template('dashboard/domains/list.html', 
                             domains=domains,
                             is_admin=can_see_all_org_data())
    
    except Exception as e:
        logger.error(f"List domains error: {e}", exc_info=True)
        flash('Error loading domains', 'error')
        return render_template('dashboard/domains/list.html', 
                             domains=[],
                             is_admin=False)


@domain_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_domain():
    """Add new domain"""
    if request.method == 'POST':
        try:
            domain_name = request.form.get('domain')
            
            if not domain_name:
                flash('Domain name is required', 'error')
                return redirect(url_for('domain.add_domain'))
            
            # Check if domain already exists in org
            existing = Domain.query.filter_by(
                organization_id=current_user.organization_id,
                domain=domain_name
            ).first()
            
            if existing:
                flash('Domain already exists in your organization', 'error')
                return redirect(url_for('domain.add_domain'))
            
            # Create domain with user ownership
            domain = Domain(
                organization_id=current_user.organization_id,
                domain=domain_name,
                created_by_user_id=current_user.id
            )
            
            db.session.add(domain)
            db.session.commit()
            
            flash(f'Domain {domain_name} added successfully', 'success')
            return redirect(url_for('domain.list_domains'))
        
        except Exception as e:
            logger.error(f"Add domain error: {e}", exc_info=True)
            db.session.rollback()
            flash('Error adding domain', 'error')
    
    return render_template('dashboard/domains/add.html')


@domain_bp.route('/<domain_id>/delete', methods=['POST'])
@login_required
def delete_domain(domain_id):
    """Delete domain with permission check"""
    try:
        domain = Domain.query.get(domain_id)
        
        if not domain:
            return jsonify({'success': False, 'error': 'Domain not found'}), 404
        
        # Check permission
        if not can_edit_resource(domain):
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        
        db.session.delete(domain)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Domain deleted'})
    
    except Exception as e:
        logger.error(f"Delete domain error: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
