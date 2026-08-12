from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0046_add_otp_reset_email_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='emaillog',
            name='body_html',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='emaillog',
            name='body_text',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='emaillog',
            name='email_type',
            field=models.CharField(
                choices=[
                    ('welcome', 'Welcome / Activation'),
                    ('temp_password', 'Temp Password'),
                    ('password_change', 'Password Change Notice'),
                    ('otp_reset', 'Password Reset OTP'),
                    ('system', 'System / Custom'),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
    ]
