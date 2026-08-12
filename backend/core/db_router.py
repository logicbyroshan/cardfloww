import threading
from django.conf import settings

_thread_local = threading.local()

class GuestSandboxRouter:
    """
    A database router to dynamically route database queries to a session-specific
    SQLite sandbox database when a guest user session is active.
    """
    @staticmethod
    def get_guest_db():
        return getattr(_thread_local, 'guest_sandbox_db', None)

    @staticmethod
    def set_guest_db(db_alias):
        _thread_local.guest_sandbox_db = db_alias

    @staticmethod
    def clear_guest_db():
        if hasattr(_thread_local, 'guest_sandbox_db'):
            del _thread_local.guest_sandbox_db

    def db_for_read(self, model, **hints):
        guest_db = self.get_guest_db()
        if guest_db and guest_db in settings.DATABASES:
            # Route core models and mediafiles to the guest sandbox database.
            # Avoid routing django internal models (sessions, contenttypes, admin)
            if model._meta.app_label in ('core', 'mediafiles', 'reprintcard'):
                return guest_db
        return None

    def db_for_write(self, model, **hints):
        guest_db = self.get_guest_db()
        if guest_db and guest_db in settings.DATABASES:
            # Route core models and mediafiles to the guest sandbox database.
            if model._meta.app_label in ('core', 'mediafiles', 'reprintcard'):
                return guest_db
        return None

    def allow_relation(self, obj1, obj2, **hints):
        guest_db = self.get_guest_db()
        if guest_db:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return True
