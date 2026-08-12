"""
Production-ready health check endpoint.

Returns HTTP 200 when all dependencies are reachable, HTTP 503 otherwise.
Designed for use with:
  - Load balancers (Nginx upstream health checks)
  - Container orchestrators (Docker HEALTHCHECK / K8s liveness probes)
  - CI/CD deployment verification
  - Gunicorn worker readiness

No authentication required. No sensitive data exposed.
"""

import time
import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_check(request):
    """
    Lightweight health probe.

    Checks:
      1. Database — single ``SELECT 1`` via the default connection.
      2. Cache/Redis — ``set`` + ``get`` round-trip via Django cache framework
         (only when the configured backend is Redis).
      3. App readiness — if we got this far, WSGI + Django are initialised.

    Response:
      200  ``{"status": "healthy", ...}``
      503  ``{"status": "unhealthy", ...}``  with details of failing service.
    """
    payload = {}
    healthy = True
    start = time.monotonic()

    # ── 1. Database ──────────────────────────────────────────────────────
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        payload["database"] = "ok"
    except Exception as exc:
        logger.warning("Health check: database unreachable — %s", exc)
        payload["database"] = "failed"
        healthy = False

    # ── 2. Cache / Redis ─────────────────────────────────────────────────
    cache_backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    if "Redis" in cache_backend:
        try:
            from django.core.cache import cache

            probe_key = "_health_probe"
            cache.set(probe_key, "1", timeout=5)
            value = cache.get(probe_key)
            if value == "1":
                payload["redis"] = "ok"
            else:
                raise ValueError("Cache round-trip returned unexpected value")
            cache.delete(probe_key)
        except Exception as exc:
            logger.warning("Health check: redis unreachable — %s", exc)
            payload["redis"] = "failed"
            healthy = False
    else:
        # Redis not configured — report as skipped (not a failure)
        payload["redis"] = "not_configured"

    # ── 3. App readiness ─────────────────────────────────────────────────
    payload["app"] = "ok"

    # ── Response ─────────────────────────────────────────────────────────
    elapsed_ms = round((time.monotonic() - start) * 1000, 1)
    payload["response_time_ms"] = elapsed_ms
    payload["status"] = "healthy" if healthy else "unhealthy"

    status_code = 200 if healthy else 503
    response = JsonResponse(payload, status=status_code)
    # Prevent caching by proxies / CDNs so every probe hits the app
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response
