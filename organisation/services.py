"""
Client Services — barrel re-export module.

Individual service classes live in their own files for modularity.
Import from here for backward compatibility.
"""
from .services_access import OrganisationAccessService
from .services_dashboard import OrganisationDashboardService
from .services_staff import OrganisationStaffService
from .services_card import OrganisationCardService
from .services_image import OrganisationImageService

__all__ = [
    'OrganisationAccessService',
    'OrganisationDashboardService',
    'OrganisationStaffService',
    'OrganisationCardService',
    'OrganisationImageService',
]
