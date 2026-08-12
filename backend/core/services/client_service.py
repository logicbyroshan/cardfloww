"""
Canonical location: organisation/services_client_core.py
OrganisationService is the main class. OrganisationCoreService and ClientService are aliases.
"""
from organisation.services_client_core import OrganisationService  # noqa: F401
OrganisationCoreService = OrganisationService  # alias
ClientService = OrganisationService            # compat alias
