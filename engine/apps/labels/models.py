import typing
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Count
from django.utils import timezone

from apps.labels.tasks import update_label_pairs_cache
from apps.labels.types import LabelPair
from apps.labels.utils import LABEL_OUTDATED_TIMEOUT_MINUTES

if typing.TYPE_CHECKING:
    from apps.user_management.models import Organization

MAX_KEY_NAME_LENGTH = 200
MAX_VALUE_NAME_LENGTH = 200


def get_default_label_key_color_code() -> str:
    return settings.FEATURE_LABELS_KEY_DEFAULT_COLOR


def get_default_label_value_color_code() -> str:
    return settings.FEATURE_LABELS_VALUE_DEFAULT_COLOR


# Backward-compatible alias for older imports. New code should use key/value-specific helpers.
DEFAULT_LABEL_COLOR_CODE = get_default_label_key_color_code()


class LabelKeyCache(models.Model):
    id = models.CharField(primary_key=True, editable=False, max_length=36)
    name = models.CharField(max_length=MAX_KEY_NAME_LENGTH)
    organization = models.ForeignKey("user_management.Organization", on_delete=models.CASCADE)
    last_synced = models.DateTimeField(auto_now=True)
    prescribed = models.BooleanField(default=False, null=True)
    is_managed_label = models.BooleanField(default=False)
    color_code = models.CharField(max_length=7, default=get_default_label_key_color_code)

    @property
    def is_outdated(self) -> bool:
        return timezone.now() - self.last_synced > timezone.timedelta(minutes=LABEL_OUTDATED_TIMEOUT_MINUTES)

    @classmethod
    def get_or_create_by_name(cls, organization: "Organization", key_name: str) -> typing.Optional["LabelKeyCache"]:
        """
        `get_or_create_by_name` returns the existing label key or creates it in the local labels store.
        """
        label_key = cls.objects.filter(organization=organization, name=key_name).first()
        if label_key:
            return label_key
        return cls.create_key(organization, key_name)

    @classmethod
    def create_key(
        cls,
        organization: "Organization",
        name: str,
        prescribed: bool = False,
        is_managed_label: bool = False,
        color_code: typing.Optional[str] = None,
    ) -> "LabelKeyCache":
        return cls.objects.create(
            id=str(uuid.uuid4()),
            name=name,
            organization=organization,
            prescribed=prescribed,
            is_managed_label=is_managed_label,
            color_code=color_code or get_default_label_key_color_code(),
        )

    def to_representation(self) -> dict[str, typing.Any]:
        values_count = getattr(self, "values_count", None)
        if values_count is None:
            values_count = self.values.count()

        return {
            "id": self.id,
            "name": self.name,
            "prescribed": bool(self.prescribed),
            "is_managed_label": self.is_managed_label,
            "color_code": self.color_code,
            "values_count": values_count,
        }

    def to_option_representation(self) -> dict[str, typing.Any]:
        values = [value.to_representation() for value in self.values.all().order_by("name", "id")]
        return {"key": self.to_representation(), "values": values}

    @classmethod
    def with_values_count(cls) -> models.QuerySet["LabelKeyCache"]:
        return cls.objects.annotate(values_count=Count("values"))


class LabelValueCache(models.Model):
    id = models.CharField(primary_key=True, editable=False, max_length=36)
    name = models.CharField(max_length=MAX_VALUE_NAME_LENGTH)
    key = models.ForeignKey("labels.LabelKeyCache", on_delete=models.CASCADE, related_name="values")
    last_synced = models.DateTimeField(auto_now=True)
    prescribed = models.BooleanField(default=False, null=True)
    color_code = models.CharField(max_length=7, default=get_default_label_value_color_code)

    @property
    def is_outdated(self) -> bool:
        return timezone.now() - self.last_synced > timezone.timedelta(minutes=LABEL_OUTDATED_TIMEOUT_MINUTES)

    @classmethod
    def create_value(
        cls, key: LabelKeyCache, name: str, prescribed: bool = False, color_code: typing.Optional[str] = None
    ) -> "LabelValueCache":
        return cls.objects.create(
            id=str(uuid.uuid4()),
            name=name,
            key=key,
            prescribed=prescribed,
            color_code=color_code or get_default_label_value_color_code(),
        )

    def to_representation(self) -> dict[str, typing.Any]:
        return {"id": self.id, "name": self.name, "prescribed": bool(self.prescribed), "color_code": self.color_code}


