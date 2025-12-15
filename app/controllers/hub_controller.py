"""
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
            if request.is_json:
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
@hub_bp.route('/hub/servers')
@login_required
def servers_page():
    return render_template('hub/servers.html', admin=session)


@hub_bp.route('/hub/api/servers')
@login_required
def api_servers():
    try:
        # Worker IPs
        workers = [
            {"ip": "161.97.170.33", "hostname": "mail10.sendbaba.com", "type": "worker"},
            {"ip": "75.119.151.72", "hostname": "mail9.sendbaba.com", "type": "worker"},
            {"ip": "75.119.153.106", "hostname": "mail8.sendbaba.com", "type": "worker"},
            {"ip": "173.212.214.23", "hostname": "mail5.sendbaba.com", "type": "worker"},
            {"ip": "173.212.213.239", "hostname": "mail6.sendbaba.com", "type": "worker"},
            {"ip": "173.212.213.184", "hostname": "mail7.sendbaba.com", "type": "worker"},
            {"ip": "185.215.180.157", "hostname": "mail11.sendbaba.com", "type": "worker"},
            {"ip": "185.215.164.39", "hostname": "mail12.sendbaba.com", "type": "worker"},
            {"ip": "176.126.87.21", "hostname": "mail13.sendbaba.com", "type": "worker"},
            {"ip": "185.215.167.20", "hostname": "mail14.sendbaba.com", "type": "worker"},
            {"ip": "185.208.206.35", "hostname": "mail15.sendbaba.com", "type": "worker"},
        ]
        
        # Get Celery worker status
        try:
            import sys
            sys.path.insert(0, '/opt/sendbaba-staging')
            from celery_worker_config import celery_app
            
            inspector = celery_app.control.inspect()
            ping_results = inspector.ping() or {}
            stats = inspector.stats() or {}
            
            for worker in workers:
                worker_name = f"worker@{worker['ip']}"
                worker['status'] = 'online' if worker_name in ping_results else 'offline'
                worker_stats = stats.get(worker_name, {})
                worker['concurrency'] = worker_stats.get('pool', {}).get('max-concurrency', 0)
                worker['processed'] = worker_stats.get('total', {})
        except Exception as e:
            for worker in workers:
                worker['status'] = 'unknown'
                worker['concurrency'] = 0
                worker['error'] = str(e)
        
        # Get IP pool data
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT ip_address, hostname, warmup_day, daily_limit, sent_today, is_active,
                ROUND((sent_today::numeric / NULLIF(daily_limit, 0)) * 100, 1) as usage_pct
            FROM ip_pools ORDER BY ip_address
        """)
        ip_pools = {row['ip_address']: row for row in cur.fetchall()}
        conn.close()
        
        # Merge IP pool data with workers
        for worker in workers:
            ip_data = ip_pools.get(worker['ip'], {})
            worker['warmup_day'] = ip_data.get('warmup_day', 0)
            worker['daily_limit'] = ip_data.get('daily_limit', 0)
            worker['sent_today'] = ip_data.get('sent_today', 0)
            worker['usage_pct'] = ip_data.get('usage_pct', 0)
            worker['is_warmed'] = ip_data.get('warmup_day', 0) >= 30
        
        return jsonify({
            'success': True,
            'servers': workers,
            'total_workers': len([w for w in workers if w.get('status') == 'online']),
            'total_capacity': sum(w.get('daily_limit', 0) for w in workers),
            'total_sent': sum(w.get('sent_today', 0) for w in workers)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


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
