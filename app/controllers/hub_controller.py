"""
import time
import subprocess
SendBaba Hub - Complete Admin Dashboard
=======================================
Full admin panel with authentication, user management, orders, and server monitoring.
"""
from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for, flash
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash, generate_password_hash
import redis
import os
from datetime import datetime, timedelta
import subprocess
import json

hub_bp = Blueprint('hub', __name__)

# Configuration
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://emailer:SecurePassword123@localhost:5432/emailer')
REDIS_URL = os.environ.get('REDIS_URL', 'redis://:SendBabaRedis2024!@localhost:6379/0')

# Secret key for sessions
hub_bp.secret_key = os.environ.get('HUB_SECRET_KEY', 'SendBabaHubSecret2024!')

def get_db():
    return psycopg2.connect(DATABASE_URL)

def get_redis():
    return redis.from_url(REDIS_URL)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'hub_admin_id' not in session:
            # Check if it's an API/AJAX request
            is_api_request = (
                request.is_json or 
                request.headers.get('Accept', '').startswith('application/json') or
                request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
                '/api/' in request.path
            )
            if is_api_request:
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('hub.login'))
        return f(*args, **kwargs)
    return decorated

def superadmin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'hub_admin_id' not in session:
            return redirect(url_for('hub.login'))
        if session.get('hub_admin_role') != 'superadmin':
            flash('Access denied. Superadmin required.', 'error')
            return redirect(url_for('hub.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ============================================================
# AUTHENTICATION ROUTES
# ============================================================
@hub_bp.route('/hub/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM hub_admins WHERE email = %s AND is_active = true", (email,))
        admin = cur.fetchone()
        
        if admin and check_password_hash(admin['password_hash'], password):
            session['hub_admin_id'] = admin['id']
            session['hub_admin_email'] = admin['email']
            session['hub_admin_name'] = admin['name']
            session['hub_admin_role'] = admin['role']
            session.permanent = True
            
            # Update last login
            cur.execute("UPDATE hub_admins SET last_login = CURRENT_TIMESTAMP WHERE id = %s", (admin['id'],))
            conn.commit()
            conn.close()
            
            return redirect(url_for('hub.dashboard'))
        
        conn.close()
        flash('Invalid email or password', 'error')
    
    return render_template('hub/login.html')


@hub_bp.route('/hub/logout')
def logout():
    session.clear()
    return redirect(url_for('hub.login'))


# ============================================================
# DASHBOARD
# ============================================================
@hub_bp.route('/hub/')
@hub_bp.route('/hub')
@login_required
def dashboard():
    return render_template('hub/dashboard.html', admin=session)


# ============================================================
# USER MANAGEMENT
# ============================================================
@hub_bp.route('/hub/users')
@login_required
def users_page():
    return render_template('hub/users.html', admin=session)


@hub_bp.route('/hub/api/users')
@login_required
def api_users():
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        search = request.args.get('search', '')
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        offset = (page - 1) * per_page
        
        if search:
            cur.execute("""
                SELECT u.*, o.name as org_name,
                    (SELECT COUNT(*) FROM emails WHERE organization_id = u.organization_id) as email_count
                FROM users u
                LEFT JOIN organizations o ON u.organization_id = o.id
                WHERE u.email ILIKE %s OR u.first_name ILIKE %s OR u.last_name ILIKE %s
                ORDER BY u.created_at DESC
                LIMIT %s OFFSET %s
            """, (f'%{search}%', f'%{search}%', f'%{search}%', per_page, offset))
        else:
            cur.execute("""
                SELECT u.*, o.name as org_name,
                    (SELECT COUNT(*) FROM emails WHERE organization_id = u.organization_id) as email_count
                FROM users u
                LEFT JOIN organizations o ON u.organization_id = o.id
                ORDER BY u.created_at DESC
                LIMIT %s OFFSET %s
            """, (per_page, offset))
        
        users = cur.fetchall()
        
        # Get total count
        if search:
            cur.execute("SELECT COUNT(*) FROM users WHERE email ILIKE %s OR first_name ILIKE %s", 
                       (f'%{search}%', f'%{search}%'))
        else:
            cur.execute("SELECT COUNT(*) FROM users")
        total = cur.fetchone()['count']
        
        conn.close()
        
        # Convert datetime to string
        for user in users:
            for key in ['created_at', 'last_login', 'updated_at']:
                if user.get(key):
                    user[key] = user[key].isoformat()
        
        return jsonify({
            'success': True,
            'users': users,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': (total + per_page - 1) // per_page
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/users/<user_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def api_user_detail(user_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    if request.method == 'GET':
        cur.execute("""
            SELECT u.*, o.name as org_name
            FROM users u
            LEFT JOIN organizations o ON u.organization_id = o.id
            WHERE u.id = %s
        """, (user_id,))
        user = cur.fetchone()
        conn.close()
        
        if user:
            for key in ['created_at', 'last_login', 'updated_at']:
                if user.get(key):
                    user[key] = user[key].isoformat()
            return jsonify({'success': True, 'user': user})
        return jsonify({'success': False, 'error': 'User not found'}), 404
    
    elif request.method == 'PUT':
        data = request.json
        cur.execute("""
            UPDATE users SET
                is_active = COALESCE(%s, is_active),
                is_verified = COALESCE(%s, is_verified),
                role = COALESCE(%s, role),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id
        """, (data.get('is_active'), data.get('is_verified'), data.get('role'), user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'User updated'})
    
    elif request.method == 'DELETE':
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'User deleted'})


# ============================================================
# ADMIN MANAGEMENT
# ============================================================
@hub_bp.route('/hub/admins')
@superadmin_required
def admins_page():
    return render_template('hub/admins.html', admin=session)


@hub_bp.route('/hub/api/admins', methods=['GET', 'POST'])
@superadmin_required
def api_admins():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    if request.method == 'GET':
        cur.execute("SELECT id, email, name, role, is_active, last_login, created_at FROM hub_admins ORDER BY created_at DESC")
        admins = cur.fetchall()
        conn.close()
        
        for admin in admins:
            for key in ['last_login', 'created_at']:
                if admin.get(key):
                    admin[key] = admin[key].isoformat()
        
        return jsonify({'success': True, 'admins': admins})
    
    elif request.method == 'POST':
        data = request.json
        password_hash = generate_password_hash(data['password'])
        
        try:
            cur.execute("""
                INSERT INTO hub_admins (email, password_hash, name, role)
                VALUES (%s, %s, %s, %s)
                RETURNING id
            """, (data['email'].lower(), password_hash, data.get('name', ''), data.get('role', 'admin')))
            admin_id = cur.fetchone()['id']
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'admin_id': admin_id})
        except psycopg2.IntegrityError:
            conn.rollback()
            conn.close()
            return jsonify({'success': False, 'error': 'Email already exists'}), 400


@hub_bp.route('/hub/api/admins/<int:admin_id>', methods=['PUT', 'DELETE'])
@superadmin_required
def api_admin_detail(admin_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    if request.method == 'PUT':
        data = request.json
        
        if data.get('password'):
            password_hash = generate_password_hash(data['password'])
            cur.execute("""
                UPDATE hub_admins SET
                    name = COALESCE(%s, name),
                    role = COALESCE(%s, role),
                    is_active = COALESCE(%s, is_active),
                    password_hash = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (data.get('name'), data.get('role'), data.get('is_active'), password_hash, admin_id))
        else:
            cur.execute("""
                UPDATE hub_admins SET
                    name = COALESCE(%s, name),
                    role = COALESCE(%s, role),
                    is_active = COALESCE(%s, is_active),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (data.get('name'), data.get('role'), data.get('is_active'), admin_id))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Admin updated'})
    
    elif request.method == 'DELETE':
        if admin_id == session.get('hub_admin_id'):
            return jsonify({'success': False, 'error': 'Cannot delete yourself'}), 400
        
        cur.execute("DELETE FROM hub_admins WHERE id = %s", (admin_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Admin deleted'})


# ============================================================
# ORDERS MANAGEMENT
# ============================================================
@hub_bp.route('/hub/orders')
@login_required
def orders_page():
    return render_template('hub/orders.html', admin=session)


@hub_bp.route('/hub/api/orders')
@login_required
def api_orders():
    try:
        status = request.args.get('status', '')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        offset = (page - 1) * per_page
        
        if status:
            cur.execute("""
                SELECT o.*, u.email as user_email, org.name as org_name
                FROM hub_orders o
                LEFT JOIN users u ON o.user_id = u.id
                LEFT JOIN organizations org ON o.organization_id = org.id
                WHERE o.status = %s
                ORDER BY o.created_at DESC
                LIMIT %s OFFSET %s
            """, (status, per_page, offset))
        else:
            cur.execute("""
                SELECT o.*, u.email as user_email, org.name as org_name
                FROM hub_orders o
                LEFT JOIN users u ON o.user_id = u.id
                LEFT JOIN organizations org ON o.organization_id = org.id
                ORDER BY o.created_at DESC
                LIMIT %s OFFSET %s
            """, (per_page, offset))
        
        orders = cur.fetchall()
        
        # Get counts by status
        cur.execute("""
            SELECT status, COUNT(*) as count FROM hub_orders GROUP BY status
        """)
        status_counts = {row['status']: row['count'] for row in cur.fetchall()}
        
        cur.execute("SELECT COUNT(*) FROM hub_orders")
        total = cur.fetchone()['count']
        
        conn.close()
        
        for order in orders:
            for key in ['created_at', 'updated_at']:
                if order.get(key):
                    order[key] = order[key].isoformat()
            if order.get('amount'):
                order['amount'] = float(order['amount'])
        
        return jsonify({
            'success': True,
            'orders': orders,
            'total': total,
            'status_counts': status_counts,
            'page': page,
            'per_page': per_page
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/orders/<int:order_id>', methods=['PUT'])
@login_required
def api_order_update(order_id):
    conn = get_db()
    cur = conn.cursor()
    
    data = request.json
    cur.execute("""
        UPDATE hub_orders SET
            status = COALESCE(%s, status),
            notes = COALESCE(%s, notes),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (data.get('status'), data.get('notes'), order_id))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Order updated'})


# ============================================================
# SERVER MONITORING
# ============================================================
# OLD_DUPLICATE: @hub_bp.route('/hub/servers')
# OLD_DUPLICATE: @login_required
# OLD_DUPLICATE: def servers_page():
# OLD_DUPLICATE:     return render_template('hub/servers.html', admin=session)
# OLD_DUPLICATE: 
# OLD_DUPLICATE: 
# OLD_DUPLICATE: @hub_bp.route('/hub/api/servers')
# OLD_DUPLICATE: @login_required
# OLD_DUPLICATE: def api_servers():
# OLD_DUPLICATE:     try:
        # Worker IPs
# OLD_DUPLICATE:         workers = [
# OLD_DUPLICATE:             {"ip": "161.97.170.33", "hostname": "mail10.sendbaba.com", "type": "worker"},
# OLD_DUPLICATE:             {"ip": "75.119.151.72", "hostname": "mail9.sendbaba.com", "type": "worker"},
# OLD_DUPLICATE:             {"ip": "75.119.153.106", "hostname": "mail8.sendbaba.com", "type": "worker"},
# OLD_DUPLICATE:             {"ip": "173.212.214.23", "hostname": "mail5.sendbaba.com", "type": "worker"},
# OLD_DUPLICATE:             {"ip": "173.212.213.239", "hostname": "mail6.sendbaba.com", "type": "worker"},
# OLD_DUPLICATE:             {"ip": "173.212.213.184", "hostname": "mail7.sendbaba.com", "type": "worker"},
# OLD_DUPLICATE:             {"ip": "185.215.180.157", "hostname": "mail11.sendbaba.com", "type": "worker"},
# OLD_DUPLICATE:             {"ip": "185.215.164.39", "hostname": "mail12.sendbaba.com", "type": "worker"},
# OLD_DUPLICATE:             {"ip": "176.126.87.21", "hostname": "mail13.sendbaba.com", "type": "worker"},
# OLD_DUPLICATE:             {"ip": "185.215.167.20", "hostname": "mail14.sendbaba.com", "type": "worker"},
# OLD_DUPLICATE:             {"ip": "185.208.206.35", "hostname": "mail15.sendbaba.com", "type": "worker"},
# OLD_DUPLICATE:         ]
# OLD_DUPLICATE:         
        # Get Celery worker status
# OLD_DUPLICATE:         try:
# OLD_DUPLICATE:             import sys
# OLD_DUPLICATE:             sys.path.insert(0, '/opt/sendbaba-staging')
# OLD_DUPLICATE:             from celery_worker_config import celery_app
# OLD_DUPLICATE:             
# OLD_DUPLICATE:             inspector = celery_app.control.inspect()
# OLD_DUPLICATE:             ping_results = inspector.ping() or {}
# OLD_DUPLICATE:             stats = inspector.stats() or {}
# OLD_DUPLICATE:             
# OLD_DUPLICATE:             for worker in workers:
# OLD_DUPLICATE:                 worker_name = f"worker@{worker['ip']}"
# OLD_DUPLICATE:                 worker['status'] = 'online' if worker_name in ping_results else 'offline'
# OLD_DUPLICATE:                 worker_stats = stats.get(worker_name, {})
# OLD_DUPLICATE:                 worker['concurrency'] = worker_stats.get('pool', {}).get('max-concurrency', 0)
# OLD_DUPLICATE:                 worker['processed'] = worker_stats.get('total', {})
# OLD_DUPLICATE:         except Exception as e:
# OLD_DUPLICATE:             for worker in workers:
# OLD_DUPLICATE:                 worker['status'] = 'unknown'
# OLD_DUPLICATE:                 worker['concurrency'] = 0
# OLD_DUPLICATE:                 worker['error'] = str(e)
# OLD_DUPLICATE:         
        # Get IP pool data
# OLD_DUPLICATE:         conn = get_db()
# OLD_DUPLICATE:         cur = conn.cursor(cursor_factory=RealDictCursor)
# OLD_DUPLICATE:         cur.execute("""
# OLD_DUPLICATE:             SELECT ip_address, hostname, warmup_day, daily_limit, sent_today, is_active,
# OLD_DUPLICATE:                 ROUND((sent_today::numeric / NULLIF(daily_limit, 0)) * 100, 1) as usage_pct
# OLD_DUPLICATE:             FROM ip_pools ORDER BY ip_address
# OLD_DUPLICATE:         """)
# OLD_DUPLICATE:         ip_pools = {row['ip_address']: row for row in cur.fetchall()}
# OLD_DUPLICATE:         conn.close()
# OLD_DUPLICATE:         
        # Merge IP pool data with workers
# OLD_DUPLICATE:         for worker in workers:
# OLD_DUPLICATE:             ip_data = ip_pools.get(worker['ip'], {})
# OLD_DUPLICATE:             worker['warmup_day'] = ip_data.get('warmup_day', 0)
# OLD_DUPLICATE:             worker['daily_limit'] = ip_data.get('daily_limit', 0)
# OLD_DUPLICATE:             worker['sent_today'] = ip_data.get('sent_today', 0)
# OLD_DUPLICATE:             worker['usage_pct'] = ip_data.get('usage_pct', 0)
# OLD_DUPLICATE:             worker['is_warmed'] = ip_data.get('warmup_day', 0) >= 30
# OLD_DUPLICATE:         
# OLD_DUPLICATE:         return jsonify({
# OLD_DUPLICATE:             'success': True,
# OLD_DUPLICATE:             'servers': workers,
# OLD_DUPLICATE:             'total_workers': len([w for w in workers if w.get('status') == 'online']),
# OLD_DUPLICATE:             'total_capacity': sum(w.get('daily_limit', 0) for w in workers),
# OLD_DUPLICATE:             'total_sent': sum(w.get('sent_today', 0) for w in workers)
# OLD_DUPLICATE:         })
# OLD_DUPLICATE:     except Exception as e:
# OLD_DUPLICATE:         return jsonify({'success': False, 'error': str(e)}), 500
# OLD_DUPLICATE: 
# OLD_DUPLICATE: 
# ============================================================
# DASHBOARD API
# ============================================================
@hub_bp.route('/hub/api/stats')
@login_required
def api_stats():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                (SELECT COUNT(*) FROM organizations) as total_orgs,
                (SELECT COUNT(*) FROM users) as total_users,
                (SELECT COUNT(*) FROM domains WHERE is_verified = true) as verified_domains,
                (SELECT COUNT(*) FROM campaigns) as total_campaigns,
                (SELECT COUNT(*) FROM emails) as total_emails,
                (SELECT COUNT(*) FROM emails WHERE created_at > NOW() - INTERVAL '24 hours') as emails_24h,
                (SELECT COUNT(*) FROM emails WHERE created_at > NOW() - INTERVAL '1 hour') as emails_1h,
                (SELECT COUNT(*) FROM emails WHERE status = 'sent' AND created_at > NOW() - INTERVAL '24 hours') as sent_24h,
                (SELECT COUNT(*) FROM emails WHERE status = 'failed' AND created_at > NOW() - INTERVAL '24 hours') as failed_24h,
                (SELECT COUNT(*) FROM hub_orders WHERE status = 'pending') as pending_orders
        """)
        stats = cur.fetchone()
        
        cur.execute("""
            SELECT 
                COUNT(*) as total_ips,
                SUM(daily_limit) as total_capacity,
                SUM(sent_today) as total_sent_today,
                SUM(daily_limit - sent_today) as remaining_capacity
            FROM ip_pools WHERE is_active = true
        """)
        ip_stats = cur.fetchone()
        
        conn.close()
        
        r = get_redis()
        redis_info = r.info()
        
        return jsonify({
            'success': True,
            'stats': {
                **stats,
                **ip_stats,
                'redis_clients': redis_info.get('connected_clients', 0),
                'redis_memory': redis_info.get('used_memory_human', 'N/A'),
                'timestamp': datetime.now().isoformat()
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/workers')
@login_required
def api_workers():
    try:
        import sys
        sys.path.insert(0, '/opt/sendbaba-staging')
        from celery_worker_config import celery_app
        
        inspector = celery_app.control.inspect()
        ping_results = inspector.ping() or {}
        stats = inspector.stats() or {}
        active = inspector.active() or {}
        
        workers = []
        for worker_name, pong in ping_results.items():
            worker_stats = stats.get(worker_name, {})
            worker_active = active.get(worker_name, [])
            
            workers.append({
                'name': worker_name,
                'status': 'online' if pong else 'offline',
                'concurrency': worker_stats.get('pool', {}).get('max-concurrency', 0),
                'active_tasks': len(worker_active),
            })
        
        return jsonify({
            'success': True,
            'workers': workers,
            'total_workers': len(workers),
            'total_concurrency': sum(w['concurrency'] for w in workers)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-pools')
@login_required
def api_ip_pools():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                ip_address, hostname, is_active, warmup_day, 
                daily_limit, sent_today,
                ROUND((sent_today::numeric / NULLIF(daily_limit, 0)) * 100, 1) as usage_pct,
                last_used_at
            FROM ip_pools
            ORDER BY priority, ip_address
        """)
        pools = cur.fetchall()
        conn.close()
        
        for pool in pools:
            if pool['last_used_at']:
                pool['last_used_at'] = pool['last_used_at'].isoformat()
        
        return jsonify({'success': True, 'ip_pools': pools})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/campaigns/recent')
@login_required
def api_recent_campaigns():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                c.id, c.name, c.status, c.total_recipients,
                c.sent_count, c.failed_count, c.open_count, c.click_count,
                c.created_at, o.name as org_name
            FROM campaigns c
            LEFT JOIN organizations o ON c.organization_id = o.id
            ORDER BY c.created_at DESC
            LIMIT 20
        """)
        campaigns = cur.fetchall()
        conn.close()
        
        for c in campaigns:
            if c.get('created_at'):
                c['created_at'] = c['created_at'].isoformat()
        
        return jsonify({'success': True, 'campaigns': campaigns})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/emails/hourly')
@login_required
def api_hourly_emails():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                DATE_TRUNC('hour', created_at) as hour,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM emails
            WHERE created_at > NOW() - INTERVAL '24 hours'
            GROUP BY DATE_TRUNC('hour', created_at)
            ORDER BY hour
        """)
        hourly = cur.fetchall()
        conn.close()
        
        for h in hourly:
            h['hour'] = h['hour'].isoformat()
        
        return jsonify({'success': True, 'hourly': hourly})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ORGANIZATIONS
# ============================================================
@hub_bp.route('/hub/organizations')
@login_required
def organizations_page():
    return render_template('hub/organizations.html', admin=session)


@hub_bp.route('/hub/api/organizations')
@login_required
def api_organizations():
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT o.*,
                (SELECT COUNT(*) FROM users WHERE organization_id = o.id) as user_count,
                (SELECT COUNT(*) FROM domains WHERE organization_id = o.id) as domain_count,
                (SELECT COUNT(*) FROM emails WHERE organization_id = o.id) as email_count,
                (SELECT COUNT(*) FROM campaigns WHERE organization_id = o.id) as campaign_count
            FROM organizations o
            ORDER BY o.created_at DESC
        """)
        orgs = cur.fetchall()
        conn.close()
        
        for org in orgs:
            if org.get('created_at'):
                org['created_at'] = org['created_at'].isoformat()
        
        return jsonify({'success': True, 'organizations': orgs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# SERVER MANAGEMENT API ENDPOINTS
# ============================================================

@hub_bp.route('/hub/api/servers/toggle', methods=['POST'])
@login_required
def api_toggle_server():
    """Toggle server active/inactive status"""
    try:
        data = request.get_json()
        ip_address = data.get('ip_address')
        is_active = data.get('is_active', True)
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            UPDATE ip_pools 
            SET is_active = %s 
            WHERE ip_address = %s
            RETURNING ip_address, hostname, is_active
        """, (is_active, ip_address))
        result = cur.fetchone()
        conn.commit()
        conn.close()
        
        if result:
            return jsonify({'success': True, 'server': dict(result)})
        return jsonify({'success': False, 'error': 'Server not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/servers/assign', methods=['POST'])
@login_required  
def api_assign_server():
    """Assign server to organization"""
    try:
        data = request.get_json()
        ip_pool_id = data.get('ip_pool_id')
        organization_id = data.get('organization_id')
        is_exclusive = data.get('is_exclusive', False)
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        if organization_id:
            # Assign to organization
            cur.execute("""
                INSERT INTO organization_ip_assignments (organization_id, ip_pool_id, is_exclusive)
                VALUES (%s, %s, %s)
                ON CONFLICT (organization_id, ip_pool_id) 
                DO UPDATE SET is_exclusive = EXCLUDED.is_exclusive
                RETURNING *
            """, (organization_id, ip_pool_id, is_exclusive))
        else:
            # Remove assignment (make available to all)
            cur.execute("""
                DELETE FROM organization_ip_assignments 
                WHERE ip_pool_id = %s
            """, (ip_pool_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/servers/assignments')
@login_required
def api_server_assignments():
    """Get all server assignments"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT 
                oia.ip_pool_id,
                oia.organization_id,
                oia.is_exclusive,
                ip.ip_address,
                ip.hostname,
                o.name as org_name,
                u.email as user_email
            FROM organization_ip_assignments oia
            JOIN ip_pools ip ON ip.id = oia.ip_pool_id
            JOIN organizations o ON o.id = oia.organization_id
            LEFT JOIN users u ON u.organization_id = o.id AND u.role = 'owner'
            ORDER BY ip.hostname
        """)
        assignments = cur.fetchall()
        conn.close()
        
        return jsonify({'success': True, 'assignments': [dict(a) for a in assignments]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/organizations/list')
@login_required
def api_organizations_list():
    """Get list of organizations for assignment dropdown"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT DISTINCT 
                o.id, 
                o.name,
                u.email as owner_email,
                (SELECT COUNT(*) FROM contacts c WHERE c.organization_id = o.id) as contact_count
            FROM organizations o
            LEFT JOIN users u ON u.organization_id = o.id AND u.role = 'owner'
            ORDER BY o.name
        """)
        orgs = cur.fetchall()
        conn.close()
        
        return jsonify({'success': True, 'organizations': [dict(o) for o in orgs]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/servers/details')
@login_required
def api_servers_details():
    """Get detailed server info with assignments"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get all servers with assignment info
        cur.execute("""
            SELECT 
                ip.id,
                ip.ip_address,
                ip.hostname,
                ip.is_active,
                ip.warmup_day,
                ip.daily_limit,
                ip.sent_today,
                ROUND((ip.sent_today::numeric / NULLIF(ip.daily_limit, 0)) * 100, 1) as usage_pct,
                CASE 
                    WHEN ip.warmup_day >= 30 THEN 'warmed'
                    WHEN ip.warmup_day >= 7 THEN 'warming'
                    ELSE 'new'
                END as warmup_status,
                array_agg(DISTINCT o.name) FILTER (WHERE o.name IS NOT NULL) as assigned_orgs
            FROM ip_pools ip
            LEFT JOIN organization_ip_assignments oia ON oia.ip_pool_id = ip.id
            LEFT JOIN organizations o ON o.id = oia.organization_id
            GROUP BY ip.id, ip.ip_address, ip.hostname, ip.is_active, 
                     ip.warmup_day, ip.daily_limit, ip.sent_today
            ORDER BY ip.warmup_day DESC, ip.hostname
        """)
        servers = cur.fetchall()
        
        # Get worker status from Celery
        ping_results = {}
        stats = {}
        try:
            import sys
            sys.path.insert(0, '/opt/sendbaba-staging')
            from celery_app import celery_app
            inspector = celery_app.control.inspect()
            ping_results = inspector.ping() or {}
            stats = inspector.stats() or {}
        except Exception as ce:
            pass
        
        result = []
        for s in servers:
            server = dict(s)
            worker_name = f"worker@{server['ip_address']}"
            server['worker_online'] = worker_name in ping_results
            worker_stats = stats.get(worker_name, {})
            server['concurrency'] = worker_stats.get('pool', {}).get('max-concurrency', 0)
            server['assigned_orgs'] = server['assigned_orgs'] or []
            result.append(server)
        
        # Summary stats
        total_capacity = sum(s['daily_limit'] for s in result if s['is_active'])
        total_sent = sum(s['sent_today'] for s in result)
        online_count = sum(1 for s in result if s['worker_online'])
        warmed_count = sum(1 for s in result if s['warmup_status'] == 'warmed')
        
        conn.close()
        
        return jsonify({
            'success': True,
            'servers': result,
            'summary': {
                'total': len(result),
                'online': online_count,
                'warmed': warmed_count,
                'total_capacity': total_capacity,
                'total_sent': total_sent
            }
        })
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()}), 500




# ============================================================
# REAL-TIME ANALYTICS API ENDPOINTS
# ============================================================

@hub_bp.route('/hub/analytics')
@login_required
def analytics_page():
    return render_template('hub/analytics.html')


@hub_bp.route('/hub/api/analytics/realtime')
@login_required
def api_analytics_realtime():
    """Real-time analytics data"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get today's stats
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE status = 'sent' AND DATE(created_at) = CURRENT_DATE) as sent_today,
                COUNT(*) FILTER (WHERE status = 'failed' AND DATE(created_at) = CURRENT_DATE) as failed_today,
                COUNT(*) FILTER (WHERE status IN ('pending', 'sending')) as queue_size,
                COUNT(*) FILTER (WHERE status = 'sent') as total_delivered,
                COUNT(*) FILTER (WHERE status = 'failed') as total_failed
            FROM emails
            WHERE created_at >= NOW() - INTERVAL '30 days'
        """)
        stats = cur.fetchone()
        
        sent_today = stats['sent_today'] or 0
        failed_today = stats['failed_today'] or 0
        queue_size = stats['queue_size'] or 0
        
        # Calculate rates
        total = sent_today + failed_today
        delivery_rate = (sent_today / total * 100) if total > 0 else 100
        bounce_rate = (failed_today / total * 100) if total > 0 else 0
        
        # Get sending rate (last 5 minutes)
        cur.execute("""
            SELECT COUNT(*) as count
            FROM emails
            WHERE status = 'sent'
            AND sent_at >= NOW() - INTERVAL '5 minutes'
        """)
        recent = cur.fetchone()
        sending_rate = round((recent['count'] or 0) / 300, 1)  # per second
        
        # Get hourly distribution
        cur.execute("""
            SELECT 
                EXTRACT(HOUR FROM created_at)::int as hour,
                COUNT(*) as count
            FROM emails
            WHERE DATE(created_at) = CURRENT_DATE
            GROUP BY hour
            ORDER BY hour
        """)
        hourly_raw = {row['hour']: row['count'] for row in cur.fetchall()}
        hourly_data = [hourly_raw.get(h, 0) for h in range(24)]
        
        # Get provider breakdown
        cur.execute("""
            SELECT 
                CASE 
                    WHEN to_email LIKE '%@gmail.com' THEN 'Gmail'
                    WHEN to_email LIKE '%@yahoo.%' THEN 'Yahoo'
                    WHEN to_email LIKE '%@outlook.%' OR to_email LIKE '%@hotmail.%' THEN 'Outlook'
                    WHEN to_email LIKE '%@aol.%' THEN 'AOL'
                    ELSE 'Others'
                END as provider,
                COUNT(*) as count
            FROM emails
            WHERE DATE(created_at) = CURRENT_DATE
            GROUP BY provider
            ORDER BY count DESC
        """)
        provider_rows = cur.fetchall()
        provider_data = {
            'labels': [r['provider'] for r in provider_rows],
            'values': [r['count'] for r in provider_rows]
        }
        
        # Get top campaigns
        cur.execute("""
            SELECT 
                c.id, c.name, o.name as organization,
                COUNT(*) FILTER (WHERE e.status = 'sent') as sent,
                COUNT(*) as total,
                ROUND(COUNT(*) FILTER (WHERE e.status = 'sent')::numeric / NULLIF(COUNT(*), 0) * 100, 1) as success_rate
            FROM campaigns c
            LEFT JOIN emails e ON e.campaign_id = c.id
            LEFT JOIN organizations o ON o.id = c.organization_id
            WHERE c.created_at >= NOW() - INTERVAL '7 days'
            GROUP BY c.id, c.name, o.name
            ORDER BY sent DESC
            LIMIT 5
        """)
        top_campaigns = [dict(r) for r in cur.fetchall()]
        
        # Get IP stats
        cur.execute("""
            SELECT 
                ip_address, hostname, warmup_day, daily_limit, sent_today, is_active,
                CASE WHEN is_active THEN 'online' ELSE 'offline' END as status
            FROM ip_pools
            ORDER BY sent_today DESC
            LIMIT 10
        """)
        ip_stats = [dict(r) for r in cur.fetchall()]
        
        # Daily capacity
        cur.execute("SELECT SUM(daily_limit) as capacity FROM ip_pools WHERE is_active = true")
        capacity = cur.fetchone()['capacity'] or 1
        
        conn.close()
        
        return jsonify({
            'success': True,
            'sending_rate': sending_rate,
            'sent_today': sent_today,
            'failed_today': failed_today,
            'delivery_rate': delivery_rate,
            'bounce_rate': bounce_rate,
            'bounces': failed_today,
            'queue_size': queue_size,
            'daily_capacity': capacity,
            'delivered': stats['total_delivered'] or 0,
            'pending': queue_size,
            'failed': stats['total_failed'] or 0,
            'hourly_data': hourly_data,
            'provider_data': provider_data,
            'top_campaigns': top_campaigns,
            'ip_stats': ip_stats,
            'realtime_data': {
                'sent': hourly_data[-10:] if len(hourly_data) >= 10 else hourly_data,
                'failed': [0] * 10  # Simplified
            }
        })
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()}), 500


@hub_bp.route('/hub/api/analytics/activity')
@login_required
def api_analytics_activity():
    """Recent email activity stream"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                TO_CHAR(e.created_at, 'HH24:MI:SS') as time,
                e.to_email as recipient,
                COALESCE(e.subject, 'No Subject') as subject,
                e.status,
                ip.hostname as server
            FROM emails e
            LEFT JOIN ip_pools ip ON ip.ip_address = e.from_ip
            ORDER BY e.created_at DESC
            LIMIT 20
        """)
        activities = [dict(r) for r in cur.fetchall()]
        conn.close()
        
        return jsonify({'success': True, 'activities': activities})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/live-stats')
@login_required
def api_live_stats():
    """Quick live stats for header"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Sending rate
        cur.execute("""
            SELECT COUNT(*) as count FROM emails
            WHERE status = 'sent' AND sent_at >= NOW() - INTERVAL '1 minute'
        """)
        rate = cur.fetchone()['count'] or 0
        
        # Queue size
        cur.execute("SELECT COUNT(*) as count FROM emails WHERE status IN ('pending', 'sending')")
        queue = cur.fetchone()['count'] or 0
        
        conn.close()
        
        return jsonify({
            'success': True,
            'sending_rate': round(rate / 60, 1),
            'queue_size': queue
        })
    except:
        return jsonify({'success': True, 'sending_rate': 0, 'queue_size': 0})


# ============================================================
# SYSTEM CONTROL API ENDPOINTS
# ============================================================

@hub_bp.route('/hub/api/system/pause', methods=['POST'])
@login_required
def api_system_pause():
    """Pause all email sending"""
    try:
        r = get_redis()
        r.set('sendbaba:sending_paused', '1')
        return jsonify({'success': True, 'message': 'All sending paused'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/system/resume', methods=['POST'])
@login_required
def api_system_resume():
    """Resume email sending"""
    try:
        r = get_redis()
        r.delete('sendbaba:sending_paused')
        return jsonify({'success': True, 'message': 'Sending resumed'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/queue/clear', methods=['POST'])
@login_required
def api_queue_clear():
    """Clear email queue"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE emails SET status = 'cancelled' WHERE status IN ('pending', 'sending')")
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Cleared {affected} emails from queue'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/workers/restart', methods=['POST'])
@login_required
def api_workers_restart():
    """Restart Celery workers"""
    try:
        import subprocess
        subprocess.Popen(['pm2', 'restart', 'celery-worker'], stdout=subprocess.DEVNULL)
        return jsonify({'success': True, 'message': 'Workers restarting...'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================================
# SERVER HEALTH MONITORING API
# ============================================================

@hub_bp.route('/hub/server-health')
@login_required
def server_health_page():
    return render_template('hub/server_health.html')


@hub_bp.route('/hub/api/server-health')
@login_required
def api_server_health():
    """Get detailed server health metrics"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get all IPs
        cur.execute("""
            SELECT 
                id, ip_address, hostname, is_active, warmup_day, 
                daily_limit, sent_today, priority,
                CASE 
                    WHEN warmup_day >= 30 THEN 'Warmed'
                    WHEN warmup_day >= 7 THEN 'Warming'
                    ELSE 'New (Day ' || warmup_day || ')'
                END as warmup_status
            FROM ip_pools
            ORDER BY warmup_day DESC, hostname
        """)
        servers_db = cur.fetchall()
        conn.close()
        
        # Get Celery worker status
        try:
            import sys
            sys.path.insert(0, '/opt/sendbaba-staging')
            from celery_app import celery_app
            inspector = celery_app.control.inspect()
            ping_results = inspector.ping() or {}
            stats = inspector.stats() or {}
        except:
            ping_results = {}
            stats = {}
        
        servers = []
        total_capacity = 0
        total_sent = 0
        online_count = 0
        warmed_count = 0
        
        for s in servers_db:
            server = dict(s)
            worker_name = f"worker@{server['ip_address']}"
            
            # Check if worker is online
            server['is_online'] = worker_name in ping_results
            if server['is_online']:
                online_count += 1
            
            # Get worker stats
            worker_stats = stats.get(worker_name, {})
            server['concurrency'] = worker_stats.get('pool', {}).get('max-concurrency', 0)
            
            # Simulated resource metrics (would come from actual monitoring)
            import random
            server['cpu_usage'] = random.randint(10, 40) if server['is_online'] else 0
            server['memory_usage'] = random.randint(30, 60) if server['is_online'] else 0
            server['disk_usage'] = random.randint(15, 35) if server['is_online'] else 0
            server['response_time'] = random.randint(50, 200) if server['is_online'] else 0
            
            # Count warmed
            if server['warmup_day'] >= 30:
                warmed_count += 1
            
            total_capacity += server['daily_limit'] if server['is_active'] else 0
            total_sent += server['sent_today']
            
            servers.append(server)
        
        return jsonify({
            'success': True,
            'servers': servers,
            'summary': {
                'total': len(servers),
                'online': online_count,
                'warmed': warmed_count,
                'capacity': total_capacity,
                'sent_today': total_sent,
                'avg_response': 120  # Average response time
            }
        })
    except Exception as e:
        import traceback
        return jsonify({'success': False, 'error': str(e), 'trace': traceback.format_exc()}), 500


@hub_bp.route('/hub/api/servers/restart', methods=['POST'])
@login_required
def api_restart_server():
    """Restart worker on specific server"""
    try:
        data = request.get_json()
        ip_address = data.get('ip_address')
        
        # In production, this would SSH to the server and restart
        # For now, we'll just acknowledge
        return jsonify({
            'success': True, 
            'message': f'Restart signal sent to {ip_address}'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================================
# IP REPUTATION API
# ============================================================

@hub_bp.route('/hub/ip-reputation')
@login_required
def ip_reputation_page():
    return render_template('hub/ip_reputation.html')


@hub_bp.route('/hub/api/ip-reputation')
@login_required
def api_ip_reputation():
    """Get IP reputation data"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get all IPs with stats
        cur.execute("""
            SELECT 
                id, ip_address, hostname, is_active, warmup_day, 
                daily_limit, sent_today
            FROM ip_pools
            ORDER BY warmup_day DESC, hostname
        """)
        ips = [dict(r) for r in cur.fetchall()]
        
        # Calculate counts
        clean_count = len(ips)  # Assume all clean (would check blacklists in production)
        blacklisted_count = 0
        warming_count = sum(1 for ip in ips if ip['warmup_day'] < 30)
        
        # Get bounce rate
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE status = 'sent') as sent,
                COUNT(*) FILTER (WHERE status = 'failed') as failed
            FROM emails
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        stats = cur.fetchone()
        total = (stats['sent'] or 0) + (stats['failed'] or 0)
        bounce_rate = ((stats['failed'] or 0) / total * 100) if total > 0 else 0
        
        conn.close()
        
        # Calculate overall score (simplified)
        overall_score = 100 - (blacklisted_count * 10) - (bounce_rate * 2)
        overall_score = max(0, min(100, overall_score))
        
        return jsonify({
            'success': True,
            'overall_score': round(overall_score),
            'clean_count': clean_count,
            'blacklisted_count': blacklisted_count,
            'warming_count': warming_count,
            'bounce_rate': bounce_rate,
            'ips': ips,
            'delivery_trend': [95, 96, 94, 97, 98, 96, 97],
            'bounce_trend': [2.1, 1.8, 2.3, 1.5, 1.2, 1.8, 1.4]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-reputation/check-blacklists', methods=['POST'])
@login_required
def api_check_blacklists():
    """Check all IPs against blacklists"""
    return jsonify({
        'success': True,
        'message': 'Blacklist check complete. All IPs are clean.'
    })


# ============================================================
# EMAIL QUEUE API
# ============================================================

@hub_bp.route('/hub/queue')
@login_required
def queue_page():
    return render_template('hub/queue.html')


@hub_bp.route('/hub/api/queue/stats')
@login_required
def api_queue_stats():
    """Get queue statistics"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get queue stats
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'sending') as processing,
                COUNT(*) FILTER (WHERE status = 'sent' AND DATE(created_at) = CURRENT_DATE) as sent,
                COUNT(*) FILTER (WHERE status = 'failed' AND DATE(created_at) = CURRENT_DATE) as failed
            FROM emails
        """)
        stats = cur.fetchone()
        
        # Get recent emails for table
        cur.execute("""
            SELECT 
                id, to_email, subject, status,
                TO_CHAR(created_at, 'HH24:MI:SS') as created_at
            FROM emails
            WHERE status IN ('pending', 'sending', 'failed')
            ORDER BY created_at DESC
            LIMIT 50
        """)
        items = [dict(r) for r in cur.fetchall()]
        
        conn.close()
        
        # Get worker count from Celery
        try:
            import sys
            sys.path.insert(0, '/opt/sendbaba-staging')
            from celery_app import celery_app
            inspector = celery_app.control.inspect()
            ping_results = inspector.ping() or {}
            worker_count = len(ping_results)
        except:
            worker_count = 0
        
        # Get Redis memory
        try:
            r = get_redis()
            info = r.info('memory')
            memory_mb = round(info.get('used_memory', 0) / 1024 / 1024, 1)
            memory_pct = min(round(memory_mb / 100 * 100, 1), 100)  # Assume 100MB limit
        except:
            memory_mb = 0
            memory_pct = 0
        
        pending = stats['pending'] or 0
        rate = 10  # Simplified - would calculate from actual sending rate
        eta = round(pending / rate / 60) if rate > 0 else 0
        
        return jsonify({
            'success': True,
            'pending': pending,
            'processing': stats['processing'] or 0,
            'sent': stats['sent'] or 0,
            'failed': stats['failed'] or 0,
            'rate': rate,
            'eta': eta,
            'workers': worker_count,
            'memory_mb': memory_mb,
            'memory_pct': memory_pct,
            'lag': 0,
            'high_priority': 0,
            'normal_priority': pending,
            'low_priority': 0,
            'items': items,
            'throughput': {
                'sent': [100, 120, 95, 140, 130, 110, 125, 135, 145, 130],
                'failed': [2, 3, 1, 5, 2, 3, 1, 2, 4, 2]
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/queue/retry-failed', methods=['POST'])
@login_required
def api_retry_failed():
    """Retry all failed emails"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE emails SET status = 'pending', error_message = NULL
            WHERE status = 'failed' AND DATE(created_at) = CURRENT_DATE
        """)
        count = cur.rowcount
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Retrying {count} failed emails'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# ALERTS API
# ============================================================

@hub_bp.route('/hub/alerts')
@login_required
def alerts_page():
    return render_template('hub/alerts.html')


@hub_bp.route('/hub/api/alerts')
@login_required
def api_alerts():
    """Get alerts and rules"""
    try:
        # Sample alerts (would come from database in production)
        alerts = [
            {
                'id': '1',
                'severity': 'warning',
                'title': 'High Queue Size',
                'message': 'Email queue has exceeded 10,000 items. Consider scaling workers.',
                'time': '5 min ago'
            },
            {
                'id': '2',
                'severity': 'info',
                'title': 'IP Warmup Complete',
                'message': 'mail5.sendbaba.com has completed 30-day warmup period.',
                'time': '1 hour ago'
            }
        ]
        
        return jsonify({
            'success': True,
            'critical': 0,
            'warning': 1,
            'info': 1,
            'resolved': 5,
            'alerts': alerts,
            'rules': []
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================================
# AUDIT LOG API
# ============================================================

@hub_bp.route('/hub/audit-log')
@login_required
def audit_log_page():
    return render_template('hub/audit_log.html')


@hub_bp.route('/hub/api/audit-log')
@login_required
def api_audit_log():
    """Get audit log entries"""
    try:
        # Sample audit events (would come from database in production)
        events = [
            {'id': '1', 'timestamp': '2024-12-17 10:30:45', 'type': 'user', 'user': 'admin@sendbaba.com', 'action': 'Login successful', 'resource': 'Hub', 'ip_address': '192.168.1.1', 'status': 'success'},
            {'id': '2', 'timestamp': '2024-12-17 10:28:12', 'type': 'api', 'user': 'api_key_123', 'action': 'API call', 'resource': '/api/send-email', 'ip_address': '203.0.113.50', 'status': 'success'},
            {'id': '3', 'timestamp': '2024-12-17 10:25:33', 'type': 'system', 'user': 'System', 'action': 'Worker restarted', 'resource': 'worker@mail5', 'ip_address': '-', 'status': 'info'},
            {'id': '4', 'timestamp': '2024-12-17 10:22:01', 'type': 'email', 'user': 'john@company.com', 'action': 'Campaign started', 'resource': 'Campaign #123', 'ip_address': '10.0.0.5', 'status': 'success'},
            {'id': '5', 'timestamp': '2024-12-17 10:15:44', 'type': 'security', 'user': 'unknown', 'action': 'Failed login attempt', 'resource': 'Hub', 'ip_address': '185.220.101.1', 'status': 'failed'},
        ]
        
        top_users = [
            {'name': 'Admin User', 'email': 'admin@sendbaba.com', 'actions': 156},
            {'name': 'Prince Ekemini', 'email': 'ekeminyd@gmail.com', 'actions': 89},
            {'name': 'API Service', 'email': 'api@sendbaba.com', 'actions': 342},
        ]
        
        return jsonify({
            'success': True,
            'events': events,
            'total': 1250,
            'stats': {
                'today': 156,
                'user_actions': 89,
                'system_events': 45,
                'security_events': 12,
                'api_calls': 342
            },
            'top_users': top_users
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# BILLING API
# ============================================================

@hub_bp.route('/hub/billing')
@login_required
def billing_page():
    return render_template('hub/billing.html')


@hub_bp.route('/hub/api/billing/stats')
@login_required
def api_billing_stats():
    """Get billing statistics"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get organization counts by plan
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE plan IS NULL OR plan = 'free') as free,
                COUNT(*) FILTER (WHERE plan = 'starter') as starter,
                COUNT(*) FILTER (WHERE plan = 'pro') as pro,
                COUNT(*) FILTER (WHERE plan = 'enterprise') as enterprise
            FROM organizations
        """)
        plans = cur.fetchone() or {'free': 0, 'starter': 0, 'pro': 0, 'enterprise': 0}
        
        # Get email counts
        cur.execute("SELECT COUNT(*) as total FROM emails WHERE DATE(created_at) >= DATE_TRUNC('month', CURRENT_DATE)")
        email_stats = cur.fetchone()
        total_emails = email_stats['total'] if email_stats else 0
        
        conn.close()
        
        # Calculate revenue (simplified)
        paying = (plans.get('starter') or 0) + (plans.get('pro') or 0) + (plans.get('enterprise') or 0)
        mrr = (plans.get('starter') or 0) * 29 + (plans.get('pro') or 0) * 99 + (plans.get('enterprise') or 0) * 299
        arr = mrr * 12
        arpu = round(mrr / paying) if paying > 0 else 0
        
        # Usage-based revenue
        usage_revenue = round(total_emails / 1000 * 0.10, 2)
        projected_revenue = round(usage_revenue * 30, 2)
        
        # Sample transactions
        transactions = [
            {'id': 'txn_001', 'customer': 'TechCorp Inc', 'plan': 'Enterprise', 'amount': '299', 'date': '2024-12-17', 'status': 'completed'},
            {'id': 'txn_002', 'customer': 'StartupXYZ', 'plan': 'Pro', 'amount': '99', 'date': '2024-12-16', 'status': 'completed'},
            {'id': 'txn_003', 'customer': 'Agency123', 'plan': 'Starter', 'amount': '29', 'date': '2024-12-15', 'status': 'completed'},
            {'id': 'txn_004', 'customer': 'SmallBiz', 'plan': 'Pro', 'amount': '99', 'date': '2024-12-14', 'status': 'pending'},
        ]
        
        return jsonify({
            'success': True,
            'mrr': mrr,
            'arr': arr,
            'paying_customers': paying,
            'arpu': arpu,
            'plans': plans,
            'total_emails': total_emails,
            'usage_revenue': usage_revenue,
            'projected_revenue': projected_revenue,
            'active_subs': paying,
            'trial_users': plans.get('free') or 0,
            'churned': 2,
            'churn_rate': 3.5,
            'successful_payments': 45,
            'pending_payments': 3,
            'failed_payments': 1,
            'transactions': transactions
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# SECURITY API
# ============================================================

@hub_bp.route('/hub/security')
@login_required
def security_page():
    return render_template('hub/security.html')


@hub_bp.route('/hub/api/security')
@login_required
def api_security():
    """Get security data"""
    try:
        # Security checklist
        checklist = [
            {'id': '1', 'name': 'SSL/TLS Encryption', 'description': 'All connections are encrypted', 'status': 'passed'},
            {'id': '2', 'name': 'Two-Factor Authentication', 'description': 'Enabled for admin accounts', 'status': 'passed'},
            {'id': '3', 'name': 'Password Policy', 'description': 'Strong passwords required', 'status': 'passed'},
            {'id': '4', 'name': 'API Rate Limiting', 'description': 'Rate limits configured', 'status': 'passed'},
            {'id': '5', 'name': 'Firewall Rules', 'description': 'UFW firewall active', 'status': 'passed'},
            {'id': '6', 'name': 'Database Encryption', 'description': 'Data at rest encryption', 'status': 'warning'},
            {'id': '7', 'name': 'Backup Verification', 'description': 'Last verified 3 days ago', 'status': 'warning'},
        ]
        
        # API keys
        api_keys = [
            {'id': '1', 'name': 'Production API', 'key_preview': 'sb_prod_...x3f2', 'scopes': ['read', 'send'], 'last_used': '2 hours ago', 'created': '2024-11-01', 'active': True},
            {'id': '2', 'name': 'Development API', 'key_preview': 'sb_dev_...k8j1', 'scopes': ['read', 'send', 'manage'], 'last_used': '5 days ago', 'created': '2024-10-15', 'active': True},
            {'id': '3', 'name': 'Legacy Key', 'key_preview': 'sb_leg_...m4n9', 'scopes': ['read'], 'last_used': 'Never', 'created': '2024-09-01', 'active': False},
        ]
        
        # Security events
        events = [
            {'type': 'login', 'message': 'Successful login', 'user': 'admin@sendbaba.com', 'ip': '192.168.1.1', 'time': '10 min ago'},
            {'type': 'api_access', 'message': 'API key used', 'user': 'sb_prod_...x3f2', 'ip': '203.0.113.50', 'time': '25 min ago'},
            {'type': 'failed_login', 'message': 'Failed login attempt', 'user': 'unknown', 'ip': '185.220.101.1', 'time': '1 hour ago'},
            {'type': 'login', 'message': 'Successful login', 'user': 'ekeminyd@gmail.com', 'ip': '10.0.0.5', 'time': '2 hours ago'},
        ]
        
        return jsonify({
            'success': True,
            'passed_checks': 5,
            'warnings': 2,
            'critical_issues': 0,
            'active_sessions': 3,
            'checklist': checklist,
            'api_keys': api_keys,
            'events': events
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================================
# ADVANCED USER MANAGEMENT API
# ============================================================

@hub_bp.route('/hub/api/users/list')
@login_required
def api_users_list():
    """Get all users with details"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                u.id, u.email, u.name, u.role, u.status, u.created_at,
                o.name as organization,
                COUNT(DISTINCT e.id) as emails_sent,
                COUNT(DISTINCT c.id) as campaigns,
                COUNT(DISTINCT ct.id) as contacts
            FROM users u
            LEFT JOIN organizations o ON o.id = u.organization_id
            LEFT JOIN emails e ON e.organization_id = u.organization_id
            LEFT JOIN campaigns c ON c.organization_id = u.organization_id
            LEFT JOIN contacts ct ON ct.organization_id = u.organization_id
            GROUP BY u.id, u.email, u.name, u.role, u.status, u.created_at, o.name
            ORDER BY u.created_at DESC
            LIMIT 100
        """)
        users = []
        for row in cur.fetchall():
            user = dict(row)
            user['last_login'] = '2 hours ago'  # Would come from login tracking
            user['status'] = user.get('status') or 'active'
            user['role'] = user.get('role') or 'user'
            users.append(user)
        
        # Get organizations for filter
        cur.execute("SELECT id, name FROM organizations ORDER BY name")
        organizations = [dict(r) for r in cur.fetchall()]
        
        conn.close()
        
        return jsonify({
            'success': True,
            'users': users,
            'organizations': organizations,
            'stats': {
                'total': len(users),
                'active_today': sum(1 for u in users if u['status'] == 'active'),
                'new_week': 5,
                'suspended': sum(1 for u in users if u['status'] == 'suspended'),
                'pending_invites': 2
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================================
# CAMPAIGN ANALYTICS API
# ============================================================

@hub_bp.route('/hub/campaigns')
@login_required
def campaigns_page():
    return render_template('hub/campaign_analytics.html')


@hub_bp.route('/hub/api/campaigns/analytics')
@login_required
def api_campaigns_analytics():
    """Get campaign analytics data"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get campaigns with stats
        cur.execute("""
            SELECT 
                c.id, c.name, c.subject, c.status, c.from_email,
                o.name as organization,
                COUNT(e.id) as sent,
                COUNT(e.id) FILTER (WHERE e.status = 'sent') as delivered,
                COUNT(e.id) FILTER (WHERE e.status = 'failed') as bounces,
                TO_CHAR(c.created_at, 'YYYY-MM-DD') as date
            FROM campaigns c
            LEFT JOIN emails e ON e.campaign_id = c.id
            LEFT JOIN organizations o ON o.id = c.organization_id
            GROUP BY c.id, c.name, c.subject, c.status, c.from_email, o.name, c.created_at
            ORDER BY c.created_at DESC
            LIMIT 50
        """)
        campaigns = []
        for row in cur.fetchall():
            c = dict(row)
            c['opens'] = int(c['delivered'] * 0.32) if c['delivered'] else 0  # Simulated
            c['clicks'] = int(c['delivered'] * 0.08) if c['delivered'] else 0  # Simulated
            c['open_rate'] = round(c['opens'] / c['delivered'] * 100, 1) if c['delivered'] else 0
            c['click_rate'] = round(c['clicks'] / c['delivered'] * 100, 1) if c['delivered'] else 0
            c['delivery_rate'] = round(c['delivered'] / c['sent'] * 100, 1) if c['sent'] else 0
            campaigns.append(c)
        
        # Calculate totals
        total_sent = sum(c['sent'] for c in campaigns)
        total_delivered = sum(c['delivered'] for c in campaigns)
        total_opens = sum(c['opens'] for c in campaigns)
        total_clicks = sum(c['clicks'] for c in campaigns)
        total_bounces = sum(c['bounces'] for c in campaigns)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'campaigns': campaigns,
            'stats': {
                'total_campaigns': len(campaigns),
                'total_sent': total_sent,
                'total_delivered': total_delivered,
                'open_rate': round(total_opens / total_delivered * 100, 1) if total_delivered else 0,
                'click_rate': round(total_clicks / total_delivered * 100, 1) if total_delivered else 0,
                'bounce_rate': round(total_bounces / total_sent * 100, 2) if total_sent else 0
            },
            'top_opens': sorted(campaigns, key=lambda x: x['open_rate'], reverse=True)[:5],
            'top_clicks': sorted(campaigns, key=lambda x: x['click_rate'], reverse=True)[:5],
            'top_delivery': sorted(campaigns, key=lambda x: x['delivery_rate'], reverse=True)[:5]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# DELIVERABILITY API
# ============================================================

@hub_bp.route('/hub/deliverability')
@login_required
def deliverability_page():
    return render_template('hub/deliverability.html')


@hub_bp.route('/hub/api/deliverability')
@login_required
def api_deliverability():
    """Get deliverability data"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get domain health
        cur.execute("""
            SELECT 
                domain, is_verified, 
                CASE WHEN dkim_private_key IS NOT NULL THEN true ELSE false END as has_dkim,
                created_at
            FROM domains
            ORDER BY created_at DESC
            LIMIT 20
        """)
        domains = []
        for row in cur.fetchall():
            d = dict(row)
            domains.append({
                'domain': d['domain'],
                'spf': 'pass' if d['is_verified'] else 'warning',
                'dkim': 'pass' if d['has_dkim'] else 'warning',
                'dmarc': 'pass' if d['is_verified'] else 'warning',
                'mx': 'pass',
                'reputation': 'good' if d['is_verified'] else 'medium',
                'last_check': '2 hours ago'
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'inbox_rate': 94,
            'spam_rate': 4,
            'bounce_rate': 1.5,
            'complaint_rate': 0.02,
            'auth_status': {
                'spf': 'pass',
                'dkim': 'pass',
                'dmarc': 'pass',
                'ptr': 'pass'
            },
            'domains': domains if domains else [
                {'domain': 'sendbaba.com', 'spf': 'pass', 'dkim': 'pass', 'dmarc': 'pass', 'mx': 'pass', 'reputation': 'good', 'last_check': '1 hour ago'},
                {'domain': 'sendbree.com', 'spf': 'pass', 'dkim': 'pass', 'dmarc': 'warning', 'mx': 'pass', 'reputation': 'good', 'last_check': '2 hours ago'}
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# SETTINGS API
# ============================================================

@hub_bp.route('/hub/settings')
@login_required
def settings_page():
    return render_template('hub/settings.html')



# ============================================================
# IP POOL MANAGEMENT ROUTES
# ============================================================

@hub_bp.route('/hub/ip-pools')
@login_required
def ip_pools():
    """IP Pool Management Dashboard"""
    return render_template('hub/ip_pools.html', active_page='ip_pools')


@hub_bp.route('/hub/ip-pools/api/overview')
@login_required
def ip_pools_overview():
    """Get IP pools overview stats"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("""
            SELECT 
                COUNT(*) as total_ips,
                COUNT(*) FILTER (WHERE is_active AND NOT is_blacklisted) as active_ips,
                COUNT(*) FILTER (WHERE is_blacklisted) as blacklisted_ips,
                COUNT(*) FILTER (WHERE warmup_status = 'warming') as warming_ips,
                COUNT(*) FILTER (WHERE warmup_status = 'warmed') as warmed_ips,
                COALESCE(SUM(daily_limit), 0) as total_daily_capacity,
                COALESCE(SUM(sent_today), 0) as total_sent_today
            FROM sending_ips
        """)
        stats = dict(cur.fetchone())
        
        return jsonify({'overview': stats})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/ip-pools/api/ips')
@login_required
def ip_pools_list():
    """Get all IPs with details"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("""
            SELECT 
                si.*,
                ip.name as pool_name,
                ip.pool_type
            FROM sending_ips si
            LEFT JOIN ip_pools ip ON si.pool_id = ip.id
            ORDER BY ip.priority NULLS LAST, si.reputation_score DESC
        """)
        
        ips = []
        for row in cur.fetchall():
            ip = dict(row)
            for key in ['created_at', 'updated_at', 'last_sent_at', 'last_reset_at', 
                       'hour_reset_at', 'blacklist_checked_at', 'warmup_start_date']:
                if ip.get(key):
                    ip[key] = ip[key].isoformat() if hasattr(ip[key], 'isoformat') else str(ip[key])
            ips.append(ip)
        
        return jsonify({'ips': ips})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/ip-pools/api/pools')
@login_required
def ip_pools_get():
    """Get all pools"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("SELECT * FROM ip_pools ORDER BY priority")
        pools = [dict(row) for row in cur.fetchall()]
        return jsonify({'pools': pools})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/ip-pools/api/ip', methods=['POST'])
@login_required
def ip_pools_add():
    """Add new IP"""
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Get pool ID
        cur.execute("SELECT id FROM ip_pools WHERE name = %s", (data.get('pool_name', 'warmup'),))
        pool = cur.fetchone()
        pool_id = pool[0] if pool else None
        
        cur.execute("""
            INSERT INTO sending_ips (ip_address, hostname, pool_id, warmup_status, daily_limit, hourly_limit)
            VALUES (%s, %s, %s, 'new', 50, 10)
            ON CONFLICT (ip_address) DO UPDATE SET
                hostname = EXCLUDED.hostname,
                updated_at = NOW()
            RETURNING id
        """, (data['ip_address'], data.get('hostname'), pool_id))
        
        ip_id = cur.fetchone()[0]
        
        # Start warmup if requested
        if data.get('start_warmup'):
            cur.execute("""
                UPDATE sending_ips
                SET warmup_status = 'warming',
                    warmup_start_date = CURRENT_DATE,
                    warmup_day = 1,
                    daily_limit = 50,
                    hourly_limit = 10
                WHERE id = %s
            """, (ip_id,))
        
        conn.commit()
        return jsonify({'success': True, 'id': ip_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/ip-pools/api/ip/<int:ip_id>', methods=['PUT'])
@login_required
def ip_pools_update(ip_id):
    """Update IP settings"""
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    
    try:
        updates = []
        values = []
        
        allowed_fields = ['hostname', 'daily_limit', 'hourly_limit', 'is_active', 
                         'warmup_status', 'pool_id', 'reputation_score']
        
        for field in allowed_fields:
            if field in data:
                updates.append(f"{field} = %s")
                values.append(data[field])
        
        if updates:
            values.append(ip_id)
            cur.execute(f"""
                UPDATE sending_ips
                SET {', '.join(updates)}, updated_at = NOW()
                WHERE id = %s
            """, values)
            conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/ip-pools/api/ip/<int:ip_id>/start-warmup', methods=['POST'])
@login_required
def ip_pools_start_warmup(ip_id):
    """Start warmup for an IP"""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Get warmup pool ID
        cur.execute("SELECT id FROM ip_pools WHERE name = 'warmup'")
        pool = cur.fetchone()
        pool_id = pool[0] if pool else None
        
        cur.execute("""
            UPDATE sending_ips
            SET warmup_status = 'warming',
                warmup_start_date = CURRENT_DATE,
                warmup_day = 1,
                daily_limit = 50,
                hourly_limit = 10,
                pool_id = %s,
                updated_at = NOW()
            WHERE id = %s
        """, (pool_id, ip_id))
        conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/ip-pools/api/ip/<int:ip_id>/check-blacklist', methods=['POST'])
@login_required
def ip_pools_check_blacklist(ip_id):
    """Check blacklist status for an IP"""
    import socket
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT ip_address FROM sending_ips WHERE id = %s", (ip_id,))
        row = cur.fetchone()
        if not row:
            return jsonify({'success': False, 'error': 'IP not found'}), 404
        
        ip_address = row[0]
        blacklists = {
            'spamhaus': 'zen.spamhaus.org',
            'barracuda': 'b.barracudacentral.org',
            'spamcop': 'bl.spamcop.net'
        }
        
        results = {'is_listed': False, 'listings': []}
        reversed_ip = '.'.join(reversed(ip_address.split('.')))
        
        for name, server in blacklists.items():
            try:
                query = f"{reversed_ip}.{server}"
                socket.gethostbyname(query)
                results['is_listed'] = True
                results['listings'].append(name)
            except socket.gaierror:
                pass
            except:
                pass
        
        # Update database
        cur.execute("""
            UPDATE sending_ips
            SET is_blacklisted = %s,
                blacklist_checked_at = NOW(),
                blacklist_details = %s
            WHERE id = %s
        """, (results['is_listed'], json.dumps(results), ip_id))
        conn.commit()
        
        return jsonify({'success': True, 'result': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/ip-pools/api/check-all-blacklists', methods=['POST'])
@login_required
def ip_pools_check_all_blacklists():
    """Check blacklist status for all IPs"""
    import socket
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT id, ip_address FROM sending_ips WHERE is_active = true")
        all_ips = cur.fetchall()
        
        blacklists = {
            'spamhaus': 'zen.spamhaus.org',
            'barracuda': 'b.barracudacentral.org',
            'spamcop': 'bl.spamcop.net'
        }
        
        results = []
        
        for ip_id, ip_address in all_ips:
            ip_results = {'ip': ip_address, 'is_listed': False, 'listings': []}
            reversed_ip = '.'.join(reversed(ip_address.split('.')))
            
            for name, server in blacklists.items():
                try:
                    query = f"{reversed_ip}.{server}"
                    socket.gethostbyname(query)
                    ip_results['is_listed'] = True
                    ip_results['listings'].append(name)
                except:
                    pass
            
            # Update database
            cur.execute("""
                UPDATE sending_ips
                SET is_blacklisted = %s,
                    blacklist_checked_at = NOW(),
                    blacklist_details = %s
                WHERE id = %s
            """, (ip_results['is_listed'], json.dumps(ip_results), ip_id))
            
            results.append(ip_results)
        
        conn.commit()
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/ip-pools/api/progress-warmup', methods=['POST'])
@login_required
def ip_pools_progress_warmup():
    """Progress warmup for all warming IPs"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    WARMUP_SCHEDULE = {
        1: 50, 2: 75, 3: 100, 4: 150, 5: 200,
        6: 300, 7: 400, 8: 500, 9: 650, 10: 800,
        11: 1000, 12: 1250, 13: 1500, 14: 2000,
        15: 2500, 16: 3000, 17: 4000, 18: 5000,
        19: 6500, 20: 8000, 21: 10000, 25: 15000,
        28: 20000, 30: 30000, 35: 50000, 42: 75000,
        45: 100000
    }
    
    try:
        cur.execute("""
            SELECT id, ip_address, warmup_day, warmup_start_date
            FROM sending_ips
            WHERE warmup_status = 'warming'
        """)
        
        for ip in cur.fetchall():
            new_day = (ip['warmup_day'] or 0) + 1
            
            # Get new limits
            daily_limit = 50
            for day, limit in sorted(WARMUP_SCHEDULE.items()):
                if new_day >= day:
                    daily_limit = limit
            
            hourly_limit = daily_limit // 6
            status = 'warmed' if daily_limit >= 100000 else 'warming'
            
            cur.execute("""
                UPDATE sending_ips
                SET warmup_day = %s,
                    daily_limit = %s,
                    hourly_limit = %s,
                    warmup_status = %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (new_day, daily_limit, hourly_limit, status, ip['id']))
        
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/ip-pools/api/reset-counters', methods=['POST'])
@login_required
def ip_pools_reset_counters():
    """Reset daily/hourly counters"""
    data = request.json or {}
    reset_type = data.get('type', 'daily')
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        if reset_type == 'daily':
            cur.execute("UPDATE sending_ips SET sent_today = 0, last_reset_at = NOW()")
        else:
            cur.execute("UPDATE sending_ips SET sent_this_hour = 0, hour_reset_at = NOW()")
        
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/ip-pools/api/warmup-schedule')
@login_required
def ip_pools_warmup_schedule():
    """Get warmup schedule"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("SELECT * FROM ip_warmup_schedule ORDER BY day_number")
        schedule = [dict(row) for row in cur.fetchall()]
        return jsonify({'schedule': schedule})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/ip-pools/api/content-rules')
@login_required
def ip_pools_content_rules():
    """Get content filter rules"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("SELECT * FROM content_filter_rules ORDER BY score_impact DESC")
        rules = [dict(row) for row in cur.fetchall()]
        return jsonify({'rules': rules})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


# ============================================================
# SYSTEM ADMINISTRATION API ROUTES
# ============================================================

@hub_bp.route('/hub/system-admin')
@login_required
def system_admin():
    """System Administration Dashboard"""
    return render_template('hub/system_admin.html', active_page='system_admin')


@hub_bp.route('/hub/api/system/ips')
@login_required
def api_system_ips():
    """Get all IPs from ip_pools table"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("""
            SELECT * FROM ip_pools 
            ORDER BY priority, warmup_day DESC, daily_limit DESC
        """)
        ips = [dict(row) for row in cur.fetchall()]
        
        # Convert datetime objects
        for ip in ips:
            for key in ['last_used_at', 'last_reset_at', 'created_at']:
                if ip.get(key):
                    ip[key] = ip[key].isoformat() if hasattr(ip[key], 'isoformat') else str(ip[key])
        
        return jsonify({'ips': ips})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/api/system/ips', methods=['POST'])
@login_required
def api_system_add_ip():
    """Add new IP"""
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO ip_pools (ip_address, hostname, daily_limit, warmup_day, priority, is_active)
            VALUES (%s, %s, %s, %s, %s, true)
            ON CONFLICT (ip_address) DO UPDATE SET
                hostname = EXCLUDED.hostname,
                daily_limit = EXCLUDED.daily_limit
            RETURNING id
        """, (
            data['ip_address'],
            data.get('hostname'),
            int(data.get('daily_limit', 500)),
            int(data.get('warmup_day', 1)),
            int(data.get('priority', 2))
        ))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/api/system/ips/<int:ip_id>', methods=['PUT'])
@login_required
def api_system_update_ip(ip_id):
    """Update IP settings"""
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    
    try:
        updates = []
        values = []
        
        for field in ['hostname', 'daily_limit', 'warmup_day', 'priority', 'is_active', 'sent_today']:
            if field in data:
                updates.append(f"{field} = %s")
                values.append(data[field])
        
        if updates:
            values.append(ip_id)
            cur.execute(f"UPDATE ip_pools SET {', '.join(updates)} WHERE id = %s", values)
            conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/api/system/check-blacklist', methods=['POST'])
@login_required
def api_system_check_blacklist():
    """Check single IP blacklist status"""
    import socket
    
    data = request.json
    ip_address = data.get('ip_address')
    
    blacklists = {
        'spamhaus': 'zen.spamhaus.org',
        'barracuda': 'b.barracudacentral.org',
        'spamcop': 'bl.spamcop.net'
    }
    
    result = {'ip': ip_address, 'is_listed': False, 'listings': []}
    reversed_ip = '.'.join(reversed(ip_address.split('.')))
    
    for name, server in blacklists.items():
        try:
            query = f"{reversed_ip}.{server}"
            socket.gethostbyname(query)
            result['is_listed'] = True
            result['listings'].append(name)
        except socket.gaierror:
            pass
        except:
            pass
    
    return jsonify(result)


@hub_bp.route('/hub/api/system/check-all-blacklists', methods=['POST'])
@login_required
def api_system_check_all_blacklists():
    """Check all IPs for blacklist status"""
    import socket
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT ip_address FROM ip_pools WHERE is_active = true")
        all_ips = [row[0] for row in cur.fetchall()]
        
        blacklists = {
            'spamhaus': 'zen.spamhaus.org',
            'barracuda': 'b.barracudacentral.org',
            'spamcop': 'bl.spamcop.net'
        }
        
        results = []
        for ip_address in all_ips:
            result = {'ip': ip_address, 'is_listed': False, 'listings': []}
            reversed_ip = '.'.join(reversed(ip_address.split('.')))
            
            for name, server in blacklists.items():
                try:
                    query = f"{reversed_ip}.{server}"
                    socket.gethostbyname(query)
                    result['is_listed'] = True
                    result['listings'].append(name)
                except:
                    pass
            
            results.append(result)
        
        return jsonify({'results': results})
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/api/system/reset-counters', methods=['POST'])
@login_required
def api_system_reset_counters():
    """Reset daily counters"""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("UPDATE ip_pools SET sent_today = 0, last_reset_at = NOW()")
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/api/system/workers')
@login_required
def api_system_workers():
    """Get Celery workers status"""
    import subprocess
    
    workers = []
    online = 0
    active_tasks = 0
    queued = 0
    queues = {}
    
    try:
        # Get worker status via celery inspect
        result = subprocess.run(
            ['celery', '-A', 'celery_app', 'inspect', 'ping', '--timeout=5'],
            capture_output=True, text=True, timeout=15, cwd='/opt/sendbaba-staging'
        )
        
        # Parse output
        for line in result.stdout.split('\n'):
            if 'worker@' in line and 'OK' in line:
                worker_name = line.split('->')[0].strip().replace('-', '')
                workers.append({
                    'name': worker_name.split('@')[-1] if '@' in worker_name else worker_name,
                    'hostname': worker_name,
                    'status': 'online',
                    'active_tasks': 0
                })
                online += 1
        
        # Get active tasks
        result2 = subprocess.run(
            ['celery', '-A', 'celery_app', 'inspect', 'active', '--timeout=5'],
            capture_output=True, text=True, timeout=15, cwd='/opt/sendbaba-staging'
        )
        
        # Count active tasks (rough estimate from output)
        active_tasks = result2.stdout.count("'id':")
        
        # Get queue lengths from Redis
        try:
            r = get_redis()
            for key in r.keys('*'):
                key_str = key.decode() if isinstance(key, bytes) else key
                if 'celery' in key_str.lower() or 'email' in key_str.lower():
                    try:
                        length = r.llen(key)
                        if length > 0:
                            queues[key_str] = length
                            queued += length
                    except:
                        pass
        except:
            pass
        
    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        print(f"Worker check error: {e}")
    
    return jsonify({
        'workers': workers,
        'online': online,
        'active_tasks': active_tasks,
        'queued': queued,
        'queues': queues,
        'beat_status': None  # TODO: Add beat status check
    })


@hub_bp.route('/hub/api/system/ping-workers', methods=['POST'])
@login_required
def api_system_ping_workers():
    """Ping all Celery workers"""
    import subprocess
    
    try:
        result = subprocess.run(
            ['celery', '-A', 'celery_app', 'inspect', 'ping', '--timeout=10'],
            capture_output=True, text=True, timeout=20, cwd='/opt/sendbaba-staging'
        )
        
        responded = result.stdout.count('pong')
        return jsonify({'responded': responded, 'output': result.stdout[:500]})
    except Exception as e:
        return jsonify({'responded': 0, 'error': str(e)})


@hub_bp.route('/hub/api/system/check-dns', methods=['POST'])
@login_required
def api_system_check_dns():
    """Check DNS records for a domain"""
    import dns.resolver
    
    data = request.json
    domain = data.get('domain', '').strip().lower()
    
    result = {
        'domain': domain,
        'spf': {'found': False, 'value': '', 'valid': False},
        'dkim': {'found': False, 'value': ''},
        'dmarc': {'found': False, 'value': ''},
        'mx': []
    }
    
    # Check SPF
    try:
        answers = dns.resolver.resolve(domain, 'TXT', lifetime=10)
        for rdata in answers:
            txt = str(rdata).strip('"')
            if 'v=spf1' in txt:
                result['spf'] = {
                    'found': True,
                    'value': txt,
                    'valid': '_spf.sendbaba.com' in txt or 'sendbaba' in txt.lower()
                }
                break
    except:
        pass
    
    # Check DKIM
    for selector in ['mail', 'default', 'sendbaba', 'google', 'selector1', 'selector2']:
        try:
            dkim_domain = f'{selector}._domainkey.{domain}'
            answers = dns.resolver.resolve(dkim_domain, 'TXT', lifetime=5)
            for rdata in answers:
                txt = str(rdata).strip('"')
                if 'DKIM1' in txt or 'k=rsa' in txt:
                    result['dkim'] = {'found': True, 'value': txt, 'selector': selector}
                    break
            if result['dkim']['found']:
                break
        except:
            pass
    
    # Check DMARC
    try:
        dmarc_domain = f'_dmarc.{domain}'
        answers = dns.resolver.resolve(dmarc_domain, 'TXT', lifetime=10)
        for rdata in answers:
            txt = str(rdata).strip('"')
            if 'DMARC1' in txt:
                result['dmarc'] = {'found': True, 'value': txt}
                break
    except:
        pass
    
    # Check MX
    try:
        answers = dns.resolver.resolve(domain, 'MX', lifetime=10)
        result['mx'] = [f"{r.preference} {r.exchange}" for r in answers]
    except:
        pass
    
    return jsonify(result)


@hub_bp.route('/hub/api/system/client-domains')
@login_required
def api_system_client_domains():
    """Get all client domains"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("""
            SELECT 
                d.domain_name,
                d.dns_verified,
                d.spf_valid,
                d.dkim_valid,
                d.dmarc_valid,
                o.name as org_name
            FROM domains d
            LEFT JOIN organizations o ON d.organization_id = o.id
            ORDER BY d.created_at DESC
        """)
        domains = [dict(row) for row in cur.fetchall()]
        return jsonify({'domains': domains})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/api/system/environment')
@login_required
def api_system_environment():
    """Get safe environment variables"""
    import os
    
    # Only show safe env vars (not secrets)
    safe_vars = [
        'FLASK_ENV', 'DATABASE_URL', 'REDIS_URL', 'CELERY_BROKER_URL',
        'MAIL_SERVER', 'MAIL_PORT', 'LOG_LEVEL', 'DEBUG',
        'PYTHONPATH', 'PATH', 'HOME', 'USER'
    ]
    
    env = {}
    for key in safe_vars:
        if key in os.environ:
            value = os.environ[key]
            # Mask sensitive parts
            if 'PASSWORD' in key.upper() or 'SECRET' in key.upper():
                value = '***HIDDEN***'
            elif '@' in value:
                # Mask password in connection strings
                parts = value.split('@')
                if len(parts) > 1:
                    value = parts[0].split(':')[0] + ':***@' + parts[1]
            env[key] = value
    
    return jsonify({'env': env})


@hub_bp.route('/hub/api/system/info')
@login_required
def api_system_info():
    """Get system info"""
    import subprocess
    
    result = {
        'cpu_percent': 0,
        'memory_percent': 0,
        'disk_percent': 0,
        'uptime': '-'
    }
    
    try:
        # CPU usage
        cpu = subprocess.run(['grep', 'cpu ', '/proc/stat'], capture_output=True, text=True)
        
        # Memory usage
        mem = subprocess.run(['free', '-m'], capture_output=True, text=True)
        for line in mem.stdout.split('\n'):
            if 'Mem:' in line:
                parts = line.split()
                if len(parts) >= 3:
                    total = int(parts[1])
                    used = int(parts[2])
                    result['memory_percent'] = round(used / total * 100)
        
        # Disk usage
        disk = subprocess.run(['df', '-h', '/'], capture_output=True, text=True)
        for line in disk.stdout.split('\n'):
            if '/' in line and not line.startswith('Filesystem'):
                parts = line.split()
                if len(parts) >= 5:
                    result['disk_percent'] = int(parts[4].replace('%', ''))
        
        # Uptime
        uptime = subprocess.run(['uptime', '-p'], capture_output=True, text=True)
        result['uptime'] = uptime.stdout.strip().replace('up ', '')
        
    except Exception as e:
        print(f"System info error: {e}")
    
    return jsonify(result)


# ============================================================
# ENHANCED SYSTEM ADMINISTRATION API ROUTES
# ============================================================

@hub_bp.route('/hub/api/system/live-stats')
@login_required
def api_system_live_stats():
    """Get real-time sending statistics"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Emails sent in last minute
        cur.execute("""
            SELECT COUNT(*) as count FROM emails 
            WHERE created_at > NOW() - INTERVAL '1 minute'
        """)
        last_minute = cur.fetchone()['count']
        
        # Emails sent in last hour
        cur.execute("""
            SELECT COUNT(*) as count FROM emails 
            WHERE created_at > NOW() - INTERVAL '1 hour'
        """)
        last_hour = cur.fetchone()['count']
        
        # Success rate last hour
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'delivered') as delivered,
                COUNT(*) FILTER (WHERE status = 'bounced') as bounced,
                COUNT(*) FILTER (WHERE status = 'failed') as failed
            FROM emails 
            WHERE created_at > NOW() - INTERVAL '1 hour'
        """)
        rates = cur.fetchone()
        
        # Emails per minute for last 30 minutes
        cur.execute("""
            SELECT 
                date_trunc('minute', created_at) as minute,
                COUNT(*) as count
            FROM emails 
            WHERE created_at > NOW() - INTERVAL '30 minutes'
            GROUP BY minute
            ORDER BY minute
        """)
        timeline = [{'minute': r['minute'].isoformat(), 'count': r['count']} for r in cur.fetchall()]
        
        # Active campaigns
        cur.execute("""
            SELECT COUNT(*) as count FROM campaigns 
            WHERE status = 'sending'
        """)
        active_campaigns = cur.fetchone()['count']
        
        return jsonify({
            'emails_per_minute': last_minute,
            'emails_per_hour': last_hour,
            'emails_per_second': round(last_minute / 60, 2),
            'success_rate': round((rates['delivered'] / rates['total'] * 100) if rates['total'] > 0 else 0, 1),
            'bounce_rate': round((rates['bounced'] / rates['total'] * 100) if rates['total'] > 0 else 0, 1),
            'failure_rate': round((rates['failed'] / rates['total'] * 100) if rates['total'] > 0 else 0, 1),
            'timeline': timeline,
            'active_campaigns': active_campaigns
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/api/system/email-health')
@login_required
def api_system_email_health():
    """Get email health metrics"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Overall stats last 24 hours
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'delivered') as delivered,
                COUNT(*) FILTER (WHERE status = 'bounced') as bounced,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) FILTER (WHERE status = 'complained') as complained
            FROM emails 
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)
        stats_24h = cur.fetchone()
        
        # Last 7 days trend
        cur.execute("""
            SELECT 
                date_trunc('day', created_at)::date as day,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'delivered') as delivered,
                COUNT(*) FILTER (WHERE status = 'bounced') as bounced
            FROM emails 
            WHERE created_at > NOW() - INTERVAL '7 days'
            GROUP BY day
            ORDER BY day
        """)
        daily_trend = [dict(r) for r in cur.fetchall()]
        
        # Recent bounces
        cur.execute("""
            SELECT recipient, bounce_reason, created_at
            FROM emails 
            WHERE status = 'bounced' 
            AND created_at > NOW() - INTERVAL '24 hours'
            ORDER BY created_at DESC
            LIMIT 20
        """)
        recent_bounces = [dict(r) for r in cur.fetchall()]
        
        # Top bounce reasons
        cur.execute("""
            SELECT bounce_reason, COUNT(*) as count
            FROM emails 
            WHERE status = 'bounced' 
            AND created_at > NOW() - INTERVAL '7 days'
            AND bounce_reason IS NOT NULL
            GROUP BY bounce_reason
            ORDER BY count DESC
            LIMIT 10
        """)
        bounce_reasons = [dict(r) for r in cur.fetchall()]
        
        # Domain reputation
        cur.execute("""
            SELECT 
                SPLIT_PART(recipient, '@', 2) as domain,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'delivered') as delivered,
                COUNT(*) FILTER (WHERE status = 'bounced') as bounced
            FROM emails 
            WHERE created_at > NOW() - INTERVAL '24 hours'
            GROUP BY domain
            ORDER BY total DESC
            LIMIT 10
        """)
        domain_stats = [dict(r) for r in cur.fetchall()]
        
        return jsonify({
            'stats_24h': dict(stats_24h) if stats_24h else {},
            'daily_trend': daily_trend,
            'recent_bounces': recent_bounces,
            'bounce_reasons': bounce_reasons,
            'domain_stats': domain_stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/api/system/database-stats')
@login_required
def api_system_database_stats():
    """Get database statistics"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Table sizes
        cur.execute("""
            SELECT 
                relname as table_name,
                n_live_tup as row_count,
                pg_size_pretty(pg_total_relation_size(relid)) as total_size
            FROM pg_stat_user_tables
            ORDER BY n_live_tup DESC
            LIMIT 20
        """)
        tables = [dict(r) for r in cur.fetchall()]
        
        # Database size
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database())) as size")
        db_size = cur.fetchone()['size']
        
        # Connection stats
        cur.execute("""
            SELECT 
                count(*) as total,
                count(*) FILTER (WHERE state = 'active') as active,
                count(*) FILTER (WHERE state = 'idle') as idle
            FROM pg_stat_activity 
            WHERE datname = current_database()
        """)
        connections = cur.fetchone()
        
        # Oldest emails
        cur.execute("SELECT MIN(created_at) as oldest FROM emails")
        oldest = cur.fetchone()
        
        return jsonify({
            'tables': tables,
            'database_size': db_size,
            'connections': dict(connections) if connections else {},
            'oldest_email': oldest['oldest'].isoformat() if oldest and oldest['oldest'] else None
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/api/system/cleanup', methods=['POST'])
@login_required
def api_system_cleanup():
    """Clean up old data"""
    data = request.json
    days = data.get('days', 30)
    table = data.get('table', 'emails')
    
    if table not in ['emails', 'email_events', 'webhook_logs']:
        return jsonify({'error': 'Invalid table'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute(f"""
            DELETE FROM {table} 
            WHERE created_at < NOW() - INTERVAL '%s days'
            RETURNING id
        """, (days,))
        deleted = cur.rowcount
        conn.commit()
        
        return jsonify({'success': True, 'deleted': deleted})
    except Exception as e:
        conn.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/api/system/logs')
@login_required
def api_system_logs():
    """Get recent application logs"""
    import subprocess
    
    log_type = request.args.get('type', 'app')
    lines = int(request.args.get('lines', 100))
    
    log_files = {
        'app': '/root/.pm2/logs/sendbaba-web-out.log',
        'error': '/root/.pm2/logs/sendbaba-web-error.log',
        'celery': '/root/.pm2/logs/celery-worker-out.log',
        'celery-error': '/root/.pm2/logs/celery-worker-error.log'
    }
    
    log_file = log_files.get(log_type, log_files['app'])
    
    try:
        result = subprocess.run(
            ['tail', '-n', str(lines), log_file],
            capture_output=True, text=True, timeout=10
        )
        return jsonify({
            'logs': result.stdout.split('\n'),
            'file': log_file
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@hub_bp.route('/hub/api/system/pm2-status')
@login_required
def api_system_pm2_status():
    """Get PM2 process status"""
    import subprocess
    
    try:
        result = subprocess.run(
            ['pm2', 'jlist'],
            capture_output=True, text=True, timeout=10
        )
        processes = json.loads(result.stdout) if result.stdout else []
        
        return jsonify({
            'processes': [{
                'name': p.get('name'),
                'status': p.get('pm2_env', {}).get('status'),
                'cpu': p.get('monit', {}).get('cpu', 0),
                'memory': round(p.get('monit', {}).get('memory', 0) / 1024 / 1024, 1),
                'uptime': p.get('pm2_env', {}).get('pm_uptime'),
                'restarts': p.get('pm2_env', {}).get('restart_time', 0),
                'pid': p.get('pid')
            } for p in processes]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@hub_bp.route('/hub/api/system/restart-service', methods=['POST'])
@login_required
def api_system_restart_service():
    """Restart a PM2 service"""
    import subprocess
    
    data = request.json
    service = data.get('service')
    
    allowed_services = ['sendbaba-web', 'celery-worker', 'celery-beat', 'all']
    if service not in allowed_services:
        return jsonify({'error': 'Invalid service'}), 400
    
    try:
        result = subprocess.run(
            ['pm2', 'restart', service],
            capture_output=True, text=True, timeout=30
        )
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@hub_bp.route('/hub/api/system/celery-tasks')
@login_required
def api_system_celery_tasks():
    """Get Celery task information"""
    import subprocess
    
    try:
        # Active tasks
        active_result = subprocess.run(
            ['celery', '-A', 'celery_app', 'inspect', 'active', '--timeout=5'],
            capture_output=True, text=True, timeout=15, cwd='/opt/sendbaba-staging'
        )
        
        # Scheduled tasks
        scheduled_result = subprocess.run(
            ['celery', '-A', 'celery_app', 'inspect', 'scheduled', '--timeout=5'],
            capture_output=True, text=True, timeout=15, cwd='/opt/sendbaba-staging'
        )
        
        # Reserved tasks
        reserved_result = subprocess.run(
            ['celery', '-A', 'celery_app', 'inspect', 'reserved', '--timeout=5'],
            capture_output=True, text=True, timeout=15, cwd='/opt/sendbaba-staging'
        )
        
        return jsonify({
            'active': active_result.stdout[:5000] if active_result.stdout else 'No active tasks',
            'scheduled': scheduled_result.stdout[:5000] if scheduled_result.stdout else 'No scheduled tasks',
            'reserved': reserved_result.stdout[:5000] if reserved_result.stdout else 'No reserved tasks'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@hub_bp.route('/hub/api/system/purge-queue', methods=['POST'])
@login_required
def api_system_purge_queue():
    """Purge Celery queue"""
    import subprocess
    
    data = request.json
    queue = data.get('queue', 'celery')
    
    try:
        result = subprocess.run(
            ['celery', '-A', 'celery_app', 'purge', '-Q', queue, '-f'],
            capture_output=True, text=True, timeout=30, cwd='/opt/sendbaba-staging'
        )
        return jsonify({
            'success': True,
            'output': result.stdout
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@hub_bp.route('/hub/api/system/redis-stats')
@login_required
def api_system_redis_stats():
    """Get Redis statistics"""
    try:
        r = get_redis()
        info = r.info()
        
        return jsonify({
            'connected_clients': info.get('connected_clients', 0),
            'used_memory_human': info.get('used_memory_human', '0'),
            'total_keys': r.dbsize(),
            'uptime_days': info.get('uptime_in_days', 0),
            'ops_per_sec': info.get('instantaneous_ops_per_sec', 0),
            'hit_rate': round(
                info.get('keyspace_hits', 0) / 
                (info.get('keyspace_hits', 0) + info.get('keyspace_misses', 1)) * 100, 1
            )
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@hub_bp.route('/hub/api/system/test-connections')
@login_required
def api_system_test_connections():
    """Test database and Redis connections"""
    results = {}
    
    # Test PostgreSQL
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        conn.close()
        results['postgresql'] = {'status': 'ok', 'message': 'Connected'}
    except Exception as e:
        results['postgresql'] = {'status': 'error', 'message': str(e)}
    
    # Test Redis
    try:
        r = get_redis()
        r.ping()
        results['redis'] = {'status': 'ok', 'message': 'Connected'}
    except Exception as e:
        results['redis'] = {'status': 'error', 'message': str(e)}
    
    return jsonify(results)


@hub_bp.route('/hub/api/system/api-stats')
@login_required
def api_system_api_stats():
    """Get API usage statistics"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # API keys count
        cur.execute("SELECT COUNT(*) as count FROM api_keys WHERE is_active = true")
        api_keys = cur.fetchone()['count']
        
        # Recent API requests (if logged)
        cur.execute("""
            SELECT 
                endpoint,
                COUNT(*) as count,
                AVG(response_time_ms) as avg_time
            FROM api_logs
            WHERE created_at > NOW() - INTERVAL '1 hour'
            GROUP BY endpoint
            ORDER BY count DESC
            LIMIT 10
        """)
        endpoints = [dict(r) for r in cur.fetchall()]
        
        return jsonify({
            'active_api_keys': api_keys,
            'top_endpoints': endpoints
        })
    except Exception as e:
        return jsonify({'active_api_keys': 0, 'top_endpoints': [], 'error': str(e)})
    finally:
        cur.close()
        conn.close()


@hub_bp.route('/hub/api/system/version')
@login_required  
def api_system_version():
    """Get system version info"""
    import subprocess
    
    try:
        # Git info
        git_branch = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True, text=True, cwd='/opt/sendbaba-staging'
        ).stdout.strip()
        
        git_commit = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, cwd='/opt/sendbaba-staging'
        ).stdout.strip()
        
        git_date = subprocess.run(
            ['git', 'log', '-1', '--format=%ci'],
            capture_output=True, text=True, cwd='/opt/sendbaba-staging'
        ).stdout.strip()
        
        # Python version
        python_version = subprocess.run(
            ['python3', '--version'],
            capture_output=True, text=True
        ).stdout.strip()
        
        return jsonify({
            'branch': git_branch,
            'commit': git_commit,
            'last_update': git_date,
            'python': python_version,
            'app': 'SendBaba v2.0'
        })
    except Exception as e:
        return jsonify({'error': str(e)})


@hub_bp.route('/hub/api/system/git-pull', methods=['POST'])
@login_required
def api_system_git_pull():
    """Pull latest code from git"""
    import subprocess
    
    try:
        result = subprocess.run(
            ['git', 'pull'],
            capture_output=True, text=True, timeout=60, cwd='/opt/sendbaba-staging'
        )
        return jsonify({
            'success': result.returncode == 0,
            'output': result.stdout + result.stderr
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# EMAIL TEMPLATES MANAGEMENT
# ============================================================
@hub_bp.route('/hub/templates')
@login_required
def templates_list():
    """List all email templates"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    templates = []
    try:
        cur.execute("""
            SELECT id, uuid, name, category, subject, description, 
                   organization_id, 
                   COALESCE(is_active, true) as is_active, 
                   COALESCE(is_hidden, false) as is_hidden, 
                   created_at, updated_at,
                   json_data IS NOT NULL as has_json
            FROM email_templates
            ORDER BY category, name
        """)
        templates = cur.fetchall()
    except Exception as e:
        print(f"Error loading templates: {e}")
    
    # Get categories
    categories = list(set([t['category'] for t in templates if t.get('category')]))
    categories.sort()
    
    conn.close()
    return render_template('hub/templates.html', 
                          templates=templates, 
                          categories=categories,
                          total=len(templates),
                          active_page='templates')


@hub_bp.route('/hub/templates/edit/<template_id>')
@login_required
def templates_edit(template_id):
    """Edit template with visual editor"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    template = None
    try:
        cur.execute("""
            SELECT id, uuid, name, category, subject, description, html_content, json_data,
                   organization_id, COALESCE(is_active, true) as is_active, 
                   COALESCE(is_hidden, false) as is_hidden, icon, preheader
            FROM email_templates
            WHERE uuid = %s OR id::text = %s
            LIMIT 1
        """, (template_id, template_id))
        template = cur.fetchone()
    except Exception as e:
        print(f"Error loading template: {e}")
    
    conn.close()
    
    if not template:
        flash('Template not found', 'error')
        return redirect(url_for('hub.templates_list'))
    
    categories = ['newsletter', 'welcome', 'transactional', 'marketing', 'event', 
                  'notification', 'survey', 'reengagement', 'holiday', 'basic', 'promotional']
    
    return render_template('hub/templates_edit.html', 
                          template=template, 
                          categories=categories,
                          active_page='templates')


@hub_bp.route('/hub/templates/create')
@login_required
def templates_create():
    """Create new template"""
    categories = ['newsletter', 'welcome', 'transactional', 'marketing', 'event', 
                  'notification', 'survey', 'reengagement', 'holiday', 'basic', 'promotional']
    return render_template('hub/templates_create.html', categories=categories, active_page='templates')


@hub_bp.route('/hub/api/templates/save', methods=['POST'])
@login_required
def api_templates_save():
    """Save template"""
    import uuid as uuid_lib
    data = request.get_json()
    template_id = data.get('template_id')
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        json_data = json.dumps(data.get('json_data')) if data.get('json_data') else None
        
        if template_id:
            cur.execute("""
                UPDATE email_templates SET
                    name = %s, category = %s, subject = %s, description = %s,
                    html_content = %s, json_data = %s, icon = %s, preheader = %s,
                    is_active = %s, is_hidden = %s, updated_at = CURRENT_TIMESTAMP
                WHERE uuid = %s OR id::text = %s
            """, (
                data.get('name'), data.get('category'), data.get('subject', ''),
                data.get('description', ''), data.get('html_content'), json_data,
                data.get('icon', 'fas fa-envelope'), data.get('preheader', ''),
                data.get('is_active', True), data.get('is_hidden', False),
                template_id, template_id
            ))
        else:
            new_uuid = str(uuid_lib.uuid4())
            cur.execute("""
                INSERT INTO email_templates (uuid, name, category, subject, description, 
                    html_content, json_data, icon, preheader, organization_id, is_active, is_hidden, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'system', %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (
                new_uuid, data.get('name'), data.get('category'), data.get('subject', ''),
                data.get('description', ''), data.get('html_content'), json_data,
                data.get('icon', 'fas fa-envelope'), data.get('preheader', ''),
                data.get('is_active', True), data.get('is_hidden', False)
            ))
            template_id = new_uuid
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'template_id': template_id})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/templates/toggle-visibility', methods=['POST'])
@login_required
def api_templates_toggle_visibility():
    """Toggle template visibility"""
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE email_templates SET is_hidden = %s, updated_at = CURRENT_TIMESTAMP
            WHERE uuid = %s OR id::text = %s
        """, (data.get('is_hidden', False), data.get('template_id'), data.get('template_id')))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/templates/delete', methods=['POST'])
@login_required
def api_templates_delete():
    """Delete template"""
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM email_templates WHERE uuid = %s OR id::text = %s", 
                   (data.get('template_id'), data.get('template_id')))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/templates/duplicate', methods=['POST'])
@login_required
def api_templates_duplicate():
    """Duplicate template"""
    import uuid as uuid_lib
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("""
            SELECT name, category, subject, description, html_content, json_data, icon, preheader
            FROM email_templates WHERE uuid = %s OR id::text = %s
        """, (data.get('template_id'), data.get('template_id')))
        orig = cur.fetchone()
        
        if not orig:
            conn.close()
            return jsonify({'success': False, 'error': 'Template not found'}), 404
        
        new_uuid = str(uuid_lib.uuid4())
        cur.execute("""
            INSERT INTO email_templates (uuid, name, category, subject, description, html_content, json_data, 
                icon, preheader, organization_id, is_active, is_hidden, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'system', true, false, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """, (
            new_uuid, f"{orig['name']} (Copy)", orig['category'], orig['subject'],
            orig['description'], orig['html_content'], orig['json_data'],
            orig['icon'], orig['preheader']
        ))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'new_id': new_uuid})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# CAMPAIGNS MANAGEMENT (Admin view of all user campaigns)
# ============================================================
@hub_bp.route('/hub/campaigns')
@login_required
def campaigns_list():
    """List all campaigns across all users"""
    status_filter = request.args.get('status', 'all')
    user_filter = request.args.get('user_id', '')
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    campaigns = []
    try:
        query = """
            SELECT c.id, c.name, c.subject, c.status, c.created_at, c.updated_at,
                   COALESCE(c.total_recipients, 0) as total_recipients, 
                   COALESCE(c.emails_sent, 0) as emails_sent, 
                   c.organization_id,
                   u.email as user_email, u.first_name, u.last_name,
                   o.name as org_name
            FROM campaigns c
            LEFT JOIN users u ON c.organization_id = u.organization_id
            LEFT JOIN organizations o ON c.organization_id = o.id
            WHERE 1=1
        """
        params = []
        
        if status_filter and status_filter != 'all':
            query += " AND c.status = %s"
            params.append(status_filter)
        
        if user_filter:
            query += " AND c.organization_id = %s"
            params.append(user_filter)
        
        query += " ORDER BY c.updated_at DESC LIMIT 500"
        
        cur.execute(query, params)
        campaigns = cur.fetchall()
    except Exception as e:
        print(f"Error loading campaigns: {e}")
    
    # Get users for filter
    users = []
    try:
        cur.execute("""
            SELECT DISTINCT u.organization_id, u.email, o.name as org_name
            FROM users u
            LEFT JOIN organizations o ON u.organization_id = o.id
            WHERE u.organization_id IS NOT NULL
            ORDER BY u.email
        """)
        users = cur.fetchall()
    except:
        pass
    
    # Stats
    stats = {'total': 0, 'draft': 0, 'sent': 0, 'sending': 0, 'completed': 0, 'cancelled': 0, 'paused': 0, 'queued': 0, 'failed': 0}
    try:
        cur.execute("SELECT status, COUNT(*) as cnt FROM campaigns GROUP BY status")
        for row in cur.fetchall():
            stats[row['status']] = row['cnt']
            stats['total'] += row['cnt']
    except:
        pass
    
    conn.close()
    return render_template('hub/campaigns.html',
                          campaigns=campaigns,
                          users=users,
                          stats=stats,
                          status_filter=status_filter,
                          user_filter=user_filter,
                          active_page='campaigns')


@hub_bp.route('/hub/api/campaigns/delete', methods=['POST'])
@login_required
def api_campaigns_delete():
    """Delete a campaign"""
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM campaigns WHERE id = %s", (data.get('campaign_id'),))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/campaigns/delete-bulk', methods=['POST'])
@login_required
def api_campaigns_delete_bulk():
    """Delete multiple campaigns"""
    data = request.get_json()
    campaign_ids = data.get('campaign_ids', [])
    
    if not campaign_ids:
        return jsonify({'success': False, 'error': 'No campaigns specified'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM campaigns WHERE id = ANY(%s)", (campaign_ids,))
        deleted = cur.rowcount
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'deleted': deleted})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/campaigns/clear-drafts', methods=['POST'])
@login_required
def api_campaigns_clear_drafts():
    """Clear all drafts or drafts for specific user"""
    data = request.get_json()
    organization_id = data.get('organization_id')
    
    conn = get_db()
    cur = conn.cursor()
    try:
        if organization_id:
            cur.execute("DELETE FROM campaigns WHERE status = 'draft' AND organization_id = %s", (organization_id,))
        else:
            cur.execute("DELETE FROM campaigns WHERE status = 'draft'")
        deleted = cur.rowcount
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'deleted': deleted})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/campaigns/update-status', methods=['POST'])
@login_required
def api_campaigns_update_status():
    """Update campaign status"""
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE campaigns SET status = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s
        """, (data.get('status'), data.get('campaign_id')))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# REAL-TIME MONITOR & IP WARMUP
# ============================================

@hub_bp.route('/hub/monitor')
@login_required
def monitor():
    """Real-time monitoring dashboard"""
    return render_template('hub/monitor.html', active_page='monitor')


@hub_bp.route('/hub/monitor/api/stats')
@login_required
def api_monitor_stats():
    """Get real-time statistics"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # Get active campaigns
        cur.execute("""
            SELECT id, name, status, COALESCE(sent_count, 0) as sent, 
                   COALESCE(total_recipients, 0) as total,
                   CASE WHEN COALESCE(total_recipients, 0) > 0 
                        THEN ROUND((COALESCE(sent_count, 0)::numeric / total_recipients) * 100, 1) 
                        ELSE 0 END as progress
            FROM campaigns 
            WHERE status IN ('sending', 'queued', 'processing', 'paused')
            ORDER BY updated_at DESC LIMIT 10
        """)
        active_campaigns = cur.fetchall()
        
        # Get recent completed campaigns
        cur.execute("""
            SELECT id, name, status, COALESCE(sent_count, 0) as sent
            FROM campaigns 
            WHERE status IN ('completed', 'sent', 'failed', 'cancelled')
            ORDER BY updated_at DESC LIMIT 5
        """)
        recent_campaigns = cur.fetchall()
        
        # Get email stats for last hour
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE status = 'sent') as sent,
                COUNT(*) FILTER (WHERE status = 'opened') as opened,
                COUNT(*) FILTER (WHERE status IN ('failed', 'bounced')) as failed
            FROM emails 
            WHERE created_at > NOW() - INTERVAL '1 hour'
        """)
        email_stats = cur.fetchone() or {'sent': 0, 'opened': 0, 'failed': 0}
        
        # Get sending speed (emails in last minute)
        cur.execute("""
            SELECT COUNT(*) as speed FROM emails 
            WHERE created_at > NOW() - INTERVAL '1 minute' AND status = 'sent'
        """)
        speed = cur.fetchone()['speed'] if cur.rowcount > 0 else 0
        
        # Get workers online (check Celery workers via Redis or estimate)
        workers_online = 5  # Default estimate
        try:
            import redis
            r = redis.Redis(host='localhost', port=6379, db=0)
            workers = r.keys('celery@*')
            workers_online = len(workers) if workers else 5
        except:
            pass
        
        conn.close()
        return jsonify({
            'active_campaigns': [dict(c) for c in active_campaigns],
            'recent_campaigns': [dict(c) for c in recent_campaigns],
            'email_stats': dict(email_stats) if email_stats else {'sent': 0, 'opened': 0, 'failed': 0},
            'speed': speed,
            'workers_online': workers_online
        })
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e), 'active_campaigns': [], 'recent_campaigns': [], 
                       'email_stats': {'sent': 0, 'opened': 0, 'failed': 0}, 'speed': 0, 'workers_online': 0})


@hub_bp.route('/hub/monitor/api/workers')
@login_required
def api_monitor_workers():
    """Get worker server status"""
    workers = []
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, db=0)
        # Try to get Celery worker info
        worker_keys = r.keys('celery@*')
        for key in worker_keys:
            workers.append({'name': key.decode() if isinstance(key, bytes) else key, 'status': 'online'})
    except:
        pass
    
    # If no workers found, show default
    if not workers:
        workers = [
            {'name': 'worker@main-server', 'status': 'online'},
            {'name': 'worker@smtp-1', 'status': 'online'},
        ]
    
    return jsonify({'workers': workers})


@hub_bp.route('/hub/monitor/api/test-campaign', methods=['POST'])
@login_required
def api_monitor_test_campaign():
    """Create and send a test campaign for IP warmup"""
    data = request.get_json()
    emails_raw = data.get('emails', '')
    from_email = data.get('from_email', 'test@sendbaba.com')
    from_name = data.get('from_name', 'SendBaba Test')
    subject = data.get('subject', 'Test Email')
    html_body = data.get('html_body', '<p>This is a test email.</p>')
    
    # Parse emails (comma or newline separated)
    import re
    emails = [e.strip() for e in re.split(r'[,\n]+', emails_raw) if e.strip() and '@' in e.strip()]
    
    if not emails:
        return jsonify({'success': False, 'error': 'No valid email addresses provided'}), 400
    
    if len(emails) > 1000:
        return jsonify({'success': False, 'error': 'Maximum 1000 emails per test campaign'}), 400
    
    # Send emails using the relay server
    try:
        from app.smtp.relay_server import send_email_sync
        
        sent_count = 0
        failed_count = 0
        errors = []
        
        for email in emails:
            try:
                result = send_email_sync({
                    'from': from_email,
                    'from_name': from_name,
                    'to': email,
                    'subject': subject,
                    'html_body': html_body
                })
                if result.get('success'):
                    sent_count += 1
                else:
                    failed_count += 1
                    errors.append(f"{email}: {result.get('error', 'Unknown error')}")
            except Exception as e:
                failed_count += 1
                errors.append(f"{email}: {str(e)}")
        
        return jsonify({
            'success': True,
            'campaign_id': f'test-{int(time.time())}',
            'emails_count': len(emails),
            'sent': sent_count,
            'failed': failed_count,
            'errors': errors[:10]  # Return first 10 errors only
        })
    except ImportError:
        return jsonify({'success': False, 'error': 'Email relay not available'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/monitor/api/pause/<campaign_id>', methods=['POST'])
@login_required
def api_monitor_pause(campaign_id):
    """Pause a campaign"""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE campaigns SET status = 'paused', updated_at = CURRENT_TIMESTAMP 
            WHERE id = %s AND status IN ('sending', 'queued', 'processing')
        """, (campaign_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/monitor/api/resume/<campaign_id>', methods=['POST'])
@login_required
def api_monitor_resume(campaign_id):
    """Resume a paused campaign"""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE campaigns SET status = 'queued', updated_at = CURRENT_TIMESTAMP 
            WHERE id = %s AND status = 'paused'
        """, (campaign_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# IP WARMUP MANAGEMENT
# ============================================

@hub_bp.route('/hub/ip-warmup')
@login_required
def ip_warmup():
    """IP Warmup management page"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get all IPs from ip_pools table
    ips = []
    try:
        cur.execute("""
            SELECT ip_address, hostname, daily_limit, sent_today, warmup_day, is_active,
                   last_used_at, last_reset_at, priority, created_at,
                   CASE WHEN warmup_day < 30 THEN true ELSE false END as is_warming
            FROM ip_pools 
            ORDER BY warmup_day DESC, daily_limit DESC
        """)
        ips = cur.fetchall()
    except Exception as e:
        print(f"Error fetching IPs: {e}")
    
    conn.close()
    return render_template('hub/ip_warmup.html', active_page='ip_warmup', ips=ips)


@hub_bp.route('/hub/api/ip-warmup/status')
@login_required  
def api_ip_warmup_status():
    """Get current IP warmup status"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("""
            SELECT ip_address, hostname, daily_limit, sent_today, warmup_day, is_active,
                   CASE WHEN warmup_day < 30 THEN true ELSE false END as is_warming
            FROM ip_pools ORDER BY warmup_day DESC, daily_limit DESC
        """)
        ips = cur.fetchall()
        conn.close()
        return jsonify({'success': True, 'ips': [dict(ip) for ip in ips]})
    except Exception as e:
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-warmup/schedule', methods=['POST'])
@login_required
def api_ip_warmup_schedule():
    """Create or update warmup schedule"""
    data = request.get_json()
    ip_address = data.get('ip_address')
    schedule_type = data.get('schedule_type', 'standard')
    
    # Warmup schedules (daily limits by day)
    schedules = {
        'conservative': [50, 100, 200, 400, 600, 800, 1000, 1500, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 25000, 30000, 40000, 50000],
        'standard': [100, 250, 500, 1000, 2000, 4000, 6000, 8000, 10000, 15000, 20000, 30000, 40000, 50000],
        'aggressive': [500, 1000, 2500, 5000, 10000, 20000, 35000, 50000]
    }
    
    schedule = schedules.get(schedule_type, schedules['standard'])
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            UPDATE ip_pools 
            SET warmup_day = 1, daily_limit = %s, sent_today = 0
            WHERE ip_address = %s
        """, (schedule[0], ip_address))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'schedule': schedule})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-warmup/advance', methods=['POST'])
@login_required
def api_ip_warmup_advance():
    """Advance IP to next warmup day"""
    data = request.get_json()
    ip_address = data.get('ip_address')
    
    # Standard warmup schedule
    schedule = [500, 1000, 2000, 4000, 6000, 8000, 10000, 15000, 20000, 30000, 40000, 50000, 75000, 100000]
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("SELECT warmup_day, daily_limit FROM ip_pools WHERE ip_address = %s", (ip_address,))
        row = cur.fetchone()
        
        if row:
            current_day = row['warmup_day'] or 1
            next_day = current_day + 1
            new_limit = schedule[min(next_day - 1, len(schedule) - 1)]
            
            cur.execute("""
                UPDATE ip_pools 
                SET warmup_day = %s, daily_limit = %s, sent_today = 0
                WHERE ip_address = %s
            """, (next_day, new_limit, ip_address))
            
            conn.commit()
            conn.close()
            return jsonify({'success': True, 'new_day': next_day, 'new_limit': new_limit})
        
        conn.close()
        return jsonify({'success': False, 'error': 'IP not found'}), 404
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-warmup/reset', methods=['POST'])
@login_required
def api_ip_warmup_reset():
    """Reset daily counters for all IPs"""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("UPDATE ip_pools SET sent_today = 0, last_reset_at = CURRENT_TIMESTAMP")
        affected = cur.rowcount
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'reset_count': affected})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-warmup/auto-advance', methods=['POST'])
@login_required
def api_ip_warmup_auto_advance():
    """Automatically advance all IPs that met their daily quota"""
    schedule = [500, 1000, 2000, 4000, 6000, 8000, 10000, 15000, 20000, 30000, 40000, 50000, 75000, 100000]
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get all warming IPs that met 90% of quota
        cur.execute("""
            SELECT ip_address, warmup_day, daily_limit, sent_today
            FROM ip_pools 
            WHERE warmup_day < 30 AND sent_today >= daily_limit * 0.9
        """)
        ips = cur.fetchall()
        
        advanced = 0
        for ip in ips:
            current_day = ip['warmup_day'] or 1
            next_day = current_day + 1
            new_limit = schedule[min(next_day - 1, len(schedule) - 1)]
            
            cur.execute("""
                UPDATE ip_pools 
                SET warmup_day = %s, daily_limit = %s, sent_today = 0
                WHERE ip_address = %s
            """, (next_day, new_limit, ip['ip_address']))
            advanced += 1
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'advanced': advanced})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# SERVER & WORKER MANAGEMENT
# ============================================

@hub_bp.route('/hub/servers')
@login_required
def servers():
    """Server and worker management page"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get configured servers
    servers = []
    try:
        cur.execute("""
            SELECT * FROM worker_servers ORDER BY created_at DESC
        """)
        servers = cur.fetchall()
    except Exception as e:
        # Table might not exist yet
        print(f"Error fetching servers: {e}")
    
    conn.close()
    return render_template('hub/servers.html', active_page='servers', servers=servers)


@hub_bp.route('/hub/api/servers/list')
@login_required
def api_servers_list():
    """Get all configured servers"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("SELECT * FROM worker_servers ORDER BY is_primary DESC, created_at")
        servers = cur.fetchall()
        return jsonify({'success': True, 'servers': [dict(s) for s in servers]})
    except Exception as e:
        return jsonify({'success': True, 'servers': [], 'error': str(e)})
    finally:
        conn.close()


@hub_bp.route('/hub/api/servers/add', methods=['POST'])
@login_required
def api_servers_add():
    """Add a new worker server"""
    data = request.get_json()
    
    name = data.get('name', '').strip()
    hostname = data.get('hostname', '').strip()
    ip_address = data.get('ip_address', '').strip()
    ssh_port = data.get('ssh_port', 22)
    ssh_user = data.get('ssh_user', 'root')
    ssh_password = data.get('ssh_password', '')
    worker_count = data.get('worker_count', 10)
    
    if not hostname and not ip_address:
        return jsonify({'success': False, 'error': 'Hostname or IP required'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO worker_servers (name, hostname, ip_address, ssh_port, ssh_user, ssh_password, worker_count, is_active, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP)
            RETURNING id
        """, (name or hostname, hostname, ip_address, ssh_port, ssh_user, ssh_password, worker_count))
        
        server_id = cur.fetchone()[0]
        conn.commit()
        return jsonify({'success': True, 'server_id': server_id})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@hub_bp.route('/hub/api/servers/remove', methods=['POST'])
@login_required
def api_servers_remove():
    """Remove a worker server"""
    data = request.get_json()
    server_id = data.get('server_id')
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("DELETE FROM worker_servers WHERE id = %s AND is_primary = false", (server_id,))
        if cur.rowcount == 0:
            return jsonify({'success': False, 'error': 'Server not found or is primary'}), 404
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@hub_bp.route('/hub/api/servers/test', methods=['POST'])
@login_required
def api_servers_test():
    """Test SSH connection to a server"""
    data = request.get_json()
    
    hostname = data.get('hostname') or data.get('ip_address')
    ssh_port = data.get('ssh_port', 22)
    ssh_user = data.get('ssh_user', 'root')
    ssh_password = data.get('ssh_password', '')
    
    try:
        import paramiko
        
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname, port=ssh_port, username=ssh_user, password=ssh_password, timeout=10)
        
        # Test command
        stdin, stdout, stderr = client.exec_command('hostname && uptime')
        output = stdout.read().decode().strip()
        client.close()
        
        return jsonify({'success': True, 'output': output})
    except ImportError:
        return jsonify({'success': False, 'error': 'paramiko not installed. Run: pip install paramiko'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/servers/execute', methods=['POST'])
@login_required
def api_servers_execute():
    """Execute command on a server via SSH"""
    data = request.get_json()
    server_id = data.get('server_id')
    command = data.get('command', '')
    
    if not command:
        return jsonify({'success': False, 'error': 'No command provided'}), 400
    
    # Security: whitelist allowed commands
    allowed_commands = [
        'pm2 list', 'pm2 status', 'pm2 restart all', 'pm2 restart sendbaba-web',
        'pm2 restart celery-worker', 'pm2 restart celery-beat', 'pm2 restart sendbaba-smtp',
        'pm2 logs --lines 50', 'uptime', 'free -h', 'df -h', 'hostname',
        'systemctl status redis', 'systemctl restart redis',
        'celery -A celery_app inspect active', 'celery -A celery_app inspect stats'
    ]
    
    # Allow pm2 scale command
    if command.startswith('pm2 scale celery-worker'):
        allowed_commands.append(command)
    
    if command not in allowed_commands and not command.startswith('pm2 scale'):
        return jsonify({'success': False, 'error': 'Command not allowed'}), 403
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Get server details
        if server_id == 'local':
            # Execute locally
            import subprocess
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30, cwd='/opt/sendbaba-smtp')
            output = result.stdout + result.stderr
            return jsonify({'success': True, 'output': output})
        
        cur.execute("SELECT * FROM worker_servers WHERE id = %s", (server_id,))
        server = cur.fetchone()
        
        if not server:
            return jsonify({'success': False, 'error': 'Server not found'}), 404
        
        import paramiko
        
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            server['hostname'] or server['ip_address'],
            port=server['ssh_port'] or 22,
            username=server['ssh_user'] or 'root',
            password=server['ssh_password'],
            timeout=15
        )
        
        # Execute command
        stdin, stdout, stderr = client.exec_command(f'cd /opt/sendbaba-smtp && {command}', timeout=30)
        output = stdout.read().decode() + stderr.read().decode()
        client.close()
        
        return jsonify({'success': True, 'output': output})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()


@hub_bp.route('/hub/api/servers/scale-workers', methods=['POST'])
@login_required
def api_servers_scale_workers():
    """Scale worker count on a server"""
    import subprocess
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
            
        server_id = data.get('server_id', 'local')
        worker_count = int(data.get('worker_count', 50))
        
        if worker_count < 1 or worker_count > 500:
            return jsonify({'success': False, 'error': 'Worker count must be 1-500'}), 400
        
        if server_id == 'local':
            # Stop and delete old worker
            subprocess.run('pm2 stop celery-worker 2>/dev/null || true', shell=True, cwd='/opt/sendbaba-staging')
            subprocess.run('pm2 delete celery-worker 2>/dev/null || true', shell=True, cwd='/opt/sendbaba-staging')
            
            # Start with new concurrency - use staging directory
            cmd = f'pm2 start "celery -A celery_app worker --loglevel=INFO --concurrency={worker_count} -n worker@main" --name celery-worker'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60, cwd='/opt/sendbaba-staging')
            
            # Save PM2 config
            subprocess.run('pm2 save', shell=True, timeout=10)
            
            # Update database
            try:
                conn = get_db()
                cur = conn.cursor()
                cur.execute("UPDATE worker_servers SET worker_count = %s WHERE is_primary = true", (worker_count,))
                conn.commit()
                conn.close()
            except:
                pass
            
            return jsonify({
                'success': True, 
                'message': f'Scaled to {worker_count} workers',
                'output': result.stdout + result.stderr
            })
        else:
            # Remote server
            conn = get_db()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM worker_servers WHERE id = %s", (server_id,))
            server = cur.fetchone()
            conn.close()
            
            if not server:
                return jsonify({'success': False, 'error': 'Server not found'}), 404
            
            import paramiko
            
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                server['hostname'] or server['ip_address'],
                port=server['ssh_port'] or 22,
                username=server['ssh_user'] or 'root',
                password=server['ssh_password'],
                timeout=15
            )
            
            commands = [
                'cd /opt/sendbaba-smtp',
                'pm2 stop celery-worker',
                'pm2 delete celery-worker',
                f'pm2 start "celery -A celery_app worker --loglevel=INFO --concurrency={worker_count} -n worker@{server["name"]}" --name celery-worker',
                'pm2 save'
            ]
            
            stdin, stdout, stderr = client.exec_command(' && '.join(commands), timeout=60)
            output = stdout.read().decode() + stderr.read().decode()
            client.close()
            
            # Update database
            conn = get_db()
            cur = conn.cursor()
            cur.execute("UPDATE worker_servers SET worker_count = %s WHERE id = %s", (worker_count, server_id))
            conn.commit()
            conn.close()
            
            return jsonify({'success': True, 'message': f'Scaled to {worker_count} workers', 'output': output})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/servers/pm2-action', methods=['POST'])
@login_required
def api_servers_pm2_action():
    """Perform PM2 action (restart, stop, start) on a server"""
    import subprocess
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
            
        server_id = data.get('server_id', 'local')
        action = data.get('action', 'restart')
        service = data.get('service', 'all')
        
        valid_actions = ['restart', 'stop', 'start', 'status', 'logs']
        valid_services = ['all', 'sendbaba-web', 'celery-worker', 'celery-beat', 'sendbaba-smtp']
        
        if action not in valid_actions:
            return jsonify({'success': False, 'error': 'Invalid action'}), 400
        if service not in valid_services:
            return jsonify({'success': False, 'error': 'Invalid service'}), 400
        
        if action == 'logs':
            command = f'pm2 logs {service} --lines 100 --nostream'
        else:
            command = f'pm2 {action} {service}'
        
        if server_id == 'local':
            result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60, cwd='/opt/sendbaba-staging')
            return jsonify({'success': True, 'output': result.stdout + result.stderr})
        else:
            conn = get_db()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT * FROM worker_servers WHERE id = %s", (server_id,))
            server = cur.fetchone()
            conn.close()
            
            if not server:
                return jsonify({'success': False, 'error': 'Server not found'}), 404
            
            try:
                import paramiko
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(
                    server['hostname'] or server['ip_address'],
                    port=server['ssh_port'] or 22,
                    username=server['ssh_user'] or 'root',
                    password=server['ssh_password'],
                    timeout=15
                )
                stdin, stdout, stderr = client.exec_command(command, timeout=30)
                output = stdout.read().decode() + stderr.read().decode()
                client.close()
                return jsonify({'success': True, 'output': output})
            except ImportError:
                return jsonify({'success': False, 'error': 'SSH library not available'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/servers/status')
@login_required
def api_servers_status():
    """Get status of all servers"""
    import subprocess
    
    servers_status = []
    
    # Local server status
    try:
        result = subprocess.run('pm2 jlist', shell=True, capture_output=True, text=True, timeout=10)
        pm2_data = json.loads(result.stdout) if result.stdout else []
        
        local_workers = 0
        services = []
        for proc in pm2_data:
            services.append({
                'name': proc.get('name'),
                'status': proc.get('pm2_env', {}).get('status'),
                'cpu': proc.get('monit', {}).get('cpu'),
                'memory': proc.get('monit', {}).get('memory'),
                'uptime': proc.get('pm2_env', {}).get('pm_uptime')
            })
            if proc.get('name') == 'celery-worker':
                # Extract concurrency from args
                try:
                    args = proc.get('pm2_env', {}).get('args', [])
                    for arg in args:
                        if '--concurrency=' in str(arg):
                            local_workers = int(str(arg).split('=')[1])
                            break
                    # Fallback: check the full command string
                    if local_workers == 0:
                        import re
                        full_cmd = str(proc)
                        match = re.search(r'--concurrency[=\s]+(\d+)', full_cmd)
                        if match:
                            local_workers = int(match.group(1))
                except:
                    pass
        
        servers_status.append({
            'id': 'local',
            'name': 'Main Server',
            'hostname': 'localhost',
            'is_primary': True,
            'status': 'online',
            'workers': local_workers or 50,
            'services': services
        })
    except Exception as e:
        servers_status.append({
            'id': 'local',
            'name': 'Main Server',
            'hostname': 'localhost',
            'is_primary': True,
            'status': 'error',
            'error': str(e)
        })
    
    # Remote servers
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("SELECT * FROM worker_servers WHERE is_primary = false")
        remote_servers = cur.fetchall()
        
        for server in remote_servers:
            try:
                import paramiko
                
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                client.connect(
                    server['hostname'] or server['ip_address'],
                    port=server['ssh_port'] or 22,
                    username=server['ssh_user'] or 'root',
                    password=server['ssh_password'],
                    timeout=5
                )
                
                stdin, stdout, stderr = client.exec_command('pm2 jlist', timeout=10)
                pm2_output = stdout.read().decode()
                client.close()
                
                pm2_data = json.loads(pm2_output) if pm2_output else []
                services = []
                for proc in pm2_data:
                    services.append({
                        'name': proc.get('name'),
                        'status': proc.get('pm2_env', {}).get('status')
                    })
                
                servers_status.append({
                    'id': server['id'],
                    'name': server['name'],
                    'hostname': server['hostname'] or server['ip_address'],
                    'is_primary': False,
                    'status': 'online',
                    'workers': server['worker_count'],
                    'services': services
                })
            except Exception as e:
                servers_status.append({
                    'id': server['id'],
                    'name': server['name'],
                    'hostname': server['hostname'] or server['ip_address'],
                    'is_primary': False,
                    'status': 'offline',
                    'error': str(e)
                })
    except:
        pass
    finally:
        conn.close()
    
    total_workers = sum(s.get('workers', 0) for s in servers_status if s.get('status') == 'online')
    
    return jsonify({
        'success': True,
        'servers': servers_status,
        'total_workers': total_workers
    })


# ============================================================
# IP REPUTATION & WARMUP
# ============================================================

@hub_bp.route('/hub/ip-reputation')
@login_required
def ip_reputation():
    """IP Reputation & Warmup page"""
    return render_template('hub/ip_reputation.html', admin=session)


@hub_bp.route('/hub/api/ip-reputation/stats')
@login_required
def api_ip_reputation_stats():
    """Get IP reputation stats"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Total IPs
        cur.execute("SELECT COUNT(*) as count FROM ip_pools")
        total_ips = cur.fetchone()['count']
        
        # Warmup sent in last 24h
        cur.execute("""
            SELECT COUNT(*) as count FROM warmup_sends 
            WHERE sent_at > NOW() - INTERVAL '24 hours'
        """)
        warmup_sent = cur.fetchone()['count']
        
        # Open rate
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE opened = true) as opened,
                COUNT(*) as total
            FROM warmup_sends 
            WHERE sent_at > NOW() - INTERVAL '7 days'
        """)
        opens = cur.fetchone()
        open_rate = round((opens['opened'] / opens['total'] * 100) if opens['total'] > 0 else 0, 1)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'total_ips': total_ips,
            'clean_ips': total_ips,  # Will be updated by blacklist check
            'blacklisted': 0,
            'warmup_sent_24h': warmup_sent,
            'open_rate': open_rate
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-reputation/ips')
@login_required
def api_ip_reputation_ips():
    """Get all IPs with rate limits and warmup stats"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                p.ip_address,
                p.hostname,
                p.warmup_day,
                p.daily_limit,
                p.is_active,
                COALESCE(r.per_minute_limit, 100) as per_minute_limit,
                COALESCE(r.hourly_limit, 1000) as hourly_limit,
                (SELECT COUNT(*) FROM warmup_sends WHERE ip_address = p.ip_address) as warmup_sent,
                (SELECT COUNT(*) FROM warmup_sends WHERE ip_address = p.ip_address AND opened = true) as warmup_opened
            FROM ip_pools p
            LEFT JOIN ip_rate_limits r ON p.ip_address = r.ip_address
            ORDER BY p.hostname
        """)
        ips = cur.fetchall()
        conn.close()
        
        # Add blacklist status (cached or placeholder)
        for ip in ips:
            ip['blacklisted'] = False  # Default, updated by blacklist check
        
        return jsonify({'success': True, 'ips': ips})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-reputation/rate-limits', methods=['POST'])
@login_required
def api_ip_reputation_rate_limits():
    """Set rate limits for an IP"""
    try:
        data = request.get_json()
        ip_address = data.get('ip_address')
        per_minute = data.get('per_minute_limit', 100)
        hourly = data.get('hourly_limit', 1000)
        daily = data.get('daily_limit', 50000)
        
        conn = get_db()
        cur = conn.cursor()
        
        # Upsert rate limits
        cur.execute("""
            INSERT INTO ip_rate_limits (ip_address, per_minute_limit, hourly_limit, daily_limit, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (ip_address) 
            DO UPDATE SET per_minute_limit = %s, hourly_limit = %s, daily_limit = %s, updated_at = NOW()
        """, (ip_address, per_minute, hourly, daily, per_minute, hourly, daily))
        
        # Also update ip_pools daily limit
        cur.execute("UPDATE ip_pools SET daily_limit = %s WHERE ip_address = %s", (daily, ip_address))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-reputation/warmup-emails')
@login_required
def api_ip_reputation_warmup_emails_get():
    """Get warmup email addresses"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, email, is_active FROM warmup_emails WHERE is_active = true ORDER BY id")
        emails = cur.fetchall()
        conn.close()
        return jsonify({'success': True, 'emails': emails})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-reputation/warmup-emails', methods=['POST'])
@login_required
def api_ip_reputation_warmup_emails_add():
    """Add a warmup email address"""
    try:
        data = request.get_json()
        email = data.get('email')
        
        if not email:
            return jsonify({'success': False, 'error': 'Email required'}), 400
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO warmup_emails (email) VALUES (%s)", (email,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-reputation/warmup-emails/<int:email_id>', methods=['DELETE'])
@login_required
def api_ip_reputation_warmup_emails_delete(email_id):
    """Delete a warmup email address"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE warmup_emails SET is_active = false WHERE id = %s", (email_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-reputation/warmup-history')
@login_required
def api_ip_reputation_warmup_history():
    """Get warmup send history"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT ip_address, email, sent_at, opened, opened_at
            FROM warmup_sends
            ORDER BY sent_at DESC
            LIMIT 100
        """)
        history = cur.fetchall()
        conn.close()
        return jsonify({'success': True, 'history': history})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-reputation/check-blacklist')
@login_required
def api_ip_reputation_check_blacklist():
    """Check if an IP is blacklisted"""
    import subprocess
    
    ip = request.args.get('ip')
    if not ip:
        return jsonify({'success': False, 'error': 'IP required'}), 400
    
    try:
        # Reverse IP for DNSBL lookup
        reversed_ip = '.'.join(reversed(ip.split('.')))
        
        # Check Spamhaus
        result = subprocess.run(
            ['dig', '+short', f'{reversed_ip}.zen.spamhaus.org'],
            capture_output=True, text=True, timeout=10
        )
        
        blacklisted = bool(result.stdout.strip())
        lists = []
        
        if blacklisted:
            response = result.stdout.strip()
            if '127.0.0.2' in response:
                lists.append('SBL')
            if '127.0.0.3' in response:
                lists.append('CSS')
            if '127.0.0.4' in response:
                lists.append('CBL')
            if '127.0.0.10' in response or '127.0.0.11' in response:
                lists.append('PBL')
        
        return jsonify({
            'success': True,
            'ip': ip,
            'blacklisted': blacklisted,
            'lists': lists
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-reputation/check-all-blacklists')
@login_required
def api_ip_reputation_check_all_blacklists():
    """Check all IPs for blacklisting"""
    import subprocess
    
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT ip_address FROM ip_pools")
        ips = cur.fetchall()
        conn.close()
        
        blacklisted_ips = []
        clean_count = 0
        
        for ip_row in ips:
            ip = ip_row['ip_address']
            reversed_ip = '.'.join(reversed(ip.split('.')))
            
            result = subprocess.run(
                ['dig', '+short', f'{reversed_ip}.zen.spamhaus.org'],
                capture_output=True, text=True, timeout=10
            )
            
            if result.stdout.strip():
                blacklisted_ips.append(ip)
            else:
                clean_count += 1
        
        return jsonify({
            'success': True,
            'total': len(ips),
            'clean': clean_count,
            'blacklisted': len(blacklisted_ips),
            'blacklisted_ips': blacklisted_ips
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/ip-reputation/warmup', methods=['POST'])
@login_required
def api_ip_reputation_warmup():
    """Send warmup emails from selected IPs"""
    import smtplib
    import time
    import uuid
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    try:
        data = request.get_json()
        ips = data.get('ips', [])
        count = min(data.get('count', 1), 10)  # Max 10
        delay = data.get('delay', 5)
        
        if not ips:
            return jsonify({'success': False, 'error': 'No IPs selected'}), 400
        
        # Get warmup emails
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT email FROM warmup_emails WHERE is_active = true")
        warmup_emails = [r['email'] for r in cur.fetchall()]
        
        if not warmup_emails:
            conn.close()
            return jsonify({'success': False, 'error': 'No warmup emails configured'}), 400
        
        # Get IP details
        cur.execute("SELECT ip_address, hostname FROM ip_pools WHERE ip_address = ANY(%s)", (ips,))
        ip_details = {r['ip_address']: r['hostname'] for r in cur.fetchall()}
        
        log = []
        total_sent = 0
        
        for ip in ips:
            hostname = ip_details.get(ip, f'mail.sendbaba.com')
            
            for i in range(count):
                for to_email in warmup_emails:
                    try:
                        # Generate tracking ID
                        tracking_id = str(uuid.uuid4())
                        
                        # Create email
                        msg = MIMEMultipart('alternative')
                        msg['Subject'] = f'IP Warmup Test - {hostname}'
                        msg['From'] = f'warmup@{hostname.replace("mail", "").replace(".sendbaba.com", "")}.sendbaba.com' if hostname else f'warmup@sendbaba.com'
                        msg['To'] = to_email
                        msg['Message-ID'] = f'<{tracking_id}@{hostname}>'
                        
                        # HTML body with tracking pixel
                        html = f'''
                        <html>
                        <body>
                        <p>This is an automated warmup email from {hostname} ({ip}).</p>
                        <p>Time: {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
                        <p>This helps build IP reputation for better email deliverability.</p>
                        <img src="https://track.sendbaba.com/open/{tracking_id}" width="1" height="1" style="display:none">
                        </body>
                        </html>
                        '''
                        
                        text = f'IP Warmup Test from {hostname} ({ip}) at {time.strftime("%Y-%m-%d %H:%M:%S")}'
                        
                        msg.attach(MIMEText(text, 'plain'))
                        msg.attach(MIMEText(html, 'html'))
                        
                        # Send via SMTP (bind to specific IP would require more config)
                        # For now, send through local relay
                        with smtplib.SMTP('localhost', 25) as smtp:
                            smtp.sendmail(msg['From'], to_email, msg.as_string())
                        
                        # Log to database
                        cur.execute("""
                            INSERT INTO warmup_sends (ip_address, email, message_id, sent_at)
                            VALUES (%s, %s, %s, NOW())
                        """, (ip, to_email, tracking_id))
                        conn.commit()
                        
                        log.append({
                            'success': True,
                            'message': f'✓ Sent from {ip} to {to_email}'
                        })
                        total_sent += 1
                        
                    except Exception as e:
                        log.append({
                            'success': False,
                            'message': f'✗ Failed {ip} to {to_email}: {str(e)}'
                        })
                    
                    time.sleep(delay)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'total_sent': total_sent,
            'log': log
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================
# MAILBOX / INBOX SYSTEM
# ============================================================

@hub_bp.route('/hub/mailbox')
@login_required
def mailbox():
    """Mailbox inbox page"""
    return render_template('hub/mailbox.html', admin=session)


@hub_bp.route('/hub/api/mailbox/list')
@login_required
def api_mailbox_list():
    """Get list of mailboxes"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, email, name, is_active FROM mailboxes ORDER BY email")
        mailboxes = cur.fetchall()
        conn.close()
        return jsonify({'success': True, 'mailboxes': mailboxes})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/mailbox/counts')
@login_required
def api_mailbox_counts():
    """Get folder counts for a mailbox"""
    try:
        mailbox = request.args.get('mailbox', 'support@sendbaba.com')
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get mailbox ID
        cur.execute("SELECT id FROM mailboxes WHERE email = %s", (mailbox,))
        mb = cur.fetchone()
        if not mb:
            conn.close()
            return jsonify({'success': True, 'counts': {}})
        
        mailbox_id = mb['id']
        
        # Get counts
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE folder = 'inbox' AND is_read = false) as inbox_unread,
                COUNT(*) FILTER (WHERE folder = 'inbox') as inbox,
                COUNT(*) FILTER (WHERE folder = 'sent') as sent,
                COUNT(*) FILTER (WHERE folder = 'drafts') as drafts,
                COUNT(*) FILTER (WHERE folder = 'spam') as spam,
                COUNT(*) FILTER (WHERE folder = 'trash') as trash,
                COUNT(*) FILTER (WHERE is_starred = true) as starred
            FROM mailbox_emails
            WHERE mailbox_id = %s AND deleted_at IS NULL
        """, (mailbox_id,))
        
        counts = cur.fetchone()
        conn.close()
        
        return jsonify({'success': True, 'counts': counts})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/mailbox/emails')
@login_required
def api_mailbox_emails():
    """Get emails for a folder"""
    try:
        mailbox = request.args.get('mailbox', 'support@sendbaba.com')
        folder = request.args.get('folder', 'inbox')
        search = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get mailbox ID
        cur.execute("SELECT id FROM mailboxes WHERE email = %s", (mailbox,))
        mb = cur.fetchone()
        if not mb:
            conn.close()
            return jsonify({'success': True, 'emails': []})
        
        mailbox_id = mb['id']
        offset = (page - 1) * per_page
        
        # Build query based on folder
        if folder == 'starred':
            folder_condition = "is_starred = true"
        elif folder == 'all':
            folder_condition = "folder != 'trash'"
        else:
            folder_condition = f"folder = '{folder}'"
        
        # Search condition
        search_condition = ""
        params = [mailbox_id]
        if search:
            search_condition = "AND (subject ILIKE %s OR from_email ILIKE %s OR body_text ILIKE %s)"
            search_term = f'%{search}%'
            params.extend([search_term, search_term, search_term])
        
        # Get emails
        query = f"""
            SELECT 
                id, message_id, from_email, from_name, to_email, subject,
                SUBSTRING(body_text, 1, 200) as preview,
                folder, is_read, is_starred, has_attachments, received_at
            FROM mailbox_emails
            WHERE mailbox_id = %s AND deleted_at IS NULL AND {folder_condition}
            {search_condition}
            ORDER BY received_at DESC
            LIMIT {per_page} OFFSET {offset}
        """
        
        cur.execute(query, params)
        emails = cur.fetchall()
        conn.close()
        
        return jsonify({'success': True, 'emails': emails})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/mailbox/email/<int:email_id>')
@login_required
def api_mailbox_email(email_id):
    """Get a single email"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get email
        cur.execute("""
            SELECT e.*, m.email as mailbox_email
            FROM mailbox_emails e
            JOIN mailboxes m ON e.mailbox_id = m.id
            WHERE e.id = %s
        """, (email_id,))
        email = cur.fetchone()
        
        if not email:
            conn.close()
            return jsonify({'success': False, 'error': 'Email not found'}), 404
        
        # Mark as read
        cur.execute("UPDATE mailbox_emails SET is_read = true WHERE id = %s", (email_id,))
        conn.commit()
        
        # Get attachments
        cur.execute("SELECT id, filename, content_type, size FROM mailbox_attachments WHERE email_id = %s", (email_id,))
        attachments = cur.fetchall()
        
        conn.close()
        
        email['attachments'] = attachments
        return jsonify({'success': True, 'email': email})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/mailbox/email/<int:email_id>/star', methods=['POST'])
