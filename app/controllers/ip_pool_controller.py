"""
IP Pool Management Controller - Admin interface for SendGrid-style IP management
"""
from flask import Blueprint, render_template, request, jsonify, session, redirect
from functools import wraps
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import json

from app.services.ip_pool_manager import IPPoolManager, SenderReputationManager, ContentFilter

ip_pool_bp = Blueprint('ip_pool', __name__, url_prefix='/hub/ip-pools')


def get_db():
    return psycopg2.connect(
        host='localhost', database='emailer',
        user='emailer', password='SecurePassword123'
    )


def hub_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('hub_admin_id'):
            return redirect('/hub/login')
        return f(*args, **kwargs)
    return decorated


@ip_pool_bp.route('/')
@hub_admin_required
def dashboard():
    """IP Pool Management Dashboard"""
    return render_template('hub/ip_pools.html', active_page='ip_pools')


@ip_pool_bp.route('/api/overview')
@hub_admin_required
def get_overview():
    """Get overview stats"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Pool stats
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
        
        # Pool breakdown
        pool_stats = IPPoolManager.get_pool_stats()
        
        return jsonify({
            'overview': stats,
            'pools': pool_stats
        })
        
    finally:
        cur.close()
        conn.close()


@ip_pool_bp.route('/api/ips')
@hub_admin_required
def get_all_ips():
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
            ORDER BY ip.priority, si.reputation_score DESC
        """)
        
        ips = []
        for row in cur.fetchall():
            ip = dict(row)
            # Convert datetime objects to strings
            for key in ['created_at', 'updated_at', 'last_sent_at', 'last_reset_at', 
                       'hour_reset_at', 'blacklist_checked_at', 'warmup_start_date']:
                if ip.get(key):
                    ip[key] = ip[key].isoformat() if hasattr(ip[key], 'isoformat') else str(ip[key])
            ips.append(ip)
        
        return jsonify({'ips': ips})
        
    finally:
        cur.close()
        conn.close()


@ip_pool_bp.route('/api/ip/<int:ip_id>', methods=['PUT'])
@hub_admin_required
def update_ip(ip_id):
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
        
    finally:
        cur.close()
        conn.close()


@ip_pool_bp.route('/api/ip', methods=['POST'])
@hub_admin_required
def add_ip():
    """Add new IP"""
    data = request.json
    
    success = IPPoolManager.add_ip(
        data['ip_address'],
        data.get('hostname'),
        data.get('pool_name', 'warmup')
    )
    
    return jsonify({'success': success})


@ip_pool_bp.route('/api/ip/<int:ip_id>/start-warmup', methods=['POST'])
@hub_admin_required
def start_warmup(ip_id):
    """Start warmup for an IP"""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT ip_address FROM sending_ips WHERE id = %s", (ip_id,))
        row = cur.fetchone()
        if row:
            IPPoolManager.start_warmup(row[0])
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': 'IP not found'}), 404
        
    finally:
        cur.close()
        conn.close()


@ip_pool_bp.route('/api/ip/<int:ip_id>/check-blacklist', methods=['POST'])
@hub_admin_required
def check_blacklist(ip_id):
    """Check blacklist status for an IP"""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT ip_address FROM sending_ips WHERE id = %s", (ip_id,))
        row = cur.fetchone()
        if row:
            result = IPPoolManager.check_blacklists(row[0])
            return jsonify({'success': True, 'result': result})
        return jsonify({'success': False, 'error': 'IP not found'}), 404
        
    finally:
        cur.close()
        conn.close()


@ip_pool_bp.route('/api/check-all-blacklists', methods=['POST'])
@hub_admin_required
def check_all_blacklists():
    """Check blacklist status for all IPs"""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT ip_address FROM sending_ips WHERE is_active = true")
        results = []
        
        for row in cur.fetchall():
            result = IPPoolManager.check_blacklists(row[0])
            results.append({'ip': row[0], **result})
        
        return jsonify({'success': True, 'results': results})
        
    finally:
        cur.close()
        conn.close()


@ip_pool_bp.route('/api/progress-warmup', methods=['POST'])
@hub_admin_required
def progress_warmup():
    """Progress warmup for all IPs"""
    IPPoolManager.progress_warmup()
    return jsonify({'success': True})


@ip_pool_bp.route('/api/reset-counters', methods=['POST'])
@hub_admin_required
def reset_counters():
    """Reset daily/hourly counters"""
    reset_type = request.json.get('type', 'daily')
    
    if reset_type == 'daily':
        IPPoolManager.reset_daily_counters()
    else:
        IPPoolManager.reset_hourly_counters()
    
    return jsonify({'success': True})


@ip_pool_bp.route('/api/pools')
@hub_admin_required
def get_pools():
    """Get all pools"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("SELECT * FROM ip_pools ORDER BY priority")
        pools = [dict(row) for row in cur.fetchall()]
        return jsonify({'pools': pools})
        
    finally:
        cur.close()
        conn.close()


@ip_pool_bp.route('/api/move-ip-to-pool', methods=['POST'])
@hub_admin_required
def move_ip_to_pool():
    """Move IP to different pool"""
    data = request.json
    success = IPPoolManager.move_ip_to_pool(data['ip_address'], data['pool_name'])
    return jsonify({'success': success})


@ip_pool_bp.route('/api/warmup-schedule')
@hub_admin_required
def get_warmup_schedule():
    """Get warmup schedule"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("SELECT * FROM ip_warmup_schedule ORDER BY day_number")
        schedule = [dict(row) for row in cur.fetchall()]
        return jsonify({'schedule': schedule})
        
    finally:
        cur.close()
        conn.close()


@ip_pool_bp.route('/api/content-rules')
@hub_admin_required
def get_content_rules():
    """Get content filter rules"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("SELECT * FROM content_filter_rules ORDER BY score_impact DESC")
        rules = [dict(row) for row in cur.fetchall()]
        return jsonify({'rules': rules})
        
    finally:
        cur.close()
        conn.close()


@ip_pool_bp.route('/api/content-rules', methods=['POST'])
@hub_admin_required
def add_content_rule():
    """Add content filter rule"""
    data = request.json
    ContentFilter.add_rule(
        data['rule_name'],
        data['rule_type'],
        data['pattern'],
        data.get('action', 'flag'),
        data.get('score_impact', 10)
    )
    return jsonify({'success': True})


@ip_pool_bp.route('/api/sender-reputation')
@hub_admin_required
def get_sender_reputations():
    """Get sender reputation list"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute("""
            SELECT 
                sr.*,
                o.name as org_name,
                ip.name as pool_name
            FROM sender_reputation sr
            LEFT JOIN organizations o ON sr.organization_id = o.id
            LEFT JOIN ip_pools ip ON sr.assigned_pool_id = ip.id
            ORDER BY sr.reputation_score DESC
        """)
        senders = [dict(row) for row in cur.fetchall()]
        return jsonify({'senders': senders})
        
    finally:
        cur.close()
        conn.close()
