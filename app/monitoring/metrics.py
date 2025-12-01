"""
Prometheus Metrics for SendBaba
"""
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
from functools import wraps
import time

# Create registry
REGISTRY = CollectorRegistry()

# Counters
EMAILS_SENT = Counter(
    'sendbaba_emails_sent_total',
    'Total emails sent',
    ['status', 'domain'],
    registry=REGISTRY
)

EMAILS_BOUNCED = Counter(
    'sendbaba_emails_bounced_total',
    'Total emails bounced',
    ['type'],
    registry=REGISTRY
)

WEBHOOK_DELIVERIES = Counter(
    'sendbaba_webhook_deliveries_total',
    'Total webhook deliveries',
    ['status', 'event'],
    registry=REGISTRY
)

# Histograms
EMAIL_SEND_DURATION = Histogram(
    'sendbaba_email_send_duration_seconds',
    'Time to send email',
    ['mx_server'],
    registry=REGISTRY
)

SMTP_CONNECTION_DURATION = Histogram(
    'sendbaba_smtp_connection_duration_seconds',
    'SMTP connection establishment time',
    registry=REGISTRY
)

# Gauges
QUEUE_SIZE = Gauge(
    'sendbaba_queue_size',
    'Current queue size',
    ['queue_name'],
    registry=REGISTRY
)

ACTIVE_WORKERS = Gauge(
    'sendbaba_active_workers',
    'Number of active Celery workers',
    registry=REGISTRY
)

WARMUP_PROGRESS = Gauge(
    'sendbaba_warmup_progress',
    'IP warmup progress percentage',
    ['ip'],
    registry=REGISTRY
)

CONNECTION_POOL_SIZE = Gauge(
    'sendbaba_connection_pool_size',
    'SMTP connection pool size',
    ['server'],
    registry=REGISTRY
)


def track_email_send(status: str, domain: str):
    """Track email send"""
    EMAILS_SENT.labels(status=status, domain=domain).inc()


def track_bounce(bounce_type: str):
    """Track bounce"""
    EMAILS_BOUNCED.labels(type=bounce_type).inc()


def track_webhook(status: str, event: str):
    """Track webhook delivery"""
    WEBHOOK_DELIVERIES.labels(status=status, event=event).inc()


def time_email_send(mx_server: str):
    """Decorator to time email sending"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                EMAIL_SEND_DURATION.labels(mx_server=mx_server).observe(time.time() - start)
        return wrapper
    return decorator


def get_metrics():
    """Generate Prometheus metrics"""
    return generate_latest(REGISTRY)
