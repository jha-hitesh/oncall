from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("phone_notifications", "0003_smsrecord_represents_bundle_uuid"),
    ]

    operations = [
        migrations.AddField(
            model_name="phonecallrecord",
            name="represents_bundle_uuid",
            field=models.CharField(db_index=True, default=None, max_length=100, null=True),
        ),
    ]
