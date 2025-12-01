"""
Prometheus Metrics Endpoint
"""
from flask import Blueprint, Response
from app.monitoring.metrics import get_metrics
import redis
import logging

logger = logging.getLogger(__name__)

metrics_bp = Blueprint('metrics', __name__)


@metrics_bp.route('/metrics')
def prometheus_metrics():
    """Prometheus metrics endpoint"""
    try:
        # Update queue sizes
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        
        from app.monitoring.metrics import QUEUE_SIZE
        
        for queue_name in ['email_queue', 'high', 'default', 'bulk', 'low']:
            size = r.llen(queue_name)
            QUEUE_SIZE.labels(queue_name=queue_name).set(size)
        
        return Response(get_metrics(), mimetype='text/plain')
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        return Response(f"# Error: {e}", mimetype='text/plain')
