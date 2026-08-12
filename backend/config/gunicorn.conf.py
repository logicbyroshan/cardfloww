"""Gunicorn configuration tuned for low-resource production hosts.

Defaults target 1 CPU / 1 GB RAM deployments while allowing environment
variables to override every value.
"""

import multiprocessing
import os


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int, *, minimum: int | None = None, maximum: int | None = None) -> int:
    value = os.getenv(name)
    try:
        parsed = int(str(value).strip()) if value is not None else int(default)
    except (TypeError, ValueError):
        parsed = int(default)

    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


_cpu_count = max(multiprocessing.cpu_count(), 1)
_default_workers = 2 if _cpu_count <= 2 else min(4, _cpu_count + 1)

bind = os.getenv("GUNICORN_BIND", "unix:/run/gunicorn.sock")
backlog = _env_int("GUNICORN_BACKLOG", 2048, minimum=128, maximum=8192)

# Default to ASGI worker so Django Channels/websockets work out of the box.
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "uvicorn.workers.UvicornWorker").strip() or "uvicorn.workers.UvicornWorker"
workers = _env_int("WEB_CONCURRENCY", _default_workers, minimum=1, maximum=4)
threads = _env_int("GUNICORN_THREADS", 2, minimum=1, maximum=8) if worker_class == "gthread" else 1

# Keep timeout tight; large exports are routed to background workers (async).
timeout = _env_int("GUNICORN_TIMEOUT", 60, minimum=30, maximum=300)
graceful_timeout = _env_int("GUNICORN_GRACEFUL_TIMEOUT", 30, minimum=10, maximum=120)
keepalive = _env_int("GUNICORN_KEEPALIVE", 5, minimum=1, maximum=30)

# Recycle workers to cap memory growth from long-lived Python processes.
max_requests = _env_int("GUNICORN_MAX_REQUESTS", 1000, minimum=100, maximum=10000)
max_requests_jitter = _env_int("GUNICORN_MAX_REQUESTS_JITTER", 100, minimum=0, maximum=1000)

preload_app = _env_bool("GUNICORN_PRELOAD", True)

# Linux-only optimization; ignored automatically on non-Linux systems.
worker_tmp_dir = os.getenv("GUNICORN_WORKER_TMP_DIR", "/dev/shm")
if os.name == "nt":
    worker_tmp_dir = None

accesslog = os.getenv("GUNICORN_ACCESSLOG", "-")
errorlog = os.getenv("GUNICORN_ERRORLOG", "-")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")
capture_output = _env_bool("GUNICORN_CAPTURE_OUTPUT", True)


def post_worker_init(worker):
    # Used by startup guards to detect server context safely.
    os.environ["GUNICORN_WORKER_READY"] = "true"
