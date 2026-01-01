"""
SendBaba Distributed Sender - Database Driven
==============================================
No hardcoding - all limits from database
"""
import logging
from celery import Celery
from app.tasks.worker_manager import (
    get_available_workers, 
    distribute_emails, 
    get_total_capacity,
    update_worker_stats
)
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

DB_CONFIG = {
    'host': 'localhost',
    'database': 'emailer',
    'user': 'emailer',
    'password': 'SecurePassword123'
}

def get_db():
    return psycopg2.connect(**DB_CONFIG)

def get_capacity_report():
    """Get current sending capacity report"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE status = 'active' AND is_active = TRUE) as active_servers,
                COUNT(*) FILTER (WHERE status = 'warming' AND is_active = TRUE) as warming_servers,
                COUNT(*) as total_servers,
                COALESCE(SUM(daily_limit) FILTER (WHERE is_active = TRUE), 0) as total_daily_capacity,
                COALESCE(SUM(sent_today) FILTER (WHERE is_active = TRUE), 0) as total_sent_today
            FROM worker_servers
        """)
        capacity = cur.fetchone()
        
        cur.execute("""
            SELECT ip_address, hostname, status, warmup_day, daily_limit, sent_today,
                   ROUND((sent_today::numeric / NULLIF(daily_limit, 0)) * 100, 1) as usage_pct
            FROM worker_servers 
            WHERE is_active = TRUE
            ORDER BY status DESC, daily_limit DESC
        """)
        servers = cur.fetchall()
        
        return_db(conn)
        
        return {
            'success': True,
            'capacity': dict(capacity) if capacity else {},
            'servers': [dict(s) for s in servers],
            'remaining_today': (capacity['total_daily_capacity'] or 0) - (capacity['total_sent_today'] or 0) if capacity else 0
        }
    except Exception as e:
        logger.error(f"Capacity report error: {e}")
        return {'success': False, 'error': str(e), 'capacity': {}, 'servers': [], 'remaining_today': 0}


def launch_campaign(campaign_id, contacts, campaign_data, chunk_size=500):
    """Launch a campaign by chunking contacts and queuing tasks"""
    try:
        total = len(contacts)
        chunks = [contacts[i:i+chunk_size] for i in range(0, total, chunk_size)]
        
        logger.info(f"Launching campaign {campaign_id}: {total} contacts in {len(chunks)} chunks")
        
        for i, chunk in enumerate(chunks):
            chunk_data = {
                'campaign_id': campaign_id,
                'campaign': campaign_data,
                'contacts': chunk,
                'chunk_id': i + 1
            }
            send_email_chunk.delay(chunk_data)
        
        return {
            'success': True,
            'campaign_id': campaign_id,
            'total_contacts': total,
            'chunks_queued': len(chunks)
        }
    except Exception as e:
        logger.error(f"Launch campaign error: {e}")
        return {'success': False, 'error': str(e)}
