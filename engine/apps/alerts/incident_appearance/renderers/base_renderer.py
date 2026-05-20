import typing
from abc import ABC, abstractmethod

from django.db.models import QuerySet
from django.utils.functional import cached_property

if typing.TYPE_CHECKING:
    from apps.alerts.models import Alert, AlertGroup, BundledNotification


class AlertBaseRenderer(ABC):
    def __init__(self, alert: "Alert"):
        self.alert = alert

    @cached_property
    def templated_alert(self):
        return self.templater_class(self.alert).render()

    @property
    @abstractmethod
    def templater_class(self):
        raise NotImplementedError


class AlertGroupBaseRenderer(ABC):
    def __init__(self, alert_group: "AlertGroup", alert: typing.Optional["Alert"] = None):
        if alert is None:
            alert = alert_group.alerts.first()

        self.alert_group = alert_group
        self.alert_renderer = self.alert_renderer_class(alert)

    @property
    @abstractmethod
    def alert_renderer_class(self):
        raise NotImplementedError


class AlertGroupBundleBaseRenderer:
    def __init__(self, notifications: "QuerySet[BundledNotification]"):
        self.notifications = notifications

    def get_bundle_template_context(self) -> dict[str, typing.Any]:
        alert_groups = []
        channels = []

        for notification in self.notifications:
            if notification.alert_group not in alert_groups:
                alert_groups.append(notification.alert_group)
            if notification.alert_receive_channel not in channels:
                channels.append(notification.alert_receive_channel)

        stack_slug = channels[0].organization.stack_slug if channels else ""

        return {
            "total_alert_groups": len(alert_groups),
            "total_channels": len(channels),
            "channel_names": [channel.short_name for channel in channels],
            "alert_group_names": [alert_group.web_title_cache or "" for alert_group in alert_groups],
            "alert_group_codes": [f"#{alert_group.inside_organization_number}" for alert_group in alert_groups],
            "stack_slug": stack_slug,
        }
