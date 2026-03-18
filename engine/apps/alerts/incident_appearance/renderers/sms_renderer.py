from django.conf import settings

from apps.alerts.incident_appearance.renderers.base_renderer import (
    AlertBaseRenderer,
    AlertGroupBaseRenderer,
    AlertGroupBundleBaseRenderer,
)
from apps.alerts.incident_appearance.renderers.constants import DEFAULT_BACKUP_TITLE
from apps.alerts.incident_appearance.templaters import AlertSmsTemplater
from common.jinja_templater.apply_jinja_template import apply_jinja_template
from common.utils import str_or_backup


class AlertSmsRenderer(AlertBaseRenderer):
    @property
    def templater_class(self):
        return AlertSmsTemplater


class AlertGroupSmsRenderer(AlertGroupBaseRenderer):
    @property
    def alert_renderer_class(self):
        return AlertSmsRenderer

    def render(self):
        templated_alert = self.alert_renderer.templated_alert
        title = str_or_backup(templated_alert.title, DEFAULT_BACKUP_TITLE)
        return (
            f"Grafana OnCall: Alert group #{self.alert_group.inside_organization_number}"
            f'"{title}" from stack: "{self.alert_group.channel.organization.stack_slug}", '
            f"integration: {self.alert_group.channel.short_name}, "
            f"alerts registered: {self.alert_group.alerts.count()}."
        )


class AlertGroupSMSBundleRenderer(AlertGroupBundleBaseRenderer):
    def render(self) -> str:
        context = self.get_bundle_template_context()
        return apply_jinja_template(settings.NOTIFICATION_BUNDLE_SMS_TEMPLATE, **context)
