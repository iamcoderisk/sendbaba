"""
SendBaba Bounce Handling Service
================================
Production-ready bounce processing with:
- Automatic bounce classification (hard/soft/spam/complaint)
- Auto-add to suppression list
- Bounce rate monitoring & alerts
- Auto-pause campaigns if bounce rate > 5%
- Webhook notifications
- Gmail/Yahoo feedback loop integration
"""
import re
import uuid
import logging
import redis
import hashlib
import hmac
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)

# Redis connection
redis_client = redis.Redis(
    host='localhost',
    port=6379,
    password='SendBabaRedis2024!',
    decode_responses=True
)


class BounceType(Enum):
    HARD = 'hard'           # Permanent - invalid address
    SOFT = 'soft'           # Temporary - retry later
    SPAM = 'spam'           # Spam complaint
    COMPLAINT = 'complaint' # User complaint (FBL)
    UNSUBSCRIBE = 'unsubscribe'
    UNKNOWN = 'unknown'


class BounceAction(Enum):
    SUPPRESS = 'suppress'   # Add to suppression list
    RETRY = 'retry'         # Retry sending
    NONE = 'none'           # No action needed
    PAUSE = 'pause'         # Pause campaign


# Bounce pattern definitions
BOUNCE_PATTERNS = {
    BounceType.HARD: [
        # User/mailbox doesn't exist
        (r'user.*unknown', 'User unknown'),
        (r'mailbox.*not.*found', 'Mailbox not found'),
        (r'no.*such.*user', 'No such user'),
        (r'recipient.*rejected', 'Recipient rejected'),
        (r'address.*rejected', 'Address rejected'),
        (r'invalid.*recipient', 'Invalid recipient'),
        (r'does.*not.*exist', 'Address does not exist'),
        (r'account.*disabled', 'Account disabled'),
        (r'account.*suspended', 'Account suspended'),
        (r'mailbox.*unavailable', 'Mailbox unavailable'),
        
        # SMTP codes - permanent failures
        (r'550[\s\-]5\.1\.1', '550 5.1.1 - User unknown'),
        (r'550[\s\-]5\.1\.2', '550 5.1.2 - Bad destination'),
        (r'551[\s\-]', '551 - User not local'),
        (r'552[\s\-]', '552 - Message too large'),
        (r'553[\s\-]', '553 - Mailbox name invalid'),
        (r'554[\s\-]5\.7\.1', '554 5.7.1 - Relay denied'),
        (r'550.*user.*unknown', '550 User unknown'),
        (r'550.*invalid', '550 Invalid address'),
    ],
    
    BounceType.SOFT: [
        # Temporary issues
        (r'mailbox.*full', 'Mailbox full'),
        (r'quota.*exceeded', 'Quota exceeded'),
        (r'over.*quota', 'Over quota'),
        (r'insufficient.*storage', 'Insufficient storage'),
        (r'temporarily.*unavailable', 'Temporarily unavailable'),
        (r'try.*again.*later', 'Try again later'),
        (r'too.*many.*connections', 'Too many connections'),
        (r'service.*unavailable', 'Service unavailable'),
        (r'connection.*timed.*out', 'Connection timeout'),
        (r'greylist', 'Greylisted'),
        
        # SMTP codes - temporary failures
        (r'421[\s\-]', '421 - Service unavailable'),
        (r'450[\s\-]', '450 - Mailbox busy'),
        (r'451[\s\-]', '451 - Local error'),
        (r'452[\s\-]', '452 - Insufficient storage'),
        (r'4\.2\.2', '4.2.2 - Mailbox full'),
        (r'4\.4\.2', '4.4.2 - Timeout'),
        (r'4\.7\.0', '4.7.0 - IP reputation'),
    ],
    
    BounceType.SPAM: [
        # Spam detection
        (r'spam.*detected', 'Spam detected'),
        (r'blocked.*spam', 'Blocked as spam'),
        (r'rejected.*spam', 'Rejected as spam'),
        (r'blacklist', 'Blacklisted'),
        (r'blocklist', 'Blocklisted'),
        (r'content.*rejected', 'Content rejected'),
        (r'message.*refused', 'Message refused'),
        (r'policy.*violation', 'Policy violation'),
        (r'dmarc.*reject', 'DMARC rejection'),
        (r'spf.*fail', 'SPF failure'),
        
        # SMTP codes - spam related
        (r'550.*spam', '550 Spam'),
        (r'554.*spam', '554 Spam'),
        (r'5\.7\.1.*spam', '5.7.1 Spam'),
    ],
    
    BounceType.COMPLAINT: [
        (r'complaint', 'User complaint'),
        (r'abuse', 'Abuse report'),
        (r'reported.*spam', 'Reported as spam'),
        (r'marked.*spam', 'Marked as spam'),
    ],
}


