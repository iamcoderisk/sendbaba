"""
SendBaba Email Tasks - Production Ready v4
==========================================
Full SendGrid/Mailchimp-like functionality:
- Multi-tenant support
- High-speed distributed sending (100k+ emails in 10 min)
- Email validation & auto-correction
- Domain-based rate limiting
- Suppression list checking
- Real-time progress monitoring
- Stuck campaign recovery
- Campaign finalization
"""
import os
import sys
import uuid
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
import time
import redis
from datetime import datetime, timedelta

sys.path.insert(0, '/opt/sendbaba-staging')

from celery_app import celery_app
from config.redis_config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
from app.smtp.relay_server import send_email_sync
from app.services.email_tracker import prepare_email_for_tracking

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Redis client using central config
redis_client = redis.Redis(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    password=REDIS_PASSWORD, 
    decode_responses=True
)

# Rate limits per domain (emails per minute) - like SendGrid/Mailchimp
DOMAIN_RATE_LIMITS = {
    'gmail.com': 50,
    'googlemail.com': 50,
    'yahoo.com': 40,
    'yahoo.co.uk': 40,
    'hotmail.com': 40,
    'outlook.com': 40,
    'live.com': 40,
    'msn.com': 40,
    'aol.com': 30,
    'icloud.com': 30,
    'me.com': 30,
    'default': 100,
}


def get_db_connection():
    """Get database connection"""
    import psycopg2
    return psycopg2.connect(
        host='localhost',
        database='emailer',
        user='emailer',
        password='SecurePassword123'
    )


def validate_and_fix_email(email):
    """Validate and auto-correct email typos"""
    if not email or '@' not in email:
        return False, email, 'invalid_format'
    
    email = email.strip().lower()
    
    # Common typo fixes
    typo_fixes = {
        '@gmial.com': '@gmail.com',
        '@gmai.com': '@gmail.com',
        '@gmail.co': '@gmail.com',
        '@gamil.com': '@gmail.com',
        '@yaho.com': '@yahoo.com',
        '@yahooo.com': '@yahoo.com',
        '@hotmal.com': '@hotmail.com',
        '@hotmial.com': '@hotmail.com',
        '@outlok.com': '@outlook.com',
    }
    
    for typo, fix in typo_fixes.items():
        if typo in email:
            email = email.replace(typo, fix)
    
    return True, email, None


def personalize(content: str, contact: dict) -> str:
    """Replace merge tags with contact data"""
    if not content:
        return content
    
    replacements = {
        '{{first_name}}': contact.get('first_name', ''),
        '{{last_name}}': contact.get('last_name', ''),
        '{{email}}': contact.get('email', ''),
        '{{FIRST_NAME}}': contact.get('first_name', ''),
        '{{LAST_NAME}}': contact.get('last_name', ''),
        '*|FNAME|*': contact.get('first_name', ''),
        '*|LNAME|*': contact.get('last_name', ''),
        '*|EMAIL|*': contact.get('email', ''),
        '{{company}}': contact.get('company', ''),
        '{{phone}}': contact.get('phone', ''),
    }
    
    for tag, value in replacements.items():
        content = content.replace(tag, str(value or ''))
    
    return content


def is_gmail(email):
    """Check if email is Gmail/Google"""
    if not email:
        return False
    domain = email.split('@')[-1].lower()
    return domain in ['gmail.com', 'googlemail.com'] or 'google' in domain


def check_gmail_throttle():
    """Check if we should throttle Gmail sends"""
    key = f"gmail_throttle:{datetime.now().strftime('%Y%m%d%H%M')}"
    count = redis_client.incr(key)
    redis_client.expire(key, 120)
    
    if count > 200:
        return True, count
    return False, count


def check_rate_limit(domain, org_id):
    """Check if we're within rate limits for a domain (per org)"""
    key = f"rate:{org_id}:{domain}:{datetime.now().strftime('%Y%m%d%H%M')}"
    count = redis_client.incr(key)
    redis_client.expire(key, 120)
    
    limit = DOMAIN_RATE_LIMITS.get(domain, DOMAIN_RATE_LIMITS['default'])
    return count <= limit, count, limit


