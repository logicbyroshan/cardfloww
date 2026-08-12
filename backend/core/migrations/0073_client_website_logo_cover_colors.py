from django.db import migrations, models


def _compute_theme_colors_from_file(file_obj):
    if file_obj is None:
        return None, None

    try:
        from io import BytesIO
        from PIL import Image

        file_obj.open('rb')
        raw_data = file_obj.read()
        file_obj.close()

        image = Image.open(BytesIO(raw_data)).convert('RGBA')
        sample = image.resize((min(64, max(1, image.width)), min(64, max(1, image.height))))

        red = green = blue = count = 0
        for r, g, b, a in sample.getdata():
            if a < 128:
                continue
            if r > 240 and g > 240 and b > 240:
                continue
            red += r
            green += g
            blue += b
            count += 1

        if count == 0:
            red, green, blue = 10, 146, 221
        else:
            red //= count
            green //= count
            blue //= count

        darker = (
            max(0, red - 40),
            max(0, green - 40),
            max(0, blue - 40),
        )

        return (
            f'#{red:02x}{green:02x}{blue:02x}',
            f'#{darker[0]:02x}{darker[1]:02x}{darker[2]:02x}',
        )
    except Exception:
        return '#0a92dd', '#006da8'


def forwards(apps, schema_editor):
    Client = apps.get_model('core', 'Client')
    db_alias = schema_editor.connection.alias
    for client in Client.objects.using(db_alias).exclude(website_logo='').exclude(website_logo__isnull=True).iterator():
        cover_color, cover_color_dark = _compute_theme_colors_from_file(client.website_logo)
        Client.objects.using(db_alias).filter(pk=client.pk).update(
            website_logo_cover_color=cover_color,
            website_logo_cover_color_dark=cover_color_dark,
        )


def backwards(apps, schema_editor):
    Client = apps.get_model('core', 'Client')
    db_alias = schema_editor.connection.alias
    Client.objects.using(db_alias).update(
        website_logo_cover_color=None,
        website_logo_cover_color_dark=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0072_remove_user_is_temp_password_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='client',
            name='website_logo_cover_color',
            field=models.CharField(blank=True, max_length=16, null=True),
        ),
        migrations.AddField(
            model_name='client',
            name='website_logo_cover_color_dark',
            field=models.CharField(blank=True, max_length=16, null=True),
        ),
        migrations.RunPython(forwards, backwards),
    ]