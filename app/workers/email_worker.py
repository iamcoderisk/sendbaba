"""
Multi-tenant Email Worker
"""
import sys
import time
import logging
from datetime import datetime

sys.path.insert(0, '/opt/sendbaba-staging')

from app import create_app, db
from sqlalchemy import text
from app.smtp.relay_server import send_email_sync
from app.smtp.email_sender import prepare_email_data

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('/var/log/sendbaba-worker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = create_app()

stats = {
    'processed': 0,
    'sent': 0,
    'failed': 0,
    'start_time': time.time()
}


def process_queue():
    """Process email queue"""
    with app.app_context():
        try:
            # Get queued emails with organization context
            result = db.session.execute(text("""
                SELECT 
                    e.id, e.organization_id, e.sender, e.recipient, 
                    e.subject, e.html_body, e.text_body, e.campaign_id
                FROM emails e
                WHERE e.status = 'queued'
                ORDER BY e.created_at ASC
                LIMIT 10
            """))
            
            emails = result.fetchall()
            
            if not emails:
                return 0
            
            logger.info(f"📧 Processing {len(emails)} emails...")
            
            for email_row in emails:
                try:
                    # Prepare email with verified domain
                    email_data = prepare_email_data(email_row)
                    email_id = email_data['id']
                    recipient = email_data['to']
                    
                    logger.info(f"Sending from {email_data['from']} to {recipient}")
                    
                    # Send via relay
                    result = send_email_sync(email_data)
                    
                    if result.get('success'):
                        # Success
                        db.session.execute(text("""
                            UPDATE emails 
                            SET status = 'sent', sent_at = :sent_at
                            WHERE id = :id
                        """), {
                            'id': email_id,
                            'sent_at': datetime.utcnow()
                        })
                        
                        stats['sent'] += 1
                        logger.info(f"✅ {recipient} via {result.get('mx_server')}")
                    
                    else:
                        # Failure
                        error_msg = result.get('message', 'Unknown error')
                        
                        if result.get('bounce') and result.get('bounce_type') == 'hard':
                            status = 'bounced'
                        elif result.get('retry'):
                            status = 'failed'
                        else:
                            status = 'failed'
                        
                        db.session.execute(text("""
                            UPDATE emails 
                            SET status = :status, error_message = :error
                            WHERE id = :id
                        """), {
                            'id': email_id,
                            'status': status,
                            'error': error_msg[:500]  # Limit error length
                        })
                        
                        stats['failed'] += 1
                        logger.error(f"❌ {recipient}: {error_msg}")
                    
                    stats['processed'] += 1
                    db.session.commit()
                
                except Exception as e:
                    logger.error(f"Error processing email: {e}", exc_info=True)
                    db.session.rollback()
            
            return len(emails)
            
        except Exception as e:
            logger.error(f"Queue error: {e}", exc_info=True)
            db.session.rollback()
            return 0


def log_stats():
    """Log statistics"""
    uptime = time.time() - stats['start_time']
    rate = stats['sent'] / uptime if uptime > 0 else 0
    
    logger.info(f"""
    📊 Worker Stats:
       Processed: {stats['processed']}
       Sent: {stats['sent']} ({rate:.2f}/sec)
       Failed: {stats['failed']}
       Uptime: {uptime/60:.1f} min
    """)


if __name__ == '__main__':
    logger.info("🚀 SendBaba Multi-tenant Email Worker")
    
    last_stats = time.time()
    
    try:
        while True:
            processed = process_queue()
            
            # Log stats every 5 minutes
            if time.time() - last_stats > 300:
                log_stats()
                last_stats = time.time()
            
            # Smart sleep
            if processed > 0:
                time.sleep(1)
            else:
                time.sleep(5)
    
    except KeyboardInterrupt:
        logger.info("👋 Worker stopped")
        log_stats()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        log_stats()