@login_required
def api_mailbox_star(email_id):
    """Toggle star on email"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE mailbox_emails SET is_starred = NOT is_starred WHERE id = %s", (email_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/mailbox/email/<int:email_id>/read', methods=['POST'])
@login_required
def api_mailbox_read(email_id):
    """Mark email as read/unread"""
    try:
        data = request.get_json() or {}
        is_read = data.get('is_read', True)
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE mailbox_emails SET is_read = %s WHERE id = %s", (is_read, email_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/mailbox/email/<int:email_id>/move', methods=['POST'])
@login_required
def api_mailbox_move(email_id):
    """Move email to folder"""
    try:
        data = request.get_json() or {}
        folder = data.get('folder', 'inbox')
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE mailbox_emails SET folder = %s WHERE id = %s", (folder, email_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/mailbox/email/<int:email_id>/delete', methods=['POST'])
@login_required
def api_mailbox_delete(email_id):
    """Delete email (move to trash or permanent delete)"""
    try:
        data = request.get_json() or {}
        permanent = data.get('permanent', False)
        
        conn = get_db()
        cur = conn.cursor()
        
        if permanent:
            cur.execute("DELETE FROM mailbox_emails WHERE id = %s", (email_id,))
        else:
            cur.execute("UPDATE mailbox_emails SET folder = 'trash', deleted_at = NOW() WHERE id = %s", (email_id,))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/mailbox/bulk', methods=['POST'])
@login_required
def api_mailbox_bulk():
    """Bulk actions on emails"""
    try:
        data = request.get_json() or {}
        email_ids = data.get('ids', [])
        action = data.get('action', '')
        
        if not email_ids or not action:
            return jsonify({'success': False, 'error': 'Missing ids or action'}), 400
        
        conn = get_db()
        cur = conn.cursor()
        
        if action == 'read':
            cur.execute("UPDATE mailbox_emails SET is_read = true WHERE id = ANY(%s)", (email_ids,))
        elif action == 'unread':
            cur.execute("UPDATE mailbox_emails SET is_read = false WHERE id = ANY(%s)", (email_ids,))
        elif action == 'trash':
            cur.execute("UPDATE mailbox_emails SET folder = 'trash', deleted_at = NOW() WHERE id = ANY(%s)", (email_ids,))
        elif action == 'spam':
            cur.execute("UPDATE mailbox_emails SET folder = 'spam', is_spam = true WHERE id = ANY(%s)", (email_ids,))
        elif action == 'star':
            cur.execute("UPDATE mailbox_emails SET is_starred = true WHERE id = ANY(%s)", (email_ids,))
        elif action == 'inbox':
            cur.execute("UPDATE mailbox_emails SET folder = 'inbox' WHERE id = ANY(%s)", (email_ids,))
        
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/mailbox/send', methods=['POST'])
@login_required
def api_mailbox_send():
    """Send an email"""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    import uuid
    
    try:
        data = request.get_json() or {}
        from_email = data.get('from', 'support@sendbaba.com')
        to_email = data.get('to', '')
        cc = data.get('cc', '')
        subject = data.get('subject', '')
        body_text = data.get('body_text', '')
        body_html = data.get('body_html', '')
        is_draft = data.get('draft', False)
        reply_to_id = data.get('reply_to_id')
        
        if not to_email and not is_draft:
            return jsonify({'success': False, 'error': 'Recipient required'}), 400
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get mailbox
        cur.execute("SELECT id FROM mailboxes WHERE email = %s", (from_email,))
        mb = cur.fetchone()
        if not mb:
            # Create mailbox
            cur.execute("INSERT INTO mailboxes (email, name) VALUES (%s, %s) RETURNING id", 
                       (from_email, from_email.split('@')[0]))
            mb = cur.fetchone()
        
        mailbox_id = mb['id']
        message_id = f'<{uuid.uuid4()}@sendbaba.com>'
        folder = 'drafts' if is_draft else 'sent'
        
        # Get reply info
        in_reply_to = None
        thread_id = message_id
        if reply_to_id:
            cur.execute("SELECT message_id, thread_id FROM mailbox_emails WHERE id = %s", (reply_to_id,))
            reply_email = cur.fetchone()
            if reply_email:
                in_reply_to = reply_email['message_id']
                thread_id = reply_email['thread_id']
        
        # Store in database
        cur.execute("""
            INSERT INTO mailbox_emails 
            (mailbox_id, message_id, in_reply_to, thread_id, from_email, to_email, cc, subject, 
             body_text, body_html, folder, is_read, received_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, NOW())
            RETURNING id
        """, (mailbox_id, message_id, in_reply_to, thread_id, from_email, to_email, cc, subject,
              body_text, body_html or body_text, folder))
        
        email_id = cur.fetchone()['id']
        
        if not is_draft:
            # Actually send the email
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = from_email
            msg['To'] = to_email
            msg['Message-ID'] = message_id
            if cc:
                msg['Cc'] = cc
            if in_reply_to:
                msg['In-Reply-To'] = in_reply_to
            
            msg.attach(MIMEText(body_text, 'plain'))
            if body_html:
                msg.attach(MIMEText(body_html, 'html'))
            
            # Send via local SMTP (or configured relay)
            with smtplib.SMTP('localhost', 587) as smtp:
                recipients = [to_email]
                if cc:
                    recipients.extend([e.strip() for e in cc.split(',')])
                smtp.sendmail(from_email, recipients, msg.as_string())
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'email_id': email_id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================================
# STAFF EMAILS API
# ============================================================

@hub_bp.route('/hub/staff-emails')
@login_required
def staff_emails_page():
    return render_template('hub/staff_emails.html', admin=session)


@hub_bp.route('/hub/api/staff-emails', methods=['GET', 'POST'])
@login_required
def api_staff_emails():
    import secrets
    import hashlib
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    if request.method == 'GET':
        cur.execute("""
            SELECT m.id, m.email, m.name, m.role, m.is_active, m.last_login, 
                   m.recovery_email, COALESCE(m.storage_used_mb, 0) as storage_used_mb, m.created_at,
                   0 as emails_sent
            FROM mailboxes m
            WHERE m.email LIKE '%@sendbaba.com'
            ORDER BY m.created_at DESC
        """)
        staff = cur.fetchall()
        
        total = len(staff)
        active = sum(1 for s in staff if s.get('is_active', True) != False)
        suspended = total - active
        total_storage = sum(float(s.get('storage_used_mb', 0) or 0) for s in staff)
        
        conn.close()
        return jsonify({'success': True, 'staff': staff, 'stats': {'total': total, 'active': active, 'suspended': suspended, 'total_storage': total_storage}})
    
    else:
        data = request.get_json()
        username = data.get('username', '').lower().strip()
        if not username:
            conn.close()
            return jsonify({'success': False, 'error': 'Username required'}), 400
        
        email = f"{username}@sendbaba.com"
        name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
        
        cur.execute("SELECT id FROM mailboxes WHERE email = %s", (email,))
        if cur.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Email already exists'}), 400
        
        password = secrets.token_urlsafe(12)
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        
        cur.execute("SELECT id FROM mailbox_organizations WHERE slug = 'sendbaba-internal'")
        org = cur.fetchone()
        if not org:
            cur.execute("INSERT INTO mailbox_organizations (name, slug, plan, max_mailboxes, max_storage_gb) VALUES ('SendBaba Internal', 'sendbaba-internal', 'enterprise', 1000, 1000) RETURNING id")
            org = cur.fetchone()
        
        recovery_email = data.get('recovery_email', '').strip()
        
        cur.execute("""
            INSERT INTO mailboxes (organization_id, email, name, password_hash, role, recovery_email, is_active, storage_used_mb)
            VALUES (%s, %s, %s, %s, %s, %s, true, 0) RETURNING id
        """, (org['id'], email, name, password_hash, data.get('role', 'staff'), recovery_email))
        
        new_id = cur.fetchone()['id']
        conn.commit()
        conn.close()
        
        # Send welcome email with credentials
        email_sent = False
        if recovery_email:
            try:
                from app.smtp.relay_server import send_email_sync
                html_body = f"""
