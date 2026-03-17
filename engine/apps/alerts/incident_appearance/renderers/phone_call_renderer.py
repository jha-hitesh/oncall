from settings.base import ALERT_GROUP_PHONE_CALL_TEMPLATE
from apps.alerts.incident_appearance.renderers.base_renderer import (
    AlertBaseRenderer,
    AlertGroupBaseRenderer,
    AlertGroupBundleBaseRenderer,
)
from apps.alerts.incident_appearance.renderers.constants import DEFAULT_BACKUP_TITLE
from apps.alerts.incident_appearance.templaters import AlertPhoneCallTemplater
from common.utils import str_or_backup


class AlertPhoneCallRenderer(AlertBaseRenderer):
    @property
    def templater_class(self):
        return AlertPhoneCallTemplater


class AlertGroupPhoneCallRenderer(AlertGroupBaseRenderer):

    @property
    def alert_renderer_class(self):
        return AlertPhoneCallRenderer

    def render(self):
        templated_alert = self.alert_renderer.templated_alert
        title = str_or_backup(templated_alert.title, DEFAULT_BACKUP_TITLE)

        text = ALERT_GROUP_PHONE_CALL_TEMPLATE.format(
            integration_name=self.alert_group.channel.short_name,
            title=title,
            alert_count=self.alert_group.alerts.count(),
        )

        return text


class AlertGroupPhoneCallBundleRenderer(AlertGroupBundleBaseRenderer):
    def render(self):
        alert_groups_to_render = []
        channels_to_render = []

        for notification in self.notifications:
            if notification.alert_group not in alert_groups_to_render:
                alert_groups_to_render.append(notification.alert_group)
                if notification.alert_group.channel not in channels_to_render:
                    channels_to_render.append(notification.alert_group.channel)
                if len(alert_groups_to_render) == self.MAX_ALERT_GROUPS_TO_RENDER:
                    break

        if not alert_groups_to_render:
            return "Grafana OnCall. Multiple alert groups require your attention."

        total_alert_groups = self.notifications.values("alert_group").distinct().count()
        total_channels = self.notifications.values("alert_receive_channel").distinct().count()

        numbers = ", ".join(f"#{alert_group.inside_organization_number}" for alert_group in alert_groups_to_render)
        alert_groups_text = "Alert groups " if total_alert_groups > 1 else "Alert group "
        alert_groups_text += numbers

        if total_alert_groups > self.MAX_ALERT_GROUPS_TO_RENDER:
            alert_groups_text += f" and {total_alert_groups - self.MAX_ALERT_GROUPS_TO_RENDER} more"

        channel_names = ", ".join(channel.short_name for channel in channels_to_render[: self.MAX_CHANNELS_TO_RENDER])
        channels_text = "integrations " if total_channels > 1 else "integration "
        channels_text += channel_names

        if total_channels > self.MAX_CHANNELS_TO_RENDER:
            channels_text += f" and {total_channels - self.MAX_CHANNELS_TO_RENDER} more"

        return (
            f"Grafana OnCall. {alert_groups_text}. "
            f"From stack {alert_groups_to_render[0].channel.organization.stack_slug}. "
            f"Triggered by {channels_text}."
        )
