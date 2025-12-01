"""
Contact Controller - Fast Import with Batch Processing
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, Response
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from sqlalchemy import text
import csv
import io
import logging
import uuid
from datetime import datetime
import json

logger = logging.getLogger(__name__)

contact_bp = Blueprint('contact', __name__, url_prefix='/dashboard/contacts')
contacts_bp = contact_bp


@contact_bp.route('/')
@login_required
def index():
    """List contacts with pagination"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 100
        search = request.args.get('search', '').strip()
        offset = (page - 1) * per_page
        org_id = str(current_user.organization_id)
        
        stats_result = db.session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' OR status IS NULL THEN 1 END) as active,
                COUNT(CASE WHEN status = 'unsubscribed' THEN 1 END) as unsubscribed
            FROM contacts WHERE organization_id = :org_id
        """), {'org_id': org_id})
        stats_row = stats_result.fetchone()
        
        stats = {
            'total': stats_row[0] or 0,
            'active': stats_row[1] or 0,
            'unsubscribed': stats_row[2] or 0
        }
        
        if search:
            result = db.session.execute(text("""
                SELECT id, email, first_name, last_name, company, phone, status, created_at
                FROM contacts 
                WHERE organization_id = :org_id 
                AND (email ILIKE :search OR first_name ILIKE :search OR last_name ILIKE :search OR company ILIKE :search)
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """), {'org_id': org_id, 'search': f'%{search}%', 'limit': per_page, 'offset': offset})
        else:
            result = db.session.execute(text("""
                SELECT id, email, first_name, last_name, company, phone, status, created_at
                FROM contacts 
                WHERE organization_id = :org_id 
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
            """), {'org_id': org_id, 'limit': per_page, 'offset': offset})
        
        contacts = []
        for row in result:
            contacts.append({
                'id': row[0],
                'email': row[1],
                'first_name': row[2] or '',
                'last_name': row[3] or '',
                'company': row[4] or '',
                'phone': row[5] or '',
                'status': row[6] or 'active',
                'created_at': row[7]
            })
        
        total_pages = (stats['total'] + per_page - 1) // per_page
        
        return render_template('dashboard/contacts/list.html',
                             contacts=contacts,
                             stats=stats,
                             search=search,
                             page=page,
                             per_page=per_page,
                             total_pages=total_pages,
                             can_see_all=True)
                             
    except Exception as e:
        logger.error(f"List contacts error: {e}", exc_info=True)
        return render_template('dashboard/contacts/list.html',
                             contacts=[],
                             stats={'total': 0, 'active': 0, 'unsubscribed': 0},
                             search='',
                             page=1,
                             per_page=100,
                             total_pages=1,
                             can_see_all=True)


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
        if not file.filename or not file.filename.endswith('.csv'):
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
        
        suggestions = {}
        for col in headers:
            col_lower = col.lower()
            if 'email' in col_lower:
                suggestions['email'] = col
            elif 'first' in col_lower and 'name' in col_lower:
                suggestions['first_name'] = col
            elif 'last' in col_lower and 'name' in col_lower:
                suggestions['last_name'] = col
            elif 'company' in col_lower or 'organization' in col_lower:
                suggestions['company'] = col
            elif 'phone' in col_lower or 'mobile' in col_lower:
                suggestions['phone'] = col
        
        return jsonify({
            'success': True,
            'headers': headers,
            'preview': rows,
            'total_rows': row_count,
            'suggestions': suggestions
        })
        
    except Exception as e:
        logger.error(f"Parse file error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@contact_bp.route('/api/import-batch', methods=['POST'])
@login_required
def import_batch():
    """Import a batch of contacts - fast bulk insert"""
    try:
        data = request.get_json()
        contacts = data.get('contacts', [])
        skip_duplicates = data.get('skip_duplicates', True)
        
        if not contacts:
            return jsonify({'success': True, 'imported': 0, 'skipped': 0, 'duplicates': 0})
        
        org_id = str(current_user.organization_id)
        user_id = str(current_user.id)
        
        # Get existing emails if skipping duplicates
        existing_emails = set()
        if skip_duplicates:
            result = db.session.execute(text(
                "SELECT LOWER(email) FROM contacts WHERE organization_id = :org_id"
            ), {'org_id': org_id})
            existing_emails = {row[0] for row in result}
        
        imported = 0
        skipped = 0
        duplicates = 0
        
        values = []
        params = {}
        
        for i, contact in enumerate(contacts):
            email = str(contact.get('email', '')).strip().lower()
            
            if not email or '@' not in email:
                skipped += 1
                continue
            
            if email in existing_emails:
                duplicates += 1
                skipped += 1
                continue
            
            existing_emails.add(email)
            
            values.append(f"(:id{i}, :org{i}, :user{i}, :email{i}, :fname{i}, :lname{i}, :company{i}, :phone{i}, 'active', NOW())")
            params[f'id{i}'] = str(uuid.uuid4())
            params[f'org{i}'] = org_id
            params[f'user{i}'] = user_id
            params[f'email{i}'] = email[:255]
            params[f'fname{i}'] = str(contact.get('first_name', ''))[:255]
            params[f'lname{i}'] = str(contact.get('last_name', ''))[:255]
            params[f'company{i}'] = str(contact.get('company', ''))[:255]
            params[f'phone{i}'] = str(contact.get('phone', ''))[:50]
            imported += 1
        
        if values:
            sql = f"""
                INSERT INTO contacts (id, organization_id, created_by_user_id, email, first_name, last_name, company, phone, status, created_at)
                VALUES {', '.join(values)}
                ON CONFLICT (organization_id, email) DO NOTHING
            """
            db.session.execute(text(sql), params)
            db.session.commit()
        
        return jsonify({
            'success': True,
            'imported': imported,
            'skipped': skipped,
            'duplicates': duplicates
        })
        
    except Exception as e:
        logger.error(f"Import batch error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@contact_bp.route('/api/import', methods=['POST'])
@login_required
def import_contacts():
    """Legacy import endpoint - file upload"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        mapping = json.loads(request.form.get('mapping', '{}'))
        options = json.loads(request.form.get('options', '{}'))
        
        content = file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))
        
        org_id = str(current_user.organization_id)
        user_id = str(current_user.id)
        
        existing_emails = set()
        if options.get('skip_duplicates', True):
            result = db.session.execute(text(
                "SELECT LOWER(email) FROM contacts WHERE organization_id = :org_id"
            ), {'org_id': org_id})
            existing_emails = {row[0] for row in result}
        
        imported = 0
        skipped = 0
        duplicates = 0
        batch = []
        batch_size = 1000
        
        email_col = mapping.get('email', '')
        
        for row in csv_reader:
            email = str(row.get(email_col, '')).strip().lower()
            
            if not email or '@' not in email:
                skipped += 1
                continue
            
            if email in existing_emails:
                duplicates += 1
                skipped += 1
                continue
            
            existing_emails.add(email)
            
            batch.append({
                'id': str(uuid.uuid4()),
                'org_id': org_id,
                'user_id': user_id,
                'email': email,
                'first_name': str(row.get(mapping.get('first_name', ''), ''))[:255],
                'last_name': str(row.get(mapping.get('last_name', ''), ''))[:255],
                'company': str(row.get(mapping.get('company', ''), ''))[:255],
                'phone': str(row.get(mapping.get('phone', ''), ''))[:50]
            })
            
            if len(batch) >= batch_size:
                _insert_batch(batch)
                imported += len(batch)
                batch = []
        
        if batch:
            _insert_batch(batch)
            imported += len(batch)
        
        return jsonify({
            'success': True,
            'imported': imported,
            'skipped': skipped,
            'duplicates': duplicates
        })
        
    except Exception as e:
        logger.error(f"Import error: {e}", exc_info=True)
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


