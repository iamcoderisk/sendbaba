"""
SendBaba Celery Configuration
Production-grade task queue for bulk email
"""
from celery import Celery
from kombu import Queue, Exchange
import os

# Redis broker
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Create Celery app
celery_app = Celery(
    'sendbaba',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['app.tasks.email_tasks']
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Performance - process many tasks
    worker_prefetch_multiplier=10,
    worker_concurrency=8,
    
    # Task routing - priority queues
    task_queues=(
        Queue('high', Exchange('high'), routing_key='high', queue_arguments={'x-max-priority': 10}),
        Queue('default', Exchange('default'), routing_key='default', queue_arguments={'x-max-priority': 5}),
        Queue('low', Exchange('low'), routing_key='low', queue_arguments={'x-max-priority': 1}),
        Queue('bulk', Exchange('bulk'), routing_key='bulk'),
        Queue('retry', Exchange('retry'), routing_key='retry'),
    ),
    task_default_queue='default',
    task_default_exchange='default',
    task_default_routing_key='default',
    
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Rate limiting (per worker)
    task_annotations={
        'app.tasks.email_tasks.send_single_email': {
            'rate_limit': '100/s'  # 100 emails per second per worker
        },
        'app.tasks.email_tasks.send_bulk_batch': {
            'rate_limit': '10/s'  # 10 batches per second
        }
    },
    
    # Results expire after 1 hour
    result_expires=3600,
    
    # Beat schedule for periodic tasks
    beat_schedule={
        'process-retry-queue': {
            'task': 'app.tasks.email_tasks.process_retry_queue',
            'schedule': 60.0,  # Every minute
        },
        'update-campaign-stats': {
            'task': 'app.tasks.email_tasks.update_campaign_stats',
            'schedule': 30.0,  # Every 30 seconds
        },
        'cleanup-old-results': {
            'task': 'app.tasks.email_tasks.cleanup_old_results',
            'schedule': 3600.0,  # Every hour
        },
    },
)

# Task routes
celery_app.conf.task_routes = {
    'app.tasks.email_tasks.send_single_email': {'queue': 'default'},
    'app.tasks.email_tasks.send_bulk_batch': {'queue': 'bulk'},
    'app.tasks.email_tasks.send_high_priority': {'queue': 'high'},
    'app.tasks.email_tasks.retry_failed_email': {'queue': 'retry'},
}
