"""
Auto-scaling Worker Manager
Dynamically adjusts worker count based on queue size
"""
import redis
import subprocess
import time
import logging
import os
import signal
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REDIS_HOST = 'localhost'
REDIS_PORT = 6379

# Configuration
MIN_WORKERS = 2
MAX_WORKERS = 20
SCALE_UP_THRESHOLD = 1000  # Queue size to trigger scale up
SCALE_DOWN_THRESHOLD = 100  # Queue size to trigger scale down
CHECK_INTERVAL = 30  # Seconds between checks

worker_pids = []


def get_queue_size() -> int:
    """Get total queue size"""
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    total = 0
    for queue in ['email_queue', 'high', 'default', 'bulk', 'low']:
        total += r.llen(queue)
    return total


def get_worker_count() -> int:
    """Get current worker count"""
    return len(worker_pids)


def start_worker():
    """Start a new Celery worker"""
    if len(worker_pids) >= MAX_WORKERS:
        logger.info(f"Max workers ({MAX_WORKERS}) reached")
        return
    
    worker_id = len(worker_pids) + 1
    cmd = [
        'celery', '-A', 'celery_app', 'worker',
        '--loglevel=info',
        f'--hostname=worker{worker_id}@%h',
        '--queues=high,default,bulk,low',
        '--concurrency=4'
    ]
    
    process = subprocess.Popen(
        cmd,
        cwd='/opt/sendbaba-staging',
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    worker_pids.append(process.pid)
    logger.info(f"Started worker {worker_id} (PID: {process.pid})")


def stop_worker():
    """Stop a worker"""
    if len(worker_pids) <= MIN_WORKERS:
        logger.info(f"Min workers ({MIN_WORKERS}) reached")
        return
    
    pid = worker_pids.pop()
    try:
        os.kill(pid, signal.SIGTERM)
        logger.info(f"Stopped worker (PID: {pid})")
    except ProcessLookupError:
        logger.warning(f"Worker {pid} already stopped")


def autoscale():
    """Main autoscaling loop"""
    logger.info(f"Autoscaler started (min={MIN_WORKERS}, max={MAX_WORKERS})")
    
    # Start minimum workers
    for _ in range(MIN_WORKERS):
        start_worker()
    
    while True:
        try:
            queue_size = get_queue_size()
            current_workers = get_worker_count()
            
            logger.info(f"Queue: {queue_size}, Workers: {current_workers}")
            
            # Scale up
            if queue_size > SCALE_UP_THRESHOLD * current_workers:
                workers_needed = min(
                    MAX_WORKERS - current_workers,
                    queue_size // SCALE_UP_THRESHOLD
                )
                for _ in range(workers_needed):
                    start_worker()
            
            # Scale down
            elif queue_size < SCALE_DOWN_THRESHOLD and current_workers > MIN_WORKERS:
                stop_worker()
            
            time.sleep(CHECK_INTERVAL)
        
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            for pid in worker_pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except:
                    pass
            sys.exit(0)
        
        except Exception as e:
            logger.error(f"Autoscaler error: {e}")
            time.sleep(CHECK_INTERVAL)


if __name__ == '__main__':
    autoscale()
