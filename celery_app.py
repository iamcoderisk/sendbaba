"""
SendBaba Celery Configuration - Staging
=======================================
"""
from celery import Celery
from config.redis_config import REDIS_URL

celery_app = Celery(
    'sendbaba',
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=['app.tasks.email_tasks', 'app.tasks.turbo_sender', 'app.tasks.distributed_sender']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    task_acks_late=True,
    worker_prefetch_multiplier=4,
    task_soft_time_limit=3600,
    task_time_limit=7200,
    result_expires=86400,
    
    beat_schedule={
        'process-queued-campaigns': {
            'task': 'app.tasks.email_tasks.process_queued_campaigns',
            'schedule': 5.0,
        },
        'process-queued-emails': {
            'task': 'app.tasks.email_tasks.process_queued_single_emails',
            'schedule': 5.0,
        },
        'finalize-campaigns': {
            'task': 'app.tasks.email_tasks.finalize_campaigns',
            'schedule': 10.0,
        },
        'sync-tracking-to-db': {
            'task': 'app.tasks.email_tasks.sync_tracking_to_db',
            'schedule': 30.0,
        },
        'recover-stuck-campaigns': {
            'task': 'app.tasks.email_tasks.recover_stuck_campaigns',
            'schedule': 120.0,
        },
        'process-bounces': {
            'task': 'app.tasks.email_tasks.process_bounces',
            'schedule': 300.0,
        },
        'reset-daily-counters': {
            'task': 'app.tasks.email_tasks.reset_daily_counters',
            'schedule': 3600.0,
        },
    },
)
