"""SendBaba Celery - Simple Config"""
from celery import Celery

celery_app = Celery(
    'sendbaba',
    broker='redis://:SendBaba2024SecureRedis@localhost:6379/0',
    backend='redis://:SendBaba2024SecureRedis@localhost:6379/0',
    include=['app.tasks.email_tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    task_acks_late=True,
    worker_prefetch_multiplier=4,
    beat_schedule={
        'process-queued-campaigns': {
            'task': 'app.tasks.email_tasks.process_queued_campaigns',
            'schedule': 30.0,
        },
        'process-queued-emails': {
            'task': 'app.tasks.email_tasks.process_queued_single_emails',
            'schedule': 30.0,
        },
    },
)
