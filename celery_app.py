"""
SendBaba Celery Application
Production-grade task queue for bulk email
"""
from celery import Celery
from kombu import Queue, Exchange
import os

REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

celery_app = Celery(
    'sendbaba',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['tasks.email_tasks', 'tasks.warmup_tasks', 'tasks.webhook_tasks']
)

celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    # Performance
    worker_prefetch_multiplier=4,
    worker_concurrency=8,
    
    # Task queues with priorities
    task_queues=(
        Queue('high', Exchange('high'), routing_key='high', queue_arguments={'x-max-priority': 10}),
        Queue('default', Exchange('default'), routing_key='default', queue_arguments={'x-max-priority': 5}),
        Queue('bulk', Exchange('bulk'), routing_key='bulk', queue_arguments={'x-max-priority': 3}),
        Queue('low', Exchange('low'), routing_key='low', queue_arguments={'x-max-priority': 1}),
    ),
    task_default_queue='default',
    
    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Rate limiting per task
    task_annotations={
        'tasks.email_tasks.send_single_email': {'rate_limit': '100/s'},
        'tasks.email_tasks.send_bulk_batch': {'rate_limit': '10/s'},
    },
    
    # Results
    result_expires=3600,
    
    # Beat schedule for periodic tasks
    beat_schedule={
        'process-bounce-queue': {
            'task': 'tasks.email_tasks.process_bounces',
            'schedule': 60.0,
        },
        'update-warmup-stats': {
            'task': 'tasks.warmup_tasks.update_warmup_progress',
            'schedule': 300.0,
        },
        'process-webhooks': {
            'task': 'tasks.webhook_tasks.process_webhook_queue',
            'schedule': 5.0,
        },
        'cleanup-old-tracking': {
            'task': 'tasks.email_tasks.cleanup_old_tracking',
            'schedule': 86400.0,
        },
    },
)
