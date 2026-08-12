import sys
from django.core.management.base import BaseCommand
from organisation.models import Organisation
from assistants.models import Assistant
from assistants.services import AssistantService

class Command(BaseCommand):
    help = 'Enable all delegable permissions for all assistants of a specific client identified by name.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--client',
            type=str,
            help='Name (or part of name) of the client to find.'
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('--- Enable Assistant Permissions Tool ---'))
        
        client_input = options.get('client')
        
        if not client_input:
            # Interactive mode - list all clients or prompt
            clients = list(Organisation.objects.all().order_by('name'))
            if not clients:
                self.stdout.write(self.style.ERROR('No clients found in the system.'))
                return
                
            self.stdout.write("Available clients:")
            for i, client in enumerate(clients, 1):
                assistant_count = Assistant.objects.filter(client=client).count()
                self.stdout.write(f"{i}. {client.name} (ID: {client.id}) - {assistant_count} assistants")
                
            self.stdout.write("\n")
            selection = input('Enter the number corresponding to the client (or q to quit): ').strip()
            
            if selection.lower() == 'q':
                self.stdout.write('Operation cancelled.')
                return
                
            try:
                index = int(selection) - 1
                if index < 0 or index >= len(clients):
                    self.stdout.write(self.style.ERROR('Invalid selection. Must be within the range.'))
                    return
                selected_client = clients[index]
            except ValueError:
                self.stdout.write(self.style.ERROR('Invalid input. Please enter a number.'))
                return
        else:
            # Find client by name
            client_input = client_input.strip()
            clients = list(Organisation.objects.filter(name__icontains=client_input))
            if not clients:
                self.stdout.write(self.style.ERROR(f"No clients found matching name: '{client_input}'"))
                return
            elif len(clients) == 1:
                selected_client = clients[0]
            else:
                self.stdout.write(self.style.WARNING(f"Multiple clients found matching '{client_input}':"))
                for i, client in enumerate(clients, 1):
                    self.stdout.write(f"{i}. {client.name} (ID: {client.id})")
                self.stdout.write("\n")
                selection = input('Enter the number corresponding to the client (or q to quit): ').strip()
                if selection.lower() == 'q':
                    self.stdout.write('Operation cancelled.')
                    return
                try:
                    index = int(selection) - 1
                    if index < 0 or index >= len(clients):
                        self.stdout.write(self.style.ERROR('Invalid selection.'))
                        return
                    selected_client = clients[index]
                except ValueError:
                    self.stdout.write(self.style.ERROR('Invalid input. Please enter a number.'))
                    return

        self.stdout.write(self.style.WARNING(f"\nSelected client: {selected_client.name} (ID: {selected_client.id})"))
        
        # Get assistants
        assistants = Assistant.objects.filter(client=selected_client).select_related('user')
        if not assistants.exists():
            self.stdout.write(self.style.ERROR(f"No assistants found for client: {selected_client.name}"))
            return
            
        self.stdout.write(f"Found {assistants.count()} assistant(s). Enabling all permissions...")
        
        updated_count = 0
        permission_fields = AssistantService.ASSISTANT_PERMISSION_FIELDS
        
        for assistant in assistants:
            fields_to_update = []
            for field in permission_fields:
                if getattr(assistant, field) is not True:
                    setattr(assistant, field, True)
                    fields_to_update.append(field)
            
            if fields_to_update:
                assistant.save(update_fields=fields_to_update)
                self.stdout.write(self.style.SUCCESS(
                    f"Enabled permissions for {assistant.user.username} ({assistant.user.get_full_name() or ''}): "
                    f"{', '.join(fields_to_update)}"
                ))
                updated_count += 1
            else:
                self.stdout.write(f"Assistant {assistant.user.username} already has all permissions enabled.")
                
        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully updated {updated_count} assistant(s)."))