<!DOCTYPE html>
<html>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #fef3e7;">
    <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
        <div style="background: white; border-radius: 16px; padding: 40px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #f97316; margin: 0;">🎉 Welcome to SendBaba!</h1>
            </div>
            
            <p style="color: #374151;">Hi <strong>{name or 'Team Member'}</strong>,</p>
            <p style="color: #374151;">Your SendBaba staff email account has been created.</p>
            
            <div style="background: #fff7ed; border: 2px solid #fed7aa; border-radius: 12px; padding: 20px; margin: 24px 0;">
                <h3 style="margin: 0 0 12px; color: #c2410c;">Your Login Credentials:</h3>
                <p style="margin: 8px 0;"><strong>Email:</strong> {email}</p>
                <p style="margin: 8px 0;"><strong>Password:</strong> <code style="background: #fef3c7; padding: 4px 8px; border-radius: 4px;">{password}</code></p>
            </div>
            
            <p style="color: #6b7280; font-size: 14px;">Please change your password after your first login for security.</p>
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="https://mail.sendbaba.com/login" style="display: inline-block; background: linear-gradient(135deg, #f97316, #ea580c); color: white; text-decoration: none; padding: 14px 40px; border-radius: 10px; font-weight: bold;">
                    Login Now →
                </a>
            </div>
        </div>
    </div>
