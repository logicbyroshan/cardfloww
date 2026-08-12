import django
from django.db import models
from django.core.exceptions import ObjectDoesNotExist

# Import the actual models
from core.models import User, Photographer, PhotographerAssignment
from operators.models import Operator
from assistants.models import Assistant
from organisation.models import Organisation

class StaffCompatWrapper:
    def __init__(self, delegate, staff_type):
        self.delegate = delegate
        self.staff_type = staff_type

    @property
    def id(self):
        import sys
        try:
            frame = sys._getframe(1)
            for _ in range(10):
                if not frame:
                    break
                filename = frame.f_code.co_filename
                if filename:
                    norm = filename.replace('\\', '/').lower()
                    if ('django/db/models/fields/' in norm or 
                        'django/db/models/base' in norm or 
                        'django/db/models/sql/' in norm or 
                        'django/db/backends/' in norm or 
                        'django/db/models/query' in norm):
                        return self.delegate.id
                frame = frame.f_back
        except Exception:
            pass

        if self.staff_type == 'operator':
            return self.delegate.id + 100000
        elif self.staff_type == 'assistant':
            return self.delegate.id + 200000
        else:
            return self.delegate.id + 300000

    @property
    def pk(self):
        return self.id

    @property
    def user(self):
        return self.delegate.user

    @property
    def user_id(self):
        return self.delegate.user_id

    @property
    def Organisation(self):
        if hasattr(self.delegate, 'client'):
            return self.delegate.client
        return None

    @property
    def client_id(self):
        if hasattr(self.delegate, 'client_id'):
            return self.delegate.client_id
        return None

    @property
    def created_at(self):
        return getattr(self.delegate, 'created_at', None)

    @property
    def department(self):
        return getattr(self.delegate, 'department', '')

    @property
    def designation(self):
        return getattr(self.delegate, 'designation', '')

    def get_staff_type_display(self):
        if self.staff_type == 'operator':
            return 'Admin Staff'
        elif self.staff_type == 'assistant':
            return 'Client Staff'
        else:
            return 'Photographer'

    @property
    def assigned_clients(self):
        if hasattr(self.delegate, 'assigned_organisations'):
            return self.delegate.assigned_organisations
        if self.staff_type == 'photographer':
            class AssignedClientsWrapper:
                def __init__(self, photographer):
                    self.photographer = photographer
                def all(self):
                    client_ids = self.photographer.photographer_assignments.values_list('client_id', flat=True)
                    return Organisation.objects.filter(id__in=client_ids)
                def values_list(self, *args, **kwargs):
                    client_ids = self.photographer.photographer_assignments.values_list('client_id', flat=True)
                    return Organisation.objects.filter(id__in=client_ids).values_list(*args, **kwargs)
                def add(self, *clients):
                    from core.models import PhotographerAssignment
                    for c in clients:
                        PhotographerAssignment.objects.get_or_create(photographer=self.photographer, client=c)
                def remove(self, *clients):
                    from core.models import PhotographerAssignment
                    PhotographerAssignment.objects.filter(photographer=self.photographer, client__in=clients).delete()
                def clear(self):
                    from core.models import PhotographerAssignment
                    PhotographerAssignment.objects.filter(photographer=self.photographer).delete()
                def set(self, clients, **kwargs):
                    from core.models import PhotographerAssignment
                    PhotographerAssignment.objects.filter(photographer=self.photographer).delete()
                    for c in clients:
                        PhotographerAssignment.objects.create(photographer=self.photographer, client=c)
            return AssignedClientsWrapper(self.delegate)
        return Organisation.objects.none()

    def __getattr__(self, name):
        if 'delegate' not in self.__dict__:
            raise AttributeError("delegate not yet initialized")
        return getattr(self.delegate, name)

    def __setattr__(self, name, value):
        if name in ('delegate', 'staff_type'):
            super().__setattr__(name, value)
        else:
            setattr(self.delegate, name, value)

    def save(self, *args, **kwargs):
        return self.delegate.save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        user = self.delegate.user
        self.delegate.delete(*args, **kwargs)
        if user:
            user.delete()

    @property
    def __class__(self):
        return self.delegate.__class__

    @property
    def _meta(self):
        return self.delegate._meta

    def __eq__(self, other):
        if hasattr(other, 'delegate'):
            return self.delegate == other.delegate
        return self.delegate == other

    def __hash__(self):
        return hash(self.delegate)

    def can_access_organisation(self, client_id: int) -> bool:
        from core.services.permission_service import PermissionService
        return PermissionService.can_access_client(self.user, client_id)

    def get_accessible_client_ids(self) -> list:
        from core.services.permission_service import PermissionService
        return PermissionService.get_accessible_client_ids(self.user)


def _match_filter(item_val, lookup_type, target_val):
    if lookup_type == 'exact':
        return item_val == target_val
    elif lookup_type == 'iexact':
        return str(item_val or '').lower() == str(target_val or '').lower()
    elif lookup_type == 'contains':
        return str(target_val) in str(item_val)
    elif lookup_type == 'icontains':
        return str(target_val).lower() in str(item_val or '').lower()
    elif lookup_type == 'in':
        try:
            return item_val in target_val
        except TypeError:
            return False
    elif lookup_type == 'isnull':
        if target_val:
            return item_val is None
        else:
            return item_val is not None
    return item_val == target_val


