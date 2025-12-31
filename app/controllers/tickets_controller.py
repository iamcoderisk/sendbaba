"""
MyHelpr Ticketing System Controller
Full-featured support ticket system
"""
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, session, current_app, send_file
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
import uuid
import os
import json

tickets_bp = Blueprint('tickets', __name__)

UPLOAD_FOLDER = '/opt/sendbaba-staging/app/static/uploads/tickets'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 'txt', 'zip'}

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    return psycopg2.connect(
        host='localhost',
        database='emailer',
        user='emailer',
        password='SecurePassword123'
    )

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access support.', 'warning')
            return redirect('/auth/login?next=' + request.path)
        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/auth/login')
        user = get_current_user()
        if not user or not user.get('is_staff') and not user.get('is_superuser'):
            flash('Access denied. Staff only.', 'error')
            return redirect('/support')
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    if 'user_id' not in session:
        return None
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()
    conn.close()
    return user

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def log_activity(ticket_id, user_id, action, details=None):
    """Log ticket activity"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO ticket_activities (ticket_id, user_id, action, details)
        VALUES (%s, %s, %s, %s)
    """, (ticket_id, user_id, action, json.dumps(details or {})))
    conn.commit()
    conn.close()

# ============================================
# USER SUPPORT PAGES
# ============================================

@tickets_bp.route('/support')
@login_required
def support_home():
    """User's ticket dashboard"""
    user = get_current_user()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get filters
    status_filter = request.args.get('status', 'all')
    
    # Build query
    query = """
        SELECT t.*, tc.name as category_name, tc.icon as category_icon, tc.color as category_color,
               (SELECT COUNT(*) FROM ticket_replies WHERE ticket_id = t.id AND is_internal_note = false) as reply_count,
               (SELECT COUNT(*) FROM ticket_replies WHERE ticket_id = t.id AND is_staff = true AND created_at > t.updated_at) as unread_replies
        FROM tickets t
        LEFT JOIN ticket_categories tc ON t.category_id = tc.id
        WHERE t.user_id = %s
    """
    params = [user['id']]
    
    if status_filter != 'all':
        query += " AND t.status = %s"
        params.append(status_filter)
    
    query += " ORDER BY t.updated_at DESC"
    
    cur.execute(query, params)
    tickets = cur.fetchall()
    
    # Get categories for new ticket
    cur.execute("SELECT * FROM ticket_categories WHERE is_active = true ORDER BY sort_order")
    categories = cur.fetchall()
    
    # Stats
    cur.execute("""
        SELECT 
            COUNT(*) FILTER (WHERE status = 'open') as open_count,
            COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
            COUNT(*) FILTER (WHERE status IN ('resolved', 'closed')) as resolved_count,
            COUNT(*) as total_count
        FROM tickets WHERE user_id = %s
    """, (user['id'],))
    stats = cur.fetchone()
    
    conn.close()
    return render_template('support/index.html', 
                         tickets=tickets, 
                         categories=categories, 
                         stats=stats, 
                         user=user,
                         status_filter=status_filter)

