"""
Gunicorn Configuration for Production Deployment
Manages multiple Python worker processes for handling concurrent requests
"""
import multiprocessing
import os

# Server socket
bind = "0.0.0.0:8000"
backlog = 2048  # Maximum number of pending connections

# Worker Processes
workers = multiprocessing.cpu_count() * 2 + 1  # (CPU cores × 2) + 1
# For 2-core laptop: 5 workers
# For 4-core server: 9 workers
# For 8-core server: 17 workers

worker_class = "uvicorn.workers.UvicornWorker"  # ASGI-compatible worker
worker_connections = 1000  # Max simultaneous clients per worker
max_requests = 1000  # Restart worker after 1000 requests (prevents memory leaks)
max_requests_jitter = 50  # Add randomness to prevent all workers restarting at once

# Timeouts
timeout = 45  # Worker timeout for accepting request (30s submission + 15s buffer)
keepalive = 5  # Keep connections alive for 5 seconds (reduces connection overhead)
graceful_timeout = 30  # Time for graceful worker shutdown

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"  # Log errors to stdout
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "vendor_backend"

# Server mechanics
daemon = False  # Run in foreground (for Docker/systemd compatibility)
pidfile = None  # No PID file needed
umask = 0
user = None
group = None
tmp_upload_dir = None

# Worker lifecycle
preload_app = False  # Don't preload app (allows per-worker initialization)

def on_starting(server):
    """Called just before the master process is initialized"""
    print(f"🚀 Gunicorn starting with {workers} workers")
    print(f"📊 Backlog: {backlog} connections")
    print(f"⏱️  Timeout: {timeout}s")
    print(f"🔄 Max requests per worker: {max_requests}")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP"""
    print("🔄 Reloading workers...")

def when_ready(server):
    """Called just after the server is started"""
    print(f"✅ Gunicorn ready - listening on {bind}")
    print(f"💪 Ready to handle concurrent requests")

def worker_int(worker):
    """Called when a worker receives the SIGINT or SIGQUIT signal"""
    print(f"⚠️  Worker {worker.pid} interrupted")

def worker_abort(worker):
    """Called when a worker receives the SIGABRT signal"""
    print(f"❌ Worker {worker.pid} aborted")
