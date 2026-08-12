"""
managers/models.py

NOTE: This app was temporarily created during the deep-rename refactor.
The `Assistant` model lives here as an alias for backward compatibility.
`Assistant` keeps its original name — no rename was applied.

All new code should import from `assistants.models` directly.
"""
from assistants.models import Assistant

__all__ = ['Assistant']
