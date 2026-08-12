from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0058_client_website_logo'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='website_is_visible',
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text='Controls visibility on public website trusted clients section.',
            ),
        ),
    ]
