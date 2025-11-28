"""
Contact Controller - Team Member Isolated with Pagination
Members see only their contacts, Admins/Owners see all
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.contact import Contact, BulkImport
from app.models.team import TeamMember
import csv
import io
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

contact_bp = Blueprint('contact', __name__, url_prefix='/dashboard/contacts')


def get_team_member():
    """Get current user's team member record"""
    return TeamMember.query.filter_by(
        user_id=current_user.id,
        organization_id=current_user.organization_id
    ).first()


def can_see_all_contacts():
    """Check if user can see all org contacts (admin/owner)"""
    team_member = get_team_member()
    if team_member:
        return team_member.role in ['admin', 'owner']
    return getattr(current_user, 'role', None) in ['admin', 'owner']


@contact_bp.route('/')
@login_required
def index():
    """List contacts based on team member permissions with pagination"""
    try:
        # Pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = 100  # Show 100 contacts per page
        search = request.args.get('search', '').strip()
        
        # Base query
        query = Contact.query.filter_by(organization_id=current_user.organization_id)
        
        # Apply permission filter
        if not can_see_all_contacts():
            query = query.filter_by(created_by_user_id=current_user.id)
        
        # Apply search filter if provided
        if search:
            search_filter = f"%{search}%"
            query = query.filter(
                db.or_(
                    Contact.email.ilike(search_filter),
                    Contact.first_name.ilike(search_filter),
                    Contact.last_name.ilike(search_filter),
                    Contact.company.ilike(search_filter)
                )
            )
        
        # Get total counts for stats (without pagination)
        total_query = Contact.query.filter_by(organization_id=current_user.organization_id)
        if not can_see_all_contacts():
            total_query = total_query.filter_by(created_by_user_id=current_user.id)
        
        total_contacts = total_query.count()
        active_contacts = total_query.filter_by(status='active').count()
        unsubscribed = total_query.filter_by(status='unsubscribed').count()
        
        # Paginate the results
        pagination = query.order_by(Contact.created_at.desc()).paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        stats = {
            'total': total_contacts,
            'active': active_contacts,
            'unsubscribed': unsubscribed
        }
        
        return render_template('dashboard/contacts/list.html', 
                             contacts=pagination.items,
                             pagination=pagination,
                             stats=stats,
                             search=search,
                             can_see_all=can_see_all_contacts())
        
    except Exception as e:
        logger.error(f"List contacts error: {e}", exc_info=True)
        flash('Error loading contacts', 'error')
        return render_template('dashboard/contacts/list.html', 
                             contacts=[], 
                             pagination=None,
                             stats={'total': 0, 'active': 0, 'unsubscribed': 0},
                             search='',
                             can_see_all=False)


@contact_bp.route('/import')
@login_required
def import_page():
    """Import contacts page"""
    return render_template('dashboard/contacts/import.html')


