"""
Client Access Service — ownership and access-control checks.

Ensures clients (and client-staff) can only reach their own data.
"""
from typing import Optional
from django.db.models import Q

from organisation.models import Organisation
from tables.models import Table, IDCard
from core.services.permission_service import PermissionService


class OrganisationAccessService:
    """
    Service for managing client data access.
    Ensures clients can only access their own data.
    """

    @staticmethod
    def _normalize_positive_int_ids(raw_ids):
        """Normalize mixed values into unique positive integers."""
        if not isinstance(raw_ids, (list, tuple, set)):
            return []

        out = []
        seen = set()
        for value in raw_ids:
            if isinstance(value, bool):
                continue
            try:
                number = int(str(value).strip())
            except (TypeError, ValueError):
                continue
            if number <= 0 or number in seen:
                continue
            seen.add(number)
            out.append(number)
        return out

    @staticmethod
    def _get_staff_profile(user):
        """Resolve the staff/assistant profile for an authenticated user.

        Assistants created via the auto-create flow are stored in the
        ``Assistant`` model (related_name='assistant_profile').  Legacy
        client-staff users use ``staff_profile``.  This helper tries both
        so that access checks work regardless of which model backs the user.
        """
        # Prefer the Assistant model (role='assistant') — most common for
        # auto-created assistants.
        profile = getattr(user, 'assistant_profile', None)
        if profile is not None:
            return profile
        # Fall back to legacy staff_profile (role='client_staff').
        profile = getattr(user, 'staff_profile', None)
        if profile is not None:
            return profile
        # Last resort: DB lookup in the Assistant table.
        try:
            from assistants.models import Assistant as _Assistant
            profile = _Assistant.objects.filter(user=user).first()
            if profile is not None:
                return profile
        except Exception:
            pass
        # Final fallback: legacy Staff model.
        try:
            from staff.models import Staff as _Staff
            profile = _Staff.objects.filter(user=user).first()
        except Exception:
            profile = None
        return profile

    @staticmethod
    def _assigned_group_ids_for_access(staff):
        """Return group IDs that explicitly grant group-level access.

        When assignment_scopes exist, only ``scope_type='group'`` entries should
        grant group-level access. Table scopes should not implicitly unlock all
        tables in the parent group.
        """
        cached = getattr(staff, '_cached_assigned_group_ids_for_access', None)
        if cached is not None:
            return cached

        scopes = getattr(staff, 'assignment_scopes', None)
        if isinstance(scopes, list) and scopes:
            explicit_group_ids = []
            seen = set()
            has_any_valid_scope = False

            for scope in scopes:
                if not isinstance(scope, dict):
                    continue
                stype = str(scope.get('scope_type', '') or '').strip().lower()
                if stype not in ('group', 'table'):
                    continue
                has_any_valid_scope = True
                if stype != 'group':
                    continue

                sid = scope.get('scope_id')
                try:
                    sid_int = int(str(sid).strip())
                except (TypeError, ValueError):
                    continue
                if sid_int <= 0 or sid_int in seen:
                    continue
                seen.add(sid_int)
                explicit_group_ids.append(sid_int)

            if has_any_valid_scope:
                setattr(staff, '_cached_assigned_group_ids_for_access', explicit_group_ids)
                return explicit_group_ids

        fallback_group_ids = list(staff.assigned_groups.values_list('id', flat=True))
        setattr(staff, '_cached_assigned_group_ids_for_access', fallback_group_ids)
        return fallback_group_ids

    @staticmethod
    def _assigned_table_ids_for_access(staff):
        """Return cached normalized assigned table IDs for client_staff checks.
        Checks both legacy assigned_table_ids field and new assignment_scopes.
        """
        cached = getattr(staff, '_cached_assigned_table_ids_for_access', None)
        if cached is not None:
            return cached

        scopes = getattr(staff, 'assignment_scopes', None)
        if isinstance(scopes, list) and scopes:
            explicit_table_ids = []
            seen = set()
            has_any_valid_scope = False

            for scope in scopes:
                if not isinstance(scope, dict):
                    continue
                stype = str(scope.get('scope_type', '') or '').strip().lower()
                if stype not in ('group', 'table'):
                    continue
                has_any_valid_scope = True
                if stype != 'table':
                    continue

                sid = scope.get('scope_id')
                try:
                    sid_int = int(str(sid).strip())
                except (TypeError, ValueError):
                    continue
                if sid_int <= 0 or sid_int in seen:
                    continue
                seen.add(sid_int)
                explicit_table_ids.append(sid_int)

            if has_any_valid_scope:
                setattr(staff, '_cached_assigned_table_ids_for_access', explicit_table_ids)
                return explicit_table_ids

        assigned_table_ids = OrganisationAccessService._normalize_positive_int_ids(
            getattr(staff, 'assigned_table_ids', None) or []
        )
        setattr(staff, '_cached_assigned_table_ids_for_access', assigned_table_ids)
        return assigned_table_ids

    @staticmethod
    def _assigned_client_ids_for_access(staff):
        """Return cached assigned client IDs for admin_staff access checks.

        This avoids repeating the same M2M query multiple times during a
        single request where several can_access_* checks are performed.
        """
        cached = getattr(staff, '_cached_assigned_client_ids_for_access', None)
        if cached is not None:
            return cached

        assigned_ids = set(staff.assigned_organisations.values_list('id', flat=True))
        setattr(staff, '_cached_assigned_client_ids_for_access', assigned_ids)
        return assigned_ids

    @staticmethod
    def get_organisation_for_user(user) -> Optional[Organisation]:
        """
        Get the Client instance for a user.
        Works for both 'client' and 'client_staff' roles.
        Delegates role checks to PermissionService (single authority).
        """
        if not user.is_authenticated:
            return None

        if PermissionService.is_client(user):
            client_profile = getattr(user, 'client_profile', None)
            if client_profile is None:
                from organisation.models import Organisation
                client_profile = Organisation.objects.filter(user_id=user.pk).first()
            if client_profile:
                return client_profile
            
            # Check if sub-manager has managed assistants with an organisation
            from assistants.models import Assistant
            first_asst = Assistant.objects.filter(manager=user).select_related('organisation').first()
            if first_asst and first_asst.organisation:
                return first_asst.organisation

            # Check if user has an operator profile with assigned organisations
            if hasattr(user, 'operator_profile') and user.operator_profile:
                return user.operator_profile.assigned_organisations.first()

            return None

        if PermissionService.is_client_staff(user):
            staff = OrganisationAccessService._get_staff_profile(user)
            if staff:
                return staff.client

        return None

    @staticmethod
    def can_access_organisation(user, client_id: int) -> bool:
        """Check if user can access a specific client's data.
        super_admin has unrestricted access.
        admin_staff/photographer is restricted to assigned clients.
        """
        if PermissionService.is_super_admin(user):
            return True
        if PermissionService.is_operator(user) or PermissionService.is_photographer(user):
            staff = OrganisationAccessService._get_staff_profile(user)
            if not staff:
                return False
            assigned_ids = OrganisationAccessService._assigned_client_ids_for_access(staff)
            return (not assigned_ids) or (client_id in assigned_ids)
        client = OrganisationAccessService.get_organisation_for_user(user)
        if client is None:
            return False
        return client.id == client_id

    @staticmethod
    def can_access_group(user, group: Table) -> bool:
        """Check if user can access a specific group.
        super_admin has unrestricted access.
        admin_staff/photographer is restricted to assigned clients.
        client_staff: must have group in assigned_groups (empty = all groups).
        """
        if PermissionService.is_super_admin(user):
            return True
        if PermissionService.is_operator(user) or PermissionService.is_photographer(user):
            staff = OrganisationAccessService._get_staff_profile(user)
            if not staff:
                return False
            assigned_ids = OrganisationAccessService._assigned_client_ids_for_access(staff)
            return (not assigned_ids) or (group.organisation_id in assigned_ids)

        client = OrganisationAccessService.get_organisation_for_user(user)
        if client is None:
            return False
        if group.client_id != client.id:
            return False

        # For client_staff with assigned groups: restrict to assigned only
        if PermissionService.is_client_staff(user):
            staff = OrganisationAccessService._get_staff_profile(user)
            if staff:
                assigned_table_ids = OrganisationAccessService._assigned_table_ids_for_access(staff)
                assigned_group_ids = OrganisationAccessService._assigned_group_ids_for_access(staff)

                if assigned_table_ids and assigned_group_ids:
                    return (group.id in assigned_group_ids) or Table.objects.filter(
                        id__in=assigned_table_ids,
                        group_id=group.id,
                        group__client_id=group.client_id,
                        deleted_by_client=False,
                    ).exists()

                if assigned_table_ids:
                    return Table.objects.filter(
                        id__in=assigned_table_ids,
                        group_id=group.id,
                        group__client_id=group.client_id,
                        deleted_by_client=False,
                    ).exists()

                if assigned_group_ids:
                    return group.id in assigned_group_ids
                
            return False
        return True

    @staticmethod
    def can_access_table(user, table: Table) -> bool:
        """Check if user can access a specific table.
        super_admin has unrestricted access.
        operator/photographer is restricted to assigned clients.
        manager: restricted to assigned tables (if configured).
        assistant: restricted to assigned tables AND parent manager's table scope.
        prime_manager: owns all tables in the organisation.
        """
        if PermissionService.is_super_admin(user):
            return True
        if PermissionService.is_operator(user) or PermissionService.is_admin_staff(user) or PermissionService.is_photographer(user):
            return PermissionService.can_access_client(user, table.organisation_id)

        client = OrganisationAccessService.get_organisation_for_user(user)
        if client is None:
            return False
        if table.organisation_id != client.id:
            return False

        # Prime manager has full access to all tables of their organisation
        if getattr(user, 'role', '') in ('prime_manager', 'guest_prime_manager', 'organisation', 'client'):
            return True

        # For sub-manager with assigned tables
        if getattr(user, 'role', '') == 'manager':
            staff = OrganisationAccessService._get_staff_profile(user)
            if staff:
                assigned_table_ids = OrganisationAccessService._assigned_table_ids_for_access(staff)
                if assigned_table_ids:
                    return table.id in assigned_table_ids
            return True

        # For assistant: verify parent manager access first, then assistant's assigned tables
        if PermissionService.is_assistant(user) or PermissionService.is_client_staff(user):
            from assistants.models import Assistant
            staff = getattr(user, 'assistant_profile', None) or getattr(user, 'staff_profile', None) or Assistant.objects.filter(user=user).first()
            if staff:
                if staff.manager:
                    if not OrganisationAccessService.can_access_table(staff.manager, table):
                        return False
                assigned_table_ids = OrganisationAccessService._assigned_table_ids_for_access(staff)
                if assigned_table_ids:
                    return table.id in assigned_table_ids
                # If no specific table restrictions, assistant inherits manager's access
                return True
            return False

        return True

    @classmethod
    def get_scoped_tables_qs(cls, user, client, base_qs=None):
        """Return a queryset of tables scoped to the user's access level.
        
        This is the SINGLE AUTHORITY for table-level scoping.
        All views and services MUST use this method instead of inline Q filters.
        """
        if base_qs is None:
            from tables.models import Table
            base_qs = Table.objects.filter(
                organisation=client,
                is_active=True,
                deleted_by_manager=False,
            )
        
        if not user or not user.is_authenticated:
            return base_qs.none()

        if PermissionService.is_super_admin(user) or getattr(user, 'role', '') in ('prime_manager', 'guest_prime_manager', 'organisation', 'client'):
            return base_qs

        # For sub-manager
        if getattr(user, 'role', '') == 'manager':
            staff = OrganisationAccessService._get_staff_profile(user)
            if staff:
                assigned_table_ids = cls._assigned_table_ids_for_access(staff)
                if assigned_table_ids:
                    return base_qs.filter(id__in=assigned_table_ids)
            return base_qs

        # For assistant
        if PermissionService.is_assistant(user) or PermissionService.is_client_staff(user):
            from assistants.models import Assistant
            staff = getattr(user, 'assistant_profile', None) or getattr(user, 'staff_profile', None) or Assistant.objects.filter(user=user).first()
            if not staff:
                return base_qs.none()
            
            # Scope to parent manager's tables first
            qs = base_qs
            if staff.manager:
                qs = cls.get_scoped_tables_qs(staff.manager, client, base_qs=qs)
            
            assigned_table_ids = cls._assigned_table_ids_for_access(staff)
            if assigned_table_ids:
                return qs.filter(id__in=assigned_table_ids)
            return qs
        
        return base_qs

    @staticmethod
    def can_access_card(user, card: IDCard) -> bool:
        """Check if user can access a specific card.
        super_admin has unrestricted access.
        operator/photographer is restricted to assigned clients.
        """
        if PermissionService.is_super_admin(user):
            return True
        if PermissionService.is_operator(user) or PermissionService.is_admin_staff(user) or PermissionService.is_photographer(user):
            return PermissionService.can_access_client(user, card.table.organisation_id)

        client = OrganisationAccessService.get_organisation_for_user(user)
        if client is None:
            return False
        if card.table.organisation_id != client.id:
            return False

        # For assistant / client_staff with assigned tables
        if PermissionService.is_assistant(user) or PermissionService.is_client_staff(user):
            staff = OrganisationAccessService._get_staff_profile(user)
            if staff:
                assigned_table_ids = OrganisationAccessService._assigned_table_ids_for_access(staff)
                if assigned_table_ids:
                    return card.table_id in assigned_table_ids
                
            return False
        return True

    @staticmethod
    def get_accessible_table_ids(user):
        """Return a list of accessible table IDs for a user.
        Returns None if all tables are accessible (no restriction).
        """
        client = OrganisationAccessService.get_organisation_for_user(user)
        if client is None:
            return []
        if PermissionService.is_client_staff(user):
            qs = OrganisationAccessService.get_scoped_tables_qs(user, client)
            return list(qs.values_list('id', flat=True))
        return None

