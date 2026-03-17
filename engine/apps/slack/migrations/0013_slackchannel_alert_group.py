from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0076_escalationpolicy_invitees_and_calendar_invite_step"),
        ("slack", "0012_remove_slackmessage_organization_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="slackchannel",
            name="alert_group",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="slack_channels",
                to="alerts.alertgroup",
            ),
        ),
    ]
