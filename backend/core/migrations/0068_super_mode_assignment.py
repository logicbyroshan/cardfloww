from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0067_merge_20260416_compat'),
    ]

    operations = [
        migrations.CreateModel(
            name='SuperModeAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_assigned', models.BooleanField(db_index=True, default=False)),
                ('is_enabled', models.BooleanField(db_index=True, default=False)),
                ('ram_allocation_mb', models.PositiveIntegerField(default=0)),
                ('assigned_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assigned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='super_mode_assigned_users', to=settings.AUTH_USER_MODEL)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='super_mode_assignment', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Super Mode Assignment',
                'verbose_name_plural': 'Super Mode Assignments',
            },
        ),
        migrations.AddIndex(
            model_name='supermodeassignment',
            index=models.Index(fields=['is_assigned', 'is_enabled'], name='supermode_state_idx'),
        ),
    ]