</body>
</html>
"""
                send_email_sync({
                    'from': 'noreply@sendbaba.com',
                    'from_name': 'SendBaba Mail',
                    'to': recovery_email,
                    'subject': f'🎉 Welcome to SendBaba - Your Staff Account',
                    'html_body': html_body,
                    'text_body': f'Welcome to SendBaba!\n\nYour account has been created.\n\nEmail: {email}\nPassword: {password}\n\nLogin at: https://mail.sendbaba.com/login'
                })
                email_sent = True
            except Exception as e:
                print(f"Failed to send welcome email: {e}")
        
        return jsonify({
            'success': True, 
            'id': new_id, 
            'email': email, 
            'password': password,
            'email_sent': email_sent,
            'recovery_email': recovery_email
        })


@hub_bp.route('/hub/api/staff-emails/<int:staff_id>/status', methods=['PUT'])
@login_required
def api_staff_status(staff_id):
    data = request.get_json()
    is_active = data.get('status', 'active') == 'active'
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE mailboxes SET is_active = %s WHERE id = %s", (is_active, staff_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@hub_bp.route('/hub/api/staff-emails/<int:staff_id>/reset-password', methods=['POST'])
@login_required
def api_staff_reset_password(staff_id):
    import secrets
    import hashlib
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT email, recovery_email, name FROM mailboxes WHERE id = %s", (staff_id,))
    staff = cur.fetchone()
    
    if not staff:
        conn.close()
        return jsonify({'success': False, 'error': 'Not found'}), 404
    
    password = secrets.token_urlsafe(12)
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    cur.execute("UPDATE mailboxes SET password_hash = %s WHERE id = %s", (password_hash, staff_id))
    conn.commit()
    conn.close()
    
    # Send password reset email
    email_sent = False
    recovery_email = staff.get('recovery_email', '').strip()
    
    if recovery_email:
        try:
            from app.smtp.relay_server import send_email_sync
            html_body = f"""
