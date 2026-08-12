"""
idcards/models.py — DEPRECATED

This module is kept for backward compatibility only.
All new code should import from `tables.models` instead.

Migration path:
    Old: from idcards.models import IDCardGroup, IDCardTable, IDCard
    New: from tables.models import Table, IDCard
"""
from tables.models import Table, IDCard, IDCardTable, IDCardGroup, sanitize_text_for_storage

__all__ = ['IDCard', 'IDCardTable', 'IDCardGroup', 'Table', 'sanitize_text_for_storage']
