"""
table_api.py — Canonical Table API module matching UI terminology ("Manage Tables").

Re-exports all views from idcard_table_api.py to ensure 100% backward compatibility
and unified naming conventions across the project.
"""
from .idcard_table_api import *  # noqa: F401,F403
from .idcard_table_api import api_organisation_tables  # Explicit export
