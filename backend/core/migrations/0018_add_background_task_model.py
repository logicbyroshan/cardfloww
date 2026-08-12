# Generated migration for BackgroundTask model
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_client_perm_idcard_bulk_reupload_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='BackgroundTask',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_type', models.CharField(choices=[('bulk_upload', 'Bulk Upload'), ('reupload_images', 'Reupload Images'), ('export_zip', 'Export Zip'), ('export_pdf', 'Export PDF'), ('export_docx', 'Export DOCX'), ('export_excel', 'Export Excel')], max_length=30)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed'), ('cancelled', 'Cancelled')], db_index=True, default='pending', max_length=20)),
                ('progress', models.IntegerField(default=0)),
                ('total', models.IntegerField(default=0)),
                ('file_path', models.CharField(blank=True, max_length=500, null=True)),
                ('result_path', models.CharField(blank=True, max_length=500, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('error_message', models.TextField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='background_tasks', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='backgroundtask',
            index=models.Index(fields=['user', 'status'], name='core_backgr_user_id_5b9e4b_idx'),
        ),
        migrations.AddIndex(
            model_name='backgroundtask',
            index=models.Index(fields=['task_type', 'status'], name='core_backgr_task_ty_d1f9c0_idx'),
        ),
    ]
