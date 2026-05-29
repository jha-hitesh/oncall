from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("webhooks", "0018_alter_webhook_trigger_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="webhook",
            name="add_response_to_timeline",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="webhook",
            name="response_template",
            field=models.TextField(default=None, null=True),
        ),
    ]
