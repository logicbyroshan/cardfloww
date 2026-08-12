from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0063_add_image_mode_permissions'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientPresenceSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key', models.CharField(db_index=True, max_length=64)),
                ('tab_id', models.CharField(db_index=True, max_length=80)),
                ('user_role', models.CharField(blank=True, db_index=True, default='', max_length=20)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('last_seen_at', models.DateTimeField(auto_now=True, db_index=True)),
                ('closed_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('client', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='presence_sessions', to='core.client')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='presence_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Client Presence Session',
                'verbose_name_plural': 'Client Presence Sessions',
                'unique_together': {('session_key', 'tab_id')},
                'indexes': [
                    models.Index(fields=['client', 'closed_at', 'last_seen_at'], name='clpres_client_live_idx'),
                    models.Index(fields=['user', 'closed_at', 'last_seen_at'], name='clpres_user_live_idx'),
                    models.Index(fields=['closed_at', 'last_seen_at'], name='clpres_closed_seen_idx'),
                ],
            },
        ),
    ]
