"""
SendBaba Real-Time WebSocket Events
- Instant message delivery between SendBaba users
- Typing indicators
- Online status
"""
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask import session, request
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logger = logging.getLogger(__name__)

socketio = SocketIO()

# Track online users: {email: {sid, name, status}}
online_users = {}

def get_db():
    return psycopg2.connect("postgresql://emailer:SecurePassword123@localhost/emailer")

def init_socketio(app):
    """Initialize SocketIO with the Flask app"""
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        message_queue='redis://:SendBabaRedis2024!@localhost:6379/0',
        async_mode='gevent'
    )
    return socketio

@socketio.on('connect')
def handle_connect():
    email = session.get('webmail_user')
    name = session.get('webmail_name', '')
    
    if email:
        join_room(email)
        online_users[email] = {'sid': request.sid, 'name': name, 'status': 'online'}
        emit('user_online', {'email': email, 'name': name}, broadcast=True)
        emit('online_users', {'users': list(online_users.keys())})
        logger.info(f"🟢 {email} connected via WebSocket")

@socketio.on('disconnect')
def handle_disconnect():
    email = session.get('webmail_user')
    if email and email in online_users:
        del online_users[email]
        emit('user_offline', {'email': email}, broadcast=True)
        logger.info(f"🔴 {email} disconnected")

@socketio.on('typing')
def handle_typing(data):
    from_email = session.get('webmail_user')
    from_name = session.get('webmail_name', from_email)
    to_email = data.get('to', '').lower()
    
    if to_email and is_sendbaba_user(to_email):
        emit('typing', {'from': from_email, 'from_name': from_name}, room=to_email)

@socketio.on('stop_typing')
def handle_stop_typing(data):
    from_email = session.get('webmail_user')
    to_email = data.get('to', '').lower()
    if to_email:
        emit('stop_typing', {'from': from_email}, room=to_email)

@socketio.on('message_read')
def handle_message_read(data):
    email_id = data.get('email_id')
    reader_email = session.get('webmail_user')
    
    if email_id:
        try:
            conn = get_db()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT from_email FROM mailbox_emails WHERE id = %s", (email_id,))
            result = cur.fetchone()
            conn.close()
            
            if result and is_sendbaba_user(result['from_email']):
                emit('read_receipt', {
                    'email_id': email_id, 
                    'read_by': reader_email
                }, room=result['from_email'])
        except Exception as e:
            logger.error(f"Read receipt error: {e}")

@socketio.on('get_online_users')
def handle_get_online():
    emit('online_users', {'users': list(online_users.keys())})

def is_sendbaba_user(email):
    """Check if email is a SendBaba mailbox"""
    if not email:
        return False
    domain = email.split('@')[-1].lower() if '@' in email else ''
    
    if domain == 'sendbaba.com':
        return True
    
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM mailbox_domains 
            WHERE domain = %s AND is_active = true AND mx_verified = true
        """, (domain,))
        result = cur.fetchone()
        conn.close()
        return result is not None
    except:
        return False

def get_mailbox_id(email):
    """Get mailbox ID for an email address"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id FROM mailboxes WHERE email = %s", (email.lower(),))
        result = cur.fetchone()
        conn.close()
        return result['id'] if result else None
    except:
        return None

def notify_new_email(to_email, email_data):
    """Send real-time notification for new email"""
    to_email = to_email.lower()
    if to_email in online_users:
        socketio.emit('new_email', {
            'id': email_data.get('id'),
            'from_email': email_data.get('from_email'),
            'from_name': email_data.get('from_name'),
            'subject': email_data.get('subject'),
            'preview': (email_data.get('body_text') or '')[:100],
            'has_audio': email_data.get('has_audio', False),
            'timestamp': email_data.get('timestamp')
        }, room=to_email)
        logger.info(f"📨 Real-time notification sent to {to_email}")
        return True
    return False

def is_user_online(email):
    return email.lower() in online_users


# Chat message event
@socketio.on('chat_message')
def handle_chat_message(data):
    """Handle real-time chat message"""
    from_email = session.get('webmail_user')
    to_email = data.get('to')
    content = data.get('content')
    
    if to_email and content:
        emit('chat_message', {
            'from': from_email,
            'content': content,
            'time': datetime.now().strftime('%H:%M')
        }, room=to_email)


# Chat typing event
@socketio.on('chat_typing')
def handle_chat_typing(data):
    """Handle typing indicator for chat"""
    from_email = session.get('webmail_user')
    to_email = data.get('to')
    
    if to_email:
        emit('chat_typing', {
            'from': from_email
        }, room=to_email)
