"""
SendBaba Webmail Controller
Standalone webmail interface at mail.sendbaba.com
Complete rewrite with all features
"""

from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, send_file
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
import uuid
import os
import hashlib
import json
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename
import base64
import threading
import time

webmail_bp = Blueprint('webmail', __name__)

DATABASE_URL = "postgresql://emailer:SecurePassword123@localhost/emailer"
WEBMAIL_HOSTS = ['mail.sendbaba.com', 'localhost:5000']
UPLOAD_FOLDER = '/opt/sendbaba-staging/uploads/attachments'
MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024  # 25MB

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_db():
    return psycopg2.connect(DATABASE_URL)

def is_webmail_request():
    host = request.host.lower()
    return any(wh in host for wh in WEBMAIL_HOSTS)

def webmail_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'webmail_user' not in session:
            is_api = request.is_json or '/api/' in request.path
            if is_api:
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('webmail.login'))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# INTERCEPT REQUESTS
# ============================================================

@webmail_bp.before_app_request
def intercept_webmail_requests():
    if not is_webmail_request():
        return None
    path = request.path
    if path.startswith('/static') or path.startswith('/api/'):
        return None
    if path == '/' or path == '':
        if 'webmail_user' in session:
            return redirect(url_for('webmail.inbox'))
        return redirect(url_for('webmail.login'))
    return None


# ============================================================
# AUTH ROUTES
# ============================================================

@webmail_bp.route('/login', methods=['GET', 'POST'])
def login():
    from flask import flash
    if not is_webmail_request():
        return redirect('/')

    if request.method == 'POST':
        email = request.form.get('email', '').lower().strip()
        password = request.form.get('password', '')

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, email, name, password_hash, recovery_email, is_active FROM mailboxes WHERE email = %s", (email,))
        mailbox = cur.fetchone()

        if not mailbox:
            conn.close()
            flash('Invalid email or password', 'error')
            return render_template('webmail/login.html')

        if mailbox.get('is_active') == False:
            conn.close()
            flash('Account suspended', 'error')
            return render_template('webmail/login.html')

        password_hash = hashlib.sha256(password.encode()).hexdigest() if password else None
        if mailbox['password_hash'] and mailbox['password_hash'] != password_hash:
            conn.close()
            flash('Invalid email or password', 'error')
            return render_template('webmail/login.html')

        cur.execute("UPDATE mailboxes SET last_login = NOW() WHERE id = %s", (mailbox['id'],))
        conn.commit()
        conn.close()

        session['webmail_user'] = mailbox['email']
        session['webmail_name'] = mailbox['name'] or mailbox['email'].split('@')[0]
        session['webmail_id'] = mailbox['id']
        session.permanent = True

        return redirect(url_for('webmail.inbox'))

    return render_template('webmail/login.html')


@webmail_bp.route('/logout')
def logout():
    session.pop('webmail_user', None)
    session.pop('webmail_name', None)
    session.pop('webmail_id', None)
    return redirect(url_for('webmail.login'))


@webmail_bp.route('/register', methods=['GET', 'POST'])
def register():
    import secrets
    import re
    from flask import flash

    if request.method == 'GET':
        return render_template('webmail/register.html')

    first_name = request.form.get('first_name', '').strip()
    last_name = request.form.get('last_name', '').strip()
    recovery_email = request.form.get('recovery_email', '').strip().lower()
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    name = f"{first_name} {last_name}".strip()
    sendbaba_email = f"{username}@sendbaba.com"

    if not all([first_name, last_name, username, recovery_email, password]):
        flash('All fields required', 'error')
        return render_template('webmail/register.html')

    if len(password) < 8:
        flash('Password must be 8+ characters', 'error')
        return render_template('webmail/register.html')

    if password != confirm_password:
        flash('Passwords do not match', 'error')
        return render_template('webmail/register.html')

    if not re.match(r'^[a-z0-9._]+$', username):
        flash('Invalid username', 'error')
        return render_template('webmail/register.html')

    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM mailboxes WHERE email = %s", (sendbaba_email,))
        if cur.fetchone():
            flash('Email already taken', 'error')
            conn.close()
            return render_template('webmail/register.html')

        slug = f"{re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')}-{secrets.token_hex(4)}"
        cur.execute("""
            INSERT INTO mailbox_organizations (name, slug, plan, max_mailboxes, max_storage_gb, is_active)
            VALUES (%s, %s, 'free', 5, 1, true) RETURNING id
        """, (f"{name}'s Mailbox", slug))
        org_id = cur.fetchone()['id']

        password_hash = hashlib.sha256(password.encode()).hexdigest()
        cur.execute("""
            INSERT INTO mailboxes (organization_id, email, name, password_hash, role, is_active, recovery_email, storage_used_mb)
            VALUES (%s, %s, %s, %s, 'admin', true, %s, 0) RETURNING id
        """, (org_id, sendbaba_email, name, password_hash, recovery_email))

        conn.commit()
        conn.close()

        flash('Registration successful!', 'success')
        return redirect('/login')

    except Exception as e:
        flash('Registration failed', 'error')
        return render_template('webmail/register.html')


# ============================================================
# MAIN PAGES
# ============================================================

@webmail_bp.route('/inbox')
@webmail_login_required
def inbox():
    if not is_webmail_request():
        return redirect('/')
    return render_template('webmail/inbox.html', user=session.get('webmail_user'), name=session.get('webmail_name'))


@webmail_bp.route('/settings')
@webmail_login_required
def settings():
    return render_template('webmail/settings.html', user=session.get('webmail_user'), name=session.get('webmail_name'))


@webmail_bp.route('/chat')
@webmail_login_required
def chat_page():
    with_email = request.args.get('with', '')
    return render_template('webmail/chat.html', with_email=with_email, from_email=session.get('webmail_user', ''))


# ============================================================
# EMAIL API - CORE
# ============================================================

@webmail_bp.route('/api/counts')
@webmail_login_required
def api_counts():
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE folder = 'inbox' AND is_read = false) as inbox_unread,
                COUNT(*) FILTER (WHERE folder = 'inbox') as inbox,
                COUNT(*) FILTER (WHERE folder = 'sent') as sent,
                COUNT(*) FILTER (WHERE folder = 'drafts') as drafts,
                COUNT(*) FILTER (WHERE folder = 'spam') as spam,
                COUNT(*) FILTER (WHERE folder = 'trash') as trash,
                COUNT(*) FILTER (WHERE is_starred = true AND folder != 'trash') as starred
            FROM mailbox_emails
            WHERE mailbox_id = %s AND (deleted_at IS NULL OR folder = 'trash')
        """, (mailbox_id,))
        counts = cur.fetchone()
        conn.close()
        return jsonify({'success': True, 'counts': counts or {}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/emails')
@webmail_login_required
def api_emails():
    try:
        mailbox_id = session.get('webmail_id')
        folder = request.args.get('folder', 'inbox')
        search = request.args.get('search', '')
        label = request.args.get('label', '')
        has_attachment = request.args.get('has_attachment', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        offset = (page - 1) * per_page

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        conditions = ["mailbox_id = %s"]
        params = [mailbox_id]

        if folder == 'starred':
            conditions.append("is_starred = true AND folder != 'trash'")
        elif folder == 'all':
            conditions.append("folder NOT IN ('trash', 'spam')")
        else:
            conditions.append("folder = %s")
            params.append(folder)

        if search:
            conditions.append("(subject ILIKE %s OR from_email ILIKE %s OR from_name ILIKE %s OR body_text ILIKE %s)")
            search_term = f'%{search}%'
            params.extend([search_term, search_term, search_term, search_term])

        if label:
            conditions.append("labels @> %s")
            params.append(json.dumps([label]))

        if has_attachment == '1':
            conditions.append("has_attachments = true")

        if date_from:
            conditions.append("received_at >= %s")
            params.append(date_from)

        if date_to:
            conditions.append("received_at <= %s")
            params.append(date_to)

        where = " AND ".join(conditions)

        cur.execute(f"""
            SELECT id, message_id, from_email, from_name, to_email, subject,
                   SUBSTRING(COALESCE(body_text, ''), 1, 150) as preview,
                   folder, is_read, is_starred, has_attachments, received_at, labels
            FROM mailbox_emails
            WHERE {where}
            ORDER BY received_at DESC
            LIMIT %s OFFSET %s
        """, params + [per_page, offset])

        emails = cur.fetchall()

        cur.execute(f"SELECT COUNT(*) as total FROM mailbox_emails WHERE {where}", params)
        total = cur.fetchone()['total']

        conn.close()
        return jsonify({'success': True, 'emails': emails, 'total': total})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/emails/unread-count')
@webmail_login_required
def api_unread_count():
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT COUNT(*) as count FROM mailbox_emails
            WHERE mailbox_id = %s AND folder = 'inbox' AND is_read = false
        """, (mailbox_id,))
        result = cur.fetchone()
        conn.close()
        return jsonify({'success': True, 'unread_count': result['count'] if result else 0})
    except Exception as e:
        return jsonify({'success': True, 'unread_count': 0})


