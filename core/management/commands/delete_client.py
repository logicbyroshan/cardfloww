import logging
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from organisation.models import Organisation

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = (
        "Completely delete a client, its user account, and all associated data "
        "(tables, cards, images)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--client-name",
            type=str,
            default="",
            help="Client name to match (icontains by default).",
        )
        parser.add_argument(
            "--client-id",
            type=int,
            default=None,
            help="Client ID (preferred when names are similar).",
        )
        parser.add_argument(
            "--exact",
            action="store_true",
            default=False,
            help="Use case-insensitive exact name match for --client-name.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Actually delete the client. Default is dry-run.",
        )

    def handle(self, *args, **options):
        client = self._resolve_client(
            client_id=options.get("client_id"),
            client_name=(options.get("client_name") or "").strip(),
            exact=bool(options.get("exact")),
        )

        apply = bool(options.get("apply"))
        mode = "APPLY" if apply else "DRY-RUN"

        self.stdout.write(
            self.style.WARNING(
                f"\n=== delete_client ({mode}) ===\n"
                f"Target Client: {client.name} (ID: {client.id})\n"
                f"User Account: {client.user.username} (ID: {client.user.id})"
            )
        )

        # Count some related data for display
        total_tables = client.groups.count() if hasattr(client, 'groups') else 0 # Assuming related name 'groups' or similar
        # Wait, let's just count from IDCard
        from tables.models import IDCard
        total_cards = IDCard.objects.filter(table__group__client=client).count()
        
        self.stdout.write(f"This client has approximately {total_cards} ID Cards.")

        if not apply:
            self.stdout.write(self.style.WARNING("\nDry-run only. No data was deleted."))
            self.stdout.write(self.style.WARNING(f"Run this to apply: python manage.py delete_client --client-id {client.id} --apply"))
            return

        self.stdout.write("Deleting client data...")

        try:
            with transaction.atomic():
                user = client.user
                
                # Clean up legacy references that might exist in production DB
                from django.db import connection
                tables = connection.introspection.table_names()
                
                if 'core_guestassignment_assigned_clients' in tables:
                    with connection.cursor() as cursor:
                        cursor.execute("DELETE FROM core_guestassignment_assigned_clients WHERE client_id = %s", [client.id])
                        
                if 'cardprint_printrequest' in tables:
                    from tables.models import IDCard
                    card_ids = list(IDCard.objects.filter(table__group__client=client).values_list('id', flat=True))
                    if card_ids:
                        with connection.cursor() as cursor:
                            batch_size = 500
                            for i in range(0, len(card_ids), batch_size):
                                batch = card_ids[i:i + batch_size]
                                placeholders = ','.join(['%s'] * len(batch))
                                cursor.execute(f"DELETE FROM cardprint_printrequest WHERE card_id IN ({placeholders})", batch)
                
                # Delete the client. This will trigger client.delete() which
                # calls delete_image_folder() to delete physical image files.
                client.delete()
                
                # Delete the user account. This cascades to many things, 
                # but we explicitly delete the Client first to ensure its custom delete() runs.
                user.delete()
                
            self.stdout.write(self.style.SUCCESS(f"\nSuccessfully deleted client '{client.name}' and all its data."))
        except Exception as e:
            logger.exception("Error deleting client")
            raise CommandError(f"Failed to delete client: {e}")

    def _resolve_client(self, *, client_id, client_name, exact):
        if client_id:
            client = Organisation.objects.select_related('user').filter(id=client_id).first()
            if not client:
                raise CommandError(f"No client found with id={client_id}")
            return client

        if not client_name:
            raise CommandError("Provide either --client-id or --client-name")

        if exact:
            matches = Organisation.objects.select_related('user').filter(name__iexact=client_name)
        else:
            matches = Organisation.objects.select_related('user').filter(name__icontains=client_name)

        count = matches.count()
        if count == 0:
            mode = "iexact" if exact else "icontains"
            raise CommandError(f"No client found for {mode}='{client_name}'")

        if count > 1:
            self.stdout.write(self.style.WARNING(f"Multiple clients matched '{client_name}':"))
            for c in matches.order_by("name", "id")[:30]:
                self.stdout.write(f"  ID={c.id} | {c.name} | status={c.status}")
            raise CommandError("Please rerun with --client-id to select exactly one client")

        return matches.first()
