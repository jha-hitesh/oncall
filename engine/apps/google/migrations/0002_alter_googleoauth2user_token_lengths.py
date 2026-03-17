from django.db import migrations
import mirage.fields


class Migration(migrations.Migration):
    dependencies = [
        ("google", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="googleoauth2user",
            name="access_token",
            field=mirage.fields.EncryptedCharField(max_length=2000),
        ),
        migrations.AlterField(
            model_name="googleoauth2user",
            name="refresh_token",
            field=mirage.fields.EncryptedCharField(max_length=2000),
        ),
    ]
