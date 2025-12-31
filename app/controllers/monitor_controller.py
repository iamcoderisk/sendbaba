"""
Real-Time Campaign Monitoring Dashboard
With Test Campaign Creation for IP Warmup
"""
from flask import Blueprint, render_template, request, jsonify, session, redirect
from functools import wraps
import psycopg2
import uuid
from datetime import datetime
import subprocess
import re

monitor_bp = Blueprint('monitor', __name__, url_prefix='/hub/monitor')

# Database connection
def get_db():
    return psycopg2.connect(
        host='localhost', database='emailer',
        user='emailer', password='SecurePassword123'
    )

# Auth decorator
def hub_admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('hub_admin_id'):
            return redirect('/hub/login')
        return f(*args, **kwargs)
    return decorated


@monitor_bp.route('/')
@hub_admin_required
def dashboard():
    return render_template('hub/monitor.html', active_page='monitor')


@monitor_bp.route('/api/stats')
@hub_admin_required
def get_stats():
    """Get real-time statistics"""
    conn = get_db()
    cur = conn.cursor()
    
    # Active campaigns
    cur.execute("""
        SELECT id, name, status, sent_count, 
               (SELECT COUNT(*) FROM contacts WHERE organization_id = c.organization_id AND status = 'active') as total,
               created_at, started_at
        FROM campaigns c
        WHERE status IN ('sending', 'queued', 'scheduled')
        ORDER BY created_at DESC
        LIMIT 10
    """)
    active_campaigns = []
    for row in cur.fetchall():
        total = row[4] or 0
        sent = row[3] or 0
        progress = round((sent / total * 100), 1) if total > 0 else 0
        active_campaigns.append({
            'id': row[0],
            'name': row[1],
            'status': row[2],
            'sent': sent,
            'total': total,
            'progress': progress,
            'created_at': row[5].isoformat() if row[5] else None,
            'started_at': row[6].isoformat() if row[6] else None
        })
    
    # Recent completed campaigns
    cur.execute("""
        SELECT id, name, status, sent_count, created_at
        FROM campaigns
        WHERE status IN ('sent', 'completed', 'failed')
        ORDER BY created_at DESC
        LIMIT 5
    """)
    recent_campaigns = [{
        'id': row[0], 'name': row[1], 'status': row[2],
        'sent': row[3], 'created_at': row[4].isoformat() if row[4] else None
    } for row in cur.fetchall()]
    
    # Email stats (last hour)
    cur.execute("""
        SELECT 
            COUNT(*) FILTER (WHERE status = 'sent') as sent,
            COUNT(*) FILTER (WHERE status = 'failed') as failed,
            COUNT(*) FILTER (WHERE status = 'sending') as sending,
            COUNT(*) FILTER (WHERE status = 'opened') as opened,
            COUNT(*) FILTER (WHERE status = 'clicked') as clicked
        FROM emails
        WHERE created_at > NOW() - INTERVAL '1 hour'
    """)
    row = cur.fetchone()
    email_stats = {
        'sent': row[0] or 0,
        'failed': row[1] or 0,
        'sending': row[2] or 0,
        'opened': row[3] or 0,
        'clicked': row[4] or 0
    }
    
    # Get worker count
    try:
        result = subprocess.run(
            ['celery', '-A', 'celery_app', 'inspect', 'ping'],
            capture_output=True, text=True, timeout=10,
            cwd='/opt/sendbaba-staging'
        )
        workers_online = result.stdout.count('OK')
    except:
        workers_online = 0
    
    # Speed calculation (emails per minute in last 5 minutes)
    cur.execute("""
        SELECT COUNT(*) FROM emails 
        WHERE status = 'sent' 
        AND sent_at > NOW() - INTERVAL '5 minutes'
    """)
    emails_5min = cur.fetchone()[0] or 0
    speed = round(emails_5min / 5, 0)
    
    cur.close()
    conn.close()
    
    return jsonify({
        'active_campaigns': active_campaigns,
        'recent_campaigns': recent_campaigns,
        'email_stats': email_stats,
        'workers_online': workers_online,
        'speed': speed,
        'timestamp': datetime.now().isoformat()
    })


