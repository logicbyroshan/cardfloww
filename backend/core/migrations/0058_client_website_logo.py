from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0057_notification_expires_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='website_logo',
            field=models.ImageField(
                blank=True,
                help_text='Logo used on website trusted clients section and client portal UI.',
                null=True,
                upload_to='images/Clients/Logos/',
            ),
        ),
    ]
