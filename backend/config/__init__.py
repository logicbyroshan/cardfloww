"""Project package initialization."""

try:
	from .celery import app as celery_app  # noqa: F401
except Exception:
	celery_app = None