class StaffCompatQuerySet:
    def __init__(self, items):
        self.items = items
        self.model = Staff

    def __iter__(self):
        return iter(self.items)

    def __len__(self):
        return len(self.items)

    def count(self):
        return len(self.items)

    def filter(self, *args, **kwargs):
        filtered = self.items
        for key, val in kwargs.items():
            if key == 'staff_type':
                filtered = [item for item in filtered if item.staff_type == val]
                continue

            lookup_type = 'exact'
            parts = key.split('__')
            if len(parts) > 1 and parts[-1] in ('exact', 'iexact', 'contains', 'icontains', 'in', 'isnull'):
                lookup_type = parts.pop()

            if len(parts) > 0 and parts[-1] == 'pk':
                parts[-1] = 'id'

            if parts == ['id'] and lookup_type == 'exact':
                try:
                    val_int = int(val)
                except (TypeError, ValueError):
                    val_int = None

                if val_int is not None:
                    if val_int >= 300000:
                        # Photographer
                        filtered = [item for item in filtered if item.delegate.id == (val_int - 300000) and item.staff_type == 'photographer']
                    elif val_int >= 200000:
                        # Assistant (client_staff)
                        filtered = [item for item in filtered if item.delegate.id == (val_int - 200000) and item.staff_type == 'assistant']
                    elif val_int >= 100000:
                        # Operator (admin_staff)
                        filtered = [item for item in filtered if item.delegate.id == (val_int - 100000) and item.staff_type == 'operator']
                    else:
                        filtered = [item for item in filtered if item.delegate.id == val_int]
                else:
                    # Fallback to string-based legacy decode if it's an encoded token
                    from core.services.compat_service import CompatibilityService
                    staff_type, real_id = CompatibilityService.decode_id(val)
                    if staff_type != 'unknown':
                        filtered = [item for item in filtered if item.delegate.id == real_id and item.staff_type == staff_type]
                    else:
                        filtered = [item for item in filtered if item.delegate.id == val]
                continue

            def get_nested_val(obj, path_parts):
                current = obj
                for p in path_parts:
                    if current is None:
                        return None
                    current = getattr(current, p, None)
                return current

            filtered = [item for item in filtered if _match_filter(get_nested_val(item, parts), lookup_type, val)]
        return StaffCompatQuerySet(filtered)

    def exclude(self, *args, **kwargs):
        excluded = self.items
        for key, val in kwargs.items():
            excluded = [item for item in excluded if getattr(item, key, None) != val]
        return StaffCompatQuerySet(excluded)

    def select_related(self, *args, **kwargs):
        return self

    def prefetch_related(self, *args, **kwargs):
        return self

    def select_for_update(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def distinct(self):
        return self

    def get(self, *args, **kwargs):
        res = self.filter(*args, **kwargs)
        if len(res) == 0:
            raise ObjectDoesNotExist("Staff matching query does not exist")
        return res[0]

    def exists(self):
        return len(self.items) > 0

    def first(self):
        return self.items[0] if self.items else None

    def last(self):
        return self.items[-1] if self.items else None

    def __getitem__(self, k):
        if isinstance(k, slice):
            return StaffCompatQuerySet(self.items[k])
        return self.items[k]


class StaffCompatManager:
    def all(self):
        items = []
        for o in Operator.objects.all():
            items.append(StaffCompatWrapper(o, 'operator'))
        for a in Assistant.objects.all():
            items.append(StaffCompatWrapper(a, 'client_staff'))
        for p in Photographer.objects.all():
            items.append(StaffCompatWrapper(p, 'photographer'))
        return StaffCompatQuerySet(items)

    def filter(self, *args, **kwargs):
        return self.all().filter(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self.all().get(*args, **kwargs)

    def select_related(self, *args, **kwargs):
        return self.all().select_related(*args, **kwargs)

    def prefetch_related(self, *args, **kwargs):
        return self.all().prefetch_related(*args, **kwargs)

    def select_for_update(self, *args, **kwargs):
        return self.all().select_for_update(*args, **kwargs)

    def order_by(self, *args, **kwargs):
        return self.all().order_by(*args, **kwargs)

    def distinct(self, *args, **kwargs):
        return self.all().distinct(*args, **kwargs)

    def create(self, **kwargs):
        staff_type = kwargs.get('staff_type', 'operator')
        user = kwargs.get('user')
        if staff_type == 'operator':
            op = Operator.objects.create(user=user)
            for k, v in list(kwargs.items()):
                if k not in ('user', 'staff_type', 'id', 'pk') and hasattr(op, k):
                    setattr(op, k, v)
            op.save()
            return StaffCompatWrapper(op, 'operator')
        elif staff_type == 'assistant':
            client = kwargs.get('client')
            client_id = kwargs.get('client_id')
            if not client_id and client:
                client_id = client.id
            ast = Assistant.objects.create(user=user, client_id=client_id)
            for k, v in list(kwargs.items()):
                if k not in ('user', 'staff_type', 'client', 'client_id', 'id', 'pk') and hasattr(ast, k):
                    setattr(ast, k, v)
            ast.save()
            return StaffCompatWrapper(ast, 'client_staff')
        elif staff_type == 'photographer':
            ph = Photographer.objects.create(user=user)
            for k, v in list(kwargs.items()):
                if k not in ('user', 'staff_type', 'id', 'pk') and hasattr(ph, k):
                    setattr(ph, k, v)
            ph.save()
            return StaffCompatWrapper(ph, 'photographer')
        raise ValueError(f"Unknown staff type {staff_type}")


class StaffMeta:
    object_name = 'Staff'


class Staff:
    objects = StaffCompatManager()
    _default_manager = objects
    DoesNotExist = ObjectDoesNotExist
    _meta = StaffMeta()
