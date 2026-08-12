import logging
from django.core.management.base import BaseCommand
from django.db import transaction
from organisation.models import Organisation
from tables.models import IDCard, Table

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Interactively remove leading and trailing apostrophes (') from a specific column in a table for a client."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run the command without making any changes to the database.',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry-run')
        if dry_run:
            self.stdout.write(self.style.WARNING("--- DRY RUN MODE ENABLED ---"))
            self.stdout.write(self.style.WARNING("No changes will be saved to the database.\n"))

        self.stdout.write(self.style.MIGRATE_HEADING("--- Apostrophe Cleanup Utility ---"))

        # 1. Get Client
        client_name = input("Enter Client Name (or part of it): ").strip()
        if not client_name:
            self.stdout.write(self.style.ERROR("Client name cannot be empty."))
            return

        clients = Organisation.objects.filter(name__icontains=client_name)
        if not clients.exists():
            self.stdout.write(self.style.ERROR(f"No client found matching '{client_name}'"))
            return
        
        if clients.count() > 1:
            self.stdout.write("\nMultiple clients found:")
            client_list = list(clients)
            for i, c in enumerate(client_list):
                self.stdout.write(f"{i+1}. {c.name} (ID: {c.id})")
            
            try:
                choice = int(input(f"\nSelect client (1-{len(client_list)}): "))
                client = client_list[choice - 1]
            except (ValueError, IndexError):
                self.stdout.write(self.style.ERROR("Invalid selection."))
                return
        else:
            client = clients[0]
            self.stdout.write(self.style.SUCCESS(f"Selected Client: {client.name}"))

        # 2. Get Table
        tables = Table.objects.filter(group__client=client)
        if not tables.exists():
            self.stdout.write(self.style.ERROR(f"No ID Card Tables found for client '{client.name}'"))
            return
        
        self.stdout.write("\nAvailable Tables for this client:")
        table_list = list(tables)
        for i, t in enumerate(table_list):
            self.stdout.write(f"{i+1}. {t.name} (ID: {t.id})")
        
        try:
            choice = int(input(f"\nSelect table (1-{len(table_list)}): "))
            table = table_list[choice - 1]
        except (ValueError, IndexError):
            self.stdout.write(self.style.ERROR("Invalid selection."))
            return

        # 3. Get Column (Field)
        fields = table.fields  # List of {name, type, order}
        if not fields:
            self.stdout.write(self.style.ERROR("This table has no fields defined in its configuration."))
            return
        
        self.stdout.write("\nAvailable Columns (Fields) in this table:")
        for i, f in enumerate(fields):
            self.stdout.write(f"{i+1}. {f.get('name')} (Type: {f.get('type')})")
        
        try:
            choice = int(input(f"\nSelect column to clean (1-{len(fields)}): "))
            column_name = fields[choice - 1].get('name')
        except (ValueError, IndexError):
            self.stdout.write(self.style.ERROR("Invalid selection."))
            return

        # 4. Final Confirmation
        queryset = IDCard.objects.filter(table=table)
        total_count = queryset.count()
        
        self.stdout.write(self.style.WARNING(f"\nTargeting Table: {table.name}"))
        self.stdout.write(self.style.WARNING(f"Targeting Column: {column_name}"))
        self.stdout.write(self.style.WARNING(f"Total Records in Table: {total_count}"))
        
        confirm = input(f"\nAre you SURE you want to remove leading/trailing apostrophes from '{column_name}' for all records in this table? (yes/no): ")
        
        if confirm.lower() != 'yes':
            self.stdout.write("Operation cancelled.")
            return

        # 5. Execute Cleanup
        updated_count = 0
        skipped_count = 0
        
        self.stdout.write(f"\nProcessing {total_count} records...")
        
        try:
            # Skip transaction if dry run (not strictly necessary but cleaner)
            if dry_run:
                for card in queryset.iterator(chunk_size=500):
                    data = card.field_data or {}
                    val = data.get(column_name)
                    if val and isinstance(val, str) and (val.startswith("'") or val.endswith("'")):
                        updated_count += 1
                    else:
                        skipped_count += 1
            else:
                with transaction.atomic():
                    for card in queryset.iterator(chunk_size=500):
                        data = card.field_data or {}
                        val = data.get(column_name)
                        
                        if val and isinstance(val, str):
                            if val.startswith("'") or val.endswith("'"):
                                new_val = val.strip("'")
                                data[column_name] = new_val
                                card.field_data = data
                                card.save(update_fields=['field_data'])
                                updated_count += 1
                            else:
                                skipped_count += 1
                        else:
                            skipped_count += 1
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"An error occurred during execution: {str(e)}"))
            return

        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"\nDRY RUN COMPLETE!"))
            self.stdout.write(self.style.SUCCESS(f"- Records that WOULD have been updated: {updated_count}"))
            self.stdout.write(self.style.SUCCESS(f"- Records that WOULD have been skipped: {skipped_count}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nCleanup Complete!"))
            self.stdout.write(self.style.SUCCESS(f"- Records updated: {updated_count}"))
            self.stdout.write(self.style.SUCCESS(f"- Records skipped: {skipped_count}"))
        
        self.stdout.write(f"- Total records processed: {updated_count + skipped_count}")
