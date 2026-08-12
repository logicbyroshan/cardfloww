"""
Mediafiles Services Module

This module re-exports from the services package for backward compatibility.
All real implementations are in mediafiles/services/*.py

NO STUBS. Real implementations only.
"""

# Re-export everything from the services package
from .services import ImageService, MediaResult, ImageRenamer, ThumbnailService

# Backward compatibility alias
ServiceResult = MediaResult

__all__ = ['ImageService', 'MediaResult', 'ServiceResult', 'ImageRenamer', 'ThumbnailService']
