"""
organisation_api.py — Canonical Organisation API module matching UI terminology ("Manage Organisation").

Re-exports all views from client_api.py to ensure 100% backward compatibility
and unified naming conventions across the project.
"""
from .client_api import *  # noqa: F401,F403
