import uuid
import logging
from django.db import transaction
from core.models import User
from client.models import Client
from idcards.models import IDCardTable, IDCardGroup

logger = logging.getLogger(__name__)

class SandboxService:
    """
    Service for creating and managing isolated guest sandboxes.
    When a user logs into a guest account, this service clones the original
    guest account into a temporary, session-scoped user so that all their
    changes (assistants, ID cards, profile updates) are fully isolated.
    """

    @classmethod
    def create_session_clone(cls, original_user):
        """
        Clone a guest_user into a temporary session-bound account.
        Only clones the User, Client, and IDCardSettings (templates).
        Does NOT clone existing ID cards, since those include files.
        """
        try:
            with transaction.atomic():
                original_client = getattr(original_user, 'client_profile', None)
                if not original_client:
                    return original_user
                
                # Create a unique clone username
                clone_suffix = uuid.uuid4().hex[:8]
                clone_username = f"guestclone_{original_user.id}_{clone_suffix}"
                clone_email = f"{clone_username}@noemail.local"
                
                # Clone User
                cloned_user = User.objects.create_user(
                    username=clone_username,
                    email=clone_email,
                    password=clone_suffix, # Random password, they are already logged in
                    first_name=original_user.first_name,
                    last_name=original_user.last_name,
                    phone=original_user.phone,
                    role='guest_prime_manager',
                    is_active=True
                )
                
                # Clone Client
                cloned_client = Client(
                    user=cloned_user,
                    name=original_client.name,
                    is_guest=True,
                    address=original_client.address,
                    city=original_client.city,
                    state=original_client.state,
                    pincode=original_client.pincode,
                    status='active'
                )
                
                # Explicitly skip image_folder_code so save() generates a new one,
                # preventing the clone from deleting the original client's image folder.
                cloned_client.image_folder_code = ''
                
                # Copy permissions
                from client.services_client_core import ClientService
                for perm in ClientService.PERMISSION_FIELDS:
                    setattr(cloned_client, perm, getattr(original_client, perm, False))
                cloned_client.save()
                
                # Clone IDCardGroups and their Tables
                for group in IDCardGroup.objects.filter(client=original_client):
                    # Get original tables before cloning the group
                    original_tables = list(IDCardTable.objects.filter(group=group))
                    
                    # Duplicate the group
                    group_clone = IDCardGroup.objects.get(id=group.id)
                    group_clone.pk = None
                    group_clone.client = cloned_client
                    group_clone.save()
                    
                    # Clone tables for this group
                    for table in original_tables:
                        table_clone = IDCardTable.objects.get(id=table.id)
                        table_clone.pk = None
                        table_clone.group = group_clone
                        table_clone.save()
                
                logger.info("Created guest sandbox clone: %s (from user %s)", clone_username, original_user.id)
                return cloned_user
                
        except Exception as e:
            logger.exception("Failed to clone guest user %s: %s", original_user.id, e)
            return original_user

    @classmethod
    def cleanup_clone(cls, user_id):
        """
        Delete a cloned guest_user and all its associated data.
        """
        try:
            user = User.objects.filter(id=user_id).first()
            if not user or not user.username.startswith('guestclone_'):
                return
                
            from client.services_client_core import ClientService
            client = getattr(user, 'client_profile', None)
            
            with transaction.atomic():
                if client:
                    # ClientService.delete handles cascade and image folder deletion
                    ClientService.delete(client.id)
                else:
                    user.delete()
            logger.info("Cleaned up guest sandbox clone: %s", user.username)
        except Exception as e:
            logger.exception("Failed to cleanup guest sandbox clone %s: %s", user_id, e)
