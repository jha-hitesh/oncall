from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("labels", "0008_labelkeycache_is_managed_label"),
    ]

    operations = [
        migrations.AddField(
            model_name="labelkeycache",
            name="color_code",
            field=models.CharField(default=settings.FEATURE_LABELS_KEY_DEFAULT_COLOR, max_length=7),
        ),
        migrations.AddField(
            model_name="labelvaluecache",
            name="color_code",
            field=models.CharField(default=settings.FEATURE_LABELS_VALUE_DEFAULT_COLOR, max_length=7),
        ),
    ]
