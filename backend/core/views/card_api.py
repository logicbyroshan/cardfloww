"""
card_api.py — Canonical Card Actions & Data API module matching UI terminology ("Table Actions" / "Cards").

Re-exports all views from idcard_api.py and idcard_card_api.py to ensure 100% backward compatibility
and unified naming conventions across the project.
"""
from .idcard_api import *  # noqa: F401,F403