@tickets_bp.route('/support/new', methods=['GET', 'POST'])
@login_required
def create_ticket():
    """Create new support ticket"""
    user = get_current_user()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        description = request.form.get('description', '').strip()
        category_id = request.form.get('category_id')
        priority = request.form.get('priority', 'medium')
        
        if not subject or not description:
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('tickets.create_ticket'))
        
        # Generate ticket number
        cur.execute("SELECT generate_ticket_number()")
        ticket_number = cur.fetchone()['generate_ticket_number']
        
        # Create ticket
        cur.execute("""
            INSERT INTO tickets (ticket_number, subject, description, category_id, priority, 
                               user_id, user_email, user_name, organization_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (ticket_number, subject, description, category_id or None, priority, 
              user['id'], user['email'], user.get('name', ''), user.get('organization_id')))
        
        ticket_id = cur.fetchone()['id']
        conn.commit()
        
        # Log activity
        log_activity(ticket_id, user['id'], 'created', {'subject': subject})
        
        flash(f'Ticket {ticket_number} created successfully! Our team will respond shortly.', 'success')
        conn.close()
        return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))
    
    # GET - show form
    cur.execute("SELECT * FROM ticket_categories WHERE is_active = true ORDER BY sort_order")
    categories = cur.fetchall()
    conn.close()
    
    return render_template('support/new_ticket.html', categories=categories, user=user)

@tickets_bp.route('/support/ticket/<ticket_id>')
@login_required
def view_ticket(ticket_id):
    """View ticket details and conversation"""
    user = get_current_user()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get ticket
    cur.execute("""
        SELECT t.*, tc.name as category_name, tc.icon as category_icon, tc.color as category_color,
               u.email as user_email, u.name as user_name,
               a.email as assigned_email, a.name as assigned_name
        FROM tickets t
        LEFT JOIN ticket_categories tc ON t.category_id = tc.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN users a ON t.assigned_to = a.id
        WHERE t.id = %s AND t.user_id = %s
    """, (ticket_id, user['id']))
    ticket = cur.fetchone()
    
    if not ticket:
        flash('Ticket not found.', 'error')
        conn.close()
        return redirect(url_for('tickets.support_home'))
    
    # Get replies (excluding internal notes for users)
    cur.execute("""
        SELECT tr.*, u.email as user_email, u.name as user_name
        FROM ticket_replies tr
        LEFT JOIN users u ON tr.user_id = u.id
        WHERE tr.ticket_id = %s AND tr.is_internal_note = false
        ORDER BY tr.created_at ASC
    """, (ticket_id,))
    replies = cur.fetchall()
    
    # Mark as read by user
    cur.execute("UPDATE tickets SET is_read_by_user = true WHERE id = %s", (ticket_id,))
    conn.commit()
    conn.close()
    
    return render_template('support/view_ticket.html', ticket=ticket, replies=replies, user=user)

@tickets_bp.route('/support/ticket/<ticket_id>/reply', methods=['POST'])
@login_required
def reply_ticket(ticket_id):
    """Add reply to ticket"""
    user = get_current_user()
    message = request.form.get('message', '').strip()
    
    if not message:
        flash('Please enter a message.', 'error')
        return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Verify ticket belongs to user
    cur.execute("SELECT id, ticket_number, status FROM tickets WHERE id = %s AND user_id = %s", (ticket_id, user['id']))
    ticket = cur.fetchone()
    if not ticket:
        flash('Ticket not found.', 'error')
        conn.close()
        return redirect(url_for('tickets.support_home'))
    
    # Can't reply to closed tickets
    if ticket['status'] == 'closed':
        flash('This ticket is closed. Please open a new ticket.', 'warning')
        conn.close()
        return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))
    
    # Add reply
    cur.execute("""
        INSERT INTO ticket_replies (ticket_id, user_id, user_email, user_name, message, is_staff)
        VALUES (%s, %s, %s, %s, %s, false)
        RETURNING id
    """, (ticket_id, user['id'], user['email'], user.get('name', ''), message))
    
    reply_id = cur.fetchone()['id']
    
    # Update ticket - reopen if it was pending/resolved
    new_status = 'open' if ticket['status'] in ('pending', 'resolved') else ticket['status']
    cur.execute("""
        UPDATE tickets 
        SET updated_at = NOW(), 
            last_reply_at = NOW(), 
            last_reply_by = %s,
            is_read_by_staff = false,
            status = %s
        WHERE id = %s
    """, (user['id'], new_status, ticket_id))
    
    conn.commit()
    
    # Log activity
    log_activity(ticket_id, user['id'], 'replied', {'message_preview': message[:100]})
    
    flash('Your reply has been sent.', 'success')
    conn.close()
    return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))

@tickets_bp.route('/support/ticket/<ticket_id>/close', methods=['POST'])
@login_required
def close_ticket_user(ticket_id):
    """User closes their own ticket"""
    user = get_current_user()
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE tickets 
        SET status = 'closed', closed_at = NOW(), closed_by = %s, updated_at = NOW()
        WHERE id = %s AND user_id = %s AND status != 'closed'
        RETURNING id
    """, (user['id'], ticket_id, user['id']))
    
    if cur.fetchone():
        conn.commit()
        log_activity(ticket_id, user['id'], 'closed', {'closed_by': 'user'})
        flash('Ticket closed successfully.', 'success')
    else:
        flash('Could not close ticket.', 'error')
    
    conn.close()
    return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))

