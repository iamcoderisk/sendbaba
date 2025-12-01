"""
Gunicorn Production Configuration
"""
import multiprocessing

# Server socket
bind = "0.0.0.0:5001"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 120
keepalive = 5

# Process naming
proc_name = "sendbaba"

# Logging
accesslog = "/var/log/sendbaba/access.log"
errorlog = "/var/log/sendbaba/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Server mechanics
daemon = False
pidfile = "/var/run/sendbaba/gunicorn.pid"
umask = 0
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
# keyfile = "/etc/ssl/private/sendbaba.key"
# certfile = "/etc/ssl/certs/sendbaba.crt"

def on_starting(server):
    pass

def on_reload(server):
    pass

def worker_int(worker):
    pass

def worker_abort(worker):
    pass
