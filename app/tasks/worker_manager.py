"""
SendBaba Dynamic Worker Manager
================================
- No hardcoded limits
- All config from database
- Auto-advancing warmup
- Real-time capacity tracking
"""
import logging
from datetime import date, datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import redis

logger = logging.getLogger(__name__)

DB_CONFIG = {
    'host': 'localhost',
    'database': 'emailer',
    'user': 'emailer',
    'password': 'SecurePassword123'
}

REDIS_CONFIG = {
    'host': 'localhost',
    'port': 6379,
    'password': 'SendBabaRedis2024!',
    'decode_responses': True
}

def get_db():
    return psycopg2.connect(**DB_CONFIG)

def get_redis():
    return redis.Redis(**REDIS_CONFIG)

def get_all_workers():
    """Get all workers with their current status and limits from database"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM worker_capacity_view")
    workers = cur.fetchall()
    conn.close()
    return workers

def get_worker_by_ip(ip):
    """Get single worker info"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM worker_capacity_view WHERE ip_address = %s", (ip,))
    worker = cur.fetchone()
    conn.close()
    return worker

def get_available_workers():
    """Get workers with remaining capacity, sorted by priority"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT * FROM worker_capacity_view 
        WHERE status IN ('active', 'warming') 
        AND remaining_today > 0
        ORDER BY 
            CASE status WHEN 'active' THEN 0 ELSE 1 END,
            remaining_today DESC
    """)
    workers = cur.fetchall()
    conn.close()
    return workers

def get_total_capacity():
    """Get total system capacity"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM total_capacity_view")
    rows = cur.fetchall()
    conn.close()
    
    result = {
        'active': {'count': 0, 'daily_limit': 0, 'sent_today': 0, 'remaining': 0},
        'warming': {'count': 0, 'daily_limit': 0, 'sent_today': 0, 'remaining': 0},
    }
    for row in rows:
        status = row['status']
        if status in result:
            result[status] = {
                'count': row['worker_count'],
                'daily_limit': row['total_daily_limit'],
                'sent_today': row['total_sent_today'],
                'remaining': row['total_remaining']
            }
    
    result['total'] = {
        'count': result['active']['count'] + result['warming']['count'],
        'daily_limit': result['active']['daily_limit'] + result['warming']['daily_limit'],
        'sent_today': result['active']['sent_today'] + result['warming']['sent_today'],
        'remaining': result['active']['remaining'] + result['warming']['remaining']
    }
    return result

def update_worker_stats(ip, sent, failed, bounced):
    """Update worker stats after sending - triggers auto warmup advancement"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT update_worker_stats(%s, %s, %s, %s)", (ip, sent, failed, bounced))
    conn.commit()
    conn.close()

def register_worker(ip, hostname=None):
    """Register a new worker IP"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO worker_ips (ip_address, hostname, status, warmup_stage, current_daily_limit, warmup_started_at)
        VALUES (%s, %s, 'warming', 1, 500, NOW())
        ON CONFLICT (ip_address) DO UPDATE SET
            hostname = COALESCE(EXCLUDED.hostname, worker_ips.hostname),
            last_heartbeat = NOW(),
            updated_at = NOW()
        RETURNING *
    """, (ip, hostname))
    conn.commit()
    conn.close()

def update_worker_limit(ip, new_limit):
    """Manually update a worker's daily limit"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE worker_ips SET current_daily_limit = %s, updated_at = NOW()
        WHERE ip_address = %s
    """, (new_limit, ip))
    conn.commit()
    conn.close()

def update_worker_status(ip, status):
    """Update worker status (active, warming, paused, disabled)"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE worker_ips SET status = %s, updated_at = NOW()
        WHERE ip_address = %s
    """, (status, ip))
    conn.commit()
    conn.close()

def advance_warmup_stage(ip):
    """Manually advance warmup stage"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE worker_ips w SET
            warmup_stage = LEAST(warmup_stage + 1, 10),
            current_daily_limit = COALESCE(
                (SELECT daily_limit FROM warmup_schedule WHERE stage = w.warmup_stage + 1),
                w.current_daily_limit
            ),
            status = CASE WHEN warmup_stage >= 9 THEN 'active' ELSE status END,
            warmup_completed_at = CASE WHEN warmup_stage >= 9 THEN NOW() ELSE NULL END,
            updated_at = NOW()
        WHERE ip_address = %s
        RETURNING warmup_stage, current_daily_limit, status
    """, (ip,))
    result = cur.fetchone()
    conn.commit()
    conn.close()
    return result

def get_warmup_schedule():
    """Get warmup schedule configuration"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM warmup_schedule ORDER BY stage")
    schedule = cur.fetchall()
    conn.close()
    return schedule

def update_warmup_schedule(stage, daily_limit=None, min_success_rate=None, min_days=None):
    """Update warmup schedule"""
    conn = get_db()
    cur = conn.cursor()
    updates = []
    params = []
    if daily_limit is not None:
        updates.append("daily_limit = %s")
        params.append(daily_limit)
    if min_success_rate is not None:
        updates.append("min_success_rate = %s")
        params.append(min_success_rate)
    if min_days is not None:
        updates.append("min_days_at_stage = %s")
        params.append(min_days)
    
    if updates:
        params.append(stage)
        cur.execute(f"UPDATE warmup_schedule SET {', '.join(updates)} WHERE stage = %s", params)
        conn.commit()
    conn.close()

def distribute_emails(contacts, chunk_size=500):
    """Distribute contacts across available workers based on capacity"""
    workers = get_available_workers()
    if not workers:
        logger.warning("No workers with available capacity!")
        return []
    
    distributions = []
    contact_index = 0
    total = len(contacts)
    
    # Round-robin with capacity awareness
    worker_index = 0
    while contact_index < total:
        worker = workers[worker_index % len(workers)]
        
        # Check remaining capacity
        remaining = worker['remaining_today']
        if remaining <= 0:
            worker_index += 1
            if worker_index >= len(workers) * 2:  # Prevent infinite loop
                break
            continue
        
        # Calculate chunk for this worker
        chunk_count = min(chunk_size, remaining, total - contact_index)
        if chunk_count > 0:
            chunk = contacts[contact_index:contact_index + chunk_count]
            distributions.append({
                'ip': worker['ip_address'],
                'hostname': worker['hostname'],
                'contacts': chunk,
                'count': chunk_count
            })
            
            # Update worker's remaining in our local copy
            worker['remaining_today'] -= chunk_count
            contact_index += chunk_count
        
        worker_index += 1
    
    return distributions

def get_daily_report():
    """Get daily sending report by worker"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT 
            d.ip_address,
            w.hostname,
            w.status,
            w.warmup_stage,
            d.sent_count,
            d.failed_count,
            d.bounce_count,
            d.success_rate,
            w.current_daily_limit,
            ROUND((d.sent_count::DECIMAL / NULLIF(w.current_daily_limit, 0)) * 100, 1) as utilization
        FROM worker_daily_stats d
        JOIN worker_ips w ON d.ip_address = w.ip_address
        WHERE d.date = CURRENT_DATE
        ORDER BY d.sent_count DESC
    """)
    report = cur.fetchall()
    conn.close()
    return report