@tickets_bp.route('/support/ticket/<ticket_id>/reopen', methods=['POST'])
@login_required
def reopen_ticket_user(ticket_id):
    """User reopens their closed ticket"""
    user = get_current_user()
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE tickets 
        SET status = 'open', closed_at = NULL, closed_by = NULL, updated_at = NOW()
        WHERE id = %s AND user_id = %s AND status = 'closed'
        RETURNING id
    """, (ticket_id, user['id']))
    
    if cur.fetchone():
        conn.commit()
        log_activity(ticket_id, user['id'], 'reopened', {})
        flash('Ticket reopened successfully.', 'success')
    else:
        flash('Could not reopen ticket.', 'error')
    
    conn.close()
    return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))

@tickets_bp.route('/support/ticket/<ticket_id>/rate', methods=['POST'])
@login_required
def rate_ticket(ticket_id):
    """Rate resolved ticket"""
    user = get_current_user()
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()
    
    if not rating or rating < 1 or rating > 5:
        flash('Invalid rating.', 'error')
        return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE tickets 
        SET satisfaction_rating = %s, satisfaction_comment = %s
        WHERE id = %s AND user_id = %s AND status IN ('resolved', 'closed')
        RETURNING id
    """, (rating, comment, ticket_id, user['id']))
    
    if cur.fetchone():
        conn.commit()
        flash('Thank you for your feedback!', 'success')
    else:
        flash('Could not submit rating.', 'error')
    
    conn.close()
    return redirect(url_for('tickets.view_ticket', ticket_id=ticket_id))

# ============================================
# STAFF/ADMIN DASHBOARD
# ============================================

@tickets_bp.route('/support/admin')
@staff_required
def admin_dashboard():
    """Staff ticket dashboard"""
    user = get_current_user()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get filters
    status_filter = request.args.get('status', 'open')
    priority_filter = request.args.get('priority', 'all')
    category_filter = request.args.get('category', 'all')
    assigned_filter = request.args.get('assigned', 'all')
    search = request.args.get('search', '').strip()
    
    # Build query
    query = """
        SELECT t.*, tc.name as category_name, tc.icon as category_icon, tc.color as category_color,
               u.email as user_email, u.name as user_name,
               a.email as assigned_email, a.name as assigned_name,
               (SELECT COUNT(*) FROM ticket_replies WHERE ticket_id = t.id) as reply_count
        FROM tickets t
        LEFT JOIN ticket_categories tc ON t.category_id = tc.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN users a ON t.assigned_to = a.id
        WHERE 1=1
    """
    params = []
    
    if status_filter != 'all':
        query += " AND t.status = %s"
        params.append(status_filter)
    
    if priority_filter != 'all':
        query += " AND t.priority = %s"
        params.append(priority_filter)
    
    if category_filter != 'all':
        query += " AND t.category_id = %s"
        params.append(category_filter)
    
    if assigned_filter == 'me':
        query += " AND t.assigned_to = %s"
        params.append(user['id'])
    elif assigned_filter == 'unassigned':
        query += " AND t.assigned_to IS NULL"
    
    if search:
        query += " AND (t.ticket_number ILIKE %s OR t.subject ILIKE %s OR t.description ILIKE %s OR u.email ILIKE %s)"
        search_param = f'%{search}%'
        params.extend([search_param, search_param, search_param, search_param])
    
    query += " ORDER BY CASE t.priority WHEN 'urgent' THEN 1 WHEN 'high' THEN 2 WHEN 'medium' THEN 3 ELSE 4 END, t.updated_at DESC"
    
    cur.execute(query, params)
    tickets = cur.fetchall()
    
    # Get categories
    cur.execute("SELECT * FROM ticket_categories WHERE is_active = true ORDER BY sort_order")
    categories = cur.fetchall()
    
    # Get staff members for assignment
    cur.execute("SELECT id, email, name FROM users WHERE is_staff = true OR is_superuser = true ORDER BY name")
    staff_members = cur.fetchall()
    
    # Stats
    cur.execute("""
        SELECT 
            COUNT(*) FILTER (WHERE status = 'open') as open_count,
            COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
            COUNT(*) FILTER (WHERE status = 'resolved') as resolved_count,
            COUNT(*) FILTER (WHERE status = 'closed') as closed_count,
            COUNT(*) FILTER (WHERE assigned_to IS NULL AND status = 'open') as unassigned_count,
            COUNT(*) FILTER (WHERE priority = 'urgent' AND status = 'open') as urgent_count,
            COUNT(*) as total_count,
            COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_count
        FROM tickets
    """)
    stats = cur.fetchone()
    
    conn.close()
    return render_template('support/admin/dashboard.html',
                         tickets=tickets,
                         categories=categories,
                         staff_members=staff_members,
                         stats=stats,
                         user=user,
                         filters={
                             'status': status_filter,
                             'priority': priority_filter,
                             'category': category_filter,
                             'assigned': assigned_filter,
                             'search': search
                         })

