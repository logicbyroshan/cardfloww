from django.db import migrations

def update_user_roles(apps, schema_editor):
    User = apps.get_model('core', 'User')
    db_alias = schema_editor.connection.alias
    User.objects.using(db_alias).filter(role='admin_staff').update(role='operator')
    User.objects.using(db_alias).filter(role='client_staff').update(role='assistant')

def reverse_user_roles(apps, schema_editor):
    User = apps.get_model('core', 'User')
    db_alias = schema_editor.connection.alias
    User.objects.using(db_alias).filter(role='operator').update(role='admin_staff')
    User.objects.using(db_alias).filter(role='assistant').update(role='client_staff')

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0092_finalize_staff_removal'),
    ]

    operations = [
        migrations.RunPython(update_user_roles, reverse_user_roles),
    ]