def check_suppression(email, org_id):
    """Check if email is in suppression list"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT reason FROM suppressions 
            WHERE organization_id = %s AND email = %s
        """, (org_id, email.lower()))
        row = cursor.fetchone()
        return row[0] if row else None
    except:
        return None
    finally:
        cursor.close()
        conn.close()


def add_to_suppression(email, org_id, reason, source=None):
    """Add email to suppression list"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO suppressions (organization_id, email, reason, source, created_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (organization_id, email) DO NOTHING
        """, (org_id, email.lower(), reason, source))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to add suppression: {e}")
    finally:
        cursor.close()
        conn.close()


def log_email_event(org_id, email_id, campaign_id, recipient, event_type, event_data=None):
    """Log email event for analytics"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO email_events (organization_id, email_id, campaign_id, recipient, event_type, event_data, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
        """, (org_id, email_id, campaign_id, recipient, event_type, 
              json.dumps(event_data) if event_data else '{}'))
        conn.commit()
    except Exception as e:
        logger.debug(f"Event log error: {e}")
    finally:
        cursor.close()
        conn.close()


def update_progress(campaign_id, sent, failed, total, status='sending'):
    """Update campaign progress in Redis for real-time monitoring"""
    key = f"campaign_progress:{campaign_id}"
    redis_client.hset(key, mapping={
        'sent': sent,
        'failed': failed,
        'total': total,
        'status': status,
        'percent': int((sent + failed) / total * 100) if total > 0 else 0,
        'updated_at': datetime.now().isoformat()
    })
    redis_client.expire(key, 86400)


# =============================================================================
# CAMPAIGN TASKS
# =============================================================================