@tickets_bp.route('/support/admin/ticket/<ticket_id>')
@staff_required
def admin_view_ticket(ticket_id):
    """Staff view ticket"""
    user = get_current_user()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get ticket
    cur.execute("""
        SELECT t.*, tc.name as category_name, tc.icon as category_icon, tc.color as category_color,
               u.email as user_email, u.name as user_name,
               a.email as assigned_email, a.name as assigned_name,
               o.name as org_name
        FROM tickets t
        LEFT JOIN ticket_categories tc ON t.category_id = tc.id
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN users a ON t.assigned_to = a.id
        LEFT JOIN organizations o ON t.organization_id = o.id
        WHERE t.id = %s
    """, (ticket_id,))
    ticket = cur.fetchone()
    
    if not ticket:
        flash('Ticket not found.', 'error')
        conn.close()
        return redirect(url_for('tickets.admin_dashboard'))
    
    # Get all replies including internal notes
    cur.execute("""
        SELECT tr.*, u.email as user_email, u.name as user_name
        FROM ticket_replies tr
        LEFT JOIN users u ON tr.user_id = u.id
        WHERE tr.ticket_id = %s
        ORDER BY tr.created_at ASC
    """, (ticket_id,))
    replies = cur.fetchall()
    
    # Get activity log
    cur.execute("""
        SELECT ta.*, u.email as user_email, u.name as user_name
        FROM ticket_activities ta
        LEFT JOIN users u ON ta.user_id = u.id
        WHERE ta.ticket_id = %s
        ORDER BY ta.created_at DESC
        LIMIT 20
    """, (ticket_id,))
    activities = cur.fetchall()
    
    # Get categories and staff for dropdowns
    cur.execute("SELECT * FROM ticket_categories WHERE is_active = true ORDER BY sort_order")
    categories = cur.fetchall()
    
    cur.execute("SELECT id, email, name FROM users WHERE is_staff = true OR is_superuser = true ORDER BY name")
    staff_members = cur.fetchall()
    
    # Get canned responses
    cur.execute("SELECT * FROM ticket_canned_responses WHERE is_active = true ORDER BY title")
    canned_responses = cur.fetchall()
    
    # Mark as read by staff
    cur.execute("UPDATE tickets SET is_read_by_staff = true WHERE id = %s", (ticket_id,))
    conn.commit()
    conn.close()
    
    return render_template('support/admin/view_ticket.html',
                         ticket=ticket,
                         replies=replies,
                         activities=activities,
                         categories=categories,
                         staff_members=staff_members,
                         canned_responses=canned_responses,
                         user=user)

@tickets_bp.route('/support/admin/ticket/<ticket_id>/reply', methods=['POST'])
@staff_required
def admin_reply_ticket(ticket_id):
    """Staff reply to ticket"""
    user = get_current_user()
    message = request.form.get('message', '').strip()
    is_internal = request.form.get('is_internal') == 'true'
    new_status = request.form.get('status')
    
    if not message:
        flash('Please enter a message.', 'error')
        return redirect(url_for('tickets.admin_view_ticket', ticket_id=ticket_id))
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Add reply
    cur.execute("""
        INSERT INTO ticket_replies (ticket_id, user_id, user_email, user_name, message, is_staff, is_internal_note)
        VALUES (%s, %s, %s, %s, %s, true, %s)
        RETURNING id
    """, (ticket_id, user['id'], user['email'], user.get('name', ''), message, is_internal))
    
    reply_id = cur.fetchone()['id']
    
    # Update ticket
    update_fields = ["updated_at = NOW()", "last_reply_at = NOW()", "last_reply_by = %s"]
    update_params = [user['id']]
    
    if not is_internal:
        update_fields.append("is_read_by_user = false")
    
    if new_status:
        update_fields.append("status = %s")
        update_params.append(new_status)
        if new_status == 'closed':
            update_fields.extend(["closed_at = NOW()", "closed_by = %s"])
            update_params.append(user['id'])
    
    update_params.append(ticket_id)
    
    cur.execute(f"""
        UPDATE tickets SET {', '.join(update_fields)} WHERE id = %s
    """, update_params)
    
    conn.commit()
    
    # Log activity
    action = 'internal_note' if is_internal else 'staff_replied'
    log_activity(ticket_id, user['id'], action, {'status_change': new_status})
    
    flash('Reply sent successfully.' if not is_internal else 'Internal note added.', 'success')
    conn.close()
    return redirect(url_for('tickets.admin_view_ticket', ticket_id=ticket_id))

