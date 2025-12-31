"""
SendBaba Relay Client
Routes emails through remote relay servers based on IP pool
"""
import requests
import logging
from typing import Dict, Optional, List
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

RELAY_API_KEY = 'SendBabaRelay2024SecretKey!'
RELAY_PORT = 8025
RELAY_TIMEOUT = 30

# Cache for online relays
_online_relays = {}

def get_db():
    return psycopg2.connect(
        host='localhost', database='emailer',
        user='emailer', password='SecurePassword123'
    )

def check_relay_health(relay_ip: str) -> bool:
    """Check if relay server is healthy"""
    try:
        url = f"http://{relay_ip}:{RELAY_PORT}/health"
        response = requests.get(url, timeout=3)
        return response.status_code == 200
    except:
        return False

def get_relay_endpoints() -> List[Dict]:
    """Get list of relay servers from IP pool"""
    try:
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get active IPs with high daily limits (dedicated relay servers)
        cur.execute("""
            SELECT ip_address, hostname, daily_limit, sent_today, priority
            FROM ip_pools 
            WHERE is_active = true AND daily_limit >= 50000
            ORDER BY priority ASC, sent_today ASC
        """)
        
        relays = []
        for row in cur.fetchall():
            relays.append({
                'ip': row['ip_address'],
                'hostname': row['hostname'],
                'url': f"http://{row['ip_address']}:{RELAY_PORT}",
                'daily_limit': row['daily_limit'],
                'sent_today': row['sent_today'],
                'available': row['daily_limit'] - row['sent_today']
            })
        
        conn.close()
        return relays
        
    except Exception as e:
        logger.error(f"Error getting relay endpoints: {e}")
        return []

def get_online_relays() -> List[Dict]:
    """Get only online relay servers"""
    global _online_relays
    
    relays = get_relay_endpoints()
    online = []
    
    for r in relays:
        # Check cache first (valid for 60 seconds)
        import time
        cache_key = r['ip']
        cached = _online_relays.get(cache_key)
        
        if cached and time.time() - cached.get('checked', 0) < 60:
            if cached.get('online'):
                online.append(r)
        else:
            # Check health
            is_online = check_relay_health(r['ip'])
            _online_relays[cache_key] = {'online': is_online, 'checked': time.time()}
            if is_online:
                online.append(r)
    
    return online

def get_next_relay() -> Optional[Dict]:
    """Get next available ONLINE relay server"""
    relays = get_online_relays()
    
    # Filter relays with available capacity
    available = [r for r in relays if r['available'] > 0]
    
    if not available:
        logger.warning("No online relay servers with available capacity!")
        return None
    
    # Return the one with most capacity (load balancing)
    return max(available, key=lambda x: x['available'])

def send_via_relay(email_data: Dict, relay_ip: Optional[str] = None) -> Dict:
    """
    Send email through a relay server
    """
    try:
        # Get relay server
        if relay_ip:
            # Verify it's online
            if not check_relay_health(relay_ip):
                # Try to find another online relay
                relay = get_next_relay()
                if not relay:
                    return {'success': False, 'error': 'No online relay servers'}
                relay_ip = relay['ip']
            relay_url = f"http://{relay_ip}:{RELAY_PORT}"
        else:
            relay = get_next_relay()
            if not relay:
                return {'success': False, 'error': 'No online relay servers available'}
            relay_url = relay['url']
            relay_ip = relay['ip']
        
        logger.info(f"Sending via relay: {relay_ip}")
        
        # Send through relay
        response = requests.post(
            f"{relay_url}/send",
            json=email_data,
            headers={
                'Content-Type': 'application/json',
                'X-API-Key': RELAY_API_KEY
            },
            timeout=RELAY_TIMEOUT
        )
        
        result = response.json()
        result['relay_ip'] = relay_ip
        
        # Update sent count in database
        if result.get('success'):
            try:
                conn = get_db()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE ip_pools SET sent_today = sent_today + 1 WHERE ip_address = %s",
                    (relay_ip,)
                )
                conn.commit()
                conn.close()
            except Exception as e:
                logger.warning(f"Failed to update sent count: {e}")
        
        return result
        
    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'Relay timeout', 'relay_ip': relay_ip}
    except requests.exceptions.ConnectionError:
        return {'success': False, 'error': 'Relay connection failed', 'relay_ip': relay_ip}
    except Exception as e:
        return {'success': False, 'error': str(e), 'relay_ip': relay_ip}

def send_batch_via_relay(emails: List[Dict], relay_ip: Optional[str] = None) -> Dict:
    """Send batch of emails through relay"""
    try:
        if not relay_ip:
            relay = get_next_relay()
            if not relay:
                return {'success': False, 'error': 'No online relay servers available'}
            relay_ip = relay['ip']
        
        relay_url = f"http://{relay_ip}:{RELAY_PORT}"
        
        response = requests.post(
            f"{relay_url}/send-batch",
            json={'emails': emails},
            headers={
                'Content-Type': 'application/json',
                'X-API-Key': RELAY_API_KEY
            },
            timeout=RELAY_TIMEOUT * max(len(emails), 1)
        )
        
        result = response.json()
        result['relay_ip'] = relay_ip
        
        # Update sent count
        if result.get('success'):
            sent_count = result.get('results', {}).get('sent', 0)
            try:
                conn = get_db()
                cur = conn.cursor()
                cur.execute(
                    "UPDATE ip_pools SET sent_today = sent_today + %s WHERE ip_address = %s",
                    (sent_count, relay_ip)
                )
                conn.commit()
                conn.close()
            except:
                pass
        
        return result
        
    except Exception as e:
        return {'success': False, 'error': str(e)}