@contact_bp.route('/api/parse', methods=['POST'])
@login_required
def parse_file():
    """Parse uploaded CSV file"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        
        if not file.filename:
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        filename = secure_filename(file.filename)
        
        if not filename.endswith('.csv'):
            return jsonify({'success': False, 'error': 'Only CSV files supported'}), 400
        
        content = file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))
        
        headers = list(csv_reader.fieldnames) if csv_reader.fieldnames else []
        
        rows = []
        row_count = 0
        for row in csv_reader:
            if len(rows) < 5:
                rows.append(row)
            row_count += 1
        
        # Auto-detect columns
        email_column = None
        first_name_column = None
        last_name_column = None
        company_column = None
        phone_column = None
        
        for col in headers:
            col_lower = col.lower()
            if 'email' in col_lower or 'e-mail' in col_lower:
                email_column = col
            elif 'first' in col_lower and 'name' in col_lower:
                first_name_column = col
            elif 'last' in col_lower and 'name' in col_lower:
                last_name_column = col
            elif 'company' in col_lower or 'organization' in col_lower:
                company_column = col
            elif 'phone' in col_lower or 'mobile' in col_lower:
                phone_column = col
        
        return jsonify({
            'success': True,
            'headers': headers,
            'preview': rows,
            'total_rows': row_count,
            'suggestions': {
                'email': email_column,
                'first_name': first_name_column,
                'last_name': last_name_column,
                'company': company_column,
                'phone': phone_column
            }
        })
        
    except Exception as e:
        logger.error(f"Parse file error: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)}), 500


@contact_bp.route('/api/import', methods=['POST'])
@login_required
def import_contacts():
    """Import contacts from CSV"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        mapping = request.form.get('mapping')
        options = request.form.get('options', '{}')
        
        if not mapping:
            return jsonify({'success': False, 'error': 'No mapping provided'}), 400
        
        import json
        
        try:
            mapping = json.loads(mapping) if isinstance(mapping, str) else mapping
            options = json.loads(options) if isinstance(options, str) else options
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return jsonify({'success': False, 'error': 'Invalid JSON format'}), 400
        
        team_member = get_team_member()
        
        bulk_import = BulkImport(
            organization_id=current_user.organization_id,
            created_by_user_id=current_user.id,
            filename=secure_filename(file.filename)
        )
        db.session.add(bulk_import)
        db.session.flush()
        
        content = file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))
        
        imported = 0
        skipped = 0
        duplicates = 0
        errors = []
        
        for idx, row in enumerate(csv_reader):
            try:
                email_col = mapping.get('email')
                if not email_col or email_col not in row:
                    skipped += 1
                    continue
                
                email = str(row[email_col]).strip().lower()
                
                if not email or '@' not in email:
                    skipped += 1
                    continue
                
                if options.get('skip_duplicates', True):
                    existing = Contact.query.filter_by(
                        organization_id=current_user.organization_id,
                        email=email
                    ).first()
                    
                    if existing:
                        duplicates += 1
                        skipped += 1
                        continue
                
                first_name = row.get(mapping.get('first_name', ''), '') if mapping.get('first_name') else ''
                last_name = row.get(mapping.get('last_name', ''), '') if mapping.get('last_name') else ''
                company = row.get(mapping.get('company', ''), '') if mapping.get('company') else ''
                phone = row.get(mapping.get('phone', ''), '') if mapping.get('phone') else ''
                
                contact = Contact(
                    organization_id=current_user.organization_id,
                    email=email,
                    created_by_user_id=current_user.id,
                    created_by_team_member_id=team_member.id if team_member else None,
                    first_name=first_name,
                    last_name=last_name,
                    company=company,
                    phone=phone
                )
                
                db.session.add(contact)
                imported += 1
                bulk_import.successful_imports += 1
                
                # Commit in batches
                if imported % 500 == 0:
                    db.session.commit()
                    logger.info(f"Imported {imported} contacts so far...")
                
            except Exception as row_error:
                logger.error(f"Row {idx} import error: {row_error}")
                bulk_import.failed_imports += 1
                skipped += 1
                errors.append({'row': idx + 2, 'error': str(row_error)})
        
        bulk_import.status = 'completed'
        bulk_import.completed_at = datetime.utcnow()
        bulk_import.duplicate_emails = duplicates
        bulk_import.total_rows = imported + skipped
        bulk_import.processed_rows = imported + skipped
        bulk_import.errors = errors[:100]
        
        db.session.commit()
        
        logger.info(f"Import completed: {imported} imported, {skipped} skipped, {duplicates} duplicates")
        
        return jsonify({
            'success': True,
            'imported': imported,
            'skipped': skipped,
            'duplicates': duplicates,
            'message': f'Successfully imported {imported} contacts. Skipped {skipped}.'
        })
        
    except Exception as e:
        logger.error(f"Import error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@contact_bp.route('/api/<contact_id>/delete', methods=['POST', 'DELETE'])
@login_required
def delete_contact(contact_id):
    """Delete a contact"""
    try:
        contact = Contact.query.get(contact_id)
        
        if not contact:
            return jsonify({'success': False, 'error': 'Contact not found'}), 404
        
        if not can_see_all_contacts() and contact.created_by_user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Permission denied'}), 403
        
        db.session.delete(contact)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Contact deleted'})
        
    except Exception as e:
        logger.error(f"Delete contact error: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@contact_bp.route('/api/bulk-delete', methods=['POST'])
@login_required
def bulk_delete():
    """Bulk delete contacts"""
    try:
        data = request.get_json()
        contact_ids = data.get('ids', [])
        
        if not contact_ids:
            return jsonify({'success': False, 'error': 'No contacts selected'}), 400
        
        deleted = 0
        for contact_id in contact_ids:
            contact = Contact.query.get(contact_id)
            
            if contact and contact.organization_id == current_user.organization_id:
                if can_see_all_contacts() or contact.created_by_user_id == current_user.id:
                    db.session.delete(contact)
                    deleted += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'deleted': deleted,
            'message': f'Deleted {deleted} contact(s)'
        })
        
    except Exception as e:
        logger.error(f"Bulk delete error: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