def _insert_batch(batch):
    """Insert batch of contacts"""
    if not batch:
        return
    
    values = []
    params = {}
    
    for i, c in enumerate(batch):
        values.append(f"(:id{i}, :org{i}, :user{i}, :email{i}, :fname{i}, :lname{i}, :company{i}, :phone{i}, 'active', NOW())")
        params[f'id{i}'] = c['id']
        params[f'org{i}'] = c['org_id']
        params[f'user{i}'] = c['user_id']
        params[f'email{i}'] = c['email']
        params[f'fname{i}'] = c['first_name']
        params[f'lname{i}'] = c['last_name']
        params[f'company{i}'] = c['company']
        params[f'phone{i}'] = c['phone']
    
    sql = f"""
        INSERT INTO contacts (id, organization_id, created_by_user_id, email, first_name, last_name, company, phone, status, created_at)
        VALUES {', '.join(values)}
        ON CONFLICT (organization_id, email) DO NOTHING
    """
    db.session.execute(text(sql), params)
    db.session.commit()


@contact_bp.route('/api/<contact_id>/delete', methods=['POST', 'DELETE'])
@login_required
def delete_contact(contact_id):
    """Delete a contact"""
    try:
        result = db.session.execute(text(
            "DELETE FROM contacts WHERE id = :id AND organization_id = :org_id RETURNING id"
        ), {'id': contact_id, 'org_id': str(current_user.organization_id)})
        db.session.commit()
        
        if result.fetchone():
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'Contact not found'}), 404
        
    except Exception as e:
        logger.error(f"Delete error: {e}")
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
        
        org_id = str(current_user.organization_id)
        deleted = 0
        
        for contact_id in contact_ids:
            result = db.session.execute(text(
                "DELETE FROM contacts WHERE id = :id AND organization_id = :org_id RETURNING id"
            ), {'id': contact_id, 'org_id': org_id})
            if result.fetchone():
                deleted += 1
        
        db.session.commit()
        
        return jsonify({'success': True, 'deleted': deleted})
        
    except Exception as e:
        logger.error(f"Bulk delete error: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@contact_bp.route('/export')
@login_required
def export_contacts():
    """Export contacts as CSV"""
    try:
        org_id = str(current_user.organization_id)
        
        result = db.session.execute(text("""
            SELECT email, first_name, last_name, company, phone, status, created_at
            FROM contacts WHERE organization_id = :org_id
            ORDER BY created_at DESC
        """), {'org_id': org_id})
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Email', 'First Name', 'Last Name', 'Company', 'Phone', 'Status', 'Created At'])
        
        for row in result:
            writer.writerow([
                row[0], row[1] or '', row[2] or '', row[3] or '', 
                row[4] or '', row[5] or 'active',
                row[6].strftime('%Y-%m-%d %H:%M:%S') if row[6] else ''
            ])
        
        output.seek(0)
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename=contacts_{datetime.now().strftime("%Y%m%d")}.csv'}
        )
        
    except Exception as e:
        logger.error(f"Export error: {e}")
        flash('Error exporting contacts', 'error')
        return redirect('/dashboard/contacts')
