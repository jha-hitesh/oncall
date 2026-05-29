import typing

from django.db import models
from mirage import fields as mirage_fields

if typing.TYPE_CHECKING:
    from apps.user_management.models import Organization, User


class GoogleOAuth2Organization(models.Model):
    organization: "Organization"
    connected_by: "User | None"

    id = models.AutoField(primary_key=True)
    organization = models.OneToOneField(
        to="user_management.Organization",
        null=False,
        blank=False,
        related_name="google_oauth2_organization",
        on_delete=models.CASCADE,
    )
    connected_by = models.ForeignKey(
        to="user_management.User",
        null=True,
        blank=True,
        related_name="google_oauth2_organizations",
        on_delete=models.SET_NULL,
    )
    google_user_id = models.CharField(max_length=100)
    google_user_email = models.EmailField(null=True, default=None)
    access_token = mirage_fields.EncryptedCharField(max_length=2000)
    refresh_token = mirage_fields.EncryptedCharField(max_length=2000)
    oauth_scope = models.TextField(max_length=30000)
    created_at = models.DateTimeField(auto_now_add=True)