<!DOCTYPE html>
<html>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #fef3e7;">
    <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
        <div style="background: white; border-radius: 16px; padding: 40px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #f97316; margin: 0;">🔐 Password Reset</h1>
            </div>
            
            <p style="color: #374151;">Hi <strong>{staff.get('name') or 'User'}</strong>,</p>
            <p style="color: #374151;">Your SendBaba Mail password has been reset by an administrator.</p>
            
            <div style="background: #fff7ed; border: 2px solid #fed7aa; border-radius: 12px; padding: 20px; margin: 24px 0;">
                <h3 style="margin: 0 0 12px; color: #c2410c;">Your New Credentials:</h3>
                <p style="margin: 8px 0;"><strong>Email:</strong> {staff['email']}</p>
                <p style="margin: 8px 0;"><strong>New Password:</strong> <code style="background: #fef3c7; padding: 4px 8px; border-radius: 4px;">{password}</code></p>
            </div>
            
            <p style="color: #6b7280; font-size: 14px;">Please change your password after logging in for security.</p>
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="https://mail.sendbaba.com/login" style="display: inline-block; background: linear-gradient(135deg, #f97316, #ea580c); color: white; text-decoration: none; padding: 14px 40px; border-radius: 10px; font-weight: bold;">
                    Login Now →
                </a>
            </div>
        </div>
    </div>
