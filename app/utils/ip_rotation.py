"""
SendBaba IP Rotation Module
===========================
Handles round-robin IP selection with daily limits and warmup support.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, date
import threading
import logging

logger = logging.getLogger(__name__)

# Database config
DB_CONFIG = {
    'host': 'localhost',
    'database': 'emailer',
    'user': 'emailer',
    'password': 'SecurePassword123'
}

# Thread-safe lock for IP selection
_lock = threading.Lock()
_last_ip_index = 0


def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)


def reset_daily_counts():
    """Reset sent_today counters at midnight."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE ip_pools 
                SET sent_today = 0, last_reset_at = CURRENT_TIMESTAMP
                WHERE DATE(last_reset_at) < CURRENT_DATE
            """)
            conn.commit()
            logger.info("Daily IP counters reset")
    except Exception as e:
        logger.error(f"Failed to reset daily counts: {e}")
        conn.rollback()
    finally:
        conn.close()


def get_available_ips():
    """Get all active IPs that haven't hit their daily limit."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT ip_address, hostname, daily_limit, sent_today, warmup_day
                FROM ip_pools
                WHERE is_active = TRUE AND sent_today < daily_limit
                ORDER BY priority ASC, sent_today ASC, last_used_at ASC NULLS FIRST
            """)
            return cur.fetchall()
    finally:
        conn.close()


def get_next_ip():
    """
    Get the next available IP using round-robin with limit checking.
    Returns dict with ip_address, hostname or None if all IPs exhausted.
    """
    global _last_ip_index
    
    # Reset counts if new day
    reset_daily_counts()
    
    with _lock:
        ips = get_available_ips()
        
        if not ips:
            logger.warning("No available IPs - all at daily limit")
            return None
        
        # Round-robin selection
        _last_ip_index = (_last_ip_index + 1) % len(ips)
        selected = ips[_last_ip_index]
        
        # Increment counter
        conn = get_db_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE ip_pools 
                    SET sent_today = sent_today + 1, last_used_at = CURRENT_TIMESTAMP
                    WHERE ip_address = %s
                """, (selected['ip_address'],))
                conn.commit()
        finally:
            conn.close()
        
        logger.debug(f"Selected IP: {selected['ip_address']} ({selected['sent_today']}/{selected['daily_limit']})")
        return selected


def get_ip_for_sending():
    """
    Main function to get an IP for sending email.
    Returns tuple: (ip_address, hostname) or (None, None)
    """
    ip_data = get_next_ip()
    if ip_data:
        return ip_data['ip_address'], ip_data['hostname']
    return None, None


def get_ip_stats():
    """Get current IP pool statistics."""
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT 
                    ip_address, hostname, warmup_day, daily_limit, 
                    sent_today, is_active,
                    ROUND((sent_today::numeric / NULLIF(daily_limit, 0)) * 100, 1) as usage_pct
                FROM ip_pools
                ORDER BY server_id, ip_address
            """)
            return cur.fetchall()
    finally:
        conn.close()


def activate_ip(ip_address):
    """Activate an IP for sending."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE ip_pools SET is_active = TRUE WHERE ip_address = %s", (ip_address,))
            conn.commit()
            logger.info(f"Activated IP: {ip_address}")
            return True
    except Exception as e:
        logger.error(f"Failed to activate IP {ip_address}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def deactivate_ip(ip_address):
    """Deactivate an IP from sending."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE ip_pools SET is_active = FALSE WHERE ip_address = %s", (ip_address,))
            conn.commit()
            logger.info(f"Deactivated IP: {ip_address}")
            return True
    except Exception as e:
        logger.error(f"Failed to deactivate IP {ip_address}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def advance_warmup(ip_address):
    """Advance warmup day for an IP and update daily limit."""
    WARMUP_SCHEDULE = {
        1: 500, 2: 500,
        3: 1000, 4: 1000,
        5: 2000, 6: 2000,
        7: 5000, 8: 5000,
        9: 10000, 10: 10000,
        11: 15000, 12: 15000,
        13: 20000, 14: 20000,
        15: 25000, 16: 25000,
        17: 30000, 18: 30000,
        19: 35000, 20: 35000,
        21: 40000, 22: 40000,
        23: 45000, 24: 45000,
        25: 50000  # Max
    }
    
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT warmup_day FROM ip_pools WHERE ip_address = %s", (ip_address,))
            result = cur.fetchone()
            if result:
                current_day = result['warmup_day']
                new_day = min(current_day + 1, 31)
                new_limit = WARMUP_SCHEDULE.get(new_day, 50000)
                
                cur.execute("""
                    UPDATE ip_pools 
                    SET warmup_day = %s, daily_limit = %s
                    WHERE ip_address = %s
                """, (new_day, new_limit, ip_address))
                conn.commit()
                logger.info(f"Advanced {ip_address} to warmup day {new_day} (limit: {new_limit})")
                return new_day, new_limit
    except Exception as e:
        logger.error(f"Failed to advance warmup for {ip_address}: {e}")
        conn.rollback()
    finally:
        conn.close()
    return None, None


# Test function
if __name__ == '__main__':
    print("IP Pool Status:")
    print("-" * 80)
    for ip in get_ip_stats():
        status = "✓ ACTIVE" if ip['is_active'] else "✗ INACTIVE"
        print(f"{ip['ip_address']:18} {ip['hostname']:25} Day {ip['warmup_day']:2} | {ip['sent_today']:5}/{ip['daily_limit']:5} ({ip['usage_pct'] or 0}%) | {status}")
