from django.db import migrations, models
import django.db.models.deletion
import mirage.fields


class Migration(migrations.Migration):
    dependencies = [
        ("user_management", "0022_alter_team_unique_together"),
        ("google", "0002_alter_googleoauth2user_token_lengths"),
    ]

    operations = [
        migrations.CreateModel(
            name="GoogleOAuth2Organization",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("google_user_id", models.CharField(max_length=100)),
                ("google_user_email", models.EmailField(default=None, max_length=254, null=True)),
                ("access_token", mirage.fields.EncryptedCharField(max_length=2000)),
                ("refresh_token", mirage.fields.EncryptedCharField(max_length=2000)),
                ("oauth_scope", models.TextField(max_length=30000)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "connected_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="google_oauth2_organizations",
                        to="user_management.user",
                    ),
                ),
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="google_oauth2_organization",
                        to="user_management.organization",
                    ),
                ),
            ],
        ),
    ]