@tickets_bp.route('/support/admin/ticket/<ticket_id>/update', methods=['POST'])
@staff_required
def admin_update_ticket(ticket_id):
    """Update ticket properties"""
    user = get_current_user()
    conn = get_db()
    cur = conn.cursor()
    
    # Get current ticket state
    cur.execute("SELECT status, priority, assigned_to, category_id FROM tickets WHERE id = %s", (ticket_id,))
    old = cur.fetchone()
    
    status = request.form.get('status', old[0])
    priority = request.form.get('priority', old[1])
    assigned_to = request.form.get('assigned_to') or None
    category_id = request.form.get('category_id') or None
    
    changes = {}
    if status != old[0]:
        changes['status'] = {'from': old[0], 'to': status}
    if priority != old[1]:
        changes['priority'] = {'from': old[1], 'to': priority}
    if assigned_to != str(old[2]) if old[2] else old[2] != assigned_to:
        changes['assigned'] = True
    
    update_query = """
        UPDATE tickets SET 
            status = %s, priority = %s, assigned_to = %s, category_id = %s, updated_at = NOW()
    """
    params = [status, priority, assigned_to, category_id]
    
    if status == 'closed' and old[0] != 'closed':
        update_query += ", closed_at = NOW(), closed_by = %s"
        params.append(user['id'])
    elif status != 'closed' and old[0] == 'closed':
        update_query += ", closed_at = NULL, closed_by = NULL"
    
    update_query += " WHERE id = %s"
    params.append(ticket_id)
    
    cur.execute(update_query, params)
    conn.commit()
    
    if changes:
        log_activity(ticket_id, user['id'], 'updated', changes)
    
    flash('Ticket updated successfully.', 'success')
    conn.close()
    return redirect(url_for('tickets.admin_view_ticket', ticket_id=ticket_id))

@tickets_bp.route('/support/admin/ticket/<ticket_id>/assign', methods=['POST'])
@staff_required
def admin_assign_ticket(ticket_id):
    """Quick assign ticket"""
    user = get_current_user()
    assigned_to = request.form.get('assigned_to') or None
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE tickets SET assigned_to = %s, updated_at = NOW()
        WHERE id = %s
    """, (assigned_to, ticket_id))
    conn.commit()
    
    log_activity(ticket_id, user['id'], 'assigned', {'to': assigned_to})
    
    conn.close()
    return jsonify({'success': True})

# ============================================
# API ENDPOINTS
# ============================================

@tickets_bp.route('/support/api/stats')
@staff_required
def api_stats():
    """Get ticket statistics"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT 
            COUNT(*) FILTER (WHERE status = 'open') as open_count,
            COUNT(*) FILTER (WHERE status = 'pending') as pending_count,
            COUNT(*) FILTER (WHERE status = 'resolved') as resolved_count,
            COUNT(*) FILTER (WHERE assigned_to IS NULL AND status = 'open') as unassigned_count,
            COUNT(*) FILTER (WHERE priority = 'urgent' AND status NOT IN ('resolved', 'closed')) as urgent_count,
            COUNT(*) FILTER (WHERE DATE(created_at) = CURRENT_DATE) as today_count,
            AVG(EXTRACT(EPOCH FROM (COALESCE(closed_at, NOW()) - created_at))/3600)::numeric(10,1) as avg_resolution_hours
        FROM tickets
    """)
    stats = cur.fetchone()
    
    conn.close()
    return jsonify(stats)

@tickets_bp.route('/support/api/recent')
@staff_required
def api_recent_tickets():
    """Get recent tickets for live updates"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT t.id, t.ticket_number, t.subject, t.status, t.priority, t.created_at, t.updated_at,
               t.is_read_by_staff, u.email as user_email
        FROM tickets t
        LEFT JOIN users u ON t.user_id = u.id
        WHERE t.status IN ('open', 'pending')
        ORDER BY t.updated_at DESC
        LIMIT 10
    """)
    tickets = cur.fetchall()
    
    conn.close()
    return jsonify({'tickets': tickets})

print("✅ Tickets controller loaded")