@monitor_bp.route('/api/campaign/<campaign_id>')
@hub_admin_required
def get_campaign_details(campaign_id):
    """Get detailed campaign stats"""
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT c.id, c.name, c.status, c.sent_count, c.from_email, c.subject,
               c.created_at, c.started_at, c.completed_at,
               (SELECT COUNT(*) FROM contacts WHERE organization_id = c.organization_id AND status = 'active') as total,
               (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status = 'sent') as actual_sent,
               (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status = 'failed') as actual_failed,
               (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status = 'opened') as opens,
               (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status = 'clicked') as clicks
        FROM campaigns c
        WHERE c.id = %s
    """, (campaign_id,))
    row = cur.fetchone()
    
    if not row:
        return jsonify({'error': 'Campaign not found'}), 404
    
    cur.close()
    conn.close()
    
    return jsonify({
        'id': row[0],
        'name': row[1],
        'status': row[2],
        'sent_count': row[3],
        'from_email': row[4],
        'subject': row[5],
        'created_at': row[6].isoformat() if row[6] else None,
        'started_at': row[7].isoformat() if row[7] else None,
        'completed_at': row[8].isoformat() if row[8] else None,
        'total_contacts': row[9],
        'actual_sent': row[10],
        'actual_failed': row[11],
        'opens': row[12],
        'clicks': row[13]
    })


@monitor_bp.route('/api/test-campaign', methods=['POST'])
@hub_admin_required
def create_test_campaign():
    """Create a test campaign for IP warmup"""
    data = request.json
    
    emails_raw = data.get('emails', '')
    from_email = data.get('from_email', '')
    from_name = data.get('from_name', 'SendBaba Test')
    subject = data.get('subject', 'Test Email - IP Warmup')
    html_body = data.get('html_body', '<h1>Test Email</h1><p>This is a test email for IP warmup.</p>')
    
    # Parse emails (comma, newline, or space separated)
    emails = re.split(r'[,\n\s]+', emails_raw)
    emails = [e.strip() for e in emails if e.strip() and '@' in e]
    
    if not emails:
        return jsonify({'error': 'No valid emails provided'}), 400
    
    if not from_email:
        return jsonify({'error': 'From email required'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    
    # Get first org or create test org
    cur.execute("SELECT id FROM organizations LIMIT 1")
    org_row = cur.fetchone()
    if org_row:
        org_id = org_row[0]
    else:
        org_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO organizations (id, name, created_at)
            VALUES (%s, 'Test Organization', NOW())
        """, (org_id,))
    
    # Create campaign
    campaign_id = f"test_{int(datetime.now().timestamp())}_{uuid.uuid4().hex[:8]}"
    
    cur.execute("""
        INSERT INTO campaigns (
            id, organization_id, name, from_name, from_email, 
            subject, html_content, status, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'queued', NOW())
        RETURNING id
    """, (
        campaign_id, org_id, f"Test Campaign - {len(emails)} emails",
        from_name, from_email, subject, html_body
    ))
    
    # Create contacts for these emails
    for email in emails:
        contact_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO contacts (id, organization_id, email, status, created_at)
            VALUES (%s, %s, %s, 'active', NOW())
            ON CONFLICT (organization_id, email) DO NOTHING
        """, (contact_id, org_id, email))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({
        'success': True,
        'campaign_id': campaign_id,
        'emails_count': len(emails),
        'message': f'Test campaign created with {len(emails)} emails. It will start automatically.'
    })


@monitor_bp.route('/api/workers')
@hub_admin_required  
def get_workers():
    """Get worker status"""
    try:
        result = subprocess.run(
            ['celery', '-A', 'celery_app', 'inspect', 'ping'],
            capture_output=True, text=True, timeout=15,
            cwd='/opt/sendbaba-staging'
        )
        
        workers = []
        for line in result.stdout.split('\n'):
            if 'OK' in line:
                parts = line.split(':')
                if parts:
                    worker_name = parts[0].strip().replace('-> ', '').replace('celery@', '')
                    workers.append({'name': worker_name, 'status': 'online'})
        
        return jsonify({'workers': workers, 'total': len(workers)})
    except Exception as e:
        return jsonify({'workers': [], 'total': 0, 'error': str(e)})


@monitor_bp.route('/api/pause/<campaign_id>', methods=['POST'])
@hub_admin_required
def pause_campaign(campaign_id):
    """Pause a campaign"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE campaigns SET status = 'paused' WHERE id = %s", (campaign_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})


@monitor_bp.route('/api/resume/<campaign_id>', methods=['POST'])
@hub_admin_required
def resume_campaign(campaign_id):
    """Resume a campaign"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE campaigns SET status = 'queued' WHERE id = %s", (campaign_id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'success': True})
