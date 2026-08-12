from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0045_add_pro_user_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='emaillog',
            name='email_type',
            field=models.CharField(
                choices=[
                    ('welcome', 'Welcome / Activation'),
                    ('temp_password', 'Temp Password'),
                    ('password_change', 'Password Change Notice'),
                    ('otp_reset', 'Password Reset OTP'),
                ],
                db_index=True,
                max_length=30,
            ),
        ),
    ]
