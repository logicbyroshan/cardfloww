# Generated manually to move Office Work model state to officework app

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0069_officeworkchatmessage_officeworksharedfile_and_more'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name='OfficeWorkChatMessage'),
                migrations.DeleteModel(name='OfficeWorkTask'),
                migrations.DeleteModel(name='OfficeWorkSharedFile'),
            ],
        ),
    ]
