from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("labels", "0007_remove_alertreceivechannelassociatedlabel_inheritable_db"),
    ]

    operations = [
        migrations.AddField(
            model_name="labelkeycache",
            name="is_managed_label",
            field=models.BooleanField(default=False),
        ),
    ]
