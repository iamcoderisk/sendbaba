"""
IP Management Controller - Admin interface for managing sending IPs
"""
from flask import Blueprint, render_template, request, jsonify, session, redirect
from functools import wraps
import psycopg2
from datetime import datetime

ip_management_bp = Blueprint('ip_management', __name__, url_prefix='/hub/ip-management')


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


@ip_management_bp.route('/')
@hub_admin_required
def dashboard():
    return render_template('hub/ip_management.html', active_page='ip_management')


@ip_management_bp.route('/api/ips')
@hub_admin_required
def get_all_ips():
    """Get all IPs with their status"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, ip_address, hostname, is_active, warmup_day, daily_limit, 
               sent_today, last_used_at, priority
        FROM ip_pools
        ORDER BY is_active DESC, daily_limit DESC, ip_address
    """)
    
    ips = []
    for row in cur.fetchall():
        ips.append({
            'id': row[0],
            'ip_address': row[1],
            'hostname': row[2],
            'is_active': row[3],
            'warmup_day': row[4],
            'daily_limit': row[5],
            'sent_today': row[6] or 0,
            'last_used_at': row[7].isoformat() if row[7] else None,
            'priority': row[8] or 10
        })
    
    cur.close()
    conn.close()
    
    return jsonify({'ips': ips})


@ip_management_bp.route('/api/settings')
@hub_admin_required
def get_settings():
    """Get sending settings"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT setting_key, setting_value FROM sending_settings")
    settings = {row[0]: row[1] for row in cur.fetchall()}
    
    cur.close()
    conn.close()
    
    return jsonify(settings)


@ip_management_bp.route('/api/settings', methods=['POST'])
@hub_admin_required
def update_settings():
    """Update sending settings"""
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    
    for key, value in data.items():
        cur.execute("""
            INSERT INTO sending_settings (setting_key, setting_value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (setting_key) DO UPDATE SET setting_value = %s, updated_at = NOW()
        """, (key, str(value), str(value)))
    
    conn.commit()
    cur.close()
    conn.close()
    
    # Update the distributed sender config
    update_distributed_sender_config()
    
    return jsonify({'success': True})


@ip_management_bp.route('/api/ip/<int:ip_id>/toggle', methods=['POST'])
@hub_admin_required
def toggle_ip(ip_id):
    """Toggle IP active status"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("UPDATE ip_pools SET is_active = NOT is_active WHERE id = %s RETURNING is_active", (ip_id,))
    new_status = cur.fetchone()[0]
    
    conn.commit()
    cur.close()
    conn.close()
    
    # Update config
    update_distributed_sender_config()
    
    return jsonify({'success': True, 'is_active': new_status})


@ip_management_bp.route('/api/ip/<int:ip_id>', methods=['PUT'])
@hub_admin_required
def update_ip(ip_id):
    """Update IP settings"""
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE ip_pools SET
            hostname = COALESCE(%s, hostname),
            is_active = COALESCE(%s, is_active),
            warmup_day = COALESCE(%s, warmup_day),
            daily_limit = COALESCE(%s, daily_limit),
            priority = COALESCE(%s, priority)
        WHERE id = %s
    """, (
        data.get('hostname'),
        data.get('is_active'),
        data.get('warmup_day'),
        data.get('daily_limit'),
        data.get('priority'),
        ip_id
    ))
    
    conn.commit()
    cur.close()
    conn.close()
    
    # Update config
    update_distributed_sender_config()
    
    return jsonify({'success': True})


@ip_management_bp.route('/api/ip', methods=['POST'])
@hub_admin_required
def add_ip():
    """Add new IP"""
    data = request.json
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO ip_pools (ip_address, hostname, is_active, warmup_day, daily_limit, priority, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        RETURNING id
    """, (
        data['ip_address'],
        data.get('hostname', ''),
        data.get('is_active', False),
        data.get('warmup_day', 1),
        data.get('daily_limit', 2000),
        data.get('priority', 10)
    ))
    
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'success': True, 'id': new_id})


@ip_management_bp.route('/api/ip/<int:ip_id>', methods=['DELETE'])
@hub_admin_required
def delete_ip(ip_id):
    """Delete IP"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM ip_pools WHERE id = %s", (ip_id,))
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'success': True})


@ip_management_bp.route('/api/reset-daily-counts', methods=['POST'])
@hub_admin_required
def reset_daily_counts():
    """Reset all daily sent counts"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE ip_pools SET sent_today = 0, last_reset_at = NOW()")
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'success': True})


