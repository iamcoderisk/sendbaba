"""
Enhanced Email Worker - Redis Queue Processing
"""
import asyncio
import json
import signal
import sys
import os
from datetime import datetime
import redis
import logging

sys.path.insert(0, '/opt/sendbaba-staging')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - Worker - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from app.smtp.relay_server import send_via_relay


class EnhancedEmailWorker:
    """Enhanced email worker"""
    
    def __init__(self):
        self.running = True
        self.processed = 0
        self.failed = 0
        
        # Redis
        self.redis_client = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            decode_responses=True
        )
        
        self.redis_client.ping()
        logger.info("✅ Redis connected")
        
        # Database config (from your app/__init__.py)
        self.db_config = {
            'host': 'localhost',
            'database': 'emailer',  # Changed from emailer_staging
            'user': 'emailer',      # Changed from emailer_staging
            'password': 'SecurePassword123'
        }
        
        # Test DB connection
        try:
            import psycopg2
            conn = psycopg2.connect(**self.db_config)
            conn.close()
            logger.info("✅ Database connected")
        except Exception as e:
            logger.warning(f"⚠️  Database connection failed: {e}")
            logger.warning("Emails will still send, but won't update DB")
        
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
    
    def shutdown(self, signum, frame):
        logger.info("Shutting down...")
        self.running = False
    
    async def process_email(self, email_data: dict):
        """Process single email"""
        email_id = email_data.get('id', 'unknown')
        recipient = email_data.get('to')
        
        try:
            logger.info(f"📤 Sending to {recipient}")
            
            result = await send_via_relay(email_data)
            
            if result['success']:
                self.processed += 1
                logger.info(f"✅ Sent to {recipient}")
                
                # Update DB
                try:
                    self.update_db(email_id, 'sent')
                except Exception as db_err:
                    logger.warning(f"DB update skipped: {db_err}")
                
                return True
            else:
                retry_count = email_data.get('retry_count', 0)
                if retry_count < 3:
                    email_data['retry_count'] = retry_count + 1
                    self.redis_client.lpush('email_queue', json.dumps(email_data))
                    logger.info(f"↻ Requeued (attempt {retry_count + 1}/3)")
                else:
                    self.failed += 1
                    logger.error(f"❌ Failed after 3 retries")
                    try:
                        self.update_db(email_id, 'failed')
                    except:
                        pass
                
                return False
        
        except Exception as e:
            self.failed += 1
            logger.error(f"Error: {e}")
            return False
    
    def update_db(self, email_id: str, status: str):
        """Update email status in database"""
        try:
            import psycopg2
            
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            
            if status == 'sent':
                cursor.execute(
                    "UPDATE emails SET status = %s, sent_at = %s WHERE id = %s",
                    (status, datetime.utcnow(), email_id)
                )
            else:
                cursor.execute(
                    "UPDATE emails SET status = %s WHERE id = %s",
                    (status, email_id)
                )
            
            conn.commit()
            cursor.close()
            conn.close()
            logger.info(f"✅ DB updated: {email_id} -> {status}")
            
        except Exception as e:
            raise e
    
    async def start(self):
        """Start worker"""
        logger.info("🚀 Worker started")
        logger.info("Listening: email_queue, high_priority, outgoing_*")
        
        while self.running:
            try:
                email_data = None
                
                # Priority queues
                for priority in range(10, 0, -1):
                    result = self.redis_client.brpop(f'outgoing_{priority}', timeout=0.1)
                    if result:
                        email_data = json.loads(result[1])
                        logger.info(f"Got from outgoing_{priority}")
                        break
                
                # Standard queues
                if not email_data:
                    result = self.redis_client.brpop(['high_priority', 'email_queue'], timeout=1)
                    if result:
                        queue_name, data = result
                        email_data = json.loads(data)
                        logger.info(f"Got from {queue_name}")
                
                if email_data:
                    await self.process_email(email_data)
                else:
                    await asyncio.sleep(0.5)
                
                # Stats every 10 emails
                if (self.processed + self.failed) % 10 == 0 and (self.processed + self.failed) > 0:
                    logger.info(f"📊 Sent: {self.processed}, Failed: {self.failed}")
            
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(1)
        
        logger.info(f"Worker stopped. Sent: {self.processed}, Failed: {self.failed}")


def main():
    worker = EnhancedEmailWorker()
    asyncio.run(worker.start())


if __name__ == '__main__':
    main()