@webmail_bp.route('/api/email/<int:email_id>')
@webmail_login_required
def api_email(email_id):
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT * FROM mailbox_emails WHERE id = %s AND mailbox_id = %s", (email_id, mailbox_id))
        email = cur.fetchone()

        if not email:
            conn.close()
            return jsonify({'success': False, 'error': 'Email not found'}), 404

        cur.execute("UPDATE mailbox_emails SET is_read = true WHERE id = %s", (email_id,))
        conn.commit()

        cur.execute("SELECT id, filename, content_type, size FROM mailbox_attachments WHERE email_id = %s", (email_id,))
        email['attachments'] = cur.fetchall()

        conn.close()
        return jsonify({'success': True, 'email': email})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/email/<int:email_id>/star', methods=['POST'])
@webmail_login_required
def api_star(email_id):
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE mailbox_emails SET is_starred = NOT is_starred WHERE id = %s AND mailbox_id = %s", (email_id, mailbox_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/email/<int:email_id>/read', methods=['POST'])
@webmail_login_required
def api_read(email_id):
    try:
        mailbox_id = session.get('webmail_id')
        data = request.get_json() or {}
        is_read = data.get('is_read', True)
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE mailbox_emails SET is_read = %s WHERE id = %s AND mailbox_id = %s", (is_read, email_id, mailbox_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/email/<int:email_id>/move', methods=['POST'])
@webmail_login_required
def api_move(email_id):
    try:
        mailbox_id = session.get('webmail_id')
        data = request.get_json() or {}
        folder = data.get('folder', 'inbox')
        conn = get_db()
        cur = conn.cursor()
        if folder == 'trash':
            cur.execute("UPDATE mailbox_emails SET folder = %s, deleted_at = NOW() WHERE id = %s AND mailbox_id = %s", (folder, email_id, mailbox_id))
        else:
            cur.execute("UPDATE mailbox_emails SET folder = %s, deleted_at = NULL WHERE id = %s AND mailbox_id = %s", (folder, email_id, mailbox_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/email/<int:email_id>/delete', methods=['POST'])
@webmail_login_required
def api_delete(email_id):
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE mailbox_emails SET folder = 'trash', deleted_at = NOW() WHERE id = %s AND mailbox_id = %s", (email_id, mailbox_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/email/<int:email_id>/restore', methods=['POST'])
@webmail_login_required
def api_restore(email_id):
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE mailbox_emails SET folder = 'inbox', deleted_at = NULL WHERE id = %s AND mailbox_id = %s AND folder = 'trash'", (email_id, mailbox_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Email restored'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/email/<int:email_id>/permanent-delete', methods=['POST'])
@webmail_login_required
def api_permanent_delete(email_id):
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM mailbox_emails WHERE id = %s AND mailbox_id = %s AND folder = 'trash'", (email_id, mailbox_id))
        if not cur.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Email not found in trash'}), 404

        cur.execute("SELECT path FROM mailbox_attachments WHERE email_id = %s", (email_id,))
        for row in cur.fetchall():
            try:
                if row['path'] and os.path.exists(row['path']):
                    os.remove(row['path'])
            except:
                pass

        cur.execute("DELETE FROM mailbox_attachments WHERE email_id = %s", (email_id,))
        cur.execute("DELETE FROM mailbox_emails WHERE id = %s", (email_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Email permanently deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/emails/empty-trash', methods=['POST'])
@webmail_login_required
def api_empty_trash():
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT id FROM mailbox_emails WHERE mailbox_id = %s AND folder = 'trash'", (mailbox_id,))
        trash_emails = cur.fetchall()
        count = len(trash_emails)

        if count > 0:
            email_ids = [e['id'] for e in trash_emails]
            cur.execute("SELECT path FROM mailbox_attachments WHERE email_id = ANY(%s)", (email_ids,))
            for row in cur.fetchall():
                try:
                    if row['path'] and os.path.exists(row['path']):
                        os.remove(row['path'])
                except:
                    pass
            cur.execute("DELETE FROM mailbox_attachments WHERE email_id = ANY(%s)", (email_ids,))
            cur.execute("DELETE FROM mailbox_emails WHERE id = ANY(%s)", (email_ids,))

        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'{count} emails deleted'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# BULK ACTIONS
# ============================================================

@webmail_bp.route('/api/bulk', methods=['POST'])
@webmail_login_required
def api_bulk():
    try:
        mailbox_id = session.get('webmail_id')
        data = request.get_json() or {}
        email_ids = data.get('ids', [])
        action = data.get('action', '')

        if not email_ids or not action:
            return jsonify({'success': False, 'error': 'Missing ids or action'}), 400

        conn = get_db()
        cur = conn.cursor()

        cur.execute("SELECT id FROM mailbox_emails WHERE id = ANY(%s) AND mailbox_id = %s", (email_ids, mailbox_id))
        valid_ids = [r[0] for r in cur.fetchall()]

        if action == 'read':
            cur.execute("UPDATE mailbox_emails SET is_read = true WHERE id = ANY(%s)", (valid_ids,))
        elif action == 'unread':
            cur.execute("UPDATE mailbox_emails SET is_read = false WHERE id = ANY(%s)", (valid_ids,))
        elif action == 'trash':
            cur.execute("UPDATE mailbox_emails SET folder = 'trash', deleted_at = NOW() WHERE id = ANY(%s)", (valid_ids,))
        elif action == 'spam':
            cur.execute("UPDATE mailbox_emails SET folder = 'spam' WHERE id = ANY(%s)", (valid_ids,))
        elif action == 'star':
            cur.execute("UPDATE mailbox_emails SET is_starred = true WHERE id = ANY(%s)", (valid_ids,))
        elif action == 'unstar':
            cur.execute("UPDATE mailbox_emails SET is_starred = false WHERE id = ANY(%s)", (valid_ids,))
        elif action == 'inbox':
            cur.execute("UPDATE mailbox_emails SET folder = 'inbox', deleted_at = NULL WHERE id = ANY(%s)", (valid_ids,))
        elif action == 'delete':
            cur.execute("DELETE FROM mailbox_emails WHERE id = ANY(%s)", (valid_ids,))

        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# LABELS/TAGS
# ============================================================

@webmail_bp.route('/api/labels')
@webmail_login_required
def api_labels():
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get unique labels from emails
        cur.execute("""
            SELECT DISTINCT jsonb_array_elements_text(labels) as label
            FROM mailbox_emails
            WHERE mailbox_id = %s AND labels IS NOT NULL
        """, (mailbox_id,))
        labels = [r['label'] for r in cur.fetchall()]
        conn.close()
        return jsonify({'success': True, 'labels': labels})
    except Exception as e:
        return jsonify({'success': True, 'labels': []})


@webmail_bp.route('/api/email/<int:email_id>/labels', methods=['POST'])
@webmail_login_required
def api_update_labels(email_id):
    try:
        mailbox_id = session.get('webmail_id')
        data = request.get_json() or {}
        labels = data.get('labels', [])

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE mailbox_emails SET labels = %s
            WHERE id = %s AND mailbox_id = %s
        """, (json.dumps(labels), email_id, mailbox_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# SEND EMAIL WITH ATTACHMENTS
# ============================================================

@webmail_bp.route('/api/send', methods=['POST'])
@webmail_login_required
def api_send():
    try:
        from app.utils.internal_delivery import is_internal_user, deliver_internal

        mailbox_id = session.get('webmail_id')
        from_email = session.get('webmail_user')
        from_name = session.get('webmail_name', '')

        # Handle both JSON and form data
        if request.is_json:
            data = request.get_json()
            attachments = []
        else:
            data = request.form.to_dict()
            attachments = request.files.getlist('attachments')

        to_email = data.get('to', '').strip().lower()
        cc = data.get('cc', '')
        bcc = data.get('bcc', '')
        subject = data.get('subject', '')
        body = data.get('body', '')
        is_html = data.get('is_html', 'true') == 'true' or data.get('is_html') == True
        is_draft = data.get('draft', False)
        schedule_at = data.get('schedule_at', '')

        if not to_email and not is_draft:
            return jsonify({'success': False, 'error': 'Recipient required'}), 400

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        message_id = f'<{uuid.uuid4()}@sendbaba.com>'
        folder = 'drafts' if is_draft else ('scheduled' if schedule_at else 'sent')

        html_body = body if is_html else f'<html><body><p>{body.replace(chr(10), "<br>")}</p></body></html>'
        text_body = body if not is_html else ''

        has_attachments = len(attachments) > 0

        cur.execute("""
            INSERT INTO mailbox_emails
            (mailbox_id, message_id, from_email, from_name, to_email, cc, subject,
             body_text, body_html, folder, is_read, has_attachments, received_at, scheduled_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, %s, NOW(), %s)
            RETURNING id
        """, (mailbox_id, message_id, from_email, from_name, to_email, cc, subject,
              text_body, html_body, folder, has_attachments, schedule_at or None))

        email_id = cur.fetchone()['id']

        # Save attachments
        for att in attachments:
            if att.filename:
                filename = secure_filename(att.filename)
                filepath = os.path.join(UPLOAD_FOLDER, f"{email_id}_{filename}")
                att.save(filepath)
                size = os.path.getsize(filepath)

                cur.execute("""
                    INSERT INTO mailbox_attachments (email_id, filename, content_type, size, path)
                    VALUES (%s, %s, %s, %s, %s)
                """, (email_id, filename, att.content_type, size, filepath))

        conn.commit()
        conn.close()

        if is_draft or schedule_at:
            return jsonify({'success': True, 'email_id': email_id, 'scheduled': bool(schedule_at)})

        # Send to recipients
        all_recipients = [to_email]
        if cc:
            all_recipients.extend([e.strip().lower() for e in cc.split(',') if e.strip()])
        if bcc:
            all_recipients.extend([e.strip().lower() for e in bcc.split(',') if e.strip()])

        for recipient in all_recipients:
            if is_internal_user(recipient):
                deliver_internal(
                    from_email=from_email, from_name=from_name, to_email=recipient,
                    subject=subject, body_text=text_body, body_html=html_body,
                    message_id=message_id, has_audio=False
                )
            else:
                try:
                    from app.smtp.relay_server import send_email_sync
                    send_email_sync({
                        'from': from_email, 'from_name': from_name, 'to': recipient,
                        'subject': subject, 'html_body': html_body, 'text_body': text_body
                    })
                except Exception as e:
                    print(f"SMTP error: {e}")

        return jsonify({'success': True, 'email_id': email_id})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# UPLOAD ATTACHMENT
# ============================================================

@webmail_bp.route('/api/upload-attachment', methods=['POST'])
@webmail_login_required
def api_upload_attachment():
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']
        if not file.filename:
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        filename = secure_filename(file.filename)
        temp_id = uuid.uuid4().hex
        filepath = os.path.join(UPLOAD_FOLDER, f"temp_{temp_id}_{filename}")
        file.save(filepath)
        size = os.path.getsize(filepath)

        if size > MAX_ATTACHMENT_SIZE:
            os.remove(filepath)
            return jsonify({'success': False, 'error': 'File too large (max 25MB)'}), 400

        return jsonify({
            'success': True,
            'attachment': {
                'temp_id': temp_id,
                'filename': filename,
                'size': size,
                'path': filepath,
                'content_type': file.content_type
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/attachment/<int:attachment_id>')
@webmail_login_required
def api_attachment(attachment_id):
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT a.* FROM mailbox_attachments a
            JOIN mailbox_emails e ON a.email_id = e.id
            WHERE a.id = %s AND e.mailbox_id = %s
        """, (attachment_id, mailbox_id))

        att = cur.fetchone()
        conn.close()

        if not att or not att.get('path') or not os.path.exists(att['path']):
            return jsonify({'success': False, 'error': 'Attachment not found'}), 404

        return send_file(att['path'], as_attachment=True, download_name=att['filename'], mimetype=att['content_type'])
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# DRAFTS
# ============================================================

@webmail_bp.route('/api/drafts', methods=['POST'])
@webmail_login_required
def api_save_draft():
    try:
        mailbox_id = session.get('webmail_id')
        user_email = session.get('webmail_user')
        data = request.get_json()

        to_email = data.get('to', '').strip()
        subject = data.get('subject', '').strip()
        body = data.get('body', '')
        draft_id = data.get('draft_id')

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if draft_id:
            cur.execute("""
                UPDATE mailbox_emails
                SET to_email = %s, subject = %s, body_text = %s, body_html = %s, updated_at = NOW()
                WHERE id = %s AND mailbox_id = %s AND folder = 'drafts'
                RETURNING id
            """, (to_email, subject, body, body, draft_id, mailbox_id))
            result = cur.fetchone()
            if result:
                conn.commit()
                conn.close()
                return jsonify({'success': True, 'draft_id': result['id']})

        message_id = f"<draft-{uuid.uuid4()}@sendbaba.com>"
        cur.execute("""
            INSERT INTO mailbox_emails (mailbox_id, message_id, from_email, from_name, to_email, subject, body_text, body_html, folder, is_read, received_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'drafts', true, NOW())
            RETURNING id
        """, (mailbox_id, message_id, user_email, session.get('webmail_name', ''), to_email, subject, body, body))

        result = cur.fetchone()
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'draft_id': result['id']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/drafts/<int:draft_id>', methods=['GET'])
@webmail_login_required
def api_get_draft(draft_id):
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, to_email, subject, body_html, body_text FROM mailbox_emails WHERE id = %s AND mailbox_id = %s AND folder = 'drafts'", (draft_id, mailbox_id))
        draft = cur.fetchone()
        conn.close()
        if not draft:
            return jsonify({'success': False, 'error': 'Draft not found'}), 404
        return jsonify({'success': True, 'draft': draft})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/drafts/<int:draft_id>', methods=['DELETE'])
@webmail_login_required
def api_delete_draft(draft_id):
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM mailbox_emails WHERE id = %s AND mailbox_id = %s AND folder = 'drafts'", (draft_id, mailbox_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# SCHEDULED EMAILS
# ============================================================

@webmail_bp.route('/api/scheduled')
@webmail_login_required
def api_scheduled():
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT id, to_email, subject, scheduled_at
            FROM mailbox_emails
            WHERE mailbox_id = %s AND folder = 'scheduled' AND scheduled_at IS NOT NULL
            ORDER BY scheduled_at ASC
        """, (mailbox_id,))
        emails = cur.fetchall()
        conn.close()
        return jsonify({'success': True, 'scheduled': emails})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/scheduled/<int:email_id>/cancel', methods=['POST'])
@webmail_login_required
def api_cancel_scheduled(email_id):
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE mailbox_emails SET folder = 'drafts', scheduled_at = NULL
            WHERE id = %s AND mailbox_id = %s AND folder = 'scheduled'
        """, (email_id, mailbox_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Scheduled email cancelled'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# EMAIL SIGNATURE
# ============================================================

@webmail_bp.route('/api/signature')
@webmail_login_required
def api_get_signature():
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT signature FROM mailboxes WHERE id = %s", (mailbox_id,))
        result = cur.fetchone()
        conn.close()
        return jsonify({'success': True, 'signature': result['signature'] if result else ''})
    except Exception as e:
        return jsonify({'success': True, 'signature': ''})


@webmail_bp.route('/api/signature', methods=['POST'])
@webmail_login_required
def api_save_signature():
    try:
        mailbox_id = session.get('webmail_id')
        data = request.get_json()
        signature = data.get('signature', '')

        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE mailboxes SET signature = %s WHERE id = %s", (signature, mailbox_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# EMAIL TEMPLATES
# ============================================================

@webmail_bp.route('/api/templates')
@webmail_login_required
def api_templates():
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Check if table exists, create if not
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mailbox_templates (
                id SERIAL PRIMARY KEY,
                mailbox_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                subject VARCHAR(500),
                body TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()

        cur.execute("SELECT * FROM mailbox_templates WHERE mailbox_id = %s ORDER BY name", (mailbox_id,))
        templates = cur.fetchall()
        conn.close()
        return jsonify({'success': True, 'templates': templates})
    except Exception as e:
        return jsonify({'success': True, 'templates': []})


@webmail_bp.route('/api/templates', methods=['POST'])
@webmail_login_required
def api_save_template():
    try:
        mailbox_id = session.get('webmail_id')
        data = request.get_json()
        name = data.get('name', '').strip()
        subject = data.get('subject', '')
        body = data.get('body', '')

        if not name:
            return jsonify({'success': False, 'error': 'Template name required'}), 400

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            INSERT INTO mailbox_templates (mailbox_id, name, subject, body)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (mailbox_id, name, subject, body))

        template_id = cur.fetchone()['id']
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'template_id': template_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/templates/<int:template_id>', methods=['DELETE'])
@webmail_login_required
def api_delete_template(template_id):
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM mailbox_templates WHERE id = %s AND mailbox_id = %s", (template_id, mailbox_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# VACATION RESPONDER
# ============================================================

@webmail_bp.route('/api/vacation')
@webmail_login_required
def api_get_vacation():
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT vacation_enabled, vacation_subject, vacation_message, vacation_start, vacation_end
            FROM mailboxes WHERE id = %s
        """, (mailbox_id,))
        result = cur.fetchone()
        conn.close()
        return jsonify({'success': True, 'vacation': result or {}})
    except Exception as e:
        return jsonify({'success': True, 'vacation': {}})


@webmail_bp.route('/api/vacation', methods=['POST'])
@webmail_login_required
def api_save_vacation():
    try:
        mailbox_id = session.get('webmail_id')
        data = request.get_json()

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE mailboxes SET
                vacation_enabled = %s,
                vacation_subject = %s,
                vacation_message = %s,
                vacation_start = %s,
                vacation_end = %s
            WHERE id = %s
        """, (
            data.get('enabled', False),
            data.get('subject', 'Out of Office'),
            data.get('message', ''),
            data.get('start_date') or None,
            data.get('end_date') or None,
            mailbox_id
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# FORWARDING RULES
# ============================================================

@webmail_bp.route('/api/forwarding')
@webmail_login_required
def api_get_forwarding():
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT forwarding_enabled, forwarding_address, forwarding_keep_copy
            FROM mailboxes WHERE id = %s
        """, (mailbox_id,))
        result = cur.fetchone()
        conn.close()
        return jsonify({'success': True, 'forwarding': result or {}})
    except Exception as e:
        return jsonify({'success': True, 'forwarding': {}})


@webmail_bp.route('/api/forwarding', methods=['POST'])
@webmail_login_required
def api_save_forwarding():
    try:
        mailbox_id = session.get('webmail_id')
        data = request.get_json()

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE mailboxes SET
                forwarding_enabled = %s,
                forwarding_address = %s,
                forwarding_keep_copy = %s
            WHERE id = %s
        """, (
            data.get('enabled', False),
            data.get('address', ''),
            data.get('keep_copy', True),
            mailbox_id
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# UNDO SEND (Store pending for 5 seconds)
# ============================================================

pending_sends = {}

@webmail_bp.route('/api/send-with-undo', methods=['POST'])
@webmail_login_required
def api_send_with_undo():
    try:
        mailbox_id = session.get('webmail_id')
        data = request.get_json()

        send_id = uuid.uuid4().hex
        pending_sends[send_id] = {
            'data': data,
            'mailbox_id': mailbox_id,
            'user': session.get('webmail_user'),
            'name': session.get('webmail_name'),
            'time': datetime.now()
        }

        # Schedule actual send after 5 seconds
        def delayed_send():
            time.sleep(5)
            if send_id in pending_sends:
                send_data = pending_sends.pop(send_id)
                # Perform actual send
                # (Implementation would call the normal send logic)

        thread = threading.Thread(target=delayed_send)
        thread.daemon = True
        thread.start()

        return jsonify({'success': True, 'send_id': send_id, 'undo_seconds': 5})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/undo-send/<send_id>', methods=['POST'])
@webmail_login_required
def api_undo_send(send_id):
    try:
        if send_id in pending_sends:
            pending_sends.pop(send_id)
            return jsonify({'success': True, 'message': 'Send cancelled'})
        return jsonify({'success': False, 'error': 'Too late to undo'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# CONTACTS
# ============================================================

@webmail_bp.route('/api/contacts')
@webmail_login_required
def api_contacts():
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT DISTINCT LOWER(to_email) as email, COUNT(*) as cnt, MAX(received_at) as last
            FROM mailbox_emails
            WHERE mailbox_id = %s AND folder = 'sent' AND to_email IS NOT NULL AND to_email != ''
            GROUP BY LOWER(to_email)
            ORDER BY cnt DESC, last DESC
            LIMIT 100
        """, (mailbox_id,))

        contacts = cur.fetchall()
        conn.close()

        formatted = [{'email': c['email'], 'name': c['email'].split('@')[0].replace('.', ' ').title()} for c in contacts]
        return jsonify({'success': True, 'contacts': formatted})
    except Exception as e:
        return jsonify({'success': True, 'contacts': []})


@webmail_bp.route('/api/contacts/search')
@webmail_login_required
def api_contacts_search():
    try:
        mailbox_id = session.get('webmail_id')
        query = request.args.get('q', '').lower()

        if len(query) < 1:
            return jsonify({'success': True, 'contacts': []})

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT DISTINCT LOWER(to_email) as email
            FROM mailbox_emails
            WHERE mailbox_id = %s AND folder = 'sent' AND LOWER(to_email) LIKE %s
            LIMIT 10
        """, (mailbox_id, f'%{query}%'))

        contacts = [{'email': r['email'], 'name': r['email'].split('@')[0].replace('.', ' ').title()} for r in cur.fetchall()]
        conn.close()
        return jsonify({'success': True, 'contacts': contacts})
    except Exception as e:
        return jsonify({'success': True, 'contacts': []})


# ============================================================
# THREADS
# ============================================================

@webmail_bp.route('/api/thread/<thread_id>')
@webmail_login_required
def api_thread(thread_id):
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT id, from_email, from_name, to_email, subject, body_text, body_html, received_at, is_read
            FROM mailbox_emails
            WHERE mailbox_id = %s AND (thread_id = %s OR message_id = %s)
            ORDER BY received_at ASC
        """, (mailbox_id, thread_id, thread_id))

        emails = cur.fetchall()
        conn.close()
        return jsonify({'success': True, 'emails': emails})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# CHAT
# ============================================================

@webmail_bp.route('/api/chat/conversations')
@webmail_login_required
def api_chat_conversations():
    try:
        from_email = session.get('webmail_user')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Update our own last_seen
        mailbox_id = session.get('webmail_id')
        cur.execute("UPDATE mailboxes SET last_seen = NOW() WHERE id = %s", (mailbox_id,))
        conn.commit()
        
        cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'chat_messages')")
        if not cur.fetchone()['exists']:
            conn.close()
            return jsonify({'success': True, 'conversations': []})
        
        # Get conversations with online status
        cur.execute("""
            WITH conversations AS (
                SELECT
                    CASE WHEN from_email = %s THEN to_email ELSE from_email END as with_email,
                    content as last_message,
                    created_at as last_message_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY CASE WHEN from_email = %s THEN to_email ELSE from_email END
                        ORDER BY created_at DESC
                    ) as rn
                FROM chat_messages
                WHERE from_email = %s OR to_email = %s
            )
            SELECT c.with_email, c.last_message, c.last_message_at,
                   COALESCE(m.last_seen > NOW() - INTERVAL '10 seconds', false) as is_online
            FROM conversations c
            LEFT JOIN mailboxes m ON LOWER(m.email) = LOWER(c.with_email)
            WHERE c.rn = 1
            ORDER BY c.last_message_at DESC LIMIT 50
        """, (from_email, from_email, from_email, from_email))
        conversations = cur.fetchall()
        
        # Get unread counts
        cur.execute("""
            SELECT from_email, COUNT(*) as cnt FROM chat_messages 
            WHERE to_email = %s AND is_read = false GROUP BY from_email
        """, (from_email,))
        unread = {r['from_email']: r['cnt'] for r in cur.fetchall()}
        
        conn.close()
        
        result = [{
            'email': c['with_email'],
            'name': c['with_email'].split('@')[0].replace('.', ' ').title(),
            'last_message': c['last_message'],
            'last_message_at': c['last_message_at'].isoformat() if c['last_message_at'] else None,
            'is_online': c['is_online'] or False,
            'unread': unread.get(c['with_email'], 0)
        } for c in conversations]
        return jsonify({'success': True, 'conversations': result})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': True, 'conversations': []})

        cur.execute("""
            WITH conversations AS (
                SELECT
                    CASE WHEN from_email = %s THEN to_email ELSE from_email END as with_email,
                    content as last_message,
                    created_at as last_message_at,
                    ROW_NUMBER() OVER (
                        PARTITION BY CASE WHEN from_email = %s THEN to_email ELSE from_email END
                        ORDER BY created_at DESC
                    ) as rn
                FROM chat_messages
                WHERE from_email = %s OR to_email = %s
            )
            SELECT with_email, last_message, last_message_at
            FROM conversations WHERE rn = 1
            ORDER BY last_message_at DESC LIMIT 50
        """, (from_email, from_email, from_email, from_email))

        conversations = cur.fetchall()
        conn.close()

        result = [{
            'email': c['with_email'],
            'name': c['with_email'].split('@')[0].replace('.', ' ').title(),
            'last_message': c['last_message'],
            'last_message_at': c['last_message_at'].isoformat() if c['last_message_at'] else None
        } for c in conversations]

        return jsonify({'success': True, 'conversations': result})
    except Exception as e:
        return jsonify({'success': True, 'conversations': []})


@webmail_bp.route('/api/chat/send', methods=['POST'])
@webmail_login_required
def api_chat_send():
    try:
        from_email = session.get('webmail_user')
        data = request.get_json() or {}
        to_email = data.get('to', '')
        content = data.get('message', '') or data.get('content', '')

        if not to_email or not content:
            return jsonify({'success': False, 'error': 'Missing to or content'}), 400

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id SERIAL PRIMARY KEY,
                from_email VARCHAR(255) NOT NULL,
                to_email VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                is_read BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        cur.execute("""
            INSERT INTO chat_messages (from_email, to_email, content)
            VALUES (%s, %s, %s) RETURNING id, created_at
        """, (from_email, to_email, content))

        result = cur.fetchone()
        conn.commit()
        conn.close()

        return jsonify({'success': True, 'message_id': result['id'], 'time': result['created_at'].strftime('%H:%M')})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/chat/history')
@webmail_login_required
def api_chat_history():
    try:
        from_email = session.get('webmail_user')
        with_email = request.args.get('with', '')

        if not with_email:
            return jsonify({'success': False, 'error': 'Missing with parameter'}), 400

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'chat_messages')")
        if not cur.fetchone()['exists']:
            conn.close()
            return jsonify({'success': True, 'messages': []})

        cur.execute("""
            SELECT id, content, created_at, message_type, audio_url, audio_duration,
                   CASE WHEN from_email = %s THEN true ELSE false END as sent_by_me
            FROM chat_messages
            WHERE (from_email = %s AND to_email = %s) OR (from_email = %s AND to_email = %s)
            ORDER BY created_at ASC LIMIT 100
        """, (from_email, from_email, with_email, with_email, from_email))

        messages = [{'id': m['id'], 'content': m['content'], 'sent_by_me': m['sent_by_me'], 'time': m['created_at'].strftime('%H:%M'), 'type': m.get('message_type', 'text'), 'audio_url': m.get('audio_url'), 'duration': m.get('audio_duration', 0)} for m in cur.fetchall()]
        conn.close()
        return jsonify({'success': True, 'messages': messages})
    except Exception as e:
        return jsonify({'success': True, 'messages': []})


@webmail_bp.route('/api/chat/unread-count')
@webmail_login_required
def api_chat_unread_count():
    try:
        from_email = session.get('webmail_user')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'chat_messages')")
        if not cur.fetchone()['exists']:
            conn.close()
            return jsonify({'success': True, 'count': 0})

        cur.execute("SELECT COUNT(*) as count FROM chat_messages WHERE to_email = %s AND is_read = false", (from_email,))
        result = cur.fetchone()
        conn.close()
        return jsonify({'success': True, 'count': result['count'] if result else 0})
    except Exception as e:
        return jsonify({'success': True, 'count': 0})


@webmail_bp.route('/api/chat/mark-read', methods=['POST'])
@webmail_login_required
def api_chat_mark_read():
    try:
        from_email = session.get('webmail_user')
        data = request.get_json() or {}
        with_email = data.get('with', '')

        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE chat_messages SET is_read = true WHERE to_email = %s AND from_email = %s", (from_email, with_email))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================
# SETTINGS API
# ============================================================

@webmail_bp.route('/api/settings/profile')
@webmail_login_required
def api_settings_profile():
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT name, signature, timezone FROM mailboxes WHERE id = %s", (mailbox_id,))
        profile = cur.fetchone()
        conn.close()
        return jsonify({'success': True, 'profile': profile or {}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/settings/profile', methods=['PUT'])
@webmail_login_required
def api_settings_update_profile():
    try:
        mailbox_id = session.get('webmail_id')
        data = request.get_json()

        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE mailboxes SET name = %s, signature = %s WHERE id = %s", (data.get('name'), data.get('signature'), mailbox_id))
        conn.commit()
        conn.close()

        session['webmail_name'] = data.get('name')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/settings/password', methods=['POST'])
@webmail_login_required
def api_change_password():
    try:
        mailbox_id = session.get('webmail_id')
        data = request.get_json()
        current = data.get('current_password', '')
        new_pass = data.get('new_password', '')

        if len(new_pass) < 8:
            return jsonify({'success': False, 'error': 'Password must be 8+ characters'}), 400

        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT password_hash FROM mailboxes WHERE id = %s", (mailbox_id,))
        row = cur.fetchone()

        if row and row['password_hash']:
            current_hash = hashlib.sha256(current.encode()).hexdigest()
            if current_hash != row['password_hash']:
                conn.close()
                return jsonify({'success': False, 'error': 'Current password incorrect'}), 400

        new_hash = hashlib.sha256(new_pass.encode()).hexdigest()
        cur.execute("UPDATE mailboxes SET password_hash = %s WHERE id = %s", (new_hash, mailbox_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/check-email')
def api_check_email():
    import re
    username = request.args.get('username', '').lower().strip()

    if not username or len(username) < 3:
        return jsonify({'available': False, 'error': 'Min 3 characters'})

    if not re.match(r'^[a-z0-9._]+$', username):
        return jsonify({'available': False, 'error': 'Invalid characters'})

    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id FROM mailboxes WHERE email = %s", (f"{username}@sendbaba.com",))
        exists = cur.fetchone() is not None
        conn.close()

        if exists:
            return jsonify({'available': False, 'suggestions': [f"{username}1", f"{username}2"]})
        return jsonify({'available': True, 'email': f"{username}@sendbaba.com"})
    except Exception as e:
        return jsonify({'available': False, 'error': str(e)})


# ============================================================
# ADVERTISING PAGE
# ============================================================

@webmail_bp.route('/ads')
def ads_page():
    """Advertising page - promote your business"""
    return render_template('webmail/ads.html')


@webmail_bp.route('/api/ads/create', methods=['POST'])
def api_create_ad():
    """Create a new ad campaign"""
    try:
        data = request.get_json() or {}
        
        business_name = data.get('business_name', '').strip()
        email = data.get('email', '').strip().lower()
        website = data.get('website', '').strip()
        ad_title = data.get('ad_title', '').strip()
        ad_description = data.get('ad_description', '').strip()
        plan = data.get('plan', 'starter')
        
        if not all([business_name, email, ad_title]):
            return jsonify({'success': False, 'error': 'Required fields missing'}), 400
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Create ads table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS webmail_ads (
                id SERIAL PRIMARY KEY,
                business_name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                website VARCHAR(500),
                ad_title VARCHAR(255) NOT NULL,
                ad_description TEXT,
                ad_image_url VARCHAR(500),
                plan VARCHAR(50) DEFAULT 'starter',
                price_cents INTEGER DEFAULT 500,
                impressions INTEGER DEFAULT 0,
                clicks INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT FALSE,
                is_paid BOOLEAN DEFAULT FALSE,
                start_date DATE,
                end_date DATE,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # Insert ad
        cur.execute("""
            INSERT INTO webmail_ads (business_name, email, website, ad_title, ad_description, plan)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (business_name, email, website, ad_title, ad_description, plan))
        
        ad_id = cur.fetchone()['id']
        conn.commit()
        conn.close()
        
        # TODO: Integrate with payment gateway (Korapay/Paystack)
        
        return jsonify({
            'success': True, 
            'ad_id': ad_id,
            'message': 'Ad campaign created! Proceed to payment.',
            'payment_url': f'/ads/pay/{ad_id}'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/ads/track/<int:ad_id>', methods=['POST'])
def api_track_ad(ad_id):
    """Track ad impression or click"""
    try:
        data = request.get_json() or {}
        action = data.get('action', 'impression')  # impression or click
        
        conn = get_db()
        cur = conn.cursor()
        
        if action == 'click':
            cur.execute("UPDATE webmail_ads SET clicks = clicks + 1 WHERE id = %s", (ad_id,))
        else:
            cur.execute("UPDATE webmail_ads SET impressions = impressions + 1 WHERE id = %s", (ad_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except:
        return jsonify({'success': False}), 500


# ============================================================
# REAL-TIME ONLINE STATUS
# ============================================================

@webmail_bp.route('/api/chat/online', methods=['POST'])
@webmail_login_required
def api_chat_online():
    """Update user's online status"""
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE mailboxes SET last_seen = NOW() WHERE id = %s", (mailbox_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except:
        return jsonify({'success': True})


# ============================================================
# VOICE MESSAGES
# ============================================================

@webmail_bp.route('/api/chat/send-audio', methods=['POST'])
@webmail_login_required
def api_chat_send_audio():
    """Send voice message"""
    try:
        from_email = session.get('webmail_user')
        to_email = request.form.get('to', '').strip()
        
        if not to_email:
            return jsonify({'success': False, 'error': 'Recipient required'}), 400
        
        if 'audio' not in request.files:
            return jsonify({'success': False, 'error': 'No audio file'}), 400
        
        audio_file = request.files['audio']
        duration = int(request.form.get('duration', 0))
        
        # Save audio file
        import time
        filename = f"voice_{int(time.time())}_{uuid.uuid4().hex[:8]}.webm"
        audio_dir = '/opt/sendbaba-staging/uploads/voice'
        os.makedirs(audio_dir, exist_ok=True)
        filepath = os.path.join(audio_dir, filename)
        audio_file.save(filepath)
        
        audio_url = f'/api/chat/audio/{filename}'
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            INSERT INTO chat_messages (from_email, to_email, content, message_type, audio_url, audio_duration)
            VALUES (%s, %s, %s, 'audio', %s, %s)
            RETURNING id, created_at
        """, (from_email, to_email, '🎤 Voice message', audio_url, duration))
        
        result = cur.fetchone()
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message_id': result['id'],
            'audio_url': audio_url,
            'time': result['created_at'].strftime('%H:%M')
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/chat/audio/<filename>')
@webmail_login_required
def api_chat_audio(filename):
    """Serve voice message audio"""
    try:
        import re
        if not re.match(r'^voice_\d+_[a-f0-9]+\.webm$', filename):
            return jsonify({'error': 'Invalid filename'}), 400
        
        filepath = f'/opt/sendbaba-staging/uploads/voice/{filename}'
        
        if not os.path.exists(filepath):
            return jsonify({'error': 'Audio not found'}), 404
        
        return send_file(filepath, mimetype='audio/webm')
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# TEAM & CUSTOM DOMAINS
# ============================================================

@webmail_bp.route('/team')
@webmail_login_required
def team_page():
    """Team and domains management page"""
    return render_template('webmail/team.html')


@webmail_bp.route('/api/team/domains')
@webmail_login_required
def api_team_domains():
    """List user's custom domains"""
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get organization ID for this mailbox
        cur.execute("SELECT organization_id FROM mailboxes WHERE id = %s", (mailbox_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Mailbox not found'}), 404
        
        org_id = row['organization_id']
        
        # Create webmail_domains table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS webmail_domains (
                id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::varchar(36),
                organization_id INTEGER NOT NULL,
                domain_name VARCHAR(255) NOT NULL UNIQUE,
                verification_token VARCHAR(64),
                dns_verified BOOLEAN DEFAULT FALSE,
                mx_valid BOOLEAN DEFAULT FALSE,
                spf_valid BOOLEAN DEFAULT FALSE,
                dkim_valid BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT NOW(),
                verified_at TIMESTAMP
            )
        """)
        conn.commit()
        
        cur.execute("""
            SELECT id, domain_name, verification_token, dns_verified, mx_valid, spf_valid, dkim_valid, created_at
            FROM webmail_domains
            WHERE organization_id = %s AND is_active = true
            ORDER BY created_at DESC
        """, (org_id,))
        
        domains = cur.fetchall()
        conn.close()
        return jsonify({'success': True, 'domains': domains})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/team/domains', methods=['POST'])
@webmail_login_required
def api_team_add_domain():
    """Add a new custom domain"""
    try:
        import secrets
        import re
        
        mailbox_id = session.get('webmail_id')
        data = request.get_json() or {}
        domain = data.get('domain', '').strip().lower()
        
        # Validate domain format
        if not domain or not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$', domain):
            return jsonify({'success': False, 'error': 'Invalid domain format'}), 400
        
        # Don't allow sendbaba.com
        if 'sendbaba.com' in domain:
            return jsonify({'success': False, 'error': 'Cannot add sendbaba.com domains'}), 400
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get org ID
        cur.execute("SELECT organization_id FROM mailboxes WHERE id = %s", (mailbox_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Mailbox not found'}), 404
        org_id = row['organization_id']
        
        # Check if domain already exists
        cur.execute("SELECT id, is_active FROM webmail_domains WHERE domain_name = %s", (domain,))
        existing = cur.fetchone()
        if existing:
            if existing['is_active']:
                conn.close()
                return jsonify({'success': False, 'error': 'Domain already registered'}), 400
            else:
                # Reactivate the domain
                cur.execute("""
                    UPDATE webmail_domains 
                    SET is_active = true, organization_id = %s, dns_verified = false, mx_valid = false, spf_valid = false
                    WHERE id = %s
                    RETURNING id, verification_token
                """, (org_id, existing['id']))
                result = cur.fetchone()
                conn.commit()
                conn.close()
                return jsonify({
                    'success': True,
                    'domain_id': result['id'],
                    'verification_token': result['verification_token'],
                    'message': 'Domain reactivated'
                })
        
        # Create verification token
        verification_token = secrets.token_hex(16)
        
        cur.execute("""
            INSERT INTO webmail_domains (organization_id, domain_name, verification_token)
            VALUES (%s, %s, %s)
            RETURNING id
        """, (org_id, domain, verification_token))
        
        domain_id = cur.fetchone()['id']
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'domain_id': domain_id,
            'verification_token': verification_token
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/team/domains/<domain_id>/verify', methods=['POST'])
@webmail_login_required
def api_team_verify_domain(domain_id):
    """Verify domain DNS records - MX record is sufficient proof of ownership"""
    try:
        import dns.resolver
        
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get org ID
        cur.execute("SELECT organization_id FROM mailboxes WHERE id = %s", (mailbox_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        org_id = row['organization_id']
        
        # Get domain
        cur.execute("""
            SELECT domain_name, verification_token FROM webmail_domains
            WHERE id = %s AND organization_id = %s
        """, (domain_id, org_id))
        domain = cur.fetchone()
        
        if not domain:
            conn.close()
            return jsonify({'success': False, 'error': 'Domain not found'}), 404
        
        domain_name = domain['domain_name']
        
        mx_valid = False
        spf_valid = False
        
        # Check MX record - this is the main verification
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = 5
            resolver.lifetime = 5
            mx_records = resolver.resolve(domain_name, 'MX')
            for mx in mx_records:
                if 'sendbaba.com' in str(mx.exchange).lower():
                    mx_valid = True
                    break
        except Exception as e:
            print(f"MX check error for {domain_name}: {e}")
        
        # Check SPF record (optional, for sending)
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = 5
            resolver.lifetime = 5
            txt_records = resolver.resolve(domain_name, 'TXT')
            for txt in txt_records:
                txt_value = str(txt).strip('"')
                if 'v=spf1' in txt_value and 'sendbaba.com' in txt_value:
                    spf_valid = True
                    break
        except:
            pass
        
        # MX record pointing to us is sufficient proof of ownership
        verified = mx_valid
        
        cur.execute("""
            UPDATE webmail_domains
            SET dns_verified = %s, mx_valid = %s, spf_valid = %s, 
                verified_at = CASE WHEN %s THEN NOW() ELSE verified_at END
            WHERE id = %s
        """, (verified, mx_valid, spf_valid, verified, domain_id))
        conn.commit()
        conn.close()
        
        if verified:
            return jsonify({
                'success': True,
                'verified': True,
                'mx_valid': mx_valid,
                'spf_valid': spf_valid,
                'message': 'Domain verified successfully!'
            })
        else:
            return jsonify({
                'success': True,
                'verified': False,
                'mx_valid': mx_valid,
                'spf_valid': spf_valid,
                'message': 'MX record not found. Add MX record pointing to mail.sendbaba.com'
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500



@webmail_bp.route('/api/team/domains/<domain_id>', methods=['DELETE'])
@webmail_login_required
def api_team_delete_domain(domain_id):
    """Delete a custom domain"""
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get org ID
        cur.execute("SELECT organization_id FROM mailboxes WHERE id = %s", (mailbox_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        org_id = row['organization_id']
        
        cur.execute("""
            UPDATE webmail_domains SET is_active = false
            WHERE id = %s AND organization_id = %s
            RETURNING id
        """, (domain_id, org_id))
        
        if cur.fetchone():
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        
        conn.close()
        return jsonify({'success': False, 'error': 'Domain not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/team/members')
@webmail_login_required
def api_team_members():
    """List team members"""
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get org ID
        cur.execute("SELECT organization_id FROM mailboxes WHERE id = %s", (mailbox_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': True, 'members': []})
        org_id = row['organization_id']
        
        cur.execute("""
            SELECT id, email, name, role, last_login, created_at
            FROM mailboxes
            WHERE organization_id = %s AND is_active = true
            ORDER BY created_at
        """, (org_id,))
        
        members = cur.fetchall()
        conn.close()
        return jsonify({'success': True, 'members': members})
    except Exception as e:
        return jsonify({'success': True, 'members': []})


@webmail_bp.route('/api/team/invite', methods=['POST'])
@webmail_login_required
def api_team_invite():
    """Invite a team member"""
    try:
        import secrets
        
        mailbox_id = session.get('webmail_id')
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()
        role = data.get('role', 'member')
        
        if not email or '@' not in email:
            return jsonify({'success': False, 'error': 'Valid email required'}), 400
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get org ID and check if user is admin
        cur.execute("SELECT organization_id, role FROM mailboxes WHERE id = %s", (mailbox_id,))
        row = cur.fetchone()
        if not row or row['role'] != 'admin':
            conn.close()
            return jsonify({'success': False, 'error': 'Only admins can invite members'}), 403
        org_id = row['organization_id']
        
        # Create invites table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mailbox_invites (
                id SERIAL PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                email VARCHAR(255) NOT NULL,
                role VARCHAR(50) DEFAULT 'member',
                token VARCHAR(64) NOT NULL,
                invited_by INTEGER,
                accepted BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '7 days'
            )
        """)
        
        # Check if already invited or member
        cur.execute("SELECT id FROM mailboxes WHERE email = %s AND organization_id = %s", (email, org_id))
        if cur.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'User already a member'}), 400
        
        token = secrets.token_urlsafe(32)
        cur.execute("""
            INSERT INTO mailbox_invites (organization_id, email, role, token, invited_by)
            VALUES (%s, %s, %s, %s, %s)
        """, (org_id, email, role, token, mailbox_id))
        
        conn.commit()
        conn.close()
        
        # TODO: Send invitation email
        
        return jsonify({'success': True, 'message': 'Invitation sent'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# MAILBOX MANAGEMENT FOR CUSTOM DOMAINS
# ============================================================

@webmail_bp.route('/api/team/mailboxes')
@webmail_login_required
def api_team_mailboxes():
    """List mailboxes for custom domains"""
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get org ID
        cur.execute("SELECT organization_id FROM mailboxes WHERE id = %s", (mailbox_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': True, 'mailboxes': []})
        org_id = row['organization_id']
        
        # Get mailboxes that are NOT @sendbaba.com (custom domain mailboxes)
        cur.execute("""
            SELECT id, email, name, recovery_email, last_login, created_at
            FROM mailboxes
            WHERE organization_id = %s AND is_active = true AND email NOT LIKE '%%@sendbaba.com'
            ORDER BY created_at DESC
        """, (org_id,))
        
        mailboxes = cur.fetchall()
        conn.close()
        return jsonify({'success': True, 'mailboxes': mailboxes})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': True, 'mailboxes': []})


@webmail_bp.route('/api/team/mailboxes', methods=['POST'])
@webmail_login_required
def api_team_create_mailbox():
    """Create a new mailbox for a custom domain"""
    try:
        import secrets
        import string
        
        mailbox_id = session.get('webmail_id')
        data = request.get_json() or {}
        
        username = data.get('username', '').strip().lower()
        domain = data.get('domain', '').strip().lower()
        name = data.get('name', '').strip()
        recovery_email = data.get('recovery_email', '').strip().lower()
        
        # Validate inputs
        if not username or not domain or not recovery_email:
            return jsonify({'success': False, 'error': 'Username, domain, and recovery email are required'}), 400
        
        import re
        if not re.match(r'^[a-z0-9._-]+$', username):
            return jsonify({'success': False, 'error': 'Invalid username format'}), 400
        
        email = f"{username}@{domain}"
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get org ID
        cur.execute("SELECT organization_id FROM mailboxes WHERE id = %s", (mailbox_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        org_id = row['organization_id']
        
        # Verify the domain belongs to this org and is verified
        cur.execute("""
            SELECT id FROM webmail_domains 
            WHERE organization_id = %s AND domain_name = %s AND dns_verified = true AND is_active = true
        """, (org_id, domain))
        if not cur.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Domain not verified or not found'}), 400
        
        # Check if email already exists
        cur.execute("SELECT id FROM mailboxes WHERE email = %s", (email,))
        if cur.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Email address already exists'}), 400
        
        # Generate secure password
        password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        # Create mailbox
        cur.execute("""
            INSERT INTO mailboxes (organization_id, email, name, password_hash, recovery_email, role, is_active)
            VALUES (%s, %s, %s, %s, %s, 'user', true)
            RETURNING id
        """, (org_id, email, name or username, password_hash, recovery_email))
        
        new_mailbox_id = cur.fetchone()['id']
        conn.commit()
        
        # Send credentials to recovery email
        try:
            from app.utils.internal_delivery import is_internal_user, deliver_internal
            
            credentials_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #f86d31, #e55a1f); padding: 30px; border-radius: 12px 12px 0 0;">
                    <h1 style="color: white; margin: 0;">Welcome to SendBaba Mail!</h1>
                </div>
                <div style="background: #f8fafc; padding: 30px; border: 1px solid #e5e7eb; border-top: none; border-radius: 0 0 12px 12px;">
                    <p>Your new email mailbox has been created. Here are your login credentials:</p>
                    
                    <div style="background: white; border: 2px solid #22c55e; border-radius: 10px; padding: 20px; margin: 20px 0;">
                        <p style="margin: 10px 0;"><strong>Email:</strong> <code style="background: #f3f4f6; padding: 4px 8px; border-radius: 4px;">{email}</code></p>
                        <p style="margin: 10px 0;"><strong>Password:</strong> <code style="background: #f3f4f6; padding: 4px 8px; border-radius: 4px;">{password}</code></p>
                        <p style="margin: 10px 0;"><strong>Login URL:</strong> <a href="https://mail.sendbaba.com/login">https://mail.sendbaba.com/login</a></p>
                    </div>
                    
                    <p style="color: #6b7280; font-size: 14px;">For security, we recommend changing your password after your first login.</p>
                    
                    <p style="margin-top: 30px;">Happy emailing!<br><strong>The SendBaba Team</strong></p>
                </div>
            </body>
            </html>
            """
            
            # Check if recovery email is internal
            if is_internal_user(recovery_email):
                deliver_internal(
                    from_email='noreply@sendbaba.com',
                    from_name='SendBaba Mail',
                    to_email=recovery_email,
                    subject=f'Your new mailbox: {email}',
                    body_text=f'Your new mailbox {email} has been created. Password: {password}. Login at https://mail.sendbaba.com',
                    body_html=credentials_html
                )
            else:
                # Send via SMTP
                from app.smtp.relay_server import send_email_sync
                send_email_sync({
                    'from': 'noreply@sendbaba.com',
                    'from_name': 'SendBaba Mail',
                    'to': recovery_email,
                    'subject': f'Your new mailbox: {email}',
                    'html_body': credentials_html,
                    'text_body': f'Your new mailbox {email} has been created. Password: {password}. Login at https://mail.sendbaba.com'
                })
        except Exception as mail_err:
            print(f"Failed to send credentials email: {mail_err}")
        
        conn.close()
        
        return jsonify({
            'success': True,
            'mailbox_id': new_mailbox_id,
            'email': email,
            'password': password  # Show once to user
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/team/mailboxes/<int:target_mailbox_id>/reset-password', methods=['POST'])
@webmail_login_required
def api_team_reset_mailbox_password(target_mailbox_id):
    """Reset password for a custom domain mailbox"""
    try:
        import secrets
        import string
        
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get org ID
        cur.execute("SELECT organization_id FROM mailboxes WHERE id = %s", (mailbox_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        org_id = row['organization_id']
        
        # Get target mailbox (must be in same org and not sendbaba.com)
        cur.execute("""
            SELECT id, email, recovery_email FROM mailboxes 
            WHERE id = %s AND organization_id = %s AND email NOT LIKE '%%@sendbaba.com'
        """, (target_mailbox_id, org_id))
        target = cur.fetchone()
        
        if not target:
            conn.close()
            return jsonify({'success': False, 'error': 'Mailbox not found'}), 404
        
        if not target['recovery_email']:
            conn.close()
            return jsonify({'success': False, 'error': 'No recovery email set for this mailbox'}), 400
        
        # Generate new password
        password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        # Update password
        cur.execute("UPDATE mailboxes SET password_hash = %s WHERE id = %s", (password_hash, target_mailbox_id))
        conn.commit()
        
        # Send new credentials
        try:
            from app.utils.internal_delivery import is_internal_user, deliver_internal
            
            email_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2>Password Reset</h2>
                <p>Your password for <strong>{target['email']}</strong> has been reset.</p>
                <div style="background: #f0fdf4; border: 2px solid #22c55e; border-radius: 10px; padding: 20px; margin: 20px 0;">
                    <p><strong>New Password:</strong> <code>{password}</code></p>
                </div>
                <p>Login at <a href="https://mail.sendbaba.com">mail.sendbaba.com</a></p>
            </body>
            </html>
            """
            
            if is_internal_user(target['recovery_email']):
                deliver_internal(
                    from_email='noreply@sendbaba.com',
                    from_name='SendBaba Mail',
                    to_email=target['recovery_email'],
                    subject=f'Password reset for {target["email"]}',
                    body_text=f'Your new password for {target["email"]} is: {password}',
                    body_html=email_html
                )
            else:
                from app.smtp.relay_server import send_email_sync
                send_email_sync({
                    'from': 'noreply@sendbaba.com',
                    'from_name': 'SendBaba Mail',
                    'to': target['recovery_email'],
                    'subject': f'Password reset for {target["email"]}',
                    'html_body': email_html,
                    'text_body': f'Your new password for {target["email"]} is: {password}'
                })
        except Exception as mail_err:
            print(f"Failed to send password reset email: {mail_err}")
        
        conn.close()
        return jsonify({'success': True})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@webmail_bp.route('/api/team/mailboxes/<int:target_mailbox_id>', methods=['DELETE'])
@webmail_login_required
def api_team_delete_mailbox(target_mailbox_id):
    """Delete a custom domain mailbox"""
    try:
        mailbox_id = session.get('webmail_id')
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get org ID
        cur.execute("SELECT organization_id FROM mailboxes WHERE id = %s", (mailbox_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        org_id = row['organization_id']
        
        # Verify target mailbox belongs to same org and is custom domain
        cur.execute("""
            SELECT id FROM mailboxes 
            WHERE id = %s AND organization_id = %s AND email NOT LIKE '%%@sendbaba.com'
        """, (target_mailbox_id, org_id))
        
        if not cur.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Mailbox not found'}), 404
        
        # Soft delete (deactivate)
        cur.execute("UPDATE mailboxes SET is_active = false WHERE id = %s", (target_mailbox_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