@celery_app.task(name='app.tasks.email_tasks.process_queued_campaigns')
def process_queued_campaigns():
    """Process campaigns in 'queued' status - launches distributed sending"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Only get QUEUED campaigns
        cursor.execute("""
            SELECT id, name, organization_id FROM campaigns
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 5
        """)
        
        campaigns = cursor.fetchall()
        processed = 0
        
        for campaign_id, name, org_id in campaigns:
            logger.info(f"🚀 Launching campaign: {name} ({campaign_id})")
            
            # Atomically update status
            cursor.execute("""
                UPDATE campaigns 
                SET status = 'sending', started_at = NOW(), updated_at = NOW()
                WHERE id = %s AND status = 'queued'
                RETURNING id
            """, (campaign_id,))
            
            result = cursor.fetchone()
            conn.commit()
            
            if result:
                try:
                    from app.tasks.distributed_sender import launch_campaign
                    launch_result = launch_campaign(campaign_id, chunk_size=2000)
                    
                    if launch_result.get('success'):
                        processed += 1
                        logger.info(f"✅ Campaign launched: {name} - {launch_result.get('total_contacts', 0)} contacts")
                    else:
                        logger.error(f"❌ Campaign {name} launch failed: {launch_result.get('error')}")
                        cursor.execute("UPDATE campaigns SET status = 'failed', updated_at = NOW() WHERE id = %s", (campaign_id,))
                        conn.commit()
                        
                except Exception as e:
                    logger.error(f"❌ Campaign {name} error: {e}")
                    cursor.execute("UPDATE campaigns SET status = 'failed', updated_at = NOW() WHERE id = %s", (campaign_id,))
                    conn.commit()
        
        return {'processed': processed}
        
    except Exception as e:
        logger.error(f"process_queued_campaigns error: {e}")
        return {'processed': 0, 'error': str(e)}
    finally:
        cursor.close()
        conn.close()


@celery_app.task(name='app.tasks.email_tasks.finalize_campaigns')
def finalize_campaigns():
    """Finalize campaigns that have all emails sent but status still 'sending'"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            WITH campaign_stats AS (
                SELECT 
                    c.id,
                    c.name,
                    c.total_recipients,
                    COUNT(e.id) as email_count,
                    COUNT(e.id) FILTER (WHERE e.status = 'sent') as sent_count,
                    COUNT(e.id) FILTER (WHERE e.status = 'failed') as failed_count
                FROM campaigns c
                LEFT JOIN emails e ON e.campaign_id = c.id
                WHERE c.status = 'sending'
                AND c.total_recipients > 0
                GROUP BY c.id, c.name, c.total_recipients
            )
            UPDATE campaigns c
            SET 
                status = 'completed',
                completed_at = NOW(),
                sent_count = cs.sent_count,
                failed_count = cs.failed_count,
                updated_at = NOW()
            FROM campaign_stats cs
            WHERE c.id = cs.id
            AND cs.email_count >= cs.total_recipients
            RETURNING c.id, c.name, cs.sent_count, cs.failed_count
        """)
        
        finalized = cursor.fetchall()
        conn.commit()
        
        for campaign_id, name, sent, failed in finalized:
            logger.info(f"✅ Finalized campaign: {name} - {sent} sent, {failed} failed")
        
        return {'finalized': len(finalized)}
        
    except Exception as e:
        logger.error(f"finalize_campaigns error: {e}")
        return {'finalized': 0, 'error': str(e)}
    finally:
        cursor.close()
        conn.close()


@celery_app.task(name='app.tasks.email_tasks.execute_campaign', max_retries=3)
def execute_campaign(campaign_id: str):
    """Execute campaign using distributed sending"""
    logger.info(f"🚀 Starting distributed campaign: {campaign_id}")
    
    try:
        from app.tasks.distributed_sender import launch_campaign
        result = launch_campaign(campaign_id, chunk_size=2000)
        
        if result.get('success'):
            logger.info(f"✅ Campaign {campaign_id} launched: {result.get('chunks', 0)} chunks")
            return result
        else:
            logger.error(f"❌ Campaign launch failed: {result.get('error')}")
            return result
            
    except Exception as e:
        logger.error(f"❌ Campaign {campaign_id} error: {str(e)}")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE campaigns SET status = 'failed' WHERE id = %s", (campaign_id,))
        conn.commit()
        cursor.close()
        conn.close()
        raise


@celery_app.task(name='app.tasks.email_tasks.send_campaign', max_retries=3, soft_time_limit=7200)
def send_campaign(campaign_id: str):
    """Celery task wrapper for execute_campaign"""
    return execute_campaign(campaign_id)


@celery_app.task(name='app.tasks.email_tasks.recover_stuck_campaigns')
def recover_stuck_campaigns():
    """Recover campaigns stuck in 'sending' status for too long"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT c.id, c.name, c.total_recipients,
                   (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id AND status = 'sent') as actual_sent,
                   (SELECT COUNT(*) FROM emails WHERE campaign_id = c.id) as total_emails
            FROM campaigns c
            WHERE c.status = 'sending'
            AND c.updated_at < NOW() - INTERVAL '30 minutes'
            LIMIT 5
        """)
        
        stuck = cursor.fetchall()
        recovered = 0
        
        for campaign_id, name, total, actual_sent, total_emails in stuck:
            logger.warning(f"⚠️ Recovering stuck campaign: {name} ({actual_sent}/{total} sent)")
            
            if total_emails >= total:
                cursor.execute("""
                    UPDATE campaigns 
                    SET status = 'completed', sent_count = %s, completed_at = NOW(), updated_at = NOW()
                    WHERE id = %s
                """, (actual_sent, campaign_id))
                logger.info(f"✅ Completed: {name}")
            elif actual_sent == 0 and total_emails == 0:
                cursor.execute("""
                    UPDATE campaigns 
                    SET status = 'queued', started_at = NULL, updated_at = NOW()
                    WHERE id = %s
                """, (campaign_id,))
                logger.info(f"🔄 Reset to queued: {name}")
            else:
                cursor.execute("""
                    UPDATE campaigns 
                    SET sent_count = %s, updated_at = NOW()
                    WHERE id = %s
                """, (actual_sent, campaign_id))
                logger.info(f"📊 Updated stats: {name}")
            
            conn.commit()
            recovered += 1
        
        return {'recovered': recovered}
        
    except Exception as e:
        logger.error(f"recover_stuck_campaigns error: {e}")
        return {'recovered': 0, 'error': str(e)}
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# SINGLE EMAIL TASKS
# =============================================================================

@celery_app.task(name='app.tasks.email_tasks.process_queued_single_emails')
def process_queued_single_emails():
    """Process single emails in 'queued' status"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id FROM single_emails 
            WHERE status = 'queued' 
            ORDER BY created_at ASC 
            LIMIT 1000
        """)
        emails = cursor.fetchall()
        count = 0
        
        for (email_id,) in emails:
            send_single_email_task.delay(str(email_id))
            count += 1
        
        if count > 0:
            logger.info(f"📬 Queued {count} single emails for sending")
        
        return {'queued_count': count}
        
    except Exception as e:
        logger.error(f"process_queued_single_emails error: {e}")
        return {'queued_count': 0, 'error': str(e)}
    finally:
        cursor.close()
        conn.close()


@celery_app.task(name='app.tasks.email_tasks.send_single_email_task')
def send_single_email_task(email_id):
    """Send a single email by ID"""
    if email_id is None:
        return {'success': False, 'error': 'email_id is None'}
    
    if isinstance(email_id, dict):
        email_id = email_id.get('id') or email_id.get('email_id')
        if not email_id:
            return {'success': False, 'error': 'Invalid dict format'}
    
    email_id = str(email_id)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT id, recipient_email, subject, html_body, body, organization_id, from_email, from_name
            FROM single_emails WHERE id = %s
        """, (email_id,))
        
        row = cursor.fetchone()
        if not row:
            return {'success': False, 'error': f'Email {email_id} not found'}
        
        email_info = {
            'id': row[0], 'to': row[1], 'subject': row[2], 
            'html_body': row[3], 'text_body': row[4], 'org_id': row[5],
            'from_email': row[6], 'from_name': row[7]
        }
        
        # Check suppression
        suppression_reason = check_suppression(email_info['to'], email_info['org_id'])
        if suppression_reason:
            cursor.execute("UPDATE single_emails SET status = 'suppressed' WHERE id = %s", (email_id,))
            conn.commit()
            return {'success': False, 'error': f'Suppressed: {suppression_reason}'}
        
        # Get sender domain
        from_email = email_info.get('from_email')
        if not from_email:
            cursor.execute("SELECT domain_name FROM domains WHERE organization_id = %s AND status = 'verified' LIMIT 1", (email_info['org_id'],))
            domain_row = cursor.fetchone()
            from_email = f"noreply@{domain_row[0]}" if domain_row else 'noreply@sendbaba.com'
        
        from_name = email_info.get('from_name') or 'SendBaba'
        
        # Validate
        is_valid, to_email, reason = validate_and_fix_email(email_info['to'])
        if not is_valid:
            cursor.execute("UPDATE single_emails SET status = 'failed' WHERE id = %s", (email_id,))
            conn.commit()
            return {'success': False, 'error': f'Invalid email: {reason}'}
        
        result = send_email_sync({
            'from': from_email, 'from_name': from_name, 'to': to_email,
            'subject': email_info.get('subject', ''), 
            'html_body': email_info.get('html_body', ''), 
            'text_body': email_info.get('text_body', '')
        })
        
        status = 'sent' if result.get('success') else 'failed'
        cursor.execute("UPDATE single_emails SET status = %s, sent_at = NOW() WHERE id = %s", (status, email_id))
        conn.commit()
        
        return result
        
    except Exception as e:
        logger.error(f"Single email error: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        cursor.close()
        conn.close()


# =============================================================================
# TRACKING & ANALYTICS TASKS
# =============================================================================

@celery_app.task(name='app.tasks.email_tasks.sync_tracking_to_db')
def sync_tracking_to_db():
    """Sync tracking data from Redis to PostgreSQL"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        keys = redis_client.keys('track:*')
        synced = 0
        
        for key in keys[:100]:
            try:
                data = redis_client.hgetall(key)
                if not data or not data.get('email_id'):
                    continue
                
                email_id = data['email_id']
                
                if data.get('opened'):
                    cursor.execute("""
                        UPDATE emails SET 
                            status = CASE WHEN status = 'sent' THEN 'opened' ELSE status END,
                            opened_at = COALESCE(opened_at, NOW()), 
                            open_count = COALESCE(open_count, 0) + 1 
                        WHERE id = %s
                    """, (email_id,))
                
                if data.get('clicked'):
                    cursor.execute("""
                        UPDATE emails SET 
                            status = 'clicked', 
                            clicked_at = COALESCE(clicked_at, NOW()),
                            click_count = COALESCE(click_count, 0) + 1 
                        WHERE id = %s
                    """, (email_id,))
                
                conn.commit()
                redis_client.delete(key)
                synced += 1
                
            except Exception as e:
                conn.rollback()
        
        cursor.close()
        conn.close()
        
        return {'synced': synced}
        
    except Exception as e:
        logger.error(f"Tracking sync error: {e}")
        return {'synced': 0, 'error': str(e)}


@celery_app.task(name='app.tasks.email_tasks.reset_daily_counters')
def reset_daily_counters():
    """Reset daily email counters for IP warmup"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            UPDATE ip_pools SET sent_today = 0, last_reset_at = NOW() 
            WHERE last_reset_at IS NULL OR last_reset_at::date < CURRENT_DATE
        """)
        count = cursor.rowcount
        conn.commit()
        
        if count > 0:
            logger.info(f"🔄 Reset daily counters for {count} IPs")
        
        return {'reset': count}
        
    except Exception as e:
        logger.error(f"reset_daily_counters error: {e}")
        return {'reset': 0, 'error': str(e)}
    finally:
        cursor.close()
        conn.close()


@celery_app.task(name='app.tasks.email_tasks.process_bounces')
def process_bounces():
    """Process bounce records and add to suppression list"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT DISTINCT e.recipient, e.organization_id
            FROM emails e
            WHERE e.status = 'bounced'
            AND e.error_message LIKE '%5.1.1%'
            AND NOT EXISTS (
                SELECT 1 FROM suppressions s 
                WHERE s.email = e.recipient AND s.organization_id = e.organization_id
            )
            LIMIT 100
        """)
        
        bounces = cursor.fetchall()
        added = 0
        
        for email, org_id in bounces:
            cursor.execute("""
                INSERT INTO suppressions (organization_id, email, reason, source, created_at)
                VALUES (%s, %s, 'hard_bounce', 'auto', NOW())
                ON CONFLICT (organization_id, email) DO NOTHING
            """, (org_id, email))
            added += 1
        
        conn.commit()
        
        if added > 0:
            logger.info(f"🚫 Added {added} bounced emails to suppression")
        
        return {'suppressed': added}
        
    except Exception as e:
        logger.error(f"process_bounces error: {e}")
        return {'suppressed': 0, 'error': str(e)}
    finally:
        cursor.close()
        conn.close()


@celery_app.task(name='app.tasks.email_tasks.fast_send_campaign', soft_time_limit=7200)
def fast_send_campaign_task(campaign_id: str, max_workers: int = 100):
    """High-speed parallel campaign sender"""
    try:
        from app.tasks.fast_sender import fast_send_campaign
        return fast_send_campaign(campaign_id, max_workers)
    except ImportError:
        return execute_campaign(campaign_id)

# Import the new distribution logic
from app.tasks.distributed_sender import launch_campaign, get_capacity_report

@celery_app.task
def get_worker_capacity():
    """Get capacity report for dashboard"""
    return get_capacity_report()
