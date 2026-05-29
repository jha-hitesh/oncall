from django.conf import settings

from apps.alerts.incident_appearance.renderers.base_renderer import (
    AlertBaseRenderer,
    AlertGroupBaseRenderer,
    AlertGroupBundleBaseRenderer,
)
from apps.alerts.incident_appearance.renderers.constants import DEFAULT_BACKUP_TITLE
from apps.alerts.incident_appearance.templaters import AlertPhoneCallTemplater
from common.jinja_templater.apply_jinja_template import apply_jinja_template
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

        text = settings.ALERT_GROUP_PHONE_CALL_TEMPLATE.format(
            integration_name=self.alert_group.channel.short_name,
            title=title,
            alert_count=self.alert_group.alerts.count(),
        )

        return text


class AlertGroupPhoneCallBundleRenderer(AlertGroupBundleBaseRenderer):
    def render(self):
        context = self.get_bundle_template_context()
        return apply_jinja_template(settings.NOTIFICATION_BUNDLE_PHONECALL_TEMPLATE, **context)