@ip_management_bp.route('/api/activate-warmed', methods=['POST'])
@hub_admin_required
def activate_warmed_only():
    """Activate only warmed IPs (100K+ daily limit)"""
    conn = get_db()
    cur = conn.cursor()
    
    # Deactivate all, then activate only warmed ones
    cur.execute("UPDATE ip_pools SET is_active = false")
    cur.execute("UPDATE ip_pools SET is_active = true WHERE daily_limit >= 100000")
    
    conn.commit()
    cur.close()
    conn.close()
    
    # Update config
    update_distributed_sender_config()
    
    return jsonify({'success': True})


@ip_management_bp.route('/api/activate-all', methods=['POST'])
@hub_admin_required
def activate_all():
    """Activate all IPs"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE ip_pools SET is_active = true")
    conn.commit()
    cur.close()
    conn.close()
    
    # Update config
    update_distributed_sender_config()
    
    return jsonify({'success': True})


@ip_management_bp.route('/api/stats')
@hub_admin_required
def get_stats():
    """Get IP sending stats"""
    conn = get_db()
    cur = conn.cursor()
    
    # Total active IPs
    cur.execute("SELECT COUNT(*) FROM ip_pools WHERE is_active = true")
    active_count = cur.fetchone()[0]
    
    # Total daily capacity
    cur.execute("SELECT COALESCE(SUM(daily_limit), 0) FROM ip_pools WHERE is_active = true")
    total_capacity = cur.fetchone()[0]
    
    # Total sent today
    cur.execute("SELECT COALESCE(SUM(sent_today), 0) FROM ip_pools")
    total_sent = cur.fetchone()[0]
    
    # Warmed vs cold
    cur.execute("SELECT COUNT(*) FROM ip_pools WHERE daily_limit >= 100000")
    warmed_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM ip_pools WHERE daily_limit < 100000")
    cold_count = cur.fetchone()[0]
    
    cur.close()
    conn.close()
    
    return jsonify({
        'active_ips': active_count,
        'total_capacity': total_capacity,
        'total_sent_today': total_sent,
        'warmed_count': warmed_count,
        'cold_count': cold_count
    })


def update_distributed_sender_config():
    """Update the distributed sender with current active IPs"""
    conn = get_db()
    cur = conn.cursor()
    
    # Get active IPs
    cur.execute("SELECT ip_address FROM ip_pools WHERE is_active = true ORDER BY priority, daily_limit DESC")
    active_ips = [row[0] for row in cur.fetchall()]
    
    # Get setting
    cur.execute("SELECT setting_value FROM sending_settings WHERE setting_key = 'use_warmed_ips_only'")
    row = cur.fetchone()
    use_warmed_only = row[0] == 'true' if row else True
    
    cur.close()
    conn.close()
    
    # Update distributed_sender.py with new IPs
    if active_ips:
        ip_list = ",\n    ".join([f"'{ip}'" for ip in active_ips])
        
        with open('/opt/sendbaba-staging/app/tasks/distributed_sender.py', 'r') as f:
            content = f.read()
        
        # Replace the WARMED_IPS list
        import re
        pattern = r"WARMED_IPS = \[.*?\]"
        replacement = f"WARMED_IPS = [\n    {ip_list}\n]"
        content = re.sub(pattern, replacement, content, flags=re.DOTALL)
        
        with open('/opt/sendbaba-staging/app/tasks/distributed_sender.py', 'w') as f:
            f.write(content)
        
        # Restart celery worker to pick up changes
        import subprocess
        subprocess.run(['pm2', 'restart', 'celery-worker'], capture_output=True)


@ip_management_bp.route('/api/check-blacklist', methods=['POST'])
@hub_admin_required
def check_single_blacklist():
    """Check single IP against blacklists"""
    import socket
    
    data = request.json
    ip_address = data.get('ip_address')
    
    blacklists = {
        'spamhaus': 'zen.spamhaus.org',
        'barracuda': 'b.barracudacentral.org',
        'spamcop': 'bl.spamcop.net',
        'sorbs': 'dnsbl.sorbs.net'
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
            pass  # Not listed
        except Exception:
            pass
    
    return jsonify(result)


@ip_management_bp.route('/api/check-all-blacklists', methods=['POST'])
@hub_admin_required
def check_all_blacklists():
    """Check all active IPs against blacklists"""
    import socket
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT ip_address FROM ip_pools WHERE is_active = true")
    all_ips = [row[0] for row in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    blacklists = {
        'spamhaus': 'zen.spamhaus.org',
        'barracuda': 'b.barracudacentral.org',
        'spamcop': 'bl.spamcop.net',
        'sorbs': 'dnsbl.sorbs.net'
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
            except socket.gaierror:
                pass
            except Exception:
                pass
        
        results.append(result)
    
    return jsonify({'results': results})