class AssociatedLabel(models.Model):
    """
    Abstract model, is used to keep information about label association with other instances
    (integrations, schedules, etc.). To add ability to associate labels with a type of instances ,
    inhere this model and add a foreign key to the instance model.

    Attention: add `AssociatedLabel` to the end of the name of inheritor (example: AlertReceiveChannelAssociatedLabel)
    """

    key = models.ForeignKey(LabelKeyCache, on_delete=models.CASCADE)
    value = models.ForeignKey(LabelValueCache, on_delete=models.CASCADE)
    organization = models.ForeignKey("user_management.Organization", on_delete=models.CASCADE, related_name="labels")

    class Meta:
        abstract = True

    @staticmethod
    def update_association(
        label_pairs: typing.List[LabelPair], instance: models.Model, organization: "Organization"
    ) -> None:
        """
        Update label associations for selected instance: delete associations with labels that are not in `labels_data`,
        create new associations and labels, if needed.
        Then call celery task to update cache for labels from `labels_data`

        instance: the model instance that the labels are associated with (e.g. AlertReceiveChannel instance)
        """
        labels_data_keys = {label["key"]["id"]: label["key"]["name"] for label in label_pairs}
        labels_data_values = {label["value"]["id"]: label["value"]["name"] for label in label_pairs}

        # delete associations with labels that are not presented in labels_data
        instance.labels.exclude(key_id__in=labels_data_keys.keys(), value_id__in=labels_data_values.keys()).delete()

        labels_keys = []
        labels_values = []
        labels_associations = []

        for label_pair in label_pairs:
            key_id = label_pair["key"]["id"]
            key_name = label_pair["key"]["name"]
            key_prescribed = label_pair["key"]["prescribed"]

            value_id = label_pair["value"]["id"]
            value_name = label_pair["value"]["name"]
            value_prescribed = label_pair["value"]["prescribed"]

            label_key = LabelKeyCache(
                id=key_id,
                name=key_name,
                organization=organization,
                prescribed=key_prescribed,
                color_code=label_pair["key"].get("color_code", get_default_label_key_color_code()),
            )
            labels_keys.append(label_key)

            label_value = LabelValueCache(
                id=value_id,
                name=value_name,
                key_id=key_id,
                prescribed=value_prescribed,
                color_code=label_pair["value"].get("color_code", get_default_label_value_color_code()),
            )
            labels_values.append(label_value)
            associated_instance = {instance.labels.field.name: instance}
            labels_associations.append(
                instance.labels.model(
                    key_id=key_id, value_id=value_id, organization=organization, **associated_instance
                )
            )

        # create labels cache and associations that don't exist.
        # Ignoring conflicts because some labels might laready exist. They will be updates in task.
        LabelKeyCache.objects.bulk_create(labels_keys, ignore_conflicts=True, batch_size=5000)
        LabelValueCache.objects.bulk_create(labels_values, ignore_conflicts=True, batch_size=5000)
        instance.labels.model.objects.bulk_create(labels_associations, ignore_conflicts=True, batch_size=5000)

        update_label_pairs_cache.apply_async((label_pairs,))

    @staticmethod
    def get_associating_label_field_name() -> str:
        """Returns ForeignKey field name for the associated model"""
        raise NotImplementedError


class AlertReceiveChannelAssociatedLabel(AssociatedLabel):
    """Keeps information about label association with alert receive channel instances"""

    alert_receive_channel = models.ForeignKey(
        "alerts.AlertReceiveChannel", on_delete=models.CASCADE, related_name="labels"
    )

    class Meta:
        unique_together = ["key_id", "value_id", "alert_receive_channel_id"]

    @staticmethod
    def get_associating_label_field_name() -> str:
        """Returns ForeignKey field name for the associated model"""
        return "alert_receive_channel"


class AlertGroupAssociatedLabel(models.Model):
    """
    A model for alert group labels (similar to AlertReceiveChannelAssociatedLabel for integrations).
    The key difference is that alert group labels do not use label IDs, but rather key and value names explicitly.
    This is done to make alert group labels "static" (so they don't change when the labels are updated in label repo).
    """

    alert_group = models.ForeignKey("alerts.AlertGroup", on_delete=models.CASCADE, related_name="labels")
    organization = models.ForeignKey(
        "user_management.Organization", on_delete=models.CASCADE, related_name="alert_group_labels"
    )

    key_name = models.CharField(max_length=MAX_KEY_NAME_LENGTH)
    value_name = models.CharField(max_length=MAX_VALUE_NAME_LENGTH)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "key_name", "value_name", "alert_group"],
                name="unique_alert_group_label",
            )
        ]


class WebhookAssociatedLabel(AssociatedLabel):
    """Keeps information about label association with outgoing webhooks instances"""

    webhook = models.ForeignKey(
        "webhooks.Webhook",
        on_delete=models.CASCADE,
        related_name="labels",
    )
    organization = models.ForeignKey(
        "user_management.Organization", on_delete=models.CASCADE, related_name="webhook_labels"
    )

    class Meta:
        unique_together = ["key_id", "value_id", "webhook_id"]

    @staticmethod
    def get_associating_label_field_name() -> str:
        """Returns ForeignKey field name for the associated model"""
        return "webhook"
