from django.core.management.base import BaseCommand
from core.models import User
from django.db.models import Q

class Command(BaseCommand):
    help = "Report users with custom passwords, and whether they have phone, email, or both."

    def handle(self, *args, **options):
        # Custom password: not unusable, not empty
        users = User.objects.filter(~Q(password="!"), ~Q(password=""))
        print(f"Total users with custom password: {users.count()}")
        only_phone = users.filter(Q(email="") | Q(email__isnull=True)).exclude(Q(phone="") | Q(phone__isnull=True))
        both = users.exclude(Q(email="") | Q(email__isnull=True)).exclude(Q(phone="") | Q(phone__isnull=True))
        print(f"Users with only phone: {only_phone.count()}")
        print(f"Users with both phone and email: {both.count()}")
        print("\n--- Users with only phone ---")
        for u in only_phone:
            print(f"ID: {u.id}, Phone: {u.phone}, Email: {u.email}, Username: {u.username}")
        print("\n--- Users with both phone and email ---")
        for u in both:
            print(f"ID: {u.id}, Phone: {u.phone}, Email: {u.email}, Username: {u.username}")
