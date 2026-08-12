"""
client/models.py — DEPRECATED

This module is kept for backward compatibility only.
All new code should import from `organisation.models` instead.

Migration path:
    Old: from client.models import Client
    New: from organisation.models import Organisation
"""
# Re-export Organisation as Client for backward compatibility
from organisation.models import Organisation, generate_folder_code_from_name, generate_unique_suffix

# Alias: any code still doing `from client.models import Client` will get Organisation
Client = Organisation

__all__ = ['Client', 'Organisation', 'generate_folder_code_from_name', 'generate_unique_suffix']
