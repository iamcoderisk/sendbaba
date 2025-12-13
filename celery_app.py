"""
SendBaba Celery Configuration
=============================
Production-ready configuration with:
- Fast campaign processing (10s intervals)
- Stuck campaign recovery
- Email validation integration
"""
from celery import Celery

celery_app = Celery(
    'sendbaba',
    broker='redis://:SendBaba2024SecureRedis@localhost:6379/0',
    backend='redis://:SendBaba2024SecureRedis@localhost:6379/0',
    include=['app.tasks.email_tasks']
)

celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    
    # Task execution
    task_acks_late=True,
    worker_prefetch_multiplier=2,
    task_soft_time_limit=3600,
    task_time_limit=7200,
    
    # Result backend
    result_expires=86400,
    
    # Beat schedule - 10 SECOND intervals
    beat_schedule={
        'process-queued-campaigns': {
            'task': 'app.tasks.email_tasks.process_queued_campaigns',
            'schedule': 10.0,  # Every 10 seconds
        },
        'process-queued-emails': {
            'task': 'app.tasks.email_tasks.process_queued_single_emails',
            'schedule': 10.0,  # Every 10 seconds
        },
        'sync-tracking-to-db': {
            'task': 'app.tasks.email_tasks.sync_tracking_to_db',
            'schedule': 30.0,  # Every 30 seconds
        },
        'recover-stuck-campaigns': {
            'task': 'app.tasks.email_tasks.recover_stuck_campaigns',
            'schedule': 60.0,  # Every minute
        },
        'reset-daily-counters': {
            'task': 'app.tasks.email_tasks.reset_daily_counters',
            'schedule': 3600.0,  # Every hour
        },
    },
)