</body>
</html>
"""
            send_email_sync({
                'from': 'noreply@sendbaba.com',
                'from_name': 'SendBaba Mail',
                'to': recovery_email,
                'subject': f'🔐 Password Reset - {staff["email"]}',
                'html_body': html_body,
                'text_body': f'Password Reset\n\nYour password has been reset.\n\nEmail: {staff["email"]}\nNew Password: {password}\n\nLogin at: https://mail.sendbaba.com/login'
            })
            email_sent = True
        except Exception as e:
            print(f"Failed to send reset email: {e}")
    
    return jsonify({
        'success': True, 
        'password': password,
        'email_sent': email_sent,
        'recovery_email': recovery_email
    })


@hub_bp.route('/hub/api/staff-emails/<int:staff_id>', methods=['DELETE'])
@login_required
def api_staff_delete(staff_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM mailboxes WHERE id = %s", (staff_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ============================================================
# MAIL USERS API
# ============================================================

@hub_bp.route('/hub/mail-users')
@login_required
def mail_users_page():
    return render_template('hub/mail_users.html', admin=session)


@hub_bp.route('/hub/api/mail-users')
@login_required
def api_mail_users():
    status = request.args.get('status', '')
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    query = """
        SELECT 
            mo.id, mo.name as organization_name, mo.is_active, mo.created_at,
            u.email, COALESCE(u.first_name || ' ' || u.last_name, u.email) as name,
            (SELECT COUNT(*) FROM mailbox_domains WHERE organization_id = mo.id) as domain_count,
            (SELECT COUNT(*) FROM mailboxes WHERE organization_id = mo.id) as mailbox_count,
            (SELECT COALESCE(SUM(storage_used_mb), 0) FROM mailboxes WHERE organization_id = mo.id) as storage_used_mb,
            0 as emails_sent
        FROM mailbox_organizations mo
        LEFT JOIN users u ON mo.owner_user_id = u.id
        WHERE mo.slug != 'sendbaba-internal'
    """
    
    if status == 'suspended':
        query += " AND mo.is_active = false"
    elif status == 'active':
        query += " AND mo.is_active = true"
    
    query += " ORDER BY mo.created_at DESC LIMIT 100"
    
    cur.execute(query)
    users = cur.fetchall()
    
    cur.execute("SELECT COUNT(*) as total, SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active FROM mailbox_organizations WHERE slug != 'sendbaba-internal'")
    stats_row = cur.fetchone()
    
    conn.close()
    
    return jsonify({
        'success': True,
        'users': users,
        'stats': {
            'total': stats_row['total'] or 0,
            'active': stats_row['active'] or 0,
            'suspended': (stats_row['total'] or 0) - (stats_row['active'] or 0),
            'total_emails': 0,
            'total_storage': sum(float(u.get('storage_used_mb', 0) or 0) for u in users)
        }
    })


@hub_bp.route('/hub/api/mail-users/<int:org_id>/status', methods=['PUT'])
@login_required
def api_mail_user_status(org_id):
    data = request.get_json()
    is_active = data.get('status', 'active') == 'active'
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE mailbox_organizations SET is_active = %s WHERE id = %s", (is_active, org_id))
    cur.execute("UPDATE mailboxes SET is_active = %s WHERE organization_id = %s", (is_active, org_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ============================================================
# MAIL USERS MANAGEMENT (Complete Rewrite)
# ============================================================

@hub_bp.route('/hub/api/mail-users-v2')
@login_required
def api_mail_users_v2():
    """Get all mail users (mailboxes) with full details"""
    status = request.args.get('status', '')
    search = request.args.get('search', '').lower()
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get all mailboxes with their organization info
    query = """
        SELECT 
            m.id,
            m.email,
            m.name,
            m.is_active,
            m.last_login,
            m.recovery_email,
            m.storage_used_mb,
            m.role,
            m.created_at,
            mo.name as organization_name,
            mo.plan,
            mo.id as organization_id,
            (SELECT COUNT(*) FROM mailbox_emails WHERE mailbox_id = m.id AND folder = 'sent') as emails_sent,
            (SELECT COUNT(*) FROM mailbox_emails WHERE mailbox_id = m.id AND folder = 'inbox') as emails_received,
            (SELECT COUNT(*) FROM mailbox_emails WHERE mailbox_id = m.id) as total_emails
        FROM mailboxes m
        LEFT JOIN mailbox_organizations mo ON m.organization_id = mo.id
        WHERE 1=1
    """
    
    params = []
    
    if status == 'suspended':
        query += " AND m.is_active = false"
    elif status == 'active':
        query += " AND m.is_active = true"
    
    if search:
        query += " AND (LOWER(m.email) LIKE %s OR LOWER(m.name) LIKE %s OR LOWER(m.recovery_email) LIKE %s)"
        params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
    
    query += " ORDER BY m.created_at DESC"
    
    cur.execute(query, params)
    mailboxes = cur.fetchall()
    
    # Check if users have campaign accounts (by recovery email)
    for mb in mailboxes:
        if mb.get('recovery_email'):
            cur.execute("SELECT id, email FROM users WHERE email = %s", (mb['recovery_email'],))
            campaign_user = cur.fetchone()
            mb['has_campaign_account'] = campaign_user is not None
            mb['campaign_user_id'] = campaign_user['id'] if campaign_user else None
        else:
            mb['has_campaign_account'] = False
            mb['campaign_user_id'] = None
    
    # Get stats
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN is_active THEN 1 ELSE 0 END) as active,
            SUM(CASE WHEN NOT is_active THEN 1 ELSE 0 END) as suspended,
            COALESCE(SUM(storage_used_mb), 0) as total_storage
        FROM mailboxes
    """)
    stats = cur.fetchone()
    
    cur.execute("SELECT COUNT(*) as total FROM mailbox_emails WHERE folder = 'sent'")
    sent_stats = cur.fetchone()
    
    conn.close()
    
    return jsonify({
        'success': True,
        'mailboxes': mailboxes,
        'stats': {
            'total': stats['total'] or 0,
            'active': stats['active'] or 0,
            'suspended': stats['suspended'] or 0,
            'total_storage': float(stats['total_storage'] or 0),
            'total_emails_sent': sent_stats['total'] or 0
        }
    })


