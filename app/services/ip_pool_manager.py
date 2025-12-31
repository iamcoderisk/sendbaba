"""
SendBaba IP Pool Manager - SendGrid-Style IP Management
========================================================
Handles:
1. IP Pool categorization (premium, standard, warmup, quarantine)
2. Automatic warmup progression
3. Reputation-based IP selection
4. Sender isolation for bad actors
5. Blacklist monitoring
"""

import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import re
import socket

logger = logging.getLogger(__name__)

DB_CONFIG = {
    'host': 'localhost',
    'database': 'emailer',
    'user': 'emailer',
    'password': 'SecurePassword123'
}


def get_db():
    return psycopg2.connect(**DB_CONFIG)


class IPPoolManager:
    """Manages IP pools and selection for sending"""
    
    # Warmup schedule (day -> daily_limit)
    WARMUP_SCHEDULE = {
        1: 50, 2: 75, 3: 100, 4: 150, 5: 200,
        6: 300, 7: 400, 8: 500, 9: 650, 10: 800,
        11: 1000, 12: 1250, 13: 1500, 14: 2000,
        15: 2500, 16: 3000, 17: 4000, 18: 5000,
        19: 6500, 20: 8000, 21: 10000, 25: 15000,
        28: 20000, 30: 30000, 35: 50000, 42: 75000,
        45: 100000
    }
    
    @classmethod
    def get_ip_for_sending(cls, organization_id: str, recipient_domain: str = None) -> Optional[Dict]:
        """
        Get the best IP for sending based on:
        1. Sender reputation tier
        2. IP pool assignment
        3. Current usage vs limits
        4. Recipient domain preferences
        """
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Get sender's reputation and pool assignment
            cur.execute("""
                SELECT reputation_tier, assigned_pool_id, dedicated_ip_id, is_suspended
                FROM sender_reputation
                WHERE organization_id = %s
            """, (organization_id,))
            
            sender = cur.fetchone()
            
            if sender and sender['is_suspended']:
                logger.warning(f"Sender {organization_id} is suspended")
                return None
            
            # If sender has dedicated IP, use that
            if sender and sender['dedicated_ip_id']:
                cur.execute("""
                    SELECT * FROM sending_ips
                    WHERE id = %s AND is_active = true AND is_blacklisted = false
                    AND sent_today < daily_limit
                """, (sender['dedicated_ip_id'],))
                ip = cur.fetchone()
                if ip:
                    return dict(ip)
            
            # Get pool based on sender tier
            pool_name = 'standard'
            if sender:
                tier_to_pool = {
                    'premium': 'premium',
                    'standard': 'standard',
                    'probation': 'warmup',
                    'suspended': None
                }
                pool_name = tier_to_pool.get(sender['reputation_tier'], 'standard')
            
            if not pool_name:
                return None
            
            # Get available IP from pool with capacity
            cur.execute("""
                SELECT si.* FROM sending_ips si
                JOIN ip_pools ip ON si.pool_id = ip.id
                WHERE ip.name = %s
                AND si.is_active = true
                AND si.is_blacklisted = false
                AND si.warmup_status IN ('warmed', 'warming')
                AND si.sent_today < si.daily_limit
                AND si.sent_this_hour < si.hourly_limit
                ORDER BY 
                    si.reputation_score DESC,
                    (si.daily_limit - si.sent_today) DESC
                LIMIT 1
            """, (pool_name,))
            
            ip = cur.fetchone()
            
            # Fallback to any available IP if pool is empty
            if not ip:
                cur.execute("""
                    SELECT * FROM sending_ips
                    WHERE is_active = true
                    AND is_blacklisted = false
                    AND sent_today < daily_limit
                    AND sent_this_hour < hourly_limit
                    ORDER BY reputation_score DESC, sent_today ASC
                    LIMIT 1
                """)
                ip = cur.fetchone()
            
            return dict(ip) if ip else None
            
        finally:
            cur.close()
            conn.close()
    
    @classmethod
    def increment_ip_usage(cls, ip_address: str, success: bool = True):
        """Update IP usage counters after sending"""
        conn = get_db()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                UPDATE sending_ips
                SET sent_today = sent_today + 1,
                    sent_this_hour = sent_this_hour + 1,
                    sent_total = sent_total + 1,
                    last_sent_at = NOW()
                WHERE ip_address = %s
            """, (ip_address,))
            conn.commit()
        finally:
            cur.close()
            conn.close()
    
    @classmethod
    def reset_daily_counters(cls):
        """Reset daily counters (run at midnight)"""
        conn = get_db()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                UPDATE sending_ips
                SET sent_today = 0, last_reset_at = NOW()
                WHERE sent_today > 0
            """)
            conn.commit()
            logger.info("Daily IP counters reset")
        finally:
            cur.close()
            conn.close()
    
    @classmethod
    def reset_hourly_counters(cls):
        """Reset hourly counters (run every hour)"""
        conn = get_db()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                UPDATE sending_ips
                SET sent_this_hour = 0, hour_reset_at = NOW()
                WHERE sent_this_hour > 0
            """)
            conn.commit()
        finally:
            cur.close()
            conn.close()
    
    @classmethod
    def progress_warmup(cls):
        """Progress warmup for all warming IPs (run daily)"""
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Get all warming IPs
            cur.execute("""
                SELECT id, ip_address, warmup_day, warmup_start_date
                FROM sending_ips
                WHERE warmup_status = 'warming'
                AND warmup_start_date IS NOT NULL
            """)
            
            for ip in cur.fetchall():
                # Calculate new warmup day
                days_since_start = (datetime.now().date() - ip['warmup_start_date']).days
                new_day = days_since_start + 1
                
                # Get new limits from schedule
                daily_limit = 50
                for day, limit in sorted(cls.WARMUP_SCHEDULE.items()):
                    if new_day >= day:
                        daily_limit = limit
                
                hourly_limit = daily_limit // 6  # Spread over 6 hours
                
                # Check if fully warmed
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
                
                logger.info(f"IP {ip['ip_address']} warmup day {new_day}: {daily_limit}/day")
            
            conn.commit()
            
        finally:
            cur.close()
            conn.close()
    
    @classmethod
    def start_warmup(cls, ip_address: str):
        """Start warmup process for a new IP"""
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
                WHERE ip_address = %s
            """, (pool_id, ip_address))
            conn.commit()
            
            logger.info(f"Started warmup for IP {ip_address}")
            
        finally:
            cur.close()
            conn.close()
    
    @classmethod
    def check_blacklists(cls, ip_address: str) -> Dict:
        """Check if IP is on any blacklists"""
        blacklists = {
            'spamhaus': 'zen.spamhaus.org',
            'barracuda': 'b.barracudacentral.org',
            'spamcop': 'bl.spamcop.net',
            'sorbs': 'dnsbl.sorbs.net'
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
                pass  # Not listed
            except Exception as e:
                logger.debug(f"Blacklist check error for {name}: {e}")
        
        # Update database
        conn = get_db()
        cur = conn.cursor()
        try:
            import json
            cur.execute("""
                UPDATE sending_ips
                SET is_blacklisted = %s,
                    blacklist_checked_at = NOW(),
                    blacklist_details = %s
                WHERE ip_address = %s
            """, (results['is_listed'], json.dumps(results), ip_address))
            conn.commit()
        finally:
            cur.close()
            conn.close()
        
        return results
    
    @classmethod
    def add_ip(cls, ip_address: str, hostname: str = None, pool_name: str = 'warmup') -> bool:
        """Add a new IP to the system"""
        conn = get_db()
        cur = conn.cursor()
        
        try:
            # Get pool ID
            cur.execute("SELECT id FROM ip_pools WHERE name = %s", (pool_name,))
            pool = cur.fetchone()
            pool_id = pool[0] if pool else None
            
            cur.execute("""
                INSERT INTO sending_ips (ip_address, hostname, pool_id, warmup_status, daily_limit, hourly_limit)
                VALUES (%s, %s, %s, 'new', 50, 10)
                ON CONFLICT (ip_address) DO UPDATE SET
                    hostname = EXCLUDED.hostname,
                    updated_at = NOW()
                RETURNING id
            """, (ip_address, hostname, pool_id))
            
            conn.commit()
            logger.info(f"Added IP {ip_address} to pool {pool_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add IP {ip_address}: {e}")
            conn.rollback()
            return False
        finally:
            cur.close()
            conn.close()
    
    @classmethod
    def move_ip_to_pool(cls, ip_address: str, pool_name: str):
        """Move an IP to a different pool"""
        conn = get_db()
        cur = conn.cursor()
        
        try:
            cur.execute("SELECT id FROM ip_pools WHERE name = %s", (pool_name,))
            pool = cur.fetchone()
            if not pool:
                logger.error(f"Pool {pool_name} not found")
                return False
            
            cur.execute("""
                UPDATE sending_ips
                SET pool_id = %s, updated_at = NOW()
                WHERE ip_address = %s
            """, (pool[0], ip_address))
            conn.commit()
            
            logger.info(f"Moved IP {ip_address} to pool {pool_name}")
            return True
            
        finally:
            cur.close()
            conn.close()
    
    @classmethod
    def get_pool_stats(cls) -> List[Dict]:
        """Get statistics for all IP pools"""
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            cur.execute("""
                SELECT 
                    ip.name as pool_name,
                    ip.pool_type,
                    COUNT(si.id) as total_ips,
                    COUNT(si.id) FILTER (WHERE si.is_active AND NOT si.is_blacklisted) as active_ips,
                    COUNT(si.id) FILTER (WHERE si.is_blacklisted) as blacklisted_ips,
                    COALESCE(SUM(si.daily_limit), 0) as total_daily_capacity,
                    COALESCE(SUM(si.sent_today), 0) as sent_today,
                    COALESCE(AVG(si.reputation_score), 0) as avg_reputation
                FROM ip_pools ip
                LEFT JOIN sending_ips si ON si.pool_id = ip.id
                GROUP BY ip.id, ip.name, ip.pool_type
                ORDER BY ip.priority
            """)
            
            return [dict(row) for row in cur.fetchall()]
            
        finally:
            cur.close()
            conn.close()


class SenderReputationManager:
    """Manages sender reputation and pool assignments"""
    
    @classmethod
    def update_sender_reputation(cls, organization_id: str):
        """Recalculate sender reputation based on recent activity"""
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        try:
            # Get recent stats (last 30 days)
            cur.execute("""
                SELECT 
                    COUNT(*) as total_sent,
                    COUNT(*) FILTER (WHERE status = 'delivered') as delivered,
                    COUNT(*) FILTER (WHERE status = 'bounced') as bounced,
                    COUNT(*) FILTER (WHERE status = 'complained') as complaints
                FROM emails
                WHERE organization_id = %s
                AND created_at > NOW() - INTERVAL '30 days'
            """, (organization_id,))
            
            stats = cur.fetchone()
            
            if not stats or stats['total_sent'] == 0:
                return
            
            # Calculate rates
            bounce_rate = (stats['bounced'] / stats['total_sent']) * 100
            complaint_rate = (stats['complaints'] / stats['total_sent']) * 100
            
            # Calculate reputation score (0-100)
            score = 100
            score -= min(bounce_rate * 5, 30)  # Up to -30 for bounces
            score -= min(complaint_rate * 20, 50)  # Up to -50 for complaints
            score = max(0, min(100, score))
            
            # Determine tier
            if score >= 80:
                tier = 'premium'
            elif score >= 50:
                tier = 'standard'
            elif score >= 20:
                tier = 'probation'
            else:
                tier = 'suspended'
            
            # Update or insert reputation record
            cur.execute("""
                INSERT INTO sender_reputation (organization_id, reputation_score, reputation_tier,
                    total_sent, total_bounced, total_complaints, bounce_rate, complaint_rate)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (organization_id) DO UPDATE SET
                    reputation_score = EXCLUDED.reputation_score,
                    reputation_tier = EXCLUDED.reputation_tier,
                    total_sent = sender_reputation.total_sent + EXCLUDED.total_sent,
                    total_bounced = sender_reputation.total_bounced + EXCLUDED.total_bounced,
                    total_complaints = sender_reputation.total_complaints + EXCLUDED.total_complaints,
                    bounce_rate = EXCLUDED.bounce_rate,
                    complaint_rate = EXCLUDED.complaint_rate,
                    updated_at = NOW()
            """, (organization_id, score, tier, stats['total_sent'], 
                  stats['bounced'], stats['complaints'], bounce_rate, complaint_rate))
            
            conn.commit()
            
            # Auto-assign pool based on tier
            pool_map = {
                'premium': 'premium',
                'standard': 'standard',
                'probation': 'warmup',
                'suspended': 'quarantine'
            }
            
            cur.execute("""
                UPDATE sender_reputation sr
                SET assigned_pool_id = ip.id
                FROM ip_pools ip
                WHERE sr.organization_id = %s
                AND ip.name = %s
            """, (organization_id, pool_map.get(tier, 'standard')))
            
            conn.commit()
            
            logger.info(f"Updated reputation for {organization_id}: score={score}, tier={tier}")
            
        finally:
            cur.close()
            conn.close()
    
    @classmethod
    def suspend_sender(cls, organization_id: str, reason: str):
        """Suspend a sender for policy violations"""
        conn = get_db()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                UPDATE sender_reputation
                SET is_suspended = true,
                    suspension_reason = %s,
                    suspended_at = NOW(),
                    reputation_tier = 'suspended'
                WHERE organization_id = %s
            """, (reason, organization_id))
            conn.commit()
            
            logger.warning(f"Suspended sender {organization_id}: {reason}")
            
        finally:
            cur.close()
            conn.close()


class ContentFilter:
    """Filters outgoing content for spam patterns"""
    
    @classmethod
    def check_content(cls, subject: str, body: str, from_email: str) -> Dict:
        """
        Check email content for spam patterns
        Returns: {'is_spam': bool, 'score': int, 'reasons': list}
        """
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        result = {
            'is_spam': False,
            'score': 0,
            'reasons': [],
            'action': 'allow'
        }
        
        try:
            cur.execute("""
                SELECT rule_name, rule_type, pattern, action, score_impact
                FROM content_filter_rules
                WHERE is_active = true
            """)
            
            content = f"{subject} {body}".lower()
            
            for rule in cur.fetchall():
                matched = False
                
                if rule['rule_type'] == 'keyword':
                    # Check for keywords (case insensitive)
                    keywords = rule['pattern'].split('|')
                    for kw in keywords:
                        if kw.lower() in content:
                            matched = True
                            break
                
                elif rule['rule_type'] == 'pattern':
                    # Regex pattern matching
                    try:
                        if re.search(rule['pattern'], content, re.IGNORECASE):
                            matched = True
                    except:
                        pass
                
                if matched:
                    result['score'] += rule['score_impact']
                    result['reasons'].append(rule['rule_name'])
                    
                    if rule['action'] == 'reject':
                        result['action'] = 'reject'
                        result['is_spam'] = True
            
            # Threshold check
            if result['score'] >= 50:
                result['is_spam'] = True
                if result['action'] != 'reject':
                    result['action'] = 'flag'
            
            return result
            
        finally:
            cur.close()
            conn.close()
    
    @classmethod
    def add_rule(cls, rule_name: str, rule_type: str, pattern: str, 
                 action: str = 'flag', score_impact: int = 10):
        """Add a new content filter rule"""
        conn = get_db()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                INSERT INTO content_filter_rules (rule_name, rule_type, pattern, action, score_impact)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (rule_name, rule_type, pattern, action, score_impact))
            conn.commit()
        finally:
            cur.close()
            conn.close()


# Convenience functions for the distributed sender
def get_best_ip_for_sending(organization_id: str = None) -> Optional[str]:
    """Get the best available IP for sending"""
    ip = IPPoolManager.get_ip_for_sending(organization_id or 'default')
    return ip['ip_address'] if ip else None


def record_send_result(ip_address: str, success: bool):
    """Record the result of a send attempt"""
    IPPoolManager.increment_ip_usage(ip_address, success)


def check_content_before_send(subject: str, body: str, from_email: str) -> Dict:
    """Check content before sending"""
    return ContentFilter.check_content(subject, body, from_email)