class BounceService:
    """
    Comprehensive bounce handling service.
    
    Usage:
        service = BounceService()
        result = service.process_bounce(email_id, error_message, org_id)
    """
    
    def __init__(self, db_connection=None):
        self.db = db_connection
        self._init_db()
    
    def _init_db(self):
        """Initialize database connection if not provided"""
        if self.db is None:
            import psycopg2
            self.db = psycopg2.connect(
                host='localhost',
                database='emailer',
                user='emailer',
                password='SecurePassword123'
            )
    
    def _get_cursor(self):
        """Get database cursor"""
        return self.db.cursor()
    
    # =========================================================================
    # BOUNCE CLASSIFICATION
    # =========================================================================
    
    def classify_bounce(self, error_message: str) -> Tuple[BounceType, str, BounceAction]:
        """
        Classify bounce based on error message.
        
        Returns:
            (bounce_type, reason, action)
        """
        if not error_message:
            return BounceType.UNKNOWN, 'Unknown error', BounceAction.NONE
        
        error_lower = error_message.lower()
        
        # Check patterns in order of severity
        for bounce_type in [BounceType.COMPLAINT, BounceType.SPAM, 
                           BounceType.HARD, BounceType.SOFT]:
            patterns = BOUNCE_PATTERNS.get(bounce_type, [])
            for pattern, reason in patterns:
                if re.search(pattern, error_lower):
                    action = self._get_action_for_type(bounce_type)
                    return bounce_type, reason, action
        
        return BounceType.UNKNOWN, 'Unclassified bounce', BounceAction.NONE
    
    def _get_action_for_type(self, bounce_type: BounceType) -> BounceAction:
        """Determine action based on bounce type"""
        if bounce_type in [BounceType.HARD, BounceType.SPAM, BounceType.COMPLAINT]:
            return BounceAction.SUPPRESS
        elif bounce_type == BounceType.SOFT:
            return BounceAction.RETRY
        return BounceAction.NONE
    
    # =========================================================================
    # BOUNCE PROCESSING
    # =========================================================================
    
    def process_bounce(self, email_id: str, error_message: str, 
                      org_id: str = None, email_address: str = None,
                      campaign_id: str = None) -> Dict:
        """
        Process a bounce event.
        
        Args:
            email_id: ID of the bounced email
            error_message: Error/bounce message from SMTP
            org_id: Organization ID
            email_address: Recipient email (if known)
            campaign_id: Campaign ID (if applicable)
        
        Returns:
            Dict with processing results
        """
        try:
            cur = self._get_cursor()
            
            # Get email details if not provided
            if not email_address or not org_id:
                cur.execute("""
                    SELECT to_email, recipient, organization_id, campaign_id 
                    FROM emails WHERE id = %s
                """, (email_id,))
                row = cur.fetchone()
                if row:
                    email_address = row[0] or row[1]
                    org_id = row[2]
                    campaign_id = campaign_id or row[3]
            
            if not email_address:
                return {'success': False, 'error': 'Email address not found'}
            
            email_address = email_address.lower().strip()
            
            # Classify the bounce
            bounce_type, reason, action = self.classify_bounce(error_message)
            
            logger.info(f"Bounce: {email_address} - Type: {bounce_type.value} - {reason}")
            
            # Record the bounce
            bounce_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO email_bounces (id, email_id, bounce_type, reason, bounced_at)
                VALUES (%s, %s, %s, %s, NOW())
            """, (bounce_id, email_id, bounce_type.value, reason))
            
            # Update email status
            cur.execute("""
                UPDATE emails SET status = 'bounced', error_message = %s, updated_at = NOW()
                WHERE id = %s
            """, (f"{bounce_type.value}: {reason}", email_id))
            
            self.db.commit()
            
            # Take action based on bounce type
            result = {
                'success': True,
                'email': email_address,
                'bounce_type': bounce_type.value,
                'reason': reason,
                'action': action.value,
                'suppressed': False,
                'campaign_paused': False
            }
            
            if action == BounceAction.SUPPRESS:
                self.add_to_suppression(email_address, org_id, bounce_type.value, reason)
                result['suppressed'] = True
            
            # Check bounce rate and pause if needed
            if campaign_id:
                should_pause, bounce_rate = self.check_bounce_rate(campaign_id, org_id)
                result['bounce_rate'] = bounce_rate
                if should_pause:
                    self.pause_campaign(campaign_id, f"Bounce rate too high: {bounce_rate:.1%}")
                    result['campaign_paused'] = True
            
            # Trigger webhook
            self.trigger_webhook(org_id, 'email.bounced', {
                'email': email_address,
                'email_id': email_id,
                'bounce_type': bounce_type.value,
                'reason': reason,
                'campaign_id': campaign_id,
                'timestamp': datetime.utcnow().isoformat()
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Process bounce error: {e}")
            self.db.rollback()
            return {'success': False, 'error': str(e)}
    
    # =========================================================================
    # SUPPRESSION LIST
    # =========================================================================
    
    def add_to_suppression(self, email: str, org_id: str, 
                          bounce_type: str, reason: str) -> bool:
        """Add email to suppression list"""
        try:
            email = email.lower().strip()
            cur = self._get_cursor()
            
            # Check if already suppressed
            cur.execute("""
                SELECT id, bounce_count FROM suppression_list WHERE email = %s
            """, (email,))
            existing = cur.fetchone()
            
            if existing:
                # Update bounce count
                cur.execute("""
                    UPDATE suppression_list 
                    SET bounce_count = bounce_count + 1, 
                        last_bounce_at = NOW(),
                        reason = %s
                    WHERE email = %s
                """, (reason, email))
            else:
                # Insert new suppression
                suppression_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO suppression_list (id, email, type, reason, added_at, bounce_count, last_bounce_at)
                    VALUES (%s, %s, %s, %s, NOW(), 1, NOW())
                """, (suppression_id, email, bounce_type, reason))
            
            self.db.commit()
            
            # Also add to Redis for fast lookups
            redis_client.sadd(f'suppression:{org_id}', email)
            redis_client.sadd('suppression:global', email)
            
            # Update contact status
            cur.execute("""
                UPDATE contacts SET status = 'bounced' 
                WHERE email = %s AND organization_id = %s
            """, (email, org_id))
            self.db.commit()
            
            logger.info(f"Added to suppression: {email} ({bounce_type})")
            return True
            
        except Exception as e:
            logger.error(f"Add to suppression error: {e}")
            self.db.rollback()
            return False
    
    def is_suppressed(self, email: str, org_id: str = None) -> Tuple[bool, Optional[Dict]]:
        """
        Check if email is suppressed.
        
        Returns:
            (is_suppressed, suppression_info)
        """
        email = email.lower().strip()
        
        # Fast Redis check first
        if redis_client.sismember('suppression:global', email):
            return True, {'source': 'global', 'email': email}
        
        if org_id and redis_client.sismember(f'suppression:{org_id}', email):
            return True, {'source': 'organization', 'email': email}
        
        # Database check for detailed info
        try:
            cur = self._get_cursor()
            cur.execute("""
                SELECT type, reason, added_at, bounce_count 
                FROM suppression_list WHERE email = %s
            """, (email,))
            row = cur.fetchone()
            
            if row:
                return True, {
                    'email': email,
                    'type': row[0],
                    'reason': row[1],
                    'added_at': row[2].isoformat() if row[2] else None,
                    'bounce_count': row[3]
                }
        except Exception as e:
            logger.error(f"Suppression check error: {e}")
        
        return False, None
    
    def remove_from_suppression(self, email: str, org_id: str = None) -> bool:
        """Remove email from suppression list"""
        try:
            email = email.lower().strip()
            cur = self._get_cursor()
            
            cur.execute("DELETE FROM suppression_list WHERE email = %s", (email,))
            self.db.commit()
            
            # Remove from Redis
            redis_client.srem('suppression:global', email)
            if org_id:
                redis_client.srem(f'suppression:{org_id}', email)
            
            logger.info(f"Removed from suppression: {email}")
            return True
            
        except Exception as e:
            logger.error(f"Remove from suppression error: {e}")
            return False
    
    # =========================================================================
    # BOUNCE RATE MONITORING
    # =========================================================================
    
    def check_bounce_rate(self, campaign_id: str, org_id: str, 
                         threshold: float = 0.05) -> Tuple[bool, float]:
        """
        Check bounce rate for a campaign.
        
        Args:
            campaign_id: Campaign ID
            org_id: Organization ID
            threshold: Max allowed bounce rate (default 5%)
        
        Returns:
            (should_pause, bounce_rate)
        """
        try:
            cur = self._get_cursor()
            
            # Get email stats for this campaign
            cur.execute("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'bounced' THEN 1 ELSE 0 END) as bounced,
                    SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent
                FROM emails
                WHERE campaign_id = %s
            """, (campaign_id,))
            
            row = cur.fetchone()
            total = row[0] or 0
            bounced = row[1] or 0
            sent = row[2] or 0
            
            # Calculate bounce rate (bounced / (sent + bounced))
            delivered = sent + bounced
            if delivered < 100:  # Need minimum sample size
                return False, 0.0
            
            bounce_rate = bounced / delivered if delivered > 0 else 0
            
            # Store in Redis for quick access
            redis_client.hset(f'campaign_stats:{campaign_id}', mapping={
                'total': total,
                'sent': sent,
                'bounced': bounced,
                'bounce_rate': f'{bounce_rate:.4f}'
            })
            
            should_pause = bounce_rate > threshold
            
            if should_pause:
                logger.warning(f"Campaign {campaign_id} bounce rate {bounce_rate:.2%} exceeds threshold {threshold:.2%}")
                
                # Send alert
                self.send_bounce_alert(org_id, campaign_id, bounce_rate)
            
            return should_pause, bounce_rate
            
        except Exception as e:
            logger.error(f"Check bounce rate error: {e}")
            return False, 0.0
    
    def get_bounce_stats(self, org_id: str, days: int = 7) -> Dict:
        """Get bounce statistics for an organization"""
        try:
            cur = self._get_cursor()
            
            cur.execute("""
                SELECT 
                    DATE(bounced_at) as date,
                    bounce_type,
                    COUNT(*) as count
                FROM email_bounces eb
                JOIN emails e ON eb.email_id = e.id
                WHERE e.organization_id = %s
                AND eb.bounced_at > NOW() - INTERVAL '%s days'
                GROUP BY DATE(bounced_at), bounce_type
                ORDER BY date DESC
            """, (org_id, days))
            
            rows = cur.fetchall()
            
            stats = {
                'by_date': {},
                'by_type': {'hard': 0, 'soft': 0, 'spam': 0, 'complaint': 0, 'unknown': 0},
                'total': 0
            }
            
            for row in rows:
                date_str = row[0].isoformat() if row[0] else 'unknown'
                bounce_type = row[1] or 'unknown'
                count = row[2]
                
                if date_str not in stats['by_date']:
                    stats['by_date'][date_str] = {'hard': 0, 'soft': 0, 'spam': 0, 'total': 0}
                
                stats['by_date'][date_str][bounce_type] = count
                stats['by_date'][date_str]['total'] += count
                stats['by_type'][bounce_type] += count
                stats['total'] += count
            
            return stats
            
        except Exception as e:
            logger.error(f"Get bounce stats error: {e}")
            return {}
    
    # =========================================================================
    # CAMPAIGN MANAGEMENT
    # =========================================================================
    
    def pause_campaign(self, campaign_id: str, reason: str) -> bool:
        """Pause a campaign due to high bounce rate"""
        try:
            cur = self._get_cursor()
            
            cur.execute("""
                UPDATE campaigns 
                SET status = 'paused', 
                    updated_at = NOW()
                WHERE id = %s AND status = 'sending'
                RETURNING organization_id, name
            """, (campaign_id,))
            
            row = cur.fetchone()
            self.db.commit()
            
            if row:
                org_id, name = row
                logger.warning(f"Paused campaign {name}: {reason}")
                
                # Store pause reason
                redis_client.hset(f'campaign:{campaign_id}', 'pause_reason', reason)
                
                # Trigger webhook
                self.trigger_webhook(org_id, 'campaign.paused', {
                    'campaign_id': campaign_id,
                    'campaign_name': name,
                    'reason': reason,
                    'timestamp': datetime.utcnow().isoformat()
                })
                
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Pause campaign error: {e}")
            self.db.rollback()
            return False
    
    # =========================================================================
    # WEBHOOKS
    # =========================================================================
    
    def trigger_webhook(self, org_id: str, event: str, data: Dict) -> bool:
        """Trigger a webhook for an event"""
        try:
            # Get webhook config
            config = redis_client.hgetall(f'webhook:{org_id}')
            
            if not config or config.get('enabled') != 'true':
                return False
            
            url = config.get('url')
            secret = config.get('secret')
            enabled_events = config.get('events', '').split(',')
            
            if not url or event not in enabled_events:
                return False
            
            # Prepare payload
            payload = {
                'event': event,
                'data': data,
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Sign payload
            payload_str = json.dumps(payload, sort_keys=True)
            signature = hmac.new(
                secret.encode(),
                payload_str.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Send webhook (async via celery would be better)
            headers = {
                'Content-Type': 'application/json',
                'X-SendBaba-Signature': signature,
                'X-SendBaba-Event': event
            }
            
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=10)
                logger.info(f"Webhook sent: {event} -> {url} ({response.status_code})")
                return response.status_code < 400
            except requests.RequestException as e:
                logger.warning(f"Webhook failed: {url} - {e}")
                
                # Queue for retry
                redis_client.lpush(f'webhook_retry:{org_id}', json.dumps({
                    'url': url,
                    'payload': payload,
                    'signature': signature,
                    'event': event,
                    'attempts': 1
                }))
                
                return False
                
        except Exception as e:
            logger.error(f"Trigger webhook error: {e}")
            return False
    
    # =========================================================================
    # ALERTS
    # =========================================================================
    
    def send_bounce_alert(self, org_id: str, campaign_id: str, bounce_rate: float):
        """Send alert when bounce rate is too high"""
        try:
            cur = self._get_cursor()
            
            # Get org email
            cur.execute("""
                SELECT u.email, c.name
                FROM users u
                JOIN organizations o ON u.organization_id = o.id
                JOIN campaigns c ON c.id = %s
                WHERE u.organization_id = %s AND u.role = 'owner'
                LIMIT 1
            """, (campaign_id, org_id))
            
            row = cur.fetchone()
            if not row:
                return
            
            owner_email, campaign_name = row
            
            # Log alert
            logger.warning(f"ALERT: Campaign '{campaign_name}' bounce rate {bounce_rate:.2%} - notifying {owner_email}")
            
            # TODO: Send actual email alert
            # For now, just log and store
            redis_client.lpush(f'alerts:{org_id}', json.dumps({
                'type': 'high_bounce_rate',
                'campaign_id': campaign_id,
                'campaign_name': campaign_name,
                'bounce_rate': f'{bounce_rate:.2%}',
                'timestamp': datetime.utcnow().isoformat()
            }))
            
        except Exception as e:
            logger.error(f"Send bounce alert error: {e}")


# =============================================================================
# FEEDBACK LOOP HANDLERS (Gmail, Yahoo, etc.)
# =============================================================================

class FeedbackLoopHandler:
    """
    Handle Feedback Loop (FBL) reports from ISPs.
    
    Gmail ARF: Abuse Reporting Format
    Yahoo CFL: Complaint Feedback Loop
    """
    
    def __init__(self, bounce_service: BounceService):
        self.bounce_service = bounce_service
    
    def process_arf_report(self, arf_data: Dict) -> Dict:
        """
        Process ARF (Abuse Reporting Format) report.
        
        ARF is used by Gmail, Yahoo, and other ISPs to report spam complaints.
        """
        try:
            # Extract email from ARF
            original_to = arf_data.get('Original-Rcpt-To') or arf_data.get('original_to')
            feedback_type = arf_data.get('Feedback-Type', 'abuse')
            
            if not original_to:
                return {'success': False, 'error': 'No recipient found in ARF'}
            
            # This is a complaint - add to suppression
            result = self.bounce_service.process_bounce(
                email_id=arf_data.get('email_id', str(uuid.uuid4())),
                error_message=f"Complaint: {feedback_type}",
                email_address=original_to
            )
            
            logger.info(f"Processed ARF complaint: {original_to}")
            return result
            
        except Exception as e:
            logger.error(f"Process ARF error: {e}")
            return {'success': False, 'error': str(e)}
    
    def process_gmail_postmaster(self, data: Dict) -> Dict:
        """
        Process Gmail Postmaster Tools data.
        
        This requires OAuth integration with Gmail Postmaster API.
        """
        # Placeholder for Gmail Postmaster integration
        logger.info("Gmail Postmaster data received")
        return {'success': True, 'message': 'Postmaster data logged'}


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================
_bounce_service = None

def get_bounce_service() -> BounceService:
    """Get singleton bounce service instance"""
    global _bounce_service
    if _bounce_service is None:
        _bounce_service = BounceService()
    return _bounce_service
