"""
assistants/models.py — DEPRECATED

This module is kept for backward compatibility only.
All new code should import from `managers.models` instead.

Migration path:
    Old: from assistants.models import Assistant
    New: from managers.models import Manager
"""
from managers.models import Manager, Assistant

__all__ = ['Assistant', 'Manager']