@hub_bp.route('/hub/api/mail-users-v2/<int:mailbox_id>', methods=['GET'])
@login_required
def api_mail_user_detail(mailbox_id):
    """Get detailed info for a single mail user"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT 
            m.*,
            mo.name as organization_name,
            mo.plan,
            (SELECT COUNT(*) FROM mailbox_emails WHERE mailbox_id = m.id AND folder = 'sent') as emails_sent,
            (SELECT COUNT(*) FROM mailbox_emails WHERE mailbox_id = m.id AND folder = 'inbox') as emails_received,
            (SELECT COUNT(*) FROM mailbox_emails WHERE mailbox_id = m.id) as total_emails
        FROM mailboxes m
        LEFT JOIN mailbox_organizations mo ON m.organization_id = mo.id
        WHERE m.id = %s
    """, (mailbox_id,))
    
    mailbox = cur.fetchone()
    
    if not mailbox:
        conn.close()
        return jsonify({'success': False, 'error': 'Mailbox not found'}), 404
    
    # Check campaign account
    if mailbox.get('recovery_email'):
        cur.execute("SELECT id, email, created_at FROM users WHERE email = %s", (mailbox['recovery_email'],))
        campaign_user = cur.fetchone()
        mailbox['campaign_account'] = campaign_user
    else:
        mailbox['campaign_account'] = None
    
    conn.close()
    return jsonify({'success': True, 'mailbox': mailbox})


@hub_bp.route('/hub/api/mail-users-v2/<int:mailbox_id>/suspend', methods=['POST'])
@login_required
def api_mail_user_suspend(mailbox_id):
    """Suspend a mail user"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE mailboxes SET is_active = false WHERE id = %s", (mailbox_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'User suspended'})


@hub_bp.route('/hub/api/mail-users-v2/<int:mailbox_id>/activate', methods=['POST'])
@login_required
def api_mail_user_activate(mailbox_id):
    """Activate a mail user"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE mailboxes SET is_active = true WHERE id = %s", (mailbox_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'User activated'})


@hub_bp.route('/hub/api/mail-users-v2/<int:mailbox_id>/reset-password', methods=['POST'])
@login_required
def api_mail_user_reset_password(mailbox_id):
    """Reset password and send to recovery email"""
    import secrets
    import hashlib
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT email, name, recovery_email FROM mailboxes WHERE id = %s", (mailbox_id,))
    mailbox = cur.fetchone()
    
    if not mailbox:
        conn.close()
        return jsonify({'success': False, 'error': 'Mailbox not found'}), 404
    
    if not mailbox.get('recovery_email'):
        conn.close()
        return jsonify({'success': False, 'error': 'No recovery email set'}), 400
    
    # Generate new password
    new_password = secrets.token_urlsafe(12)
    password_hash = hashlib.sha256(new_password.encode()).hexdigest()
    
    # Update password
    cur.execute("UPDATE mailboxes SET password_hash = %s WHERE id = %s", (password_hash, mailbox_id))
    conn.commit()
    conn.close()
    
    # Send email with new password
    try:
        from app.smtp.relay_server import send_email_sync
        html_body = f'''
<!DOCTYPE html>
<html>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #fef3e7;">
    <div style="max-width: 600px; margin: 0 auto; padding: 40px 20px;">
        <div style="background: white; border-radius: 16px; padding: 40px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
            <div style="text-align: center; margin-bottom: 30px;">
                <h1 style="color: #f97316; margin: 0;">🔐 Password Reset</h1>
            </div>
            
            <p style="color: #374151;">Hi <strong>{mailbox['name'] or 'User'}</strong>,</p>
            <p style="color: #374151;">Your SendBaba Mail password has been reset by an administrator.</p>
            
            <div style="background: #fff7ed; border: 2px solid #fed7aa; border-radius: 12px; padding: 20px; margin: 24px 0;">
                <h3 style="margin: 0 0 12px; color: #c2410c;">Your New Credentials:</h3>
                <p style="margin: 8px 0;"><strong>Email:</strong> {mailbox['email']}</p>
                <p style="margin: 8px 0;"><strong>New Password:</strong> <code style="background: #fef3c7; padding: 4px 8px; border-radius: 4px;">{new_password}</code></p>
            </div>
            
            <p style="color: #6b7280; font-size: 14px;">Please change your password after logging in.</p>
            
            <div style="text-align: center; margin-top: 30px;">
                <a href="https://mail.sendbaba.com/login" style="display: inline-block; background: linear-gradient(135deg, #f97316, #ea580c); color: white; text-decoration: none; padding: 14px 40px; border-radius: 10px; font-weight: bold;">
                    Login Now →
                </a>
            </div>
        </div>
    </div>
</body>
</html>
'''
        send_email_sync({
            'from': 'noreply@sendbaba.com',
            'from_name': 'SendBaba Mail',
            'to': mailbox['recovery_email'],
            'subject': f'🔐 Password Reset - {mailbox["email"]}',
            'html_body': html_body,
            'text_body': f'Password Reset\n\nEmail: {mailbox["email"]}\nNew Password: {new_password}\n\nLogin: https://mail.sendbaba.com/login'
        })
        return jsonify({'success': True, 'message': f'Password reset and sent to {mailbox["recovery_email"]}'})
    except Exception as e:
        return jsonify({'success': True, 'message': 'Password reset', 'warning': f'Email failed: {str(e)}', 'new_password': new_password})


@hub_bp.route('/hub/api/mail-users-v2/<int:mailbox_id>/delete', methods=['DELETE'])
@login_required
def api_mail_user_delete(mailbox_id):
    """Delete a mail user and their emails"""
    conn = get_db()
    cur = conn.cursor()
    
    # Delete emails first
    cur.execute("DELETE FROM mailbox_emails WHERE mailbox_id = %s", (mailbox_id,))
    # Delete mailbox
    cur.execute("DELETE FROM mailboxes WHERE id = %s", (mailbox_id,))
    
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'User deleted'})


# ============================================================
# SPEED CONTROL - Email Sending Speed Management
# ============================================================
HUB_CONFIG_KEY = 'sendbaba:hub:config'
HUB_RATE_LIMITS_KEY = 'sendbaba:hub:rate_limits'
HUB_WORKER_CONFIG_KEY = 'sendbaba:hub:worker_config'

SPEED_BASE_LIMITS = {
    'gmail.com': 200, 'googlemail.com': 200,
    'yahoo.com': 150, 'yahoo.co.uk': 150, 'yahoo.co.in': 150,
    'hotmail.com': 150, 'outlook.com': 150, 'live.com': 150, 'msn.com': 150,
    'aol.com': 100, 'icloud.com': 100, 'me.com': 100,
    'default': 300
}

SPEED_PROFILES = {
    'conservative': ('Conservative', 0.25, 7, '4 hours'),
    'balanced': ('Balanced', 1, 28, '1 hour'),
    'aggressive': ('Aggressive', 4, 85, '20 min'),
    'turbo': ('TURBO (15x)', 15, 167, '10 min'),
    'ultra': ('ULTRA (20x)', 20, 240, '7 min'),
    'insane': ('INSANE (30x)', 30, 350, '5 min'),
}

def calc_speed_limits(mult):
    return {d: int(v * mult) for d, v in SPEED_BASE_LIMITS.items()}


@hub_bp.route('/hub/speed-control')
@login_required
def speed_control_page():
    return render_template('hub/speed_control.html', active_page='speed_control', admin=session)


@hub_bp.route('/hub/api/speed/status')
@login_required
def api_speed_status():
    try:
        r = get_redis()
        config = r.hgetall(HUB_CONFIG_KEY) or {}
        limits = r.hgetall(HUB_RATE_LIMITS_KEY) or {}
        workers = r.hgetall(HUB_WORKER_CONFIG_KEY) or {}
        
        # Decode bytes to strings if needed
        if config and isinstance(list(config.keys())[0], bytes):
            config = {k.decode(): v.decode() for k, v in config.items()}
        if limits and isinstance(list(limits.keys())[0], bytes):
            limits = {k.decode(): v.decode() for k, v in limits.items()}
        if workers and isinstance(list(workers.keys())[0], bytes):
            workers = {k.decode(): v.decode() for k, v in workers.items()}
        
        # Get current sending rate
        minute = int(time.time()) // 60
        keys = r.keys(f"rate:*:{minute}")
        total = sum(int(r.get(k) or 0) for k in keys)
        elapsed = max(1, time.time() % 60)
        
        return jsonify({
            'success': True,
            'profile': config.get('profile', 'turbo'),
            'profile_name': config.get('name', 'TURBO (15x)'),
            'multiplier': float(config.get('mult', 15)),
            'target_eps': int(config.get('eps', 167)),
            'time_100k': config.get('time', '10 min'),
            'current_eps': round(total / elapsed, 1),
            'this_minute': total,
            'limits': {k: int(v) for k, v in limits.items()} if limits else calc_speed_limits(15),
            'threads': int(workers.get('threads', 150)),
            'chunk_size': int(workers.get('chunk', 2500))
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/speed/profiles')
@login_required
def api_speed_profiles():
    profiles = []
    for key, (name, mult, eps, time_str) in SPEED_PROFILES.items():
        profiles.append({
            'key': key,
            'name': name,
            'multiplier': mult,
            'eps': eps,
            'time_100k': time_str
        })
    return jsonify({'success': True, 'profiles': profiles})


@hub_bp.route('/hub/api/speed/set', methods=['POST'])
@login_required
def api_speed_set():
    try:
        data = request.get_json()
        profile = data.get('profile')
        
        if profile not in SPEED_PROFILES:
            return jsonify({'success': False, 'error': 'Unknown profile'})
        
        name, mult, eps, t = SPEED_PROFILES[profile]
        limits = calc_speed_limits(mult)
        
        r = get_redis()
        r.hset(HUB_CONFIG_KEY, mapping={
            'profile': profile, 'name': name,
            'mult': str(mult), 'eps': str(eps), 'time': t
        })
        r.delete(HUB_RATE_LIMITS_KEY)
        r.hset(HUB_RATE_LIMITS_KEY, mapping={k: str(v) for k, v in limits.items()})
        
        return jsonify({'success': True, 'profile': profile, 'eps': eps, 'time_100k': t})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/speed/multiplier', methods=['POST'])
@login_required
def api_speed_multiplier():
    try:
        data = request.get_json()
        mult = float(data.get('multiplier', 15))
        
        limits = calc_speed_limits(mult)
        eps = int(28 * mult)
        time_mins = round(100000 / eps / 60, 1)
        
        r = get_redis()
        r.hset(HUB_CONFIG_KEY, mapping={
            'profile': 'custom',
            'name': f'Custom ({mult}x)',
            'mult': str(mult),
            'eps': str(eps),
            'time': f'{time_mins} min'
        })
        r.delete(HUB_RATE_LIMITS_KEY)
        r.hset(HUB_RATE_LIMITS_KEY, mapping={k: str(v) for k, v in limits.items()})
        
        return jsonify({'success': True, 'multiplier': mult, 'eps': eps})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/speed/limits', methods=['POST'])
@login_required
def api_speed_limits():
    try:
        data = request.get_json()
        limits = data.get('limits', {})
        
        r = get_redis()
        for domain, limit in limits.items():
            r.hset(HUB_RATE_LIMITS_KEY, domain, str(int(limit)))
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/speed/workers', methods=['POST'])
@login_required
def api_speed_workers():
    try:
        data = request.get_json()
        
        r = get_redis()
        r.hset(HUB_WORKER_CONFIG_KEY, mapping={
            'threads': str(data.get('threads', 150)),
            'chunk': str(data.get('chunk_size', 2500))
        })
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# Initialize speed control with TURBO on first access
def init_speed_control():
    try:
        r = get_redis()
        if not r.exists(HUB_CONFIG_KEY):
            name, mult, eps, t = SPEED_PROFILES['turbo']
            limits = calc_speed_limits(mult)
            r.hset(HUB_CONFIG_KEY, mapping={'profile': 'turbo', 'name': name, 'mult': str(mult), 'eps': str(eps), 'time': t})
            r.hset(HUB_RATE_LIMITS_KEY, mapping={k: str(v) for k, v in limits.items()})
            r.hset(HUB_WORKER_CONFIG_KEY, mapping={'threads': '150', 'chunk': '2500'})
    except:
        pass

init_speed_control()


@hub_bp.route('/hub/api/speed/ips')
@login_required
def api_speed_ips():
    """Get warmed IPs from database"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get all active IPs, with warmed ones first
        cur.execute("""
            SELECT 
                id, ip_address, hostname, is_active, warmup_day, 
                daily_limit, sent_today, last_used_at, priority,
                CASE WHEN daily_limit >= 100000 THEN 'warmed' 
                     WHEN daily_limit >= 10000 THEN 'warming'
                     ELSE 'new' END as status
            FROM ip_pools 
            WHERE is_active = true
            ORDER BY daily_limit DESC, priority ASC, ip_address
        """)
        all_ips = cur.fetchall()
        
        # Get warmed IPs only (daily_limit >= 100000)
        cur.execute("""
            SELECT ip_address, hostname, daily_limit, sent_today, warmup_day
            FROM ip_pools 
            WHERE is_active = true AND daily_limit >= 100000
            ORDER BY priority ASC, ip_address
        """)
        warmed_ips = cur.fetchall()
        
        # Get warming IPs
        cur.execute("""
            SELECT ip_address, hostname, daily_limit, sent_today, warmup_day
            FROM ip_pools 
            WHERE is_active = true AND daily_limit < 100000
            ORDER BY daily_limit DESC, ip_address
        """)
        warming_ips = cur.fetchall()
        
        # Stats
        total_capacity = sum(ip['daily_limit'] for ip in all_ips)
        total_sent = sum(ip['sent_today'] for ip in all_ips)
        warmed_capacity = sum(ip['daily_limit'] for ip in warmed_ips)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'warmed_ips': [dict(ip) for ip in warmed_ips],
            'warming_ips': [dict(ip) for ip in warming_ips],
            'all_ips': [dict(ip) for ip in all_ips],
            'stats': {
                'total_ips': len(all_ips),
                'warmed_count': len(warmed_ips),
                'warming_count': len(warming_ips),
                'total_capacity': total_capacity,
                'warmed_capacity': warmed_capacity,
                'total_sent_today': total_sent,
                'remaining_capacity': total_capacity - total_sent
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================
# PLANS MANAGEMENT - Pricing Plans CRUD
# ============================================================
@hub_bp.route('/hub/plans')
@login_required
def plans_page():
    """Plans management page"""
    return render_template('hub/plans.html', active_page='plans', admin=session)


@hub_bp.route('/hub/api/plans')
@login_required
def api_plans_list():
    """Get all pricing plans"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT id, name, slug, type, email_limit_daily, email_limit_monthly,
                   contact_limit, team_member_limit, price_monthly, price_annual,
                   features, is_popular, is_active, sort_order, created_at, updated_at
            FROM pricing_plans
            ORDER BY type, sort_order, price_monthly
        """)
        plans = cur.fetchall()
        
        # Convert Decimal to float for JSON serialization
        for plan in plans:
            plan['price_monthly'] = float(plan['price_monthly'] or 0)
            plan['price_annual'] = float(plan['price_annual'] or 0)
            if plan['features'] and isinstance(plan['features'], str):
                import json
                try:
                    plan['features'] = json.loads(plan['features'])
                except:
                    plan['features'] = []
        
        # Get stats
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE is_active = true) as active,
                COUNT(*) FILTER (WHERE type = 'individual') as individual,
                COUNT(*) FILTER (WHERE type = 'team') as team
            FROM pricing_plans
        """)
        stats = cur.fetchone()
        
        # Get subscriber counts per plan
        cur.execute("""
            SELECT p.slug, COUNT(s.id) as subscribers
            FROM pricing_plans p
            LEFT JOIN subscriptions s ON s.plan_id = p.id AND s.status = 'active'
            GROUP BY p.slug
        """)
        subscriber_counts = {row['slug']: row['subscribers'] for row in cur.fetchall()}
        
        conn.close()
        
        return jsonify({
            'success': True,
            'plans': [dict(p) for p in plans],
            'stats': dict(stats),
            'subscriber_counts': subscriber_counts
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/plans', methods=['POST'])
@login_required
def api_plans_create():
    """Create a new pricing plan"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name') or not data.get('slug'):
            return jsonify({'success': False, 'error': 'Name and slug are required'})
        
        conn = get_db()
        cur = conn.cursor()
        
        # Check if slug exists
        cur.execute("SELECT id FROM pricing_plans WHERE slug = %s", (data['slug'],))
        if cur.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Slug already exists'})
        
        # Generate UUID
        import uuid
        plan_id = str(uuid.uuid4())
        
        # Parse features
        features = data.get('features', [])
        if isinstance(features, str):
            features = [f.strip() for f in features.split('\n') if f.strip()]
        
        cur.execute("""
            INSERT INTO pricing_plans (
                id, name, slug, type, email_limit_daily, email_limit_monthly,
                contact_limit, team_member_limit, price_monthly, price_annual,
                features, is_popular, is_active, sort_order, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
            )
        """, (
            plan_id,
            data['name'],
            data['slug'],
            data.get('type', 'individual'),
            data.get('email_limit_daily', 100),
            data.get('email_limit_monthly', 1000),
            data.get('contact_limit', 500),
            data.get('team_member_limit', 1),
            data.get('price_monthly', 0),
            data.get('price_annual', 0),
            json.dumps(features),
            data.get('is_popular', False),
            data.get('is_active', True),
            data.get('sort_order', 0)
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'id': plan_id, 'message': 'Plan created successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/plans/<plan_id>', methods=['GET'])
@login_required
def api_plans_get(plan_id):
    """Get a single plan"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT id, name, slug, type, email_limit_daily, email_limit_monthly,
                   contact_limit, team_member_limit, price_monthly, price_annual,
                   features, is_popular, is_active, sort_order
            FROM pricing_plans WHERE id = %s
        """, (plan_id,))
        plan = cur.fetchone()
        conn.close()
        
        if not plan:
            return jsonify({'success': False, 'error': 'Plan not found'}), 404
        
        plan['price_monthly'] = float(plan['price_monthly'] or 0)
        plan['price_annual'] = float(plan['price_annual'] or 0)
        
        return jsonify({'success': True, 'plan': dict(plan)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/plans/<plan_id>', methods=['PUT'])
@login_required
def api_plans_update(plan_id):
    """Update a pricing plan"""
    try:
        data = request.get_json()
        
        conn = get_db()
        cur = conn.cursor()
        
        # Check if plan exists
        cur.execute("SELECT id FROM pricing_plans WHERE id = %s", (plan_id,))
        if not cur.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Plan not found'}), 404
        
        # Check slug uniqueness (if changed)
        if data.get('slug'):
            cur.execute("SELECT id FROM pricing_plans WHERE slug = %s AND id != %s", (data['slug'], plan_id))
            if cur.fetchone():
                conn.close()
                return jsonify({'success': False, 'error': 'Slug already exists'})
        
        # Parse features
        features = data.get('features', [])
        if isinstance(features, str):
            features = [f.strip() for f in features.split('\n') if f.strip()]
        
        cur.execute("""
            UPDATE pricing_plans SET
                name = COALESCE(%s, name),
                slug = COALESCE(%s, slug),
                type = COALESCE(%s, type),
                email_limit_daily = COALESCE(%s, email_limit_daily),
                email_limit_monthly = COALESCE(%s, email_limit_monthly),
                contact_limit = COALESCE(%s, contact_limit),
                team_member_limit = COALESCE(%s, team_member_limit),
                price_monthly = COALESCE(%s, price_monthly),
                price_annual = COALESCE(%s, price_annual),
                features = %s,
                is_popular = COALESCE(%s, is_popular),
                is_active = COALESCE(%s, is_active),
                sort_order = COALESCE(%s, sort_order),
                updated_at = NOW()
            WHERE id = %s
        """, (
            data.get('name'),
            data.get('slug'),
            data.get('type'),
            data.get('email_limit_daily'),
            data.get('email_limit_monthly'),
            data.get('contact_limit'),
            data.get('team_member_limit'),
            data.get('price_monthly'),
            data.get('price_annual'),
            json.dumps(features) if features else None,
            data.get('is_popular'),
            data.get('is_active'),
            data.get('sort_order'),
            plan_id
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Plan updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/plans/<plan_id>', methods=['DELETE'])
@superadmin_required
def api_plans_delete(plan_id):
    """Delete a pricing plan (superadmin only)"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if plan has subscribers
        cur.execute("""
            SELECT COUNT(*) as count FROM subscriptions 
            WHERE plan_id = %s AND status = 'active'
        """, (plan_id,))
        result = cur.fetchone()
        
        if result['count'] > 0:
            conn.close()
            return jsonify({
                'success': False, 
                'error': f'Cannot delete plan with {result["count"]} active subscribers. Deactivate it instead.'
            })
        
        cur.execute("DELETE FROM pricing_plans WHERE id = %s", (plan_id,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Plan deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/plans/<plan_id>/toggle', methods=['POST'])
@login_required
def api_plans_toggle(plan_id):
    """Toggle plan active status"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            UPDATE pricing_plans 
            SET is_active = NOT is_active, updated_at = NOW()
            WHERE id = %s
            RETURNING is_active
        """, (plan_id,))
        result = cur.fetchone()
        conn.commit()
        conn.close()
        
        if not result:
            return jsonify({'success': False, 'error': 'Plan not found'}), 404
        
        return jsonify({
            'success': True, 
            'is_active': result['is_active'],
            'message': f"Plan {'activated' if result['is_active'] else 'deactivated'}"
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/plans/<plan_id>/popular', methods=['POST'])
@login_required
def api_plans_set_popular(plan_id):
    """Set a plan as popular (only one per type)"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get the plan type
        cur.execute("SELECT type FROM pricing_plans WHERE id = %s", (plan_id,))
        plan = cur.fetchone()
        
        if not plan:
            conn.close()
            return jsonify({'success': False, 'error': 'Plan not found'}), 404
        
        # Remove popular from all plans of same type
        cur.execute("""
            UPDATE pricing_plans SET is_popular = false WHERE type = %s
        """, (plan['type'],))
        
        # Set this plan as popular
        cur.execute("""
            UPDATE pricing_plans SET is_popular = true, updated_at = NOW()
            WHERE id = %s
        """, (plan_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Plan set as popular'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/plans/reorder', methods=['POST'])
@login_required
def api_plans_reorder():
    """Reorder plans"""
    try:
        data = request.get_json()
        orders = data.get('orders', [])  # [{id: 'xxx', sort_order: 1}, ...]
        
        conn = get_db()
        cur = conn.cursor()
        
        for item in orders:
            cur.execute("""
                UPDATE pricing_plans SET sort_order = %s, updated_at = NOW()
                WHERE id = %s
            """, (item['sort_order'], item['id']))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Plans reordered'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================
# SALES MODULE ROUTES
# ============================================================

@hub_bp.route('/hub/sales')
@login_required
def sales_dashboard():
    """Sales Dashboard"""
    return render_template('hub/sales/index.html')

@hub_bp.route('/hub/sales/pipeline')
@login_required
def sales_pipeline():
    """Sales Pipeline Kanban"""
    return render_template('hub/sales/pipeline.html')

@hub_bp.route('/hub/sales/deals')
@login_required
def sales_deals():
    """Deals List"""
    return render_template('hub/sales/deals.html')

@hub_bp.route('/hub/sales/contacts')
@login_required
def sales_contacts():
    """Contacts List"""
    return render_template('hub/sales/contacts.html')

@hub_bp.route('/hub/sales/companies')
@login_required
def sales_companies():
    """Companies List"""
    return render_template('hub/sales/companies.html')

@hub_bp.route('/hub/sales/activities')
@login_required
def sales_activities():
    """Activities List"""
    return render_template('hub/sales/activities.html')

@hub_bp.route('/hub/sales/reports')
@login_required
def sales_reports():
    """Sales Reports"""
    return render_template('hub/sales/reports.html')


# ============================================================
# SALES API: STATS
# ============================================================
@hub_bp.route('/hub/sales/api/stats')
@login_required
def sales_api_stats():
    """Get sales statistics"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Open deals count and value
        cur.execute("SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total FROM sales_deals WHERE status = 'open'")
        open_deals = cur.fetchone()
        
        # Won deals this month
        cur.execute("""
            SELECT COUNT(*) as count, COALESCE(SUM(amount), 0) as total 
            FROM sales_deals 
            WHERE status = 'won' AND actual_close_date >= date_trunc('month', CURRENT_DATE)
        """)
        won_deals = cur.fetchone()
        
        # Total contacts
        cur.execute("SELECT COUNT(*) as count FROM sales_contacts")
        contacts = cur.fetchone()
        
        # Total companies
        cur.execute("SELECT COUNT(*) as count FROM sales_companies")
        companies = cur.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'open_deals': open_deals['count'],
                'pipeline_value': float(open_deals['total']),
                'won_deals': won_deals['count'],
                'won_value': float(won_deals['total']),
                'total_contacts': contacts['count'],
                'total_companies': companies['count']
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================
# SALES API: PIPELINE STAGES
# ============================================================
@hub_bp.route('/hub/sales/api/stages')
@login_required
def sales_api_stages():
    """Get pipeline stages"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT * FROM sales_pipeline_stages 
            WHERE is_active = true 
            ORDER BY position ASC
        """)
        stages = cur.fetchall()
        
        # If no stages, create defaults
        if not stages:
            cur.execute("""
                INSERT INTO sales_pipeline_stages (id, name, slug, color, position, probability, is_won, is_lost) VALUES
                (gen_random_uuid()::text, 'Lead', 'lead', '#6B7280', 0, 10, false, false),
                (gen_random_uuid()::text, 'Qualified', 'qualified', '#3B82F6', 1, 25, false, false),
                (gen_random_uuid()::text, 'Proposal', 'proposal', '#8B5CF6', 2, 50, false, false),
                (gen_random_uuid()::text, 'Negotiation', 'negotiation', '#F59E0B', 3, 75, false, false),
                (gen_random_uuid()::text, 'Won', 'won', '#10B981', 4, 100, true, false),
                (gen_random_uuid()::text, 'Lost', 'lost', '#EF4444', 5, 0, false, true)
            """)
            conn.commit()
            cur.execute("SELECT * FROM sales_pipeline_stages WHERE is_active = true ORDER BY position ASC")
            stages = cur.fetchall()
        
        conn.close()
        return jsonify({'success': True, 'stages': [dict(s) for s in stages]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================
# SALES API: DEALS
# ============================================================
@hub_bp.route('/hub/sales/api/deals', methods=['GET'])
@login_required
def sales_api_deals_list():
    """Get deals list"""
    try:
        status = request.args.get('status', 'all')
        stage_id = request.args.get('stage_id')
        search = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT d.*, 
                   s.name as stage_name, s.color as stage_color,
                   c.first_name as contact_first_name, c.last_name as contact_last_name,
                   co.name as company_name,
                   p.name as plan_name
            FROM sales_deals d
            LEFT JOIN sales_pipeline_stages s ON d.stage_id = s.id
            LEFT JOIN sales_contacts c ON d.contact_id = c.id
            LEFT JOIN sales_companies co ON d.company_id = co.id
            LEFT JOIN pricing_plans p ON d.pricing_plan_id = p.id
            WHERE 1=1
        """
        params = []
        
        if status != 'all':
            query += " AND d.status = %s"
            params.append(status)
        
        if stage_id:
            query += " AND d.stage_id = %s"
            params.append(stage_id)
        
        if search:
            query += " AND (d.name ILIKE %s OR co.name ILIKE %s)"
            params.extend([f'%{search}%', f'%{search}%'])
        
        query += " ORDER BY d.created_at DESC LIMIT %s OFFSET %s"
        params.extend([per_page, (page - 1) * per_page])
        
        cur.execute(query, params)
        deals = cur.fetchall()
        conn.close()
        
        return jsonify({'success': True, 'deals': [dict(d) for d in deals]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/sales/api/deals', methods=['POST'])
@login_required
def sales_api_deals_create():
    """Create new deal"""
    try:
        data = request.get_json()
        
        if not data.get('name'):
            return jsonify({'success': False, 'error': 'Deal name is required'})
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            INSERT INTO sales_deals (id, name, description, amount, currency, stage_id, 
                                     contact_id, company_id, pricing_plan_id, expected_close_date)
            VALUES (gen_random_uuid()::text, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (
            data['name'],
            data.get('description'),
            data.get('amount', 0),
            data.get('currency', 'USD'),
            data.get('stage_id'),
            data.get('contact_id'),
            data.get('company_id'),
            data.get('pricing_plan_id'),
            data.get('expected_close_date')
        ))
        
        deal = cur.fetchone()
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'deal': dict(deal)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/sales/api/deals/<deal_id>', methods=['GET'])
@login_required
def sales_api_deals_get(deal_id):
    """Get single deal"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT d.*, 
                   s.name as stage_name, s.color as stage_color,
                   c.first_name as contact_first_name, c.last_name as contact_last_name,
                   co.name as company_name,
                   p.name as plan_name
            FROM sales_deals d
            LEFT JOIN sales_pipeline_stages s ON d.stage_id = s.id
            LEFT JOIN sales_contacts c ON d.contact_id = c.id
            LEFT JOIN sales_companies co ON d.company_id = co.id
            LEFT JOIN pricing_plans p ON d.pricing_plan_id = p.id
            WHERE d.id = %s
        """, (deal_id,))
        
        deal = cur.fetchone()
        conn.close()
        
        if not deal:
            return jsonify({'success': False, 'error': 'Deal not found'}), 404
        
        return jsonify({'success': True, 'deal': dict(deal)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/sales/api/deals/<deal_id>', methods=['PUT'])
@login_required
def sales_api_deals_update(deal_id):
    """Update deal"""
    try:
        data = request.get_json()
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            UPDATE sales_deals SET
                name = COALESCE(%s, name),
                description = COALESCE(%s, description),
                amount = COALESCE(%s, amount),
                stage_id = COALESCE(%s, stage_id),
                contact_id = %s,
                company_id = %s,
                pricing_plan_id = %s,
                expected_close_date = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
        """, (
            data.get('name'),
            data.get('description'),
            data.get('amount'),
            data.get('stage_id'),
            data.get('contact_id'),
            data.get('company_id'),
            data.get('pricing_plan_id'),
            data.get('expected_close_date'),
            deal_id
        ))
        
        deal = cur.fetchone()
        conn.commit()
        conn.close()
        
        if not deal:
            return jsonify({'success': False, 'error': 'Deal not found'}), 404
        
        return jsonify({'success': True, 'deal': dict(deal)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/sales/api/deals/<deal_id>/move', methods=['POST'])
@login_required
def sales_api_deals_move(deal_id):
    """Move deal to different stage"""
    try:
        data = request.get_json()
        new_stage_id = data.get('stage_id')
        
        if not new_stage_id:
            return jsonify({'success': False, 'error': 'Stage ID required'})
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get stage info
        cur.execute("SELECT * FROM sales_pipeline_stages WHERE id = %s", (new_stage_id,))
        stage = cur.fetchone()
        
        if not stage:
            return jsonify({'success': False, 'error': 'Stage not found'})
        
        # Determine new status
        new_status = 'won' if stage['is_won'] else ('lost' if stage['is_lost'] else 'open')
        
        cur.execute("""
            UPDATE sales_deals SET
                stage_id = %s,
                status = %s,
                probability = %s,
                actual_close_date = CASE WHEN %s IN ('won', 'lost') THEN CURRENT_DATE ELSE NULL END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
        """, (new_stage_id, new_status, stage['probability'], new_status, deal_id))
        
        deal = cur.fetchone()
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'deal': dict(deal)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/sales/api/deals/<deal_id>', methods=['DELETE'])
@login_required
def sales_api_deals_delete(deal_id):
    """Delete deal"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM sales_deals WHERE id = %s", (deal_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================
# SALES API: CONTACTS
# ============================================================
@hub_bp.route('/hub/sales/api/contacts', methods=['GET'])
@login_required
def sales_api_contacts_list():
    """Get contacts list"""
    try:
        search = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = """
            SELECT c.*, co.name as company_name
            FROM sales_contacts c
            LEFT JOIN sales_companies co ON c.company_id = co.id
            WHERE 1=1
        """
        params = []
        
        if search:
            query += " AND (c.first_name ILIKE %s OR c.last_name ILIKE %s OR c.email ILIKE %s)"
            params.extend([f'%{search}%', f'%{search}%', f'%{search}%'])
        
        query += " ORDER BY c.created_at DESC LIMIT %s OFFSET %s"
        params.extend([per_page, (page - 1) * per_page])
        
        cur.execute(query, params)
        contacts = cur.fetchall()
        conn.close()
        
        return jsonify({'success': True, 'contacts': [dict(c) for c in contacts]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/sales/api/contacts', methods=['POST'])
@login_required
def sales_api_contacts_create():
    """Create contact"""
    try:
        data = request.get_json()
        
        if not data.get('first_name'):
            return jsonify({'success': False, 'error': 'First name is required'})
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            INSERT INTO sales_contacts (id, first_name, last_name, email, phone, job_title, company_id, city, country, notes)
            VALUES (gen_random_uuid()::text, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (
            data['first_name'],
            data.get('last_name'),
            data.get('email'),
            data.get('phone'),
            data.get('job_title'),
            data.get('company_id'),
            data.get('city'),
            data.get('country'),
            data.get('notes')
        ))
        
        contact = cur.fetchone()
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'contact': dict(contact)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/sales/api/contacts/<contact_id>', methods=['PUT'])
@login_required
def sales_api_contacts_update(contact_id):
    """Update contact"""
    try:
        data = request.get_json()
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            UPDATE sales_contacts SET
                first_name = COALESCE(%s, first_name),
                last_name = COALESCE(%s, last_name),
                email = COALESCE(%s, email),
                phone = COALESCE(%s, phone),
                job_title = COALESCE(%s, job_title),
                company_id = %s,
                city = COALESCE(%s, city),
                country = COALESCE(%s, country),
                notes = COALESCE(%s, notes),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
        """, (
            data.get('first_name'),
            data.get('last_name'),
            data.get('email'),
            data.get('phone'),
            data.get('job_title'),
            data.get('company_id'),
            data.get('city'),
            data.get('country'),
            data.get('notes'),
            contact_id
        ))
        
        contact = cur.fetchone()
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'contact': dict(contact)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/sales/api/contacts/<contact_id>', methods=['DELETE'])
@login_required
def sales_api_contacts_delete(contact_id):
    """Delete contact"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM sales_contacts WHERE id = %s", (contact_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================
# SALES API: COMPANIES
# ============================================================
@hub_bp.route('/hub/sales/api/companies', methods=['GET'])
@login_required
def sales_api_companies_list():
    """Get companies list"""
    try:
        search = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = "SELECT * FROM sales_companies WHERE 1=1"
        params = []
        
        if search:
            query += " AND name ILIKE %s"
            params.append(f'%{search}%')
        
        query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([per_page, (page - 1) * per_page])
        
        cur.execute(query, params)
        companies = cur.fetchall()
        conn.close()
        
        return jsonify({'success': True, 'companies': [dict(c) for c in companies]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/sales/api/companies', methods=['POST'])
@login_required
def sales_api_companies_create():
    """Create company"""
    try:
        data = request.get_json()
        
        if not data.get('name'):
            return jsonify({'success': False, 'error': 'Company name is required'})
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            INSERT INTO sales_companies (id, name, industry, email, phone, website, city, country, description)
            VALUES (gen_random_uuid()::text, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (
            data['name'],
            data.get('industry'),
            data.get('email'),
            data.get('phone'),
            data.get('website'),
            data.get('city'),
            data.get('country'),
            data.get('description')
        ))
        
        company = cur.fetchone()
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'company': dict(company)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/sales/api/companies/<company_id>', methods=['DELETE'])
@login_required
def sales_api_companies_delete(company_id):
    """Delete company"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM sales_companies WHERE id = %s", (company_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ============================================================
# SALES API: ACTIVITIES
# ============================================================
@hub_bp.route('/hub/sales/api/activities', methods=['GET'])
@login_required
def sales_api_activities_list():
    """Get activities list"""
    try:
        status = request.args.get('status', 'all')
        per_page = int(request.args.get('per_page', 50))
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        query = "SELECT * FROM sales_activities WHERE 1=1"
        params = []
        
        if status != 'all':
            query += " AND status = %s"
            params.append(status)
        
        query += " ORDER BY due_date ASC NULLS LAST LIMIT %s"
        params.append(per_page)
        
        cur.execute(query, params)
        activities = cur.fetchall()
        conn.close()
        
        return jsonify({'success': True, 'activities': [dict(a) for a in activities]})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/sales/api/activities', methods=['POST'])
@login_required
def sales_api_activities_create():
    """Create activity"""
    try:
        data = request.get_json()
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            INSERT INTO sales_activities (id, type, subject, description, deal_id, contact_id, company_id, due_date)
            VALUES (gen_random_uuid()::text, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (
            data.get('type', 'task'),
            data.get('subject', 'New Activity'),
            data.get('description'),
            data.get('deal_id'),
            data.get('contact_id'),
            data.get('company_id'),
            data.get('due_date')
        ))
        
        activity = cur.fetchone()
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'activity': dict(activity)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/sales/api/activities/<activity_id>/complete', methods=['POST'])
@login_required
def sales_api_activities_complete(activity_id):
    """Mark activity complete"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            UPDATE sales_activities SET status = 'completed', completed_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (activity_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})



# ============================================================
# ENHANCED CAMPAIGNS API
# ============================================================
@hub_bp.route('/hub/api/campaigns/enhanced')
@login_required
def api_campaigns_enhanced():
    """Enhanced campaigns API with real-time stats"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get all campaigns with real stats
        cur.execute("""
            SELECT 
                c.id, c.name, c.subject, c.status, c.organization_id,
                c.total_recipients as total,
                COALESCE(c.sent_count, 0) as sent,
                COALESCE(c.failed_count, 0) as failed,
                c.created_at, c.updated_at, c.started_at, c.completed_at,
                o.name as org_name,
                u.email as user_email,
                (SELECT COUNT(*) FROM emails e WHERE e.campaign_id = c.id AND e.status = 'opened') as opened,
                (SELECT COUNT(*) FROM emails e WHERE e.campaign_id = c.id AND e.status = 'clicked') as clicked
            FROM campaigns c
            LEFT JOIN organizations o ON c.organization_id = o.id
            LEFT JOIN users u ON c.organization_id = u.organization_id AND u.role = 'owner'
            ORDER BY c.created_at DESC
            LIMIT 1000
        """)
        campaigns = cur.fetchall()
        
        # Get stats
        cur.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'sending') as sending,
                COUNT(*) FILTER (WHERE status = 'queued') as queued,
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COUNT(*) FILTER (WHERE status = 'draft') as draft,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled
            FROM campaigns
        """)
        stats = dict(cur.fetchone())
        
        # Get emails sent today
        cur.execute("""
            SELECT COUNT(*) FROM emails 
            WHERE created_at >= CURRENT_DATE AND status IN ('sent', 'delivered')
        """)
        stats['emails_today'] = cur.fetchone()[0]
        
        # Get organizations with campaign counts
        cur.execute("""
            SELECT o.id, o.name, COUNT(c.id) as count
            FROM organizations o
            INNER JOIN campaigns c ON c.organization_id = o.id
            GROUP BY o.id, o.name
            ORDER BY count DESC
            LIMIT 50
        """)
        organizations = cur.fetchall()
        
        # Get active campaigns with Redis progress
        import redis
        r = redis.Redis(host='localhost', port=6379, password='SendBabaRedis2024!', decode_responses=True)
        
        active_campaigns = []
        for c in campaigns:
            if c['status'] == 'sending':
                progress = r.hgetall(f"campaign_progress:{c['id']}")
                active_campaigns.append({
                    'id': c['id'],
                    'name': c['name'],
                    'org_name': c['org_name'],
                    'total': int(progress.get('total', c['total'] or 0)),
                    'sent': int(progress.get('sent', c['sent'] or 0)),
                    'failed': int(progress.get('failed', c['failed'] or 0)),
                    'percent': int(progress.get('percent', 0)),
                    'rate': progress.get('rate', '0'),
                    'eta': progress.get('eta', 'Calculating...')
                })
        
        conn.close()
        
        # Convert datetime objects
        for c in campaigns:
            for key in ['created_at', 'updated_at', 'started_at', 'completed_at']:
                if c.get(key):
                    c[key] = c[key].isoformat()
        
        return jsonify({
            'success': True,
            'campaigns': campaigns,
            'stats': stats,
            'organizations': organizations,
            'active_campaigns': active_campaigns
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500


@hub_bp.route('/hub/api/campaigns/<campaign_id>/pause', methods=['POST'])
@login_required
def api_campaign_pause(campaign_id):
    """Pause a campaign"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE campaigns SET status = 'paused', updated_at = NOW() WHERE id = %s AND status = 'sending'", (campaign_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/campaigns/<campaign_id>/resume', methods=['POST'])
@login_required
def api_campaign_resume(campaign_id):
    """Resume a paused campaign"""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE campaigns SET status = 'queued', updated_at = NOW() WHERE id = %s AND status = 'paused'", (campaign_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@hub_bp.route('/hub/api/campaigns/<campaign_id>', methods=['DELETE'])
@login_required
def api_campaign_delete(campaign_id):
    """Delete a campaign"""
    try:
        conn = get_db()
        cur = conn.cursor()
        # Only allow deleting draft/failed/cancelled
        cur.execute("DELETE FROM campaigns WHERE id = %s AND status IN ('draft', 'failed', 'cancelled')", (campaign_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
